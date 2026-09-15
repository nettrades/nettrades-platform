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
#     - /runs     - create a new run and return assistant response
#
# KEY FEATURES:
#   - Auto-detects inference backend (Dynamo / vLLM / llama.cpp)
#   - Uses a supervisor to dispatch to business sub-agents
#   - Exposes Prometheus metrics for observability
#   - Uses PostgresSaver for durable checkpointing
#   - Stub endpoints for agent-chat-ui compatibility
#
# IMPORTANT FIXES (2026-07-02):
#   1. Authentication Bypass: Now requires LANGGRAPH_API_KEY to be set.
#   2. Removed Dead Code: build_graph() function removed.
#   3. Prompt Injection Monitoring: Sanitises incoming requests.
#   4. Resilience: Retry logic and circuit breaker for supervisor invocation.
#   5. Database Connection: Fixed lifespan to use correct connection type.
#   6. agent-chat-ui Compatibility: Added stub endpoints for /assistants, /threads, etc.
#   7. NEW (2026-07-31): Added /runs endpoint and fixed /threads/{id}/runs.
#   8. FIX (2026-08-01): Pass config with thread_id to supervisor.
#
# ADDITIONS (2026-09-15):
#   9. Health monitor: lifespan now starts and stops the NodeHealthMonitor
#      singleton (src/core/node_health.py). This moves real-time node health
#      tracking out of Odoo cron and into the LangGraph service.
#  10. Node inventory: at startup the service queries Odoo for the list of
#      active GPU nodes and registers each one with the health monitor.
#  11. New endpoints: GET /nodes and GET /nodes/{node_id}/health expose the
#      live health state for debugging and for the Launcher's dashboard.
# =============================================================================

import os
import logging
import psycopg
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

# -----------------------------------------------------------------------------
# Core imports (preserved from original)
# -----------------------------------------------------------------------------
from supervisor import build_supervisor
from middleware import metrics_middleware, auth_middleware
from security.prompt_injection import PromptInjectionMiddleware

# -----------------------------------------------------------------------------
# NEW (2026-09-15): node health monitor
# -----------------------------------------------------------------------------
from node_health import get_health_monitor

# -----------------------------------------------------------------------------
# Route modules (preserved from original)
# -----------------------------------------------------------------------------
from routes import (
    health_router,
    metrics_router,
    invoke_router,
    threads_router,
    assistants_router,
    wireguard_router,
)

# -----------------------------------------------------------------------------
# Load environment variables (preserved from original)
# -----------------------------------------------------------------------------
load_dotenv()

# =============================================================================
# LOGGING CONFIGURATION (preserved from original)
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# SECURITY VALIDATION (FAIL FAST) — preserved from original
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
# CONFIGURATION (preserved from original)
# =============================================================================
DB_URI = os.getenv("DATABASE_URL", "postgresql://odoo:password@postgres:5432/odoo")

# Global dictionary to hold the compiled graph (preserved from original)
ml_models = {}


