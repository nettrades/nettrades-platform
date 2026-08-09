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
#     - /assistants - list available assistants (for agent-chat-ui)
#     - /threads  - create a new conversation thread (for agent-chat-ui)
#     - /threads/{thread_id}/state - get thread state (for agent-chat-ui)
#     - /threads/{thread_id}/runs - run a thread (for agent-chat-ui)
#     - /runs     - create a new run and return assistant response (for agent-chat-ui)
#     - /copilotkit - AG-UI endpoint for CopilotKit (new)
#
# KEY FEATURES:
#   - Auto-detects inference backend (GPUStack / vLLM / llama.cpp)
#   - Uses a supervisor to dispatch to business sub-agents
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
#
#   6. agent-chat-ui Compatibility: Added stub endpoints for /assistants,
#      /threads, /threads/{id}/state, /threads/{id}/runs to satisfy the
#      UI's expectations without requiring the full LangGraph API server.
#
#   7. NEW (2026-07-31): Added /runs endpoint and modified /threads/{id}/runs
#      to return the assistant's message inline, fixing UI 404 errors.
#
#   8. FIX (2026-08-01): The /runs and /threads/{id}/runs endpoints now pass
#      the `config` parameter with `configurable.thread_id` to the supervisor
#      invocation, satisfying the checkpointer's requirement. This resolves
#      the "Checkpointer requires one or more of the following 'configurable'
#      keys: []" error. Note: supervisor.py's invoke_supervisor_with_retry()
#      must accept a `config` argument.
#
#   9. NEW (2026-08-06): Added CopilotKit AG-UI endpoint for modern agentic UI.
#      This provides a native integration with CopilotKit frontend via the
#      AG-UI protocol, enabling generative UI, shared state, and HITL workflows.
#      Uses the official add_langgraph_fastapi_endpoint from ag-ui-langgraph.
# =============================================================================

import os
import logging
import json
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

import psycopg
from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from prometheus_client import Counter, Histogram, generate_latest, REGISTRY

# Use the synchronous PostgresSaver - this is what works with sync connections
from langgraph.checkpoint.postgres import PostgresSaver

# Fix imports to use relative imports
from supervisor import build_supervisor, invoke_supervisor_with_retry
from security.prompt_injection import sanitise_input

# =============================================================================
# CopilotKit Integration (NEW)
# =============================================================================
# CopilotKit provides a production-ready AG-UI endpoint for agentic UIs.
# It allows any AG-UI compatible frontend (React, Angular, etc.) to connect
# to our LangGraph graph with full state synchronization and generative UI.
# We use the official ag-ui-langgraph package for FastAPI integration.
try:
    from ag_ui_langgraph import add_langgraph_fastapi_endpoint
    from copilotkit import LangGraphAGUIAgent
    COPILOTKIT_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info("CopilotKit SDK and ag-ui-langgraph loaded successfully")
except ImportError as e:
    COPILOTKIT_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning(f"CopilotKit SDK not installed: {e}. The /copilotkit endpoint will not be available.")

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
# SECURITY VALIDATION (FAIL FAST)
# =============================================================================
if os.getenv("DISABLE_AUTH", "false").lower() == "true":
    logger.critical("DISABLE_AUTH is TRUE – authentication is disabled!")
    logger.critical("This is UNSAFE for production. Set DISABLE_AUTH=false in .env")
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError("DISABLE_AUTH=true is not allowed in production")

if not os.getenv("LANGGRAPH_API_KEY"):
    logger.critical("LANGGRAPH_API_KEY is not set. The /invoke endpoint will not function.")
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise RuntimeError("LANGGRAPH_API_KEY must be set in production")

