#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Odoo Tools (LLM Tool Interface)
# =============================================================================
# FILE: src/core/tools/odoo_tools.py
#
# PURPOSE:
#   Provides a set of tool functions for LangGraph agents to interact with
#   Odoo data (CRM leads, HR jobs, GPU nodes, freelancers, etc.).
#
# KEY FEATURES:
#   - Search/read Odoo models via JSON-RPC
#   - Create/update records
#   - GPU node registration
#   - Token usage tracking
#
# INTEGRATION:
#   This module now calls a dedicated Odoo JSON-RPC proxy service that
#   validates an API key. Fallback to direct Odoo JSON-RPC is also available.
#
# FIXES (2026-07-02):
#   - Converted all functions to async def with httpx.AsyncClient
#   - Removed duplicate res_partner_search stub
#   - Changed default proxy port from 3000 to 8080
# =============================================================================

import os
import logging
import json
import httpx
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

_logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")  # FIXED: changed from :3000 to :8080
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "change_me_in_production")
# Fallback direct Odoo URL (if proxy is down)
ODOO_DIRECT_URL = os.getenv("ODOO_DIRECT_URL", "http://odoo:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USER = os.getenv("ODOO_USER", 1)
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")
# Use proxy by default; fallback to direct if proxy fails
USE_PROXY = os.getenv("USE_ODOO_PROXY", "true").lower() == "true"


# -----------------------------------------------------------------------------
# Internal Helpers
# -----------------------------------------------------------------------------
async def _call_odoo_jsonrpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Internal async function to call Odoo JSON-RPC either via proxy or directly.
    """
    if USE_PROXY:
        url = f"{ODOO_PROXY_URL}/jsonrpc"
        # For direct call, we need to include credentials in the params
        # The payload should already contain the 'params' with args[0] = db, args[1] = uid, args[2] = password
        # We'll just forward the payload as-is; the caller must include the credentials.
        # However, to simplify, we can auto-inject if the payload doesn't contain them.
        # But we assume the caller already includes them.
        headers = {
            "X-API-Key": ODOO_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _logger.warning(f"Proxy call failed ({e}), falling back to direct Odoo JSON-RPC")
            # Fall through to direct call

    # Direct Odoo JSON-RPC
    url = f"{ODOO_DIRECT_URL}/jsonrpc"
    headers = {"Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        _logger.error(f"Direct Odoo JSON-RPC call failed: {e}")
        raise


def _build_execute_payload(model: str, method: str, args: List[Any], kwargs: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Build a JSON-RPC payload for executing a method on an Odoo model.

    Args:
        model: Odoo model name (e.g., 'hr.job')
        method: Odoo method name (e.g., 'search_read')
        args: Positional arguments for the method
        kwargs: Keyword arguments for the method

    Returns:
        Dict containing the JSON-RPC payload
    """
    if kwargs is None:
        kwargs = {}
    return {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [model, method, args, kwargs]
        }
    }


# -----------------------------------------------------------------------------
# Public Tool Functions (async)
# -----------------------------------------------------------------------------

async def crm_lead_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for CRM leads by domain.

    Args:
        domain: Odoo domain list (e.g., [('stage_id','=',1)])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return

    Returns:
        List of lead dictionaries
    """
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "crm.lead",
        "search_read",
        args=[domain],
        kwargs={"fields": fields, "limit": limit}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", [])


async def hr_job_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for HR jobs.

    Args:
        domain: Odoo domain list (e.g., [('state','=','open')])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return

    Returns:
        List of job dictionaries
    """
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "hr.job",
        "search_read",
        args=[domain],
        kwargs={"fields": fields, "limit": limit}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", [])


async def res_partner_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for partners (users/companies).

    Args:
        domain: Odoo domain list (e.g., [('is_company','=',True)])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return

    Returns:
        List of partner dictionaries
    """
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "res.partner",
        "search_read",
        args=[domain],
        kwargs={"fields": fields, "limit": limit}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", [])


async def gpu_node_read(node_id: int) -> Optional[Dict[str, Any]]:
    """
    Read a specific GPU node by ID.

    Args:
        node_id: ID of the GPU node

    Returns:
        Dictionary of node data, or None if not found
    """
    payload = _build_execute_payload(
        "gpu.node",
        "read",
        args=[[node_id]],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload)
    records = result.get("result", [])
    return records[0] if records else None


async def gpu_node_write(node_id: int, values: Dict[str, Any]) -> bool:
    """
    Update a GPU node record.

    Args:
        node_id: ID of the node to update
        values: Dictionary of field values to set

    Returns:
        True if successful
    """
    payload = _build_execute_payload(
        "gpu.node",
        "write",
        args=[[node_id], values],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", False)


async def gpu_node_create(values: Dict[str, Any]) -> int:
    """
    Create a new GPU node.

    Args:
        values: Dictionary of field values for the new record

    Returns:
        ID of the created node, or 0 if failed
    """
    payload = _build_execute_payload(
        "gpu.node",
        "create",
        args=[values],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", 0)


async def gpu_node_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for GPU nodes.

    Args:
        domain: Odoo domain list (e.g., [('status','=','active')])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return

    Returns:
        List of node dictionaries
    """
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "gpu.node",
        "search_read",
        args=[domain],
        kwargs={"fields": fields, "limit": limit}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", [])


async def gpu_cluster_search(domain: List[Any], fields: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search for GPU clusters.

    Args:
        domain: Odoo domain list (e.g., [('company_id','=',1)])
        fields: List of field names to return (None = all)

    Returns:
        List of cluster dictionaries
    """
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "gpu.cluster",
        "search_read",
        args=[domain],
        kwargs={"fields": fields}
    )
    result = await _call_odoo_jsonrpc(payload)
    return result.get("result", [])


# -----------------------------------------------------------------------------
# Stub functions for missing Odoo methods (placeholder)
# These may be replaced later with real implementations.
# -----------------------------------------------------------------------------

async def project_search(name: str = None, limit: int = 10):
    """
    Stub for project_search. Implement real logic later.
    """
    _logger.warning("project_search is a stub – implement real logic.")
    return [{"id": 0, "name": name or "Project"}]


async def crm_lead_create(name: str, email: str = None, phone: str = None, description: str = None):
    """
    Stub for crm_lead_create. Implement real logic later.
    """
    _logger.warning("crm_lead_create is a stub – implement real logic.")
    return {"id": 0, "name": name, "email": email, "phone": phone, "description": description}

# =============================================================================
# END OF FILE
# =============================================================================