# =============================================================================
# NEW (2026-09-15): LOAD NODE INVENTORY INTO THE HEALTH MONITOR
# =============================================================================
async def _load_node_inventory_into_monitor():
    """
    Read the GPU node inventory from Odoo and register each node with the
    health monitor. Called once at startup.

    This replaces the Odoo cron job `_cron_health_watchdog`. The advantage
    is that the monitor runs continuously (polling every 10 seconds by
    default) instead of relying on Odoo's cron, which has a minimum
    granularity of one minute and stops if Odoo is restarted.

    If Odoo is unreachable at startup, this function logs a warning and
    returns without registering any nodes. The monitor still runs, and
    nodes can be registered later via the /nodes/register endpoint (TODO).
    """
    try:
        import aiohttp
    except ImportError:
        logger.warning(
            "aiohttp not installed — cannot load node inventory. "
            "The health monitor will start with zero registered nodes."
        )
        return

    monitor = get_health_monitor()
    odoo_url = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
    api_key = os.getenv("ODOO_API_KEY", "")
    odoo_db = os.getenv("ODOO_DB", "odoo")
    odoo_user = int(os.getenv("ODOO_USER", "1"))
    odoo_password = os.getenv("ODOO_PASSWORD", "admin")

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                odoo_db,
                odoo_user,
                odoo_password,
                "gpu.node",
                "search_read",
                [[("state", "=", "active")]],
                {"fields": ["id", "node_id", "hostname", "gpu_pool", "endpoint"]},
            ],
        },
        "id": 1,
    }
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{odoo_url}/jsonrpc", json=payload, headers=headers,
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Node inventory fetch failed: HTTP {resp.status}")
                    return
                body = await resp.json()
                nodes = body.get("result", [])
                for n in nodes:
                    node_id = n.get("node_id") or f"odoo-{n['id']}"
                    endpoint = n.get("endpoint") or ""
                    if not endpoint:
                        continue
                    monitor.register_node(
                        node_id=node_id,
                        hostname=n.get("hostname", "unknown"),
                        role="rpc_worker",  # default; can be refined per-node
                        endpoint=endpoint,
                    )
                logger.info(f"Registered {len(nodes)} nodes with the health monitor")
    except Exception as e:
        logger.warning(f"Could not load node inventory: {e}")


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
      6. NEW: load node inventory and start the health monitor.

    Shutdown:
      NEW: stop the health monitor.
      Clear ml_models and close the connection.
    """
    # Create a synchronous connection using psycopg (version 3)
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

        # ---------------------------------------------------------------------
        # NEW (2026-09-15): start the node health monitor
        # ---------------------------------------------------------------------
        await _load_node_inventory_into_monitor()
        monitor = get_health_monitor()
        monitor.start()
        logger.info("Node health monitor started")

        # Store in app state for route access (preserved from original)
        app.state.ml_models = ml_models
        app.state.db_conn = conn
        app.state.health_monitor = monitor

        yield

    except Exception as e:
        logger.error(f"Lifespan startup failed: {e}")
        raise
    finally:
        # ---------------------------------------------------------------------
        # NEW (2026-09-15): stop the health monitor before closing the DB
        # ---------------------------------------------------------------------
        try:
            await get_health_monitor().stop()
            logger.info("Node health monitor stopped")
        except Exception as e:
            logger.warning(f"Error stopping health monitor: {e}")

        ml_models.clear()
        conn.close()
        logger.info("LangGraph agent shutdown complete")


# =============================================================================
# FASTAPI APPLICATION (preserved from original)
# =============================================================================
app = FastAPI(
    title="NETTRADES LangGraph Agent",
    description="AI orchestration service for autonomous enterprise platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware (preserved from original)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware (preserved from original)
app.middleware("http")(metrics_middleware)
app.middleware("http")(auth_middleware)
app.add_middleware(PromptInjectionMiddleware)

# Include routes (preserved from original)
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(invoke_router)
app.include_router(threads_router)
app.include_router(assistants_router)
app.include_router(wireguard_router)


# =============================================================================
# NEW (2026-09-15): NODE HEALTH ENDPOINTS
# =============================================================================
@app.get("/nodes")
async def list_nodes():
    """
    List every node registered with the health monitor, with its current
    health state and metrics.
    """
    monitor = get_health_monitor()
    return {
        "nodes": [
            {
                "node_id": n.node_id,
                "hostname": n.hostname,
                "role": n.role,
                "endpoint": n.endpoint,
                "is_healthy": n.is_healthy,
                "last_heartbeat": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
                "consecutive_failures": n.consecutive_failures,
                "gpu_utilization": n.gpu_utilization,
                "cpu_utilization": n.cpu_utilization,
            }
            for n in monitor._nodes.values()
        ]
    }


@app.get("/nodes/{node_id}/health")
async def get_node_health(node_id: str):
    """Get the health status of a single node by its node_id."""
    monitor = get_health_monitor()
    node = monitor._nodes.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return {
        "node_id": node.node_id,
        "hostname": node.hostname,
        "role": node.role,
        "endpoint": node.endpoint,
        "is_healthy": node.is_healthy,
        "last_heartbeat": node.last_heartbeat.isoformat() if node.last_heartbeat else None,
        "consecutive_failures": node.consecutive_failures,
        "consecutive_successes": node.consecutive_successes,
        "gpu_utilization": node.gpu_utilization,
        "cpu_utilization": node.cpu_utilization,
    }