# -*- coding: utf-8 -*-
"""WireGuard management endpoints."""

import os
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Header, Request, Response

from tools.wireguard_manager import WireGuardManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wireguard", tags=["wireguard"])


async def authenticate_request(api_key: Optional[str]) -> bool:
    """Authenticate a request using the API key."""
    if not api_key:
        return False
    expected_key = os.getenv("LANGGRAPH_API_KEY")
    if not expected_key:
        logger.warning("LANGGRAPH_API_KEY not configured")
        return False
    return api_key == expected_key


@router.get("/status")
async def wireguard_status(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """Get the status of the WireGuard VPN server."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    status = WireGuardManager.get_server_status()
    return status


@router.get("/users")
async def wireguard_list_users(
    request: Request,
    include_revoked: bool = False,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """List all WireGuard VPN users (peers)."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")
        users = WireGuardManager.list_peers(odoo_env, include_revoked)
        return {"users": users, "count": len(users)}
    except Exception as e:
        logger.error(f"Failed to list WireGuard users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users")
async def wireguard_create_user(
    request: Request,
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """Create a new WireGuard VPN user."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    partner_id = body.get('partner_id')
    name = body.get('name')
    if not partner_id or not name:
        raise HTTPException(status_code=400, detail="partner_id and name are required")
    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")
        peer = WireGuardManager.create_peer(partner_id, name, odoo_env)
        return peer
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
async def wireguard_revoke_user(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """Revoke a WireGuard VPN user."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")
        success = WireGuardManager.revoke_peer(user_id, odoo_env)
        if not success:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to revoke WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/config")
async def wireguard_get_config(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """Get the WireGuard configuration file for a user."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")
        config = WireGuardManager.get_peer_config(user_id, odoo_env)
        if not config:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        return Response(
            content=config,
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=wg-{user_id}.conf"
            }
        )
    except Exception as e:
        logger.error(f"Failed to get WireGuard config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/qrcode")
async def wireguard_get_qrcode(
    user_id: int,
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """Get a QR code for the WireGuard configuration of a user."""
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        odoo_env = request.app.state.odoo_env
        if not odoo_env:
            raise HTTPException(status_code=503, detail="Odoo environment not available")
        qr_code = WireGuardManager.get_peer_qr_code(user_id, odoo_env)
        if not qr_code:
            raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
        return {"qr_code": qr_code}
    except Exception as e:
        logger.error(f"Failed to generate QR code: {e}")
        raise HTTPException(status_code=500, detail=str(e))