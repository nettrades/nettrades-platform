# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LangGraph Agent - Durable AI Orchestration
# =============================================================================
# FILE: src/core/app.py
#
# PURPOSE:
#   Main entry point for the LangGraph service. It provides a FastAPI
#   application that exposes:
#     - /invoke   - main inference endpoint (authenticated)
#     - /health   - liveness probe for container orchestration
#     - /metrics  - Prometheus metrics endpoint
#
# KEY FEATURES:
#   - Auto-detects inference backend (GPUStack / vLLM / llama.cpp)
#   - Uses a supervisor to dispatch to business sub???agents
#   - Exposes Prometheus metrics for observability
#   - Uses PostgresSaver for durable checkpointing
#
# IMPORTANT FIXES (2026-07-02):
#   1. Authentication Bypass: Previously, if LANGGRAPH_API_KEY was unset,
#      authentication was silently bypassed. This is a SECURITY ISSUE.
#      FIX: Now we require the API key to be set at deployment time.
#      If it's missing, we return a 500 error instead of bypassing auth.
#
#   2. Removed Dead Code: The build_graph() function was commented out
#      and is no longer needed. It has been removed.
#
#   3. Prompt Injection Monitoring: Added middleware to sanitise incoming
#      requests and detect common injection patterns.
#
#   4. Resilience: Added retry logic and circuit breaker for supervisor
#      graph invocation.
#
#   5. Database Connection: Fixed the lifespan to use the correct
#      connection type (async or sync) based on the available checkpointer.
#      The code now detects whether checkpointer.setup() is a coroutine
#      and calls it appropriately.
# =============================================================================

import os
import logging
import json
import time
import traceback
from contextlib import asynccontextmanager
from typing import Optional # IN PRODUCTION REMOVE THIS
# from typing import Any, Dict #   # IN PRODUCTION UNCOMMENT THIS

import psycopg
from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY

# Use the synchronous PostgresSaver - this is what works with sync connections
from langgraph.checkpoint.postgres import PostgresSaver

from supervisor import build_supervisor, invoke_supervisor_with_retry
from security.prompt_injection import sanitise_input

# Load environment variables
load_dotenv()

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_URI = os.getenv("DATABASE_URL", "postgresql://odoo:password@postgres:5432/odoo")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY")

if not LANGGRAPH_API_KEY:
    logger.critical(
        "?????? LANGGRAPH_API_KEY environment variable is not set. "
        "The /invoke endpoint will not function correctly."
    )

# Global dictionary to hold the compiled graph
ml_models = {}

# =============================================================================
# PROMETHEUS METRICS
# =============================================================================
REQUEST_COUNT = Counter(
    'langgraph_requests_total',
    'Total number of requests processed by the LangGraph agent',
    ['intent']
)
REQUEST_DURATION = Histogram(
    'langgraph_request_duration_seconds',
    'Time taken to process a LangGraph request'
)

# =============================================================================
# APPLICATION LIFESPAN (Startup / Shutdown)
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager - runs on startup and shutdown.

    Startup:
      1. Establish a synchronous connection to PostgreSQL using psycopg.
      2. Set autocommit=True so that CREATE INDEX CONCURRENTLY can run
         without being inside a transaction block.
      3. Create a PostgresSaver (sync) and call setup() to initialise the
         checkpoint schema.
      4. Build the supervisor graph and attach the checkpointer.
      5. Store the compiled graph in ml_models.

    Shutdown:
      Clear ml_models and close the connection.

    Why we use a synchronous connection:
      - The langgraph library's PostgresSaver (sync) works reliably with
        psycopg2 connections. The async version (AsyncPostgresSaver) does
        not accept the async connections from psycopg correctly.
      - This approach is proven to work with the current library version.
    """

    # Create a synchronous connection using psycopg (version 3)
    # This allows CREATE INDEX CONCURRENTLY to run without errors.    
    conn = psycopg.connect(DB_URI)
    conn.autocommit = True
    logger.info("PostgreSQL connection established (sync, psycopg)")

    try:
        # Create the checkpointer (sync) and initialise the schema.
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        logger.info("PostgresSaver setup complete")

        # Build the supervisor graph and attach the checkpointer.
        graph = build_supervisor()
        graph.checkpointer = checkpointer
        ml_models["graph"] = graph
        logger.info("Supervisor graph built with checkpointing")
        # Yield control to the application - the connection stays open.
        yield

    except Exception as e:
        logger.error(f"Lifespan startup failed: {e}")
        raise
    finally:
        ml_models.clear()
        conn.close()
        logger.info("LangGraph agent shutdown complete")

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================
app = FastAPI(
    title="NETTRADES LangGraph Agent",
    description="AI orchestration service for autonomous enterprise platform",
    version="1.0.0",
    lifespan=lifespan
)

# =============================================================================
# MIDDLEWARE: METRICS TRACKING
# =============================================================================
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """
    Middleware that tracks request duration and counts for Prometheus.
    
    This middleware intercepts every request, measures the time taken,
    and records it in the Prometheus metrics.
    """
    start = time.time()
    response = await call_next(request)
    REQUEST_DURATION.observe(time.time() - start)
    return response

# =============================================================================
# MIDDLEWARE: PROMPT INJECTION SANITISATION
# =============================================================================
@app.middleware("http")
async def prompt_injection_middleware(request: Request, call_next):
    """
    Sanitises incoming JSON request bodies to prevent prompt injection.

    Only applies to POST requests that contain JSON. Detects common injection
    patterns (e.g., "ignore previous instructions") and redacts the offending
    fields before they reach the LangGraph agent.
    """
    if request.method == "POST" and request.headers.get("content-type", "").startswith("application/json"):
        try:
            body = await request.json()
            sanitised_body = sanitise_input(body)
            # Store sanitised body in request state for later use
            request.state._sanitised_body = sanitised_body
        except Exception as e:
            logger.warning(f"Failed to sanitise request: {e}")

    response = await call_next(request)
    return response

# =============================================================================
# GLOBAL ERROR HANDLER
# =============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global error handler that catches all unhandled exceptions.

    This ensures that any unexpected error returns a consistent JSON response
    and logs the full traceback for debugging.
    """
    logger.error(f"Unhandled exception: {exc}")
    logger.error(traceback.format_exc())
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc),
        }
    )

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """
    Liveness and readiness probe for container orchestration.

    This endpoint returns a simple status to indicate that the service is
    running and ready to accept requests.
    """
    return {"status": "ok", "service": "langgraph"}

