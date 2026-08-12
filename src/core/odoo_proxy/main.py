#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Odoo JSON-RPC Proxy
# =============================================================================
# FILE: src/core/odoo_proxy/main.py
#
# PURPOSE:
#   This FastAPI service provides a secure HTTP JSON-RPC endpoint that proxies
#   calls to the Odoo server. It validates an API key sent in the request
#   headers and forwards the JSON-RPC payload to Odoo's internal endpoint.
#
#   This service replaces the broken mcp-odoo HTTP integration, which
#   was a stdio-based MCP server that never exposed an HTTP port.
#
# USAGE:
#   The service listens on port 3000 by default and expects requests to
#   /jsonrpc with a Bearer token or X-API-Key header.
#
# DEPENDENCIES:
#   - fastapi
#   - httpx
#   - uvicorn
#
# =============================================================================

import json
import logging
import os
import sys
import hmac
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from .auth import router as auth_router, init_auth
from .mode import router as mode_router, init_mode

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse

# =============================================================================
# LOGGING SETUP (must be before any logger usage)
# =============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = int(os.getenv("ODOO_USER", "1"))
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")

ODOO_API_KEY = os.getenv("ODOO_API_KEY")
PROXY_API_KEY = os.getenv("PROXY_API_KEY")

# =============================================================================
# STARTUP VALIDATION (fail-fast)
# =============================================================================
if not ODOO_API_KEY:
    logger.critical("ODOO_API_KEY environment variable is not set")
    sys.exit(1)
if not PROXY_API_KEY:
    logger.critical("PROXY_API_KEY environment variable is not set")
    sys.exit(1)

WEAK_KEYS = ["change_me_in_production", "changeit", "password", "admin", "test"]
if PROXY_API_KEY in WEAK_KEYS:
    logger.critical(f"PROXY_API_KEY is set to a known weak value: {PROXY_API_KEY}")
    sys.exit(1)

logger.info("✅ Credentials validated at startup")

# =============================================================================
# MODEL WHITELIST (security)
# =============================================================================
ALLOWED_MODELS = {
    "res.partner",
    "sale.order",
    "project.project",
    "hr.employee",
    "nettrades.field",
    "data.episode",
    "gpu.node",
    "gpu.cluster",
    # Add business models as needed, but NEVER include res.users or ir.model
}

# =============================================================================
# RATE LIMITING
# =============================================================================
failed_attempts = defaultdict(list)
MAX_ATTEMPTS = 5
WINDOW_MINUTES = 15


async def authenticate(request: Request) -> bool:
    """
    Validate the API key from the request headers with rate limiting.

    Supports:
        - X-API-Key header
        - Authorization: Bearer <token>
    """
    client_ip = request.client.host
    api_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization", "")

    # Try X-API-Key
    if api_key and hmac.compare_digest(api_key, PROXY_API_KEY):
        failed_attempts[client_ip] = []
        return True

    # Try Bearer token
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        if hmac.compare_digest(token, PROXY_API_KEY):
            failed_attempts[client_ip] = []
            return True

    # Track failure
    now = datetime.utcnow()
    failed_attempts[client_ip].append(now)
    cutoff = now - timedelta(minutes=WINDOW_MINUTES)
    failed_attempts[client_ip] = [t for t in failed_attempts[client_ip] if t > cutoff]

    if len(failed_attempts[client_ip]) >= MAX_ATTEMPTS:
        logger.warning(f"Rate limit exceeded for {client_ip}")
        raise HTTPException(status_code=429, detail="Too many authentication failures")

    return False

# =============================================================================
# FASTAPI APP
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Set up a shared HTTP client for the proxy."""
    app.state.client = httpx.AsyncClient(
        timeout=60.0,
        follow_redirects=True,
    )
    yield
    await app.state.client.aclose()

app = FastAPI(
    title="Odoo JSON-RPC Proxy",
    description="Securely forwards JSON-RPC calls to Odoo.",
    version="1.0.0",
    lifespan=lifespan,
)

# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health")
async def health():
    """Simple health check for monitoring."""
    return {"status": "healthy", "service": "odoo-proxy"}


@app.get("/models")
async def list_models(request: Request):
    """
    Return a list of whitelisted Odoo models.

    Used by LangGraph agents to discover the data schema.
    Authentication: Requires the same API key as /jsonrpc.
    """
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return only whitelisted models
    return {
        "models": [
            {"name": m, "label": m.replace(".", " ").title()}
            for m in ALLOWED_MODELS
        ]
    }


@app.get("/models/{model_name}/fields")
async def get_model_fields(model_name: str, request: Request):
    """
    Return the fields for a whitelisted model only.

    Authentication: Requires the same API key as /jsonrpc.
    """
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if model_name not in ALLOWED_MODELS:
        logger.warning(f"Attempted access to non-whitelisted model: {model_name}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{model_name}' is not whitelisted",
        )

    # Build a JSON-RPC payload to call fields_get on the model
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                ODOO_DB,
                ODOO_USER,
                ODOO_PASSWORD,
                model_name,
                "fields_get",
                [[], ["string", "type", "required", "selection", "relation"]]
            ]
        },
        "id": 1
    }

    client = request.app.state.client
    odoo_endpoint = f"{ODOO_URL.rstrip('/')}/jsonrpc"

    try:
        response = await client.post(odoo_endpoint, json=payload)
        response.raise_for_status()
        result = response.json().get("result", {})
        return {"fields": result}
    except httpx.HTTPStatusError as e:
        logger.error(f"Odoo error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="Odoo returned an error")
    except Exception as e:
        logger.exception(f"Error fetching fields for {model_name}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/jsonrpc")
async def jsonrpc_proxy(request: Request):
    """
    Handle incoming JSON-RPC requests and proxy them to Odoo.

    Expected request format:
        {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": ["db_name", "uid", "api_key", "model_name", "method_name", [...]]
            },
            "id": 1
        }

    The proxy forwards the exact same payload to the Odoo server.
    """
    # 1. Authentication
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Read and validate request body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if "jsonrpc" not in body or body.get("jsonrpc") != "2.0":
        raise HTTPException(status_code=400, detail="Only JSON-RPC 2.0 is supported")

    # 3. Forward to Odoo
    client = request.app.state.client
    odoo_endpoint = f"{ODOO_URL.rstrip('/')}/jsonrpc"

    try:
        response = await client.post(odoo_endpoint, json=body)
        response.raise_for_status()
        return JSONResponse(content=response.json())
    except httpx.HTTPStatusError as e:
        logger.error(f"Odoo returned error: {e.response.status_code} - {e.response.text}")
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"Odoo error: {e.response.text}"},
        )
    except httpx.TimeoutException as e:
        logger.error(f"Timeout while calling Odoo: {e}")
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except Exception as e:
        logger.exception("Unexpected error in proxy")
        raise HTTPException(status_code=500, detail=f"Internal proxy error: {str(e)}")


# =============================================================================
# Initialize authentication and mode modules
# =============================================================================

init_auth(ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD)
init_mode(ODOO_URL, ODOO_API_KEY, "valkey", 6379)

# =============================================================================
# Register routers
# =============================================================================

app.include_router(auth_router)
app.include_router(mode_router)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        log_level="info",
    )