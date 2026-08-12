# =============================================================================
# FILE: src/core/odoo_proxy/mode.py
# =============================================================================
# PURPOSE:
#   Mode switching endpoints for the NETTRADES Launcher.
#   Supports Red/Yellow/Green operational modes for AI routing.
# =============================================================================

import logging
import json
import requests
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mode", tags=["operational_mode"])

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
    }
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
        _logger.warning("Redis package not installed - skipping cache write")
        return False
    except Exception as e:
        _logger.error(f"Error writing to Valkey: {e}")
        return False

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/update", response_model=ModeUpdateResponse)
async def update_mode(request: ModeUpdateRequest):
    """
    Update the operational mode.
    Writes the mode to Valkey for real-time routing.
    """
    mode = request.mode.lower()
    
    if mode not in MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}. Valid modes: red, yellow, green")

    # Write to Valkey for LangGraph to read in real-time
    cache_key = "nettrades:operational_mode"
    cache_value = json.dumps({
        "mode": mode,
        "config": MODES[mode],
        "updated_at": str(__import__('datetime').datetime.now())
    })

    if write_to_valkey(cache_key, cache_value):
        _logger.info(f"Operational mode updated to: {mode}")
        return ModeUpdateResponse(
            success=True,
            message=f"Mode updated to {mode.upper()}",
            mode=mode
        )
    else:
        # Still return success if Valkey write fails, but log the issue
        _logger.warning(f"Operational mode changed to {mode} but Valkey write failed")
        return ModeUpdateResponse(
            success=True,
            message=f"Mode updated to {mode.upper()} (Valkey cache not updated)",
            mode=mode
        )

@router.get("/status", response_model=ModeStatusResponse)
async def get_mode_status():
    """
    Get the current operational mode status.
    """
    # Try to read from Valkey first
    if VALKEY_HOST:
        try:
            import redis
            r = redis.Redis(host=VALKEY_HOST, port=VALKEY_PORT, decode_responses=True)
            value = r.get("nettrades:operational_mode")
            if value:
                data = json.loads(value)
                mode = data.get("mode", "red")
                return ModeStatusResponse(
                    mode=mode,
                    description=MODES[mode]["description"],
                    local_gpus=MODES[mode]["local_gpus"],
                    marketplace=MODES[mode]["marketplace"],
                    external_apis=MODES[mode]["external_apis"],
                    external_providers=MODES[mode]["external_providers"]
                )
        except Exception as e:
            _logger.warning(f"Error reading from Valkey: {e}")

    # Fallback: return default mode
    return ModeStatusResponse(
        mode="red",
        description=MODES["red"]["description"],
        local_gpus=True,
        marketplace=False,
        external_apis=False,
        external_providers=[]
    )

@router.get("/modes")
async def get_available_modes():
    """
    Get all available operational modes and their descriptions.
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
                    "❌ External APIs disabled"
                ]
            },
            {
                "id": "yellow",
                "label": "🟡 Hybrid Mode",
                "description": MODES["yellow"]["description"],
                "features": [
                    "✅ Local GPUs first",
                    "✅ GPU Marketplace fallback",
                    "❌ External APIs disabled"
                ]
            },
            {
                "id": "green",
                "label": "🟢 Cloud First",
                "description": MODES["green"]["description"],
                "features": [
                    "✅ Local GPUs first",
                    "✅ GPU Marketplace fallback",
                    "✅ External APIs (user-selectable)"
                ]
            }
        ]
    }