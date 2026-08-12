# =============================================================================
# FILE: src/core/odoo_proxy/auth.py
# =============================================================================
# PURPOSE:
#   Authentication endpoints for the NETTRADES Launcher.
#   Provides login/logout functionality via Odoo's authentication system.
# =============================================================================

import logging
import json
import requests
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

ODOO_URL = None
ODOO_DB = None
ODOO_USER = None
ODOO_PASSWORD = None

def init_auth(odoo_url: str, odoo_db: str, odoo_user: int, odoo_password: str):
    """Initialize authentication with Odoo credentials."""
    global ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD
    ODOO_URL = odoo_url
    ODOO_DB = odoo_db
    ODOO_USER = odoo_user
    ODOO_PASSWORD = odoo_password
    _logger.info("Authentication module initialized")

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate a user against Odoo.
    Returns a session token if successful.
    """
    if not ODOO_URL:
        raise HTTPException(status_code=503, detail="Odoo not configured")

    try:
        # Authenticate with Odoo JSON-RPC
        auth_payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "common",
                "method": "login",
                "args": [ODOO_DB, request.username, request.password]
            },
            "id": 1
        }

        response = requests.post(
            f"{ODOO_URL}/jsonrpc",
            json=auth_payload,
            timeout=10
        )

        if response.status_code != 200:
            _logger.error(f"Odoo auth error: {response.status_code}")
            raise HTTPException(status_code=503, detail="Odoo service unavailable")

        result = response.json()
        if result.get("error"):
            _logger.warning(f"Login failed for user {request.username}: {result['error']}")
            raise HTTPException(status_code=401, detail="Invalid username or password")

        user_id = result.get("result")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        # Generate a session token (in production, use JWT or secure session)
        import uuid
        session_id = str(uuid.uuid4())

        # Store session in memory (in production, use Redis or Valkey)
        # For now, we just return the session ID
        _logger.info(f"User {request.username} logged in successfully (ID: {user_id})")

        return LoginResponse(
            success=True,
            message="Login successful",
            session_id=session_id,
            user_id=user_id,
            username=request.username
        )

    except requests.exceptions.ConnectionError:
        _logger.error("Connection error to Odoo")
        raise HTTPException(status_code=503, detail="Cannot connect to Odoo")
    except Exception as e:
        _logger.error(f"Unexpected error during login: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/logout")
async def logout(request: Request):
    """
    Logout a user by invalidating their session.
    """
    # In production, invalidate the session token
    _logger.info("User logged out")
    return {"success": True, "message": "Logout successful"}

@router.get("/status")
async def status(request: Request):
    """
    Check if the user is authenticated.
    """
    # In production, validate the session token
    return {"authenticated": False, "message": "Not authenticated"}