#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Odoo Tools (LLM Tool Interface)
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
#   - Schema discovery (list models, get fields) for dynamic query construction
#
# INTEGRATION:
#   This module now calls a dedicated Odoo JSON-RPC proxy service that
#   validates an API key. Fallback to direct Odoo JSON-RPC is also available.
#
# FIXES (2026-07-02):
#   - Converted all functions to async def with httpx.AsyncClient
#   - Removed duplicate res_partner_search stub
#   - Changed default proxy port from 3000 to 8080
#   - Added schema discovery endpoints and user impersonation support
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
async def _call_odoo_jsonrpc(payload: Dict[str, Any], uid: Optional[int] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Internal async function to call Odoo JSON-RPC either via proxy or directly.

    If uid and password are provided, they are injected into the payload's
    'args' list for execute_kw. The payload is expected to have:
    params.service = 'object', params.method = 'execute_kw',
    params.args = [db, uid, password, model, method, ...]

    This allows dynamic user impersonation.
    """
    # If uid/password are given, inject them into the args
    if uid is not None and password is not None:
        # Ensure the args list exists and is a list
        args = payload.get("params", {}).get("args", [])
        if len(args) >= 3:
            # args[0] = db, args[1] = uid, args[2] = password
            args[1] = uid
            args[2] = password
            payload["params"]["args"] = args
        else:
            _logger.warning("Payload args not structured as expected for user injection")

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
    # The execute_kw expects args = [db, uid, password, model, method, args, kwargs]
    # We'll fill db, uid, password later in _call_odoo_jsonrpc
    return {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, ODOO_USER, ODOO_PASSWORD, model, method, args, kwargs]
        }
    }


# -----------------------------------------------------------------------------
# Public Tool Functions (async)
# -----------------------------------------------------------------------------

# --- Schema Discovery Tools (NEW) ---

async def list_odoo_models(uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Discover all available Odoo models (e.g., res.partner, sale.order).

    This tool returns a list of model names and their human-readable labels.
    Used by the agent to understand the data landscape.

    Returns:
        List of dictionaries with keys: model (technical name), name (label), info (description)
    """
    # We need to call the proxy's /models endpoint
    # Since the proxy uses the same API key, we can use an HTTP GET
    headers = {"X-API-Key": ODOO_API_KEY}
    url = f"{ODOO_PROXY_URL}/models"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("models", [])
    except Exception as e:
        _logger.error(f"Failed to fetch models: {e}")
        # Fallback: return empty list or raise
        raise


async def get_model_fields(model_name: str, uid: Optional[int] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the field definitions for a specific Odoo model.

    Returns a dictionary mapping field names to their metadata:
        - type (char, integer, many2one, etc.)
        - string (label)
        - required (boolean)
        - selection (list of options for selection fields)
        - relation (related model for many2one/one2many)

    Args:
        model_name: Technical name of the model (e.g., 'res.partner')

    Returns:
        Dict of field definitions.
    """
    headers = {"X-API-Key": ODOO_API_KEY}
    url = f"{ODOO_PROXY_URL}/models/{model_name}/fields"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("fields", {})
    except Exception as e:
        _logger.error(f"Failed to fetch fields for {model_name}: {e}")
        raise


async def discover_schema(uid: Optional[int] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Discover the full schema: list of models and their fields.

    This is a convenience tool that returns both models and fields in one call.
    It can be used by the agent to get a complete picture.

    Returns:
        Dict with keys: 'models' (list) and 'fields' (dict mapping model_name -> fields)
    """
    models = await list_odoo_models(uid, password)
    all_fields = {}
    for m in models:
        model_name = m.get('model')
        if model_name:
            try:
                fields = await get_model_fields(model_name, uid, password)
                all_fields[model_name] = fields
            except Exception as e:
                _logger.warning(f"Could not fetch fields for {model_name}: {e}")
    return {"models": models, "fields": all_fields}


# -----------------------------------------------------------------------------
# Existing Tool Functions (updated to accept uid/password)
# -----------------------------------------------------------------------------

async def crm_lead_search(domain: List[Any], fields: List[str] = None, limit: int = 10,
                         uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for CRM leads by domain.

    Args:
        domain: Odoo domain list (e.g., [('stage_id','=',1)])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

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
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


async def hr_job_search(domain: List[Any], fields: List[str] = None, limit: int = 10,
                       uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for HR jobs.

    Args:
        domain: Odoo domain list (e.g., [('state','=','open')])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

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
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


async def res_partner_search(domain: List[Any], fields: List[str] = None, limit: int = 10,
                            uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for partners (users/companies).

    Args:
        domain: Odoo domain list (e.g., [('is_company','=',True)])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

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
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


async def gpu_node_read(node_id: int, uid: Optional[int] = None, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read a specific GPU node by ID.

    Args:
        node_id: ID of the GPU node
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

    Returns:
        Dictionary of node data, or None if not found
    """
    payload = _build_execute_payload(
        "gpu.node",
        "read",
        args=[[node_id]],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    records = result.get("result", [])
    return records[0] if records else None


async def gpu_node_write(node_id: int, values: Dict[str, Any],
                        uid: Optional[int] = None, password: Optional[str] = None) -> bool:
    """
    Update a GPU node record.

    Args:
        node_id: ID of the node to update
        values: Dictionary of field values to set
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

    Returns:
        True if successful
    """
    payload = _build_execute_payload(
        "gpu.node",
        "write",
        args=[[node_id], values],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", False)


async def gpu_node_create(values: Dict[str, Any],
                         uid: Optional[int] = None, password: Optional[str] = None) -> int:
    """
    Create a new GPU node.

    Args:
        values: Dictionary of field values for the new record
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

    Returns:
        ID of the created node, or 0 if failed
    """
    payload = _build_execute_payload(
        "gpu.node",
        "create",
        args=[values],
        kwargs={}
    )
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", 0)


async def gpu_node_search(domain: List[Any], fields: List[str] = None, limit: int = 10,
                         uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for GPU nodes.

    Args:
        domain: Odoo domain list (e.g., [('status','=','active')])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

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
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


async def gpu_cluster_search(domain: List[Any], fields: List[str] = None,
                            uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for GPU clusters.

    Args:
        domain: Odoo domain list (e.g., [('company_id','=',1)])
        fields: List of field names to return (None = all)
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

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
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


# -----------------------------------------------------------------------------
# Stub functions for missing Odoo methods (placeholder)
# These may be replaced later with real implementations.
# -----------------------------------------------------------------------------

async def project_search(name: str = None, limit: int = 10,
                        uid: Optional[int] = None, password: Optional[str] = None):
    """
    Stub for project_search. Implement real logic later.
    """
    _logger.warning("project_search is a stub - implement real logic.")
    return [{"id": 0, "name": name or "Project"}]


async def crm_lead_create(name: str, email: str = None, phone: str = None, description: str = None,
                         uid: Optional[int] = None, password: Optional[str] = None):
    """
    Stub for crm_lead_create. Implement real logic later.
    """
    _logger.warning("crm_lead_create is a stub - implement real logic.")
    return {"id": 0, "name": name, "email": email, "phone": phone, "description": description}

# =============================================================================
# END OF FILE
# =============================================================================

async def project_match_create(values: Dict[str, Any],
                              uid: Optional[int] = None, password: Optional[str] = None) -> int:
    """
    Create a project match record (nettrades.user.match) in Odoo.

    Args:
        values: dict with keys such as project_id, freelancer_id,
                match_score, suggested_rate, status.
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user
    Returns:
        The new record's integer ID, or -1 on failure.
    """
    payload = _build_execute_payload(
        model="nettrades.user.match",
        method="create",
        args=[values],
    )
    try:
        result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
        return int(result)
    except Exception as exc:
        _logger.error("project_match_create failed: %s", exc)
        return -1