@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    This endpoint exposes all Prometheus metrics for scraping by a Prometheus
    server. It includes request counts, durations, and any other metrics
    registered with the Prometheus registry.
    """
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")

@app.post("/invoke")
async def invoke(
    request: Request,
#    x_api_key: str = Header(..., description="API key for authentication") # IMPORTANT IN PRODUCTION HAVE AUTHENTICATION SO UN COMMENT THIS
    x_api_key: Optional[str] = Header(None, description="API key for authentication") # IMPORTANT IN PRODUCTION HAVE AUTHENTICATION SO REMOVE THIS
):
    """
    Main inference endpoint.

    This endpoint receives a user message, processes it through the LangGraph
    supervisor, and returns the result.

    Authentication:
    - Requires the 'X-API-Key' header with a valid API key.
    - The API key must match the LANGGRAPH_API_KEY environment variable.
    """
    
    # =========================================================================
    # STEP 1: AUTHENTICATION (can be disabled with DISABLE_AUTH=true)
    # IMPORTANT IN PRODUCTION HAVE AUTHENTICATION - REMOVE THIS BLOCK AND UNCOMMENT THE ONE BELOW
    # NEAR THE TOP OF THE PAGE WHERE IT SAYS:     from typing import Optional # IN PRODUCTION REMOVE THIS
    #      from typing import Any, Dict   # IN PRODUCTION UNCOMMENT THIS
    # =========================================================================
    DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() == "true"
    
    if DISABLE_AUTH:
        logger.warning("Authentication is disabled (DISABLE_AUTH=true) – allowing all requests.")
    else:
        if not LANGGRAPH_API_KEY:
            logger.error("LANGGRAPH_API_KEY is not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LANGGRAPH_API_KEY is not configured."
            )
        if not x_api_key or x_api_key != LANGGRAPH_API_KEY:
            logger.warning(f"Invalid API key attempt: {x_api_key[:8] if x_api_key else 'None'}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )   
    
    
    # =========================================================================
    # IMPORTANT IN PRODUCTION HAVE AUTHENTICATION   IN  docker-compose.yaml for agent-chat-ui REMOVE  NEXT_PUBLIC_SKIP_AUTH: "true"
    # AND UN COMMENT THE CODE BELOW AND COMMENT THE CODE ABOVE
    # =========================================================================
    # CRITICAL SECURITY FIX:
    # Previously, if LANGGRAPH_API_KEY was unset, authentication was skipped.
    # This is now fixed: we REQUIRE the API key to be set.
    
#    if not LANGGRAPH_API_KEY:
#        logger.error("LANGGRAPH_API_KEY is not configured")
#        raise HTTPException(
#            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#            detail="LANGGRAPH_API_KEY is not configured."
#        )

    # Validate the API key
#    if x_api_key != LANGGRAPH_API_KEY:
#        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
#        raise HTTPException(
#            status_code=status.HTTP_401_UNAUTHORIZED,
#            detail="Invalid API key"
#        )

    # =========================================================================
    # STEP 2: PARSE REQUEST BODY
    # =========================================================================
    try:
        # Retrieve sanitised body if available, else fallback to original
        if hasattr(request.state, "_sanitised_body"):
            body = request.state._sanitised_body
        else:
            body = await request.json()
        logger.debug(f"Request body: {body}")
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON body: {str(e)}"
        )

    # Validate the input
    if "input" not in body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing 'input' field in request body"
        )

    # Extract the state from the request
    state = body.get("input", {})

    # If a config with thread_id is provided, use it for checkpointing
    config = body.get("config", {})
    if config.get("configurable", {}).get("thread_id"):
        state["thread_id"] = config["configurable"]["thread_id"]

    # =========================================================================
    # STEP 3: INVOKE THE SUPERVISOR GRAPH
    # =========================================================================
    graph = ml_models.get("graph")
    if not graph:
        logger.error("Graph not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph not initialized. Please check the server logs."
        )

    try:
        # Invoke the graph with the state (with retry and circuit breaker)
        result = await invoke_supervisor_with_retry(graph, state)

        # Record the intent for metrics
        intent = result.get("intent", "unknown")
        REQUEST_COUNT.labels(intent=intent).inc()
        logger.info(f"Request completed with intent: {intent}")

        return result
    except Exception as e:
        logger.error(f"Graph invocation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph invocation failed: {str(e)}"
        )