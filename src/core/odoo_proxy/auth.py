# =============================================================================
# FILE: src/core/odoo_proxy/auth.py
# =============================================================================
# PURPOSE:
#   Authentication endpoints for the NETTRADES Launcher.
#   Provides login/logout functionality via Odoo's authentication system.
#
# SESSION STORAGE (BUG-002 FIX):
#   Sessions are persisted in Valkey with a 24-hour TTL. This fixes
#   BUG-002, where the previous in-memory approach lost the session on
#   every container restart and made /auth/status always return
#   authenticated: False.
#
#   If Valkey is not reachable (VALKEY_HOST not set, or connection
#   failed), the module falls back to in-process storage. This keeps
#   local development working without Valkey, at the cost of sessions
#   not surviving a restart. The fallback is logged once at startup.
# =============================================================================

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import requests
import redis
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    session_id: str = None
    user_id: int = None
    username: str = None

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

ODOO_URL: Optional[str] = None
ODOO_DB: Optional[str] = None
ODOO_USER: Optional[int] = None
ODOO_PASSWORD: Optional[str] = None

# Valkey client. None when Valkey is not configured or unreachable.
_valkey_client: Optional[redis.Redis] = None

# In-process fallback for development without Valkey. Keyed by session_id.
# Not intended for production; sessions do not survive a restart.
_fallback_sessions: dict = {}

# Session lifetime. 24 hours is a reasonable default for a launcher
# used by an individual; enterprise deployments may want to shorten it.
SESSION_TTL = timedelta(hours=24)

# Valkey key prefix.
KEY_PREFIX = "nettrades:session:"


def init_auth(
    odoo_url: str,
    odoo_db: str,
    odoo_user: int,
    odoo_password: str,
    valkey_host: Optional[str] = None,
    valkey_port: int = 6379,
):
    """
    Initialise the authentication module.

    Args:
        odoo_url: The URL of the Odoo service (used to call common.login).
        odoo_db: The database name.
        odoo_user: The default internal user UID (used as a fallback).
        odoo_password: The default password (used as a fallback).
        valkey_host: Optional Valkey host. When provided, sessions are
            persisted in Valkey. When None, falls back to in-process
            storage (development only).
        valkey_port: Valkey port (default 6379).
    """
    global ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, _valkey_client
    ODOO_URL = odoo_url
    ODOO_DB = odoo_db
    ODOO_USER = odoo_user
    ODOO_PASSWORD = odoo_password

    # Try to connect to Valkey if a host was provided.
    if valkey_host:
        try:
            client = redis.Redis(
                host=valkey_host,
                port=valkey_port,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            _valkey_client = client
            _logger.info(
                "Authentication module initialised with Valkey at %s:%s",
                valkey_host, valkey_port,
            )
        except Exception as e:
            _logger.warning(
                "Valkey not available at %s:%s (%s). "
                "Sessions will not persist across restarts.",
                valkey_host, valkey_port, e,
            )
            _valkey_client = None
    else:
        _logger.info(
            "Authentication module initialised without Valkey. "
            "Sessions will not persist across restarts."
        )
        _valkey_client = None


# -----------------------------------------------------------------------------
# Session storage helpers
# -----------------------------------------------------------------------------

def _session_key(session_id: str) -> str:
    return f"{KEY_PREFIX}{session_id}"


def _store_session(session_id: str, data: dict) -> None:
    """Persist a session, using Valkey when available."""
    if _valkey_client is not None:
        try:
            _valkey_client.setex(
                _session_key(session_id),
                SESSION_TTL,
                json.dumps(data),
            )
            return
        except Exception as e:
            _logger.warning("Failed to store session in Valkey: %s", e)
            # Fall through to the in-process fallback so the login
            # does not fail outright.
    _fallback_sessions[session_id] = data


def _get_session(session_id: str) -> Optional[dict]:
    """Retrieve a session, preferring Valkey."""
    if _valkey_client is not None:
        try:
            raw = _valkey_client.get(_session_key(session_id))
            if raw:
                return json.loads(raw)
        except Exception as e:
            _logger.warning("Failed to read session from Valkey: %s", e)
    return _fallback_sessions.get(session_id)


def _delete_session(session_id: str) -> None:
    """Delete a session from both stores."""
    if _valkey_client is not None:
        try:
            _valkey_client.delete(_session_key(session_id))
        except Exception as e:
            _logger.warning("Failed to delete session from Valkey: %s", e)
    _fallback_sessions.pop(session_id, None)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate a user against Odoo.

    Calls Odoo's common.login (JSON-RPC) and, on success, creates a
    session record persisted in Valkey.
    """
    if not ODOO_URL:
        raise HTTPException(status_code=503, detail="Odoo not configured")

    try:
        auth_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "login",
                "args": [ODOO_DB, request.username, request.password],
            },
            "id": 1,
        }

        response = requests.post(
            f"{ODOO_URL}/jsonrpc",
            json=auth_payload,
            timeout=10,
        )

        if response.status_code != 200:
            _logger.error(f"Odoo auth error: {response.status_code}")
            raise HTTPException(status_code=503, detail="Odoo service unavailable")

        result = response.json()
        if result.get("error"):
            _logger.warning(
                "Login failed for user %s: %s",
                request.username, result["error"],
            )
            raise HTTPException(status_code=401, detail="Invalid username or password")

        user_id = result.get("result")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Create a session and persist it.
        session_id = str(uuid.uuid4())
        session_data = {
            "user_id": user_id,
            "username": request.username,
            "created_at": datetime.utcnow().isoformat(),
        }
        _store_session(session_id, session_data)

        _logger.info(
            "User %s logged in successfully (ID: %s)",
            request.username, user_id,
        )

        return LoginResponse(
            success=True,
            message="Login successful",
            session_id=session_id,
            user_id=user_id,
            username=request.username,
        )

    except requests.exceptions.ConnectionError:
        _logger.error("Connection error to Odoo")
        raise HTTPException(status_code=503, detail="Cannot connect to Odoo")
    except HTTPException:
        raise
    except Exception as e:
        _logger.error(f"Unexpected error during login: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/logout")
async def logout(request: Request):
    """
    Logout a user by deleting their session.

    The session_id is read from the X-Session-ID header. Missing or
    invalid session IDs are treated as a successful no-op.
    """
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        _delete_session(session_id)
        _logger.info("Session %s deleted", session_id)
    return {"success": True, "message": "Logout successful"}


@router.get("/status")
async def status(request: Request):
    """
    Check whether the caller's session is valid.

    Reads the X-Session-ID header and looks up the session in Valkey
    (or the in-process fallback). Returns authenticated: False when the
    session is missing or expired.
    """
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        return {"authenticated": False, "message": "No session ID provided"}

    data = _get_session(session_id)
    if not data:
        return {"authenticated": False, "message": "Session expired or invalid"}

    return {
        "authenticated": True,
        "user_id": data.get("user_id"),
        "username": data.get("username"),
    }