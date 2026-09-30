#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Odoo JSON-RPC Proxy
# =============================================================================
# FILE: src/core/odoo_proxy/main.py
#
# PURPOSE:
#   This FastAPI service provides a secure HTTP endpoint that proxies
#   calls to the Odoo server. It validates an API key sent in the request
#   headers and forwards the payload to Odoo.
#
#   This service replaces the broken mcp-odoo HTTP integration, which
#   was a stdio-based MCP server that never exposed an HTTP port.
#
# SUPPORTED TRANSPORTS:
#   1. /jsonrpc                 - Legacy JSON-RPC envelope (execute_kw)
#   2. /json/2/{model}/{method} - Modern JSON-2 API (Odoo 19+)
#
#   The JSON-2 transport uses a service API key stored in
#   ODOO_SERVICE_API_KEY. When that variable is set, the proxy
#   authenticates to Odoo with the scoped service user's token instead
#   of forwarding the client-supplied uid/password. This is the
#   forward-compatible path: Odoo 20 deprecates execute_kw, and the
#   JSON-2 API is the replacement.
#
# USAGE:
#   The service listens on port 8080 by default and expects requests to
#   /jsonrpc or /json/2/... with an X-API-Key header (or Bearer token).
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
from typing import Any, Dict, Optional
from auth import router as auth_router, init_auth
from mode import router as mode_router, init_mode

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

# The service API key is the Odoo API key of the scoped `nettrades-service`
# user. When set, the JSON-2 endpoint uses it to authenticate to Odoo.
# Falls back to ODOO_API_KEY for backwards compatibility.
ODOO_SERVICE_API_KEY = os.getenv("ODOO_SERVICE_API_KEY", ODOO_API_KEY or "")

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
if ODOO_SERVICE_API_KEY and ODOO_SERVICE_API_KEY != ODOO_API_KEY:
    logger.info("✅ Scoped service API key detected — JSON-2 endpoint will use it")

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
    "gpu.cluster.subnet",
    "gpu.sharing.schedule",
    "gpu.token.economics",
    "gpu.registration.token",
    "multimodal.config",
    "nettrades.wireguard",
    # Add business models as needed, but NEVER include res.users or ir.model
}


def _model_is_allowed(model_name: str) -> bool:
    """
    Check whether a model name is on the whitelist.

    Used by all endpoints that accept a model name (either from the URL
    path in JSON-2 or from the execute_kw args in JSON-RPC). Enforcing
    the whitelist in one place prevents the class of bug where only
    some endpoints check it.
    """
    return model_name in ALLOWED_MODELS


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
    description="Securely forwards JSON-RPC and JSON-2 calls to Odoo.",
    version="2.0.0",
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

    if not _model_is_allowed(model_name):
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

    SECURITY FIX (BUG-001):
        The model name is extracted from `params.args[3]` and checked
        against the whitelist. Requests targeting non-whitelisted models
        are refused with HTTP 403. Previously, only /models and
        /models/{name}/fields enforced the whitelist; /jsonrpc forwarded
        every payload. This allowed an authenticated client to call
        execute_kw('res.users', 'search_read', ...) and read user records.

    The proxy forwards the (validated) payload to the Odoo server
    unchanged. The uid/password in `params.args[1..2]` are still the
    caller's responsibility; this endpoint is the legacy path.
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

    # 3. BUG-001 FIX: Extract the model name from params.args[3] and
    #    enforce the whitelist. Only applies when the service is
    #    "object" and the method is "execute_kw"; other services pass
    #    through unchanged.
    params = body.get("params", {})
    service = params.get("service")
    method = params.get("method")
    if service == "object" and method == "execute_kw":
        args = params.get("args", [])
        if isinstance(args, list) and len(args) >= 4:
            target_model = args[3]
            if not isinstance(target_model, str) or not _model_is_allowed(target_model):
                logger.warning(
                    "Refused /jsonrpc call to non-whitelisted model: %r",
                    target_model,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Model '{target_model}' is not whitelisted",
                )
        else:
            # Malformed execute_kw call; refuse rather than forward blindly
            raise HTTPException(
                status_code=400,
                detail="execute_kw requires at least 4 positional args (db, uid, pwd, model)",
            )

    # 4. Forward to Odoo
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
# JSON-2 ENDPOINT (Odoo 19+, forward-compatible with Odoo 20)
# =============================================================================
# The JSON-2 API (introduced in Odoo 19) replaces the JSON-RPC execute_kw
# envelope with a REST-style endpoint:
#
#   POST /json/2/{model}/{method}
#   Headers: Authorization: Bearer <api_key>
#            Content-Type: application/json
#            X-Odoo-Database: <db>
#   Body:    {"ids": [...], "context": {...}, ...named_params}
#
# Odoo 20 removes the `db` service and marks execute_kw for removal in
# Odoo 22. Clients should migrate to JSON-2 as soon as practical.
#
# This proxy endpoint:
#   1. Validates the incoming PROXY_API_KEY (same as /jsonrpc)
#   2. Checks the model name against ALLOWED_MODELS
#   3. Adds the ODOO_SERVICE_API_KEY as a Bearer token when forwarding
#   4. Forwards the request body unchanged
#
# The caller does NOT need to know the service API key. The proxy holds
# it. This keeps the scoped credential inside the trusted network.
# =============================================================================

