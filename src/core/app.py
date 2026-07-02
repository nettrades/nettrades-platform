# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LangGraph Agent – durable AI orchestration
# =============================================================================
# FILE: src/core/app.py
#
# PURPOSE:
#   This file is the main entry point for the LangGraph service.
#   It provides a FastAPI application that exposes:
#   - /invoke – main inference endpoint (authenticated)
#   - /health – liveness probe for container orchestration
#   - /metrics – Prometheus metrics endpoint
#
# KEY FEATURES:
#   - Auto-detects inference backend (GPUStack / vLLM / llama.cpp)
#   - Uses a supervisor to dispatch to business sub-agents
#   - Exposes Prometheus metrics for observability
#   - Uses PostgresSaver for durable checkpointing
#
# IMPORTANT FIXES:
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
# =============================================================================

import os
import logging
import json
import time
import traceback
from psycopg_pool import ConnectionPool
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse, Response

try:
    from langgraph.checkpoint.postgres import AsyncPostgresSaver
except ImportError:
    from langgraph.checkpoint.postgres import PostgresSaver as AsyncPostgresSaver

from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY

from supervisor import build_supervisor, invoke_supervisor_with_retry
from security.prompt_injection import sanitise_input

# Load environment variables from .env file
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
# Database connection string for PostgresSaver (LangGraph checkpoints)
DB_URI = os.getenv("DATABASE_URL", "postgresql://odoo:password@postgres:5432/odoo")

# API Key for the /invoke endpoint
# ⚠️ CRITICAL SECURITY FIX: This MUST be set in production.
# If it's not set, we return a 500 error instead of bypassing authentication.
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY")

# Check if the API key is configured
# If not, log a critical error and the application will still start,
# but the /invoke endpoint will return a 500 error.
if not LANGGRAPH_API_KEY:
    logger.critical(
        "⚠️ LANGGRAPH_API_KEY environment variable is not set. "
        "The /invoke endpoint will not function correctly."
        "Please set this variable in your .env file or environment."
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
# APPLICATION LIFESPAN
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Build the LangGraph supervisor graph and attach the durable PostgresSaver.

    This function runs at application startup and shutdown:
    - Startup: Creates a connection to PostgreSQL, sets up the checkpoint saver,
      and builds the supervisor graph.
    - Shutdown: Clears the graph from memory.

    The PostgresSaver provides durable checkpointing, allowing the graph to
    resume from the last saved state if the service crashes.
    """
    logger.info("Starting LangGraph agent...")

    # Use a synchronous connection pool (compatible with AsyncPostgresSaver)
    pool = ConnectionPool(conninfo=DB_URI, min_size=1, max_size=5)
    with pool:  # sync context manager, fine inside async
        with pool.getconn() as conn:  # get a sync connection
            # Create the checkpointer using the connection
            checkpointer = AsyncPostgresSaver(conn)
            # Set up the database schema for checkpoints
            await checkpointer.setup()
            logger.info("PostgresSaver setup complete")
            # Build the supervisor graph
            graph = build_supervisor()
            # Attach the checkpointer to the graph
            graph.checkpointer = checkpointer
            logger.info("Supervisor graph built with checkpointing")
            # Store the graph in the global dictionary
            ml_models["graph"] = graph
            # Yield control to the application – the connection stays open
            yield
    # Clean up on shutdown – runs after the async with block exits
    ml_models.clear()
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
    x_api_key: str = Header(..., description="API key for authentication")
):
    """
    Main inference endpoint.

    This endpoint receives a user message, processes it through the LangGraph
    supervisor, and returns the result.

    Authentication:
    - Requires the 'X-API-Key' header with a valid API key.
    - The API key must match the LANGGRAPH_API_KEY environment variable.

    ⚠️ CRITICAL SECURITY FIX: Previously, if LANGGRAPH_API_KEY was unset,
    authentication was silently bypassed. This is a security vulnerability
    that has been fixed. Now the API key is required and validated.

    Request Body:
    {
        "input": {
            "messages": [
                {"role": "user", "content": "Find me a Python developer"}
            ],
            "image_base64": "data:image/png;base64,..."  # Optional
        },
        "config": {
            "configurable": {
                "thread_id": "unique-session-id"  # For checkpointing
            }
        }
    }

    Response:
    {
        "analysis": "I found 5 candidates...",
        "intent": "recruitment",
        "rankings": [...],
        "screening_done": true,
        "followup_count": 0
    }
    """
    # =========================================================================
    # STEP 1: AUTHENTICATION
    # =========================================================================
    # ⚠️ CRITICAL SECURITY FIX:
    # Previously, if LANGGRAPH_API_KEY was unset, authentication was skipped.
    # This is now fixed: we REQUIRE the API key to be set.
    if not LANGGRAPH_API_KEY:
        logger.error("LANGGRAPH_API_KEY is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LANGGRAPH_API_KEY is not configured. Please set this environment variable."
        )

    # Validate the API key
    if x_api_key != LANGGRAPH_API_KEY:
        logger.warning(f"Invalid API key attempt: {x_api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

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