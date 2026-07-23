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
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "change_me_in_production")
PROXY_API_KEY = os.getenv("PROXY_API_KEY", "change_me_in_production")  # For authenticating callers

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# FastAPI App
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Authentication Middleware
# -----------------------------------------------------------------------------

async def authenticate(request: Request) -> bool:
    """
    Validate the API key from the request headers.

    Supports:
        - X-API-Key header
        - Authorization: Bearer <token>
    """
    # Check X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key and api_key == PROXY_API_KEY:
        return True

    # Check Bearer token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split()[1]
        if token == PROXY_API_KEY:
            return True

    return False


# -----------------------------------------------------------------------------
# Schema Discovery Endpoints (NEW)
# -----------------------------------------------------------------------------

@app.get("/models")
async def list_models(request: Request):
    """
    Return a list of all available Odoo models (e.g., res.partner, sale.order).

    This endpoint is used by LangGraph agents to discover the data schema.
    It returns a list of model names and their human-readable labels.

    Authentication: Requires the same API key as /jsonrpc.
    """
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Build a JSON-RPC payload to call ir.model.search_read
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
                "ir.model",
                "search_read",
                [[["state", "=", "base"]]],  # domain: only base models, adjust as needed
                {"fields": ["model", "name", "info"], "limit": 200}
            ]
        },
        "id": 1
    }

    client = request.app.state.client
    odoo_endpoint = f"{ODOO_URL.rstrip('/')}/jsonrpc"

    try:
        response = await client.post(odoo_endpoint, json=payload)
        response.raise_for_status()
        result = response.json().get("result", [])
        return {"models": result}
    except httpx.HTTPStatusError as e:
        logger.error(f"Odoo error: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail="Odoo returned an error")
    except Exception as e:
        logger.exception("Error fetching models")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/{model_name}/fields")
async def get_model_fields(model_name: str, request: Request):
    """
    Return the fields, types, and relationships for a specific Odoo model.

    This endpoint is used by LangGraph agents to understand the structure of a model
    so they can build correct queries. It returns field names, types, required status,
    and selection options.

    Authentication: Requires the same API key as /jsonrpc.
    """
    if not await authenticate(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
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


# -----------------------------------------------------------------------------
# Main JSON-RPC Proxy Endpoint
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Simple health check for monitoring."""
    return {"status": "healthy", "service": "odoo-proxy"}


# -----------------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=3000,
        log_level="info",
    )