# =============================================================================
# CONFIGURATION
# =============================================================================
DB_URI = os.getenv("DATABASE_URL", "postgresql://odoo:password@postgres:5432/odoo")
LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY")

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
      6. If CopilotKit is available, add the AG-UI endpoint.

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

        # =========================================================================
        # NEW: Add CopilotKit AG-UI endpoint using official ag-ui-langgraph
        # =========================================================================
        if COPILOTKIT_AVAILABLE:
            try:
                # Create the LangGraphAGUIAgent wrapping our graph
                agent = LangGraphAGUIAgent(
                    name="supervisor",
                    description="Main orchestrator agent for the autonomous enterprise platform",
                    graph=graph,
                )
                # Mount the endpoint at /copilotkit
                add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/copilotkit")
                logger.info("CopilotKit AG-UI endpoint added at /copilotkit (using LangGraphAGUIAgent)")
            except Exception as e:
                logger.error(f"Failed to add CopilotKit endpoint: {e}")
                # Continue without CopilotKit - the rest of the app still works
        else:
            logger.info("CopilotKit not available - /copilotkit endpoint skipped")

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

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
# MIDDLEWARE: JWT VALIDATION (Odoo OAuth 2.0)
# =============================================================================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Validates JWT tokens issued by Odoo for protected endpoints.
    If AUTH_ENABLED is false, skip validation.
    """
    auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        return await call_next(request)

    # Skip validation for health and metrics endpoints
    if request.url.path in ["/health", "/metrics", "/copilotkit"]:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]
    # Validate the token (implement your validation logic)
    # For example, verify signature using Odoo's public key
    # and extract user information.
    try:
        # Placeholder validation
        # In production, use a library like python-jose to verify JWT
        # and check with Odoo's public key.
        payload = {"sub": "test-user"}
        request.state.user = payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    return await call_next(request)

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

# =============================================================================
# STUB ENDPOINTS FOR AGENT-CHAT-UI COMPATIBILITY
# =============================================================================

# In-memory store for thread states (for stub purposes only)
_thread_store: Dict[str, Dict[str, Any]] = {}

@app.get("/assistants")
async def list_assistants():
    """
    Stub endpoint for agent-chat-ui to list available assistants.

    Returns a single assistant (supervisor) with its ID and name.
    """
    return [{"assistant_id": "supervisor", "name": "Supervisor", "graph_id": "supervisor"}]

@app.post("/threads")
async def create_thread():
    """
    Stub endpoint for agent-chat-ui to create a new conversation thread.

    Generates a new UUID and returns it as thread_id.
    """
    thread_id = str(uuid.uuid4())
    _thread_store[thread_id] = {"messages": [], "state": {}}
    return {"thread_id": thread_id}

@app.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """
    Stub endpoint for agent-chat-ui to get the current state of a thread.

    Returns the messages stored in the thread (or empty list if not found).
    """
    if thread_id not in _thread_store:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"values": {"messages": _thread_store[thread_id].get("messages", [])}}

@app.post("/threads/{thread_id}/runs")
async def run_thread(thread_id: str, request: Request):
    """
    Stub endpoint for agent-chat-ui to execute a thread run.

    This endpoint forwards the request to the /invoke logic, using the
    thread_id as the configurable thread_id, and stores the response
    in the thread store so that subsequent state requests can retrieve it.

    The UI expects a run_id in response, which we generate.
    """
    if thread_id not in _thread_store:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Parse the incoming request body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Build the state dictionary in the format expected by /invoke
    state = {
        "messages": body.get("messages", []),
        "thread_id": thread_id,
    }

    graph = ml_models.get("graph")
    if not graph:
        raise HTTPException(status_code=503, detail="Graph not ready")

    try:
        # Build config with thread_id for checkpointer
        config = {"configurable": {"thread_id": thread_id}}
        # Invoke the supervisor with the state and config
        result = await invoke_supervisor_with_retry(graph, state, config=config)

        # Store the result in the thread store for later retrieval.
        assistant_message = {
            "role": "assistant",
            "content": result.get("analysis", "I processed your request.")
        }
        _thread_store[thread_id]["messages"].append(assistant_message)

        run_id = str(uuid.uuid4())
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "messages": [assistant_message],
        }
    except Exception as e:
        logger.error(f"Run thread failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# NEW ENDPOINT: /runs (standalone run creation)
# =============================================================================
@app.post("/runs")
async def create_run(request: Request):
    """
    Stub endpoint for agent-chat-ui to create a new run without a pre-existing thread.

    This endpoint creates a new thread, runs the supervisor, and returns the
    assistant's response inline. This is the primary endpoint used by the UI.
    """
    # Parse the incoming request body
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Create a new thread ID
    thread_id = str(uuid.uuid4())
    _thread_store[thread_id] = {"messages": body.get("messages", [])}

    # Build the state dictionary
    state = {
        "messages": body.get("messages", []),
        "thread_id": thread_id,
    }

    graph = ml_models.get("graph")
    if not graph:
        raise HTTPException(status_code=503, detail="Graph not ready")

    try:
        # Build config with thread_id for checkpointer
        config = {"configurable": {"thread_id": thread_id}}
        # Invoke the supervisor with the state and config
        result = await invoke_supervisor_with_retry(graph, state, config=config)

        # Extract the assistant's message
        assistant_message = {
            "role": "assistant",
            "content": result.get("analysis", "I processed your request.")
        }
        _thread_store[thread_id]["messages"].append(assistant_message)

        run_id = str(uuid.uuid4())
        # Return a response in the format expected by the UI
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "messages": [assistant_message],
        }
    except Exception as e:
        logger.error(f"Create run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Real-Time Streaming (Add SSE)
# =============================================================================

@app.post("/stream")
async def stream(request: Request):
    data = await request.json()
    async def event_generator():
        async for event in graph.astream_events(
            {"messages": data["messages"]},
            config={"configurable": {"thread_id": data.get("thread_id")}},
            version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                yield f"data: {json.dumps({'token': event['data']['chunk'].content})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# =============================================================================
# MAIN INFERENCE ENDPOINT (unchanged)
# =============================================================================

@app.post("/invoke")
async def invoke(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
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
    # =========================================================================
    DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() == "true"

    if DISABLE_AUTH:
        logger.warning("Authentication is disabled (DISABLE_AUTH=true) - allowing all requests.")
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
        # Passing config if present (for checkpointer)
        result = await invoke_supervisor_with_retry(graph, state, config=config if config else None)

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


# =============================================================================
# WireGuard Management Endpoints
# =============================================================================

from tools.wireguard_manager import WireGuardManager

# Add after the existing authentication middleware and before the /invoke endpoint

# -----------------------------------------------------------------------------
# WireGuard Management
# -----------------------------------------------------------------------------

@app.get("/api/wireguard/status")
async def wireguard_status(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Get the status of the WireGuard VPN server.
    """
    # Use existing authentication
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = WireGuardManager.get_server_status()
    return status