@app.post("/json/2/{model_name}/{method_name}")
async def json2_proxy(model_name: str, method_name: str, request: Request):
    """
    Forward a JSON-2 API call to Odoo.

    Path parameters:
        model_name  - the Odoo model (must be on the whitelist)
        method_name - the method to invoke

    Body: JSON object with `ids`, `context`, and any named parameters
    that the target method expects.

    Authentication: the proxy validates the caller's X-API-Key, then
    forwards to Odoo using ODOO_SERVICE_API_KEY (the scoped service
    user's Odoo API key).
    """
    # 1. Authenticate the caller
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Whitelist check
    if not _model_is_allowed(model_name):
        logger.warning(
            "Refused JSON-2 call to non-whitelisted model: %s",
            model_name,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Model '{model_name}' is not whitelisted",
        )

    # 3. The service API key must be configured. If not, refuse
    #    rather than silently falling back to admin credentials.
    if not ODOO_SERVICE_API_KEY:
        logger.error(
            "JSON-2 endpoint called but ODOO_SERVICE_API_KEY is not set. "
            "Set it to the nettrades-service user's API key."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JSON-2 endpoint not configured (ODOO_SERVICE_API_KEY missing)",
        )

    # 4. Read the body
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 5. Forward to Odoo's JSON-2 endpoint
    client = request.app.state.client
    odoo_endpoint = (
        f"{ODOO_URL.rstrip('/')}/json/2/{model_name}/{method_name}"
    )
    headers = {
        "Authorization": f"Bearer {ODOO_SERVICE_API_KEY}",
        "Content-Type": "application/json; charset=utf-8",
        "X-Odoo-Database": ODOO_DB,
    }

    try:
        response = await client.post(odoo_endpoint, json=body, headers=headers)
        # JSON-2 returns the raw return value on success (200) or a
        # JSON error object on failure (4xx/5xx). Pass it through.
        return JSONResponse(
            status_code=response.status_code,
            content=response.json(),
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            "Odoo JSON-2 error: HTTP %s - %s",
            e.response.status_code,
            e.response.text,
        )
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"Odoo error: {e.response.text}"},
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Odoo request timed out")
    except Exception as e:
        logger.exception("Unexpected error in JSON-2 proxy")
        raise HTTPException(status_code=500, detail=f"Internal proxy error: {str(e)}")


# =============================================================================
# Initialize authentication and mode modules
# =============================================================================

# Session persistence uses Valkey if VALKEY_HOST is configured.
init_auth(
    ODOO_URL,
    ODOO_DB,
    ODOO_USER,
    ODOO_PASSWORD,
    valkey_host=os.getenv("VALKEY_HOST", "valkey"),
    valkey_port=int(os.getenv("VALKEY_PORT", "6379")),
)
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
        port=8080,
        log_level="info",
    )