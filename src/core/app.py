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
#   - Auto-detects inference backend (GPUStack / vLLM / llama.cpp)
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
# =============================================================================

import os
import logging
import psycopg
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

from supervisor import build_supervisor
from middleware import metrics_middleware, auth_middleware
from security.prompt_injection import PromptInjectionMiddleware

# Import route modules
from routes import (
    health_router,
    metrics_router,
    invoke_router,
    threads_router,
    assistants_router,
    wireguard_router,
)

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

# Global dictionary to hold the compiled graph
ml_models = {}

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

        # Store in app state for route access
        app.state.ml_models = ml_models
        app.state.db_conn = conn

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom middleware
app.middleware("http")(metrics_middleware)
app.middleware("http")(auth_middleware)
app.add_middleware(PromptInjectionMiddleware)

# Include routes
app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(invoke_router)
app.include_router(threads_router)
app.include_router(assistants_router)
app.include_router(wireguard_router)