@app.get("/api/wireguard/users")
async def wireguard_list_users(
    request: Request,
    include_revoked: bool = False,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    List all WireGuard VPN users (peers).
    """
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        # Get Odoo environment
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")

        users = WireGuardManager.list_peers(odoo_env, include_revoked)
        return {"users": users, "count": len(users)}
    except Exception as e:
        logger.error(f"Failed to list WireGuard users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/wireguard/users")
async def wireguard_create_user(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Create a new WireGuard VPN user.

    Request body:
    {
        "partner_id": int,  # Odoo partner ID
        "name": str         # Human-readable name
    }
    """
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    partner_id = body.get('partner_id')
    name = body.get('name')

    if not partner_id or not name:
        raise HTTPException(status_code=400, detail="partner_id and name are required")

    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")

        peer = WireGuardManager.create_peer(partner_id, name, odoo_env)
        return peer
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/wireguard/users/{user_id}")
async def wireguard_revoke_user(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Revoke a WireGuard VPN user.
    """
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")

        success = WireGuardManager.revoke_peer(user_id, odoo_env)
        if not success:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to revoke WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wireguard/users/{user_id}/config")
async def wireguard_get_config(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Get the WireGuard configuration file for a user.
    """
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")

        config = WireGuardManager.get_peer_config(user_id, odoo_env)
        if not config:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")

        # Return as plain text with appropriate headers
        return Response(
            content=config,
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=wg-{user_id}.conf"
            }
        )
    except Exception as e:
        logger.error(f"Failed to get WireGuard config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/wireguard/users/{user_id}/qrcode")
async def wireguard_get_qrcode(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Get a QR code for the WireGuard configuration of a user.
    """
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")

        qr_code = WireGuardManager.get_peer_qr_code(user_id, odoo_env)
        if not qr_code:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")

        return {"qr_code": qr_code}
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Helper: Authentication
# =============================================================================

async def authenticate_request(api_key: Optional[str]) -> bool:
    """
    Authenticate a request using the API key.
    Uses the same key as the LangGraph endpoints.
    """
    if not api_key:
        return False

    expected_key = os.getenv("LANGGRAPH_API_KEY")
    if not expected_key:
        logger.warning("LANGGRAPH_API_KEY not configured")
        return False

    return api_key == expected_key