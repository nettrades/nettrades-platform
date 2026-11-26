# =============================================================================
# FILE: src/core/odoo_proxy/mode.py
# =============================================================================
# PURPOSE:
#   Mode switching endpoints for the NETTRADES Launcher.
#   Supports Red/Yellow/Green operational modes for AI routing.
#
# UPDATES (2026-10-22):
#   - Fixed BUG-019: replaced __import__('datetime').datetime.now() with a
#     normal top-level import and normal call.
#   - Fixed BUG-020: removed unused `import requests`.
#
# SECURITY FIX (2026-11-16):
#   - All three endpoints now require the same X-API-Key (or Bearer) that
#     /jsonrpc already enforces. Before this fix /mode/update was
#     unauthenticated, which meant any caller with network access to the
#     odoo-proxy could flip the platform from RED (100% sovereign) to
#     GREEN (external APIs enabled). That is a data-leakage vector, not
#     just a misconfiguration.
#
#   - Auth is implemented as a FastAPI dependency at module scope rather
#     than by importing `authenticate` from main.py. Importing from
#     main.py would create a circular import (main.py already imports
#     from mode.py to register the router). The dependency reads
#     PROXY_API_KEY at call time so a runtime re-read works if the
#     operator rotates the key without restarting the process.
# =============================================================================

import os
import hmac
import logging
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mode", tags=["operational_mode"])


# -----------------------------------------------------------------------------
# Auth dependency
# -----------------------------------------------------------------------------
# Mirrors main.py::authenticate's X-API-Key / Bearer logic, but without
# the rate limiter (which is only relevant at the JSON-RPC boundary, not
# for admin mode toggles). Fails closed: if PROXY_API_KEY is not
# configured, every request is refused with 503 rather than allowed.
# -----------------------------------------------------------------------------
async def _require_auth(request: Request) -> None:
    expected = os.getenv("PROXY_API_KEY", "")
    if not expected:
        _logger.error(
            "PROXY_API_KEY is not set — refusing /mode/* request. "
            "Set PROXY_API_KEY in the odoo-proxy environment."
        )
        raise HTTPException(
            status_code=503,
            detail="Proxy authentication is not configured",
        )

    api_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization", "")

    if api_key and hmac.compare_digest(api_key, expected):
        return
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        if hmac.compare_digest(token, expected):
            return

    _logger.warning(
        "Rejected /mode/* request: invalid or missing credentials "
        "(client=%s)",
        request.client.host if request.client else "unknown",
    )
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class ModeUpdateRequest(BaseModel):
    mode: str  # 'red', 'yellow', 'green'


class ModeUpdateResponse(BaseModel):
    success: bool
    message: str
    mode: str = None


class ModeStatusResponse(BaseModel):
    mode: str
    description: str
    local_gpus: bool
    marketplace: bool
    external_apis: bool
    external_providers: list = []


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

ODOO_URL = None
ODOO_API_KEY = None
VALKEY_HOST = None
VALKEY_PORT = 6379


def init_mode(odoo_url: str, odoo_api_key: str, valkey_host: str = None, valkey_port: int = 6379):
    """Initialize mode switching with Odoo and Valkey."""
    global ODOO_URL, ODOO_API_KEY, VALKEY_HOST, VALKEY_PORT
    ODOO_URL = odoo_url
    ODOO_API_KEY = odoo_api_key
    VALKEY_HOST = valkey_host
    VALKEY_PORT = valkey_port
    _logger.info("Mode switching module initialized")


# -----------------------------------------------------------------------------
# Mode Definitions
# -----------------------------------------------------------------------------

MODES = {
    "red": {
        "description": "100% Sovereign AI - All inference runs on local GPUs. Data never leaves your network.",
        "local_gpus": True,
        "marketplace": False,
        "external_apis": False,
        "external_providers": [],
    },
    "yellow": {
        "description": "Hybrid Mode - Local first. Use GPU marketplace when local capacity is exceeded.",
        "local_gpus": True,
        "marketplace": True,
        "external_apis": False,
        "external_providers": [],
    },
    "green": {
        "description": "Cloud First - Local GPUs → GPU Marketplace → External APIs (user-selectable).",
        "local_gpus": True,
        "marketplace": True,
        "external_apis": True,
        "external_providers": ["openai", "anthropic"],
    },
}


# -----------------------------------------------------------------------------
# Helper: Write to Valkey
# -----------------------------------------------------------------------------

