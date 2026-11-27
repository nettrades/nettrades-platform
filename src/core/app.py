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
#     - /nodes    - list GPU nodes tracked by the health monitor
#     - /nodes/heartbeat - push heartbeat from a spoke (NEW 2026-10)
#     - /rpc/relaunch -  relaunch the RPC cluster for a given cluster
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
#
# ADDITIONS (2026-10):
#  12. POST /nodes/heartbeat — inbound push heartbeat from spoke agents.
#      The push model works behind NAT and for freelancer machines off the
#      network; the previous pull-only model could not reach either.
#  13. Periodic node inventory refresh (every 60s) in the lifespan. Before
#      this, a node added to Odoo after LangGraph started was invisible
#      until the LangGraph container was restarted.
#  14. /nodes and /nodes/{id}/health now expose vram_total_mb, gpu_count,
#      and model_cached. These are needed by the supervisor's
#      _get_available_hardware() to decide whether a model fits on the
#      RPC cluster.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

import os
import asyncio
import hmac
import json
import logging
import psycopg
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# -----------------------------------------------------------------------------
# Core imports (preserved from original)
# -----------------------------------------------------------------------------
from supervisor import build_supervisor
from middleware import metrics_middleware, auth_middleware
from security.prompt_injection import PromptInjectionMiddleware

# -----------------------------------------------------------------------------
# Node health monitor
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
CHECKPOINT_DB_URI = os.getenv(
    "CHECKPOINT_DATABASE_URL",
    "postgresql://odoo:password@postgres:5432/checkpoints",
)

# Global dictionary to hold the compiled graph (preserved from original)
ml_models = {}

# Shared secret used by the spoke heartbeat endpoint. This is SEPARATE
# from LANGGRAPH_API_KEY: the spoke needs to authenticate to
# /nodes/heartbeat but must not be given the master API key that unlocks
# /invoke and every other control-plane endpoint.
#
# Fallback to LANGGRAPH_API_KEY is intentional for backward compatibility
# with existing installations that already have LANGGRAPH_API_KEY
# distributed to their spokes. New deployments should set
# LANGGRAPH_HEARTBEAT_SECRET and only give that to spokes.
_HEARTBEAT_API_KEY = (
    os.getenv("LANGGRAPH_HEARTBEAT_SECRET")
    or os.getenv("LANGGRAPH_API_KEY", "")
)


