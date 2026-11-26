# -*- coding: utf-8 -*-
# FILE: src/core/routes/wireguard.py
"""WireGuard management endpoints (HTTP-proxy based).

FIX: The previous version read request.app.state.odoo_env, which is
never set in app.py's lifespan. Every endpoint returned HTTP 503.
This version uses the odoo-proxy HTTP JSON-RPC endpoint instead,
which works inside the LangGraph container without an Odoo environment.
"""

import os
import logging
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException, Header, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wireguard", tags=["wireguard"])

LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY")
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")


async def _odoo_proxy(model: str, method: str, args: list, kwargs: dict = None) -> Any:
    """Call Odoo via the HTTP JSON-RPC proxy."""
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.getenv("ODOO_DB", "odoo"),
                int(os.getenv("ODOO_USER", "1")),
                os.getenv("ODOO_PASSWORD", "admin"),
                model, method, args, kwargs or {},
            ],
        },
        "id": 1,
    }
    headers = {"X-API-Key": ODOO_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{ODOO_PROXY_URL}/jsonrpc", json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()
        if body.get("error"):
            raise HTTPException(status_code=502, detail=f"Odoo error: {body['error']}")
        return body.get("result")


async def authenticate_request(api_key: Optional[str]) -> bool:
    if not api_key:
        return False
    expected = os.getenv("LANGGRAPH_API_KEY")
    if not expected:
        return False
    return api_key == expected


@router.get("/status")
async def wireguard_status(x_api_key: Optional[str] = Header(None)):
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        # FIX (2026-10): list_peers takes no positional arguments, so
        # the outer args list must be empty. The previous version passed
        # [[]], which Odoo treated as list_peers([]) and raised TypeError.
        result = await _odoo_proxy(
            "nettrades.wireguard", "list_peers", [], {}
        )
        return {"status": "ok", "peers": result}
    except Exception as e:
        logger.error(f"WireGuard status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
async def wireguard_list_users(
    include_revoked: bool = False,
    x_api_key: Optional[str] = Header(None),
):
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        # FIX (2026-10): see wireguard_status.
        peers = await _odoo_proxy("nettrades.wireguard", "list_peers", [], {})
        return {"users": peers, "count": len(peers) if peers else 0}
    except Exception as e:
        logger.error(f"Failed to list WireGuard users: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users")
async def wireguard_create_user(
    body: Dict[str, Any],
    x_api_key: Optional[str] = Header(None),
):
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    partner_id = body.get('partner_id')
    name = body.get('name')
    if not partner_id or not name:
        raise HTTPException(status_code=400, detail="partner_id and name are required")
    try:
        # FIX (2026-10): add_peer(client_name, client_ip=None). The name
        # is the first positional argument, so args must be [name].
        # The previous version passed [[], name], which bound client_name
        # to the empty list and client_ip to the name string.
        result = await _odoo_proxy(
            "nettrades.wireguard", "add_peer", [name], {}
        )
        return result
    except Exception as e:
        logger.error(f"Failed to create WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}")
async def wireguard_revoke_user(
    user_id: int,
    x_api_key: Optional[str] = Header(None),
):
    if not await authenticate_request(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    try:
        # FIX (2026-10): remove_peer(client_name). args must be
        # [str(user_id)], not [[], str(user_id)].
        await _odoo_proxy("nettrades.wireguard", "remove_peer", [str(user_id)], {})
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to revoke WireGuard user: {e}")
        raise HTTPException(status_code=500, detail=str(e))