def write_to_valkey(key: str, value: str) -> bool:
    """Write a value to Valkey cache."""
    if not VALKEY_HOST:
        _logger.warning("Valkey not configured - skipping cache write")
        return False

    try:
        import redis
        r = redis.Redis(host=VALKEY_HOST, port=VALKEY_PORT, decode_responses=True)
        r.set(key, value)
        _logger.info(f"Wrote to Valkey: {key}={value}")
        return True
    except ImportError:
        # Gracefully handle missing redis package
        _logger.warning("Redis package not installed - skipping cache write")
        _logger.warning("Install redis: pip install redis")
        return False
    except Exception as e:
        _logger.error(f"Error writing to Valkey: {e}")
        return False


# -----------------------------------------------------------------------------
# Helper: Read from Valkey
# -----------------------------------------------------------------------------

def read_from_valkey(key: str) -> dict:
    """Read a value from Valkey cache."""
    if not VALKEY_HOST:
        return None

    try:
        import redis
        r = redis.Redis(host=VALKEY_HOST, port=VALKEY_PORT, decode_responses=True)
        value = r.get(key)
        if value:
            return json.loads(value)
        return None
    except ImportError:
        # Gracefully handle missing redis package
        _logger.warning("Redis package not installed - skipping cache read")
        _logger.warning("Install redis: pip install redis")
        return None
    except Exception as e:
        _logger.warning(f"Error reading from Valkey: {e}")
        return None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post(
    "/update",
    response_model=ModeUpdateResponse,
    dependencies=[Depends(_require_auth)],
)
async def update_mode(request: ModeUpdateRequest):
    """
    Update the operational mode.
    Writes the mode to Valkey for real-time routing.

    Requires the same X-API-Key (or Bearer token) as /jsonrpc.
    """
    mode = request.mode.lower()

    if mode not in MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Valid modes: red, yellow, green",
        )

    # Write to Valkey for LangGraph to read in real-time
    cache_key = "nettrades:operational_mode"
    cache_value = json.dumps({
        "mode": mode,
        "config": MODES[mode],
        "updated_at": datetime.now().isoformat(),
    })

    if write_to_valkey(cache_key, cache_value):
        _logger.info(f"Operational mode updated to: {mode}")
        return ModeUpdateResponse(
            success=True,
            message=f"Mode updated to {mode.upper()}",
            mode=mode,
        )
    else:
        # Still return success if Valkey write fails, but log the issue
        _logger.warning(f"Operational mode changed to {mode} but Valkey write failed")
        return ModeUpdateResponse(
            success=True,
            message=f"Mode updated to {mode.upper()} (Valkey cache not updated)",
            mode=mode,
        )


@router.get(
    "/status",
    response_model=ModeStatusResponse,
    dependencies=[Depends(_require_auth)],
)
async def get_mode_status():
    """
    Get the current operational mode status.

    Requires the same X-API-Key (or Bearer token) as /jsonrpc.
    """
    cache_key = "nettrades:operational_mode"
    cached_data = read_from_valkey(cache_key)

    if cached_data:
        mode = cached_data.get("mode", "red")
        return ModeStatusResponse(
            mode=mode,
            description=MODES[mode]["description"],
            local_gpus=MODES[mode]["local_gpus"],
            marketplace=MODES[mode]["marketplace"],
            external_apis=MODES[mode]["external_apis"],
            external_providers=MODES[mode]["external_providers"],
        )

    # Fallback: return default mode
    return ModeStatusResponse(
        mode="red",
        description=MODES["red"]["description"],
        local_gpus=True,
        marketplace=False,
        external_apis=False,
        external_providers=[],
    )


@router.get(
    "/modes",
    dependencies=[Depends(_require_auth)],
)
async def get_available_modes():
    """
    Get all available operational modes and their descriptions.

    Requires the same X-API-Key (or Bearer token) as /jsonrpc.
    """
    return {
        "modes": [
            {
                "id": "red",
                "label": "🔴 100% Sovereign AI",
                "description": MODES["red"]["description"],
                "features": [
                    "✅ All requests to local GPUs",
                    "❌ GPU Marketplace disabled",
                    "❌ External APIs disabled",
                ],
            },
            {
                "id": "yellow",
                "label": "🟡 Hybrid Mode",
                "description": MODES["yellow"]["description"],
                "features": [
                    "✅ Local GPUs first",
                    "✅ GPU Marketplace fallback",
                    "❌ External APIs disabled",
                ],
            },
            {
                "id": "green",
                "label": "🟢 Cloud First",
                "description": MODES["green"]["description"],
                "features": [
                    "✅ Local GPUs first",
                    "✅ GPU Marketplace fallback",
                    "✅ External APIs (user-selectable)",
                ],
            },
        ]
    }