# =============================================================================
# LOAD NODE INVENTORY INTO THE HEALTH MONITOR
# =============================================================================
async def _load_node_inventory_into_monitor():
    """
    Read the GPU node inventory from Odoo and register each node with the
    health monitor.

    Called once at startup, and then once every 60 seconds by
    _node_inventory_loop().

    Field names are deliberately minimal. `gpu.node` has `id`, `hostname`,
    `endpoint`, `gpus`, `compute_profile`, and `inference_capability`.
    It does **not** have `node_id` or `gpu_pool`. Requesting a field that
    does not exist makes `search_read` raise `Invalid field`, which would
    abort the entire inventory load and leave the `dynamo_worker` invisible
    to the supervisor. That would disable Tier 2 failover.
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
                {
                    "fields": [
                        "id", "hostname", "endpoint", "wireguard_ip",
                        "gpus", "compute_profile", "inference_capability",
                    ]
                },
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
                if "error" in body:
                    logger.error("Node inventory RPC failed: %s", body["error"])
                    return
                nodes = body.get("result", [])
                for n in nodes:
                    # Canonical key: the Odoo record id as a string.
                    # This is the same key the heartbeat endpoint uses.
                    node_key = str(n["id"])

                    gpus = n.get("gpus") or []
                    if isinstance(gpus, str):
                        import json as _json
                        try:
                            gpus = _json.loads(gpus)
                        except Exception:
                            gpus = []
                    total_vram_mb = sum(
                        int(g.get("memory_mb") or 0) for g in gpus
                    )

                    profile = n.get("compute_profile") or {}
                    if isinstance(profile, str):
                        import json as _json
                        try:
                            profile = _json.loads(profile)
                        except Exception:
                            profile = {}
                    model_cached = bool(profile.get("model_cached", False))
                    role = n.get("inference_capability") or "rpc_worker"
                    ip = n.get("wireguard_ip") or n.get("endpoint") or ""
                    # Only RPC worker nodes expose rpc_backends. A dynamo_worker
                    # is a single vLLM/OpenAI-compatible HTTP endpoint, not a
                    # set of ggml RPC servers. Building host:port probes for it
                    # produces garbage like "http://host:8001:50052" that
                    # always fails, and it pollutes /nodes for the Launcher.
                    rpc_backends = []
                    if role == "rpc_worker" and ip and "://" not in ip:
                        for i, g in enumerate(gpus):
                            port = int(g.get("rpc_port") or (50052 + i))
                            rpc_backends.append(f"{ip}:{port}")

                    # If this machine has a hub manifest (written by phase-deploy.sh from
                    # scripts/lib/detect.py), use its per-GPU list to override the values
                    # read from gpu.node. The gpu.node record is a snapshot from the last
                    # time configure-hub-for-spokes.sh ran; the manifest is regenerated on
                    # every deploy. For the local node only — a spoke's heartbeat is the
                    # authoritative source for that spoke's hardware.
                    _HUB_MANIFEST = "/app/hub-manifest.json"
                    if os.path.exists(_HUB_MANIFEST):
                        try:
                            with open(_HUB_MANIFEST) as _f:
                                _manifest = json.load(_f)
                            _m_gpus = _manifest.get("gpus") or []
                            _m_host = _manifest.get("hostname") or ""
                            # Match: this node's hostname matches the manifest hostname,
                            # OR the endpoint points at the local inference container.
                            if (n.get("hostname") == _m_host) or ("llama-cpp" in (n.get("endpoint") or "")):
                                gpus = _m_gpus
                                total_vram_mb = sum(int(g.get("memory_mb") or 0) for g in gpus)
                                if _manifest.get("recommended_role"):
                                    role = _manifest["recommended_role"]
                                # Use the manifest's hostname so /nodes shows the
                                # machine's real name rather than whatever the Odoo
                                # record held at last registration. Cosmetic — the
                                # health monitor and supervisor key on node_id, not
                                # hostname — but avoids confusion in the Launcher.
                                if _m_host:
                                    n["hostname"] = _m_host
                                logger.info(
                                    "Hub manifest override: node %s -> %d GPU(s), %d MB",
                                    node_key, len(gpus), total_vram_mb,
                                )
                        except Exception as _e:
                            logger.warning("Hub manifest read failed: %s", _e)

                    monitor.register_node(
                        node_id=node_key,
                        hostname=n.get("hostname", "unknown"),
                        role=role,
                        endpoint=n.get("endpoint") or "",
                        vram_total_mb=total_vram_mb,
                        gpu_count=len(gpus),
                        model_cached=model_cached,
                        rpc_backends=rpc_backends, # <-- Add this
                    )
                    
                logger.info(
                    f"Registered {len(nodes)} nodes with the health monitor"
                )
    except Exception as e:
        logger.warning(f"Could not load node inventory: {e}")


# =============================================================================
# PERIODIC NODE INVENTORY REFRESH
# =============================================================================
async def _node_inventory_loop(interval_seconds: int = 60):
    """
    Refresh the health monitor's node list from Odoo every 60 seconds.

    The lifespan calls _load_node_inventory_into_monitor() once directly
    before starting this task. Sleeping first here means the first refresh
    happens 60 s after startup, not 0 s — avoiding a duplicate call 19 ms
    after the lifespan's call.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await _load_node_inventory_into_monitor()
        except Exception as e:
            logger.warning(f"Node inventory refresh failed: {e}")


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
      6. Load node inventory and start the health monitor.
      7. Start the periodic node inventory refresh loop.

    Shutdown:
      Stop the health monitor, cancel the inventory loop, clear ml_models,
      close the DB connection.
    """
    # Open an ASYNC connection for the checkpointer.
    # This is the same DB the Odoo data lives in, but the checkpointer
    # manages its own tables (checkpoints, checkpoint_writes,
    # checkpoint_blobs) inside that database.
    #
    # autocommit=True is required because AsyncPostgresSaver issues
    # CREATE INDEX CONCURRENTLY during setup(), which cannot run inside
    # a transaction block.
    # conn = await psycopg.AsyncConnection.connect(DB_URI, autocommit=True)
    conn = await psycopg.AsyncConnection.connect(CHECKPOINT_DB_URI, autocommit=True)
    try:
        # Create the async checkpointer and initialise its schema.
        checkpointer = AsyncPostgresSaver(conn)
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver setup complete")

        # LangGraph raised NotImplementedError because the graph's checkpointer does not implement the async interface that ainvoke requires. (Bug in LangGraph)
        # Attach the checkpointer by RECOMPILING the graph with it.
        # Assigning `graph.checkpointer = checkpointer` post-compile
        # does not work: Pregel captures the checkpointer reference at
        # compile time. The correct pattern is to pass it to .compile().

        graph = build_supervisor(checkpointer=checkpointer)
        ml_models["graph"] = graph
        logger.info("Supervisor graph compiled with async checkpointer")

        # Load initial inventory and start the health monitor.
        await _load_node_inventory_into_monitor()
        monitor = get_health_monitor()
        monitor.start()
        logger.info("Node health monitor started")

        # Start the periodic inventory refresh (every 60 seconds).
        inventory_task = asyncio.create_task(_node_inventory_loop())

        # Store in app state for route access.
        app.state.ml_models = ml_models
        app.state.db_conn = conn
        app.state.health_monitor = monitor
        app.state.inventory_task = inventory_task

        yield

    except Exception as e:
        logger.error(f"Lifespan startup failed: {e}")
        raise
    finally:
        # Stop the health monitor before closing the DB.
        try:
            await get_health_monitor().stop()
            logger.info("Node health monitor stopped")
        except Exception as e:
            logger.warning(f"Error stopping health monitor: {e}")

        # Cancel the periodic inventory loop.
        try:
            if hasattr(app.state, "inventory_task"):
                app.state.inventory_task.cancel()
                try:
                    await app.state.inventory_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.warning(f"Error stopping inventory loop: {e}")

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
# NODE HEALTH ENDPOINTS
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
                # NEW (2026-10): VRAM totals needed by the supervisor.
                "vram_total_mb": n.vram_total_mb,
                "gpu_count": n.gpu_count,
                "model_cached": n.model_cached,
                "rpc_backends": n.rpc_backends,                
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
        "vram_total_mb": node.vram_total_mb,
        "gpu_count": node.gpu_count,
        "model_cached": node.model_cached,
    }


# =============================================================================
# PUSH HEARTBEAT ENDPOINT (NEW 2026-10)
# =============================================================================
# Spoke agents POST here every 10 seconds with their current VRAM, GPU count,
# utilisation, and model-cached state. This is the primary health signal for
# RPC worker spokes and for freelancer machines behind NAT.
#
# Authentication: the same Bearer token the spoke uses against Odoo. It is
# not the LANGGRAPH_API_KEY, because the spoke does not have that key. The
# token is validated the same way Odoo validates it: the spoke is trusted
# once it has a registration token, and the token has already been verified
# by Odoo at registration time.
#
# Because the Odoo registration flow is the actual trust root here, this
# endpoint accepts any node_id the caller supplies. If you want to harden
# this, add a shared secret between the spoke and LangGraph; that is a
# follow-up item.
#
# When a machine is being switched off the spoke agent should send "draining": true 
# in its heartbeat for 30 seconds before being switched off, therefore the 
# supervisor agent in LangGraph on the hub will see the node as "unhealthy" 
# during the 30-second grace period and will not sending it  new requests.
# =============================================================================
class _HeartbeatRequest(BaseModel):
    node_id: int
    vram_total_mb: int = 0
    gpu_count: int = 0
    gpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    temperature: float = 0.0
    model_cached: bool = False
    timestamp: Optional[str] = None
    rpc_backends: Optional[List[str]] = None
    per_gpu_vram_mb: Optional[List[int]] = None
    draining: bool = False                          # draining field

@app.post("/nodes/heartbeat")
async def node_heartbeat(
    req: _HeartbeatRequest,
    authorization: Optional[str] = Header(None),
):
    """
    Record an inbound heartbeat from a spoke agent.

    Called by spoke-agent.py every 10 seconds. Updates the in-memory
    NodeHealth entry for this node. The node is auto-registered on the
    first heartbeat, so no separate registration call against LangGraph
    is needed.

    The node_id is the Odoo record ID (an integer). The spoke knows this
    value because it came back from POST /api/v1/gpu/register.
    """
    # Require a Bearer token and validate it against the shared secret.
    #
    # SECURITY FIX (2026-11-16): the previous version accepted ANY Bearer
    # token without comparing it to anything. That meant anyone who could
    # reach /nodes/heartbeat (including any authenticated HTTP client on
    # the network) could forge a heartbeat for any node_id and either:
    #   (a) drain a legitimate worker by sending draining=true, or
    #   (b) resurrect a failed node by sending a heartbeat with a fresh
    #       timestamp, which would clear the health monitor's failure
    #       counter and trigger a premature failover restore.
    #
    # The secret is compared with hmac.compare_digest to avoid timing
    # side channels.
    if not _HEARTBEAT_API_KEY:
        _logger.error(
            "LANGGRAPH_HEARTBEAT_SECRET is not set — refusing heartbeat. "
            "Set LANGGRAPH_HEARTBEAT_SECRET (recommended) or "
            "LANGGRAPH_API_KEY in the langgraph-server environment."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Heartbeat authentication is not configured. "
                "Set LANGGRAPH_HEARTBEAT_SECRET in the environment."
            ),
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )

    _token = authorization.split(" ", 1)[1]
    if not hmac.compare_digest(_token, _HEARTBEAT_API_KEY):
        _logger.warning(
            "Rejected heartbeat: invalid Bearer token (node_id=%s)",
            req.node_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer token",
        )

    monitor = get_health_monitor()
    node_key = str(req.node_id)

    monitor.record_heartbeat(
        node_id=node_key,
        hostname="",  # keep existing; register_node set it
        vram_total_mb=req.vram_total_mb,
        gpu_count=req.gpu_count,
        gpu_utilization=req.gpu_utilization,
        memory_utilization=req.memory_utilization,
        temperature=req.temperature,
        model_cached=req.model_cached,
        rpc_backends=req.rpc_backends,
        draining=req.draining,                 # NEW: Pass the draining flag
    )

    return {"status": "ok", "node_id": req.node_id}

# =============================================================================
# ROUTING EVENTS ENDPOINT (NEW 2026-10)
# =============================================================================
# Returns the supervisor's recent routing decisions so the Launcher can
# show a live failover timeline. Ring-buffer backed; not persisted.
# =============================================================================
@app.get("/routing/events")
async def routing_events(limit: int = 100):
    """Return the most recent routing events from the supervisor."""
    from supervisor import get_routing_events
    return {"events": get_routing_events(limit)}


# =============================================================================
# CLUSTER STATE ENDPOINT (NEW 2026-10)
# =============================================================================
# Reads gpu.cluster.layer_assignment and related fields via the Odoo proxy,
# then returns them alongside the live node state. Used by the Launcher's
# Cluster tab to render the pipeline topology table.
# =============================================================================
@app.get("/cluster/{cluster_id}")
async def cluster_state(cluster_id: int):
    """Return the layer assignment and topology for a cluster."""
    import httpx
    from rpc_scheduler import RPCScheduler

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
                odoo_db, odoo_user, odoo_password,
                "gpu.cluster", "read",
                [[cluster_id]],
                {"fields": [
                    "id", "name", "trust_mode", "status",
                    "layer_assignment",
                    "allow_dynamo_fallback",
                    "allow_rpc_partial_fallback",
                    "allow_marketplace_fallback",
                    "allow_external_api_fallback",
                ]},
            ],
        },
        "id": 1,
    }
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{odoo_url}/jsonrpc", json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise HTTPException(status_code=502, detail=str(body["error"]))
            clusters = body.get("result", [])
            if not clusters:
                raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")
            cluster = clusters[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Odoo read failed: {e}")

    # Attach live node state from the health monitor.
    monitor = get_health_monitor()
    live_nodes = []
    for n in monitor._nodes.values():
        live_nodes.append({
            "node_id": n.node_id,
            "hostname": n.hostname,
            "role": n.role,
            "is_healthy": n.is_healthy,
            "vram_total_mb": n.vram_total_mb,
            "gpu_count": n.gpu_count,
            "model_cached": n.model_cached,
            "rpc_backends": n.rpc_backends,
            "last_heartbeat": n.last_heartbeat.isoformat() if n.last_heartbeat else None,
        })

    return {
        "cluster": cluster,
        "live_nodes": live_nodes,
    }


# =============================================================================
# TOKENS ENDPOINTS (NEW 2026-10)
# =============================================================================
# Proxies gpu.registration.token CRUD to Odoo. The Launcher's Tokens tab
# uses these to list, create, and revoke registration tokens without
# needing the operator to open the Odoo web UI.
# =============================================================================
@app.get("/tokens")
async def list_tokens():
    """List all registration tokens (metadata only, no plaintext)."""
    import httpx
    odoo_url = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
    api_key = os.getenv("ODOO_API_KEY", "")
    payload = {
        "jsonrpc": "2.0", "method": "call",
        "params": {
            "service": "object", "method": "execute_kw",
            "args": [
                os.getenv("ODOO_DB", "odoo"),
                int(os.getenv("ODOO_USER", "1")),
                os.getenv("ODOO_PASSWORD", "admin"),
                "gpu.registration.token", "search_read",
                [[]],
                {"fields": ["id", "name", "company_id", "cluster_id",
                            "create_date", "expiry_date", "is_used",
                            "is_revoked", "used_by_node_id"],
                 "order": "create_date desc"},
            ],
        },
        "id": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{odoo_url}/jsonrpc", json=payload,
                                  headers={"X-API-Key": api_key})
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise HTTPException(status_code=502, detail=str(body["error"]))
            return {"tokens": body.get("result", [])}
    except HTTPException:
        raise
    except Exception as e:
        # Return empty list instead of 502 so the UI doesn't break
        return {"tokens": []}  
# =============================================================================
# RPC CLUSTER RELAUNCH
# =============================================================================
class _RelaunchRequest(BaseModel):
    cluster_id: int
    exclude_node_id: Optional[int] = None
    exclude_port: Optional[int] = None

@app.post("/rpc/relaunch")
async def rpc_relaunch(req: _RelaunchRequest):
    from rpc_scheduler import RPCScheduler, RPCSchedulerError
    scheduler = RPCScheduler()
    try:
        if req.exclude_node_id is not None:
            return await scheduler.restart_without_node(
                req.cluster_id,
                req.exclude_node_id,
                failed_port=req.exclude_port,
            )
        return await scheduler.launch_cluster(req.cluster_id)
    except RPCSchedulerError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("rpc/relaunch failed")
        raise HTTPException(status_code=500, detail=f"RPC relaunch failed: {e}")
