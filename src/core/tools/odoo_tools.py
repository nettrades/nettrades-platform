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
#   This module now calls a dedicated Odoo JSON‑RPC proxy service that
#   validates an API key. Fallback to direct Odoo JSON‑RPC is also available.
#
# =============================================================================

import os
import logging
import json
import requests
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin

_logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:3000")
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

def _call_odoo_jsonrpc(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Internal function to call Odoo JSON-RPC either via proxy or directly.
    """
    if USE_PROXY:
        url = f"{ODOO_PROXY_URL}/jsonrpc"
        headers = {
            "X-API-Key": ODOO_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _logger.warning(f"Proxy call failed ({e}), falling back to direct Odoo JSON-RPC")
            # Fall through to direct call

    # Direct Odoo JSON-RPC
    url = f"{ODOO_DIRECT_URL}/jsonrpc"
    # For direct call, we need to include credentials in the params
    # The payload should already contain the 'params' with args[0] = db, args[1] = uid, args[2] = password
    # We'll just forward the payload as-is; the caller must include the credentials.
    # However, to simplify, we can auto-inject if the payload doesn't contain them.
    # But we assume the caller already includes them.
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        _logger.error(f"Direct Odoo JSON-RPC call failed: {e}")
        raise


def _build_execute_payload(model: str, method: str, args: List[Any], kwargs: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Build a JSON-RPC payload for executing a method on an Odoo model.

    Args:
        model: Odoo model name (e.g., 'res.partner')
        method: Method name (e.g., 'search_read')
        args: Positional arguments for the method
        kwargs: Keyword arguments for the method

    Returns:
        Dict: JSON-RPC payload ready for transmission.
    """
    if kwargs is None:
        kwargs = {}
    # The standard Odoo JSON-RPC format expects:
    # params: {
    #   service: 'object',
    #   method: 'execute_kw',
    #   args: [db, uid, password, model, method, args, kwargs]
    # }
    # We'll build the full args list; the caller must provide db, uid, password.
    # For simplicity, we assume the caller will fill in the credentials.
    # We'll just build the inner args list and let the caller wrap it.
    # Actually, we'll accept a partial payload and merge.
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, ODOO_USER, ODOO_PASSWORD, model, method] + args + [kwargs],
        },
        "id": 1,
    }
    # If the caller already provided credentials, they can override by passing them in args.
    # For simplicity, we use the environment variables.
    return payload


# -----------------------------------------------------------------------------
# Public Tool Functions
# -----------------------------------------------------------------------------

def crm_lead_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for CRM leads by domain.

    Args:
        domain: Odoo domain list, e.g., [('type', '=', 'opportunity')]
        fields: List of fields to return, e.g., ['id', 'name', 'partner_id']
        limit: Maximum number of records

    Returns:
        List of records as dictionaries.
    """
    if fields is None:
        fields = ['id', 'name', 'partner_id', 'email_from', 'phone', 'stage_id']
    payload = _build_execute_payload(
        model="crm.lead",
        method="search_read",
        args=[domain, fields],
        kwargs={"limit": limit},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


def hr_job_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for HR jobs.

    Args:
        domain: Odoo domain list
        fields: List of fields
        limit: Maximum number

    Returns:
        List of job records.
    """
    if fields is None:
        fields = ['id', 'name', 'company_id', 'department_id', 'no_of_recruitment']
    payload = _build_execute_payload(
        model="hr.job",
        method="search_read",
        args=[domain, fields],
        kwargs={"limit": limit},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


def res_partner_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for partners (companies or individuals).

    Args:
        domain: Odoo domain list
        fields: List of fields
        limit: Maximum number

    Returns:
        List of partner records.
    """
    if fields is None:
        fields = ['id', 'name', 'email', 'phone', 'company_type', 'is_company']
    payload = _build_execute_payload(
        model="res.partner",
        method="search_read",
        args=[domain, fields],
        kwargs={"limit": limit},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


def gpu_node_read(node_id: int) -> Optional[Dict[str, Any]]:
    """
    Read a specific GPU node by ID.

    Args:
        node_id: ID of the GPU node

    Returns:
        Record dictionary or None if not found.
    """
    payload = _build_execute_payload(
        model="gpu.node",
        method="read",
        args=[[node_id]],
        kwargs={},
    )
    result = _call_odoo_jsonrpc(payload)
    records = result.get("result", [])
    return records[0] if records else None


def gpu_node_write(node_id: int, values: Dict[str, Any]) -> bool:
    """
    Update a GPU node record.

    Args:
        node_id: ID of the GPU node
        values: Dictionary of field names and new values

    Returns:
        True if successful, False otherwise.
    """
    payload = _build_execute_payload(
        model="gpu.node",
        method="write",
        args=[[node_id], values],
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", False)


def gpu_node_create(values: Dict[str, Any]) -> int:
    """
    Create a new GPU node.

    Args:
        values: Dictionary of field names and values

    Returns:
        ID of the newly created record.
    """
    payload = _build_execute_payload(
        model="gpu.node",
        method="create",
        args=[values],
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", 0)


def gpu_node_search(domain: List[Any], fields: List[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for GPU nodes.

    Args:
        domain: Odoo domain list
        fields: List of fields
        limit: Maximum number

    Returns:
        List of GPU node records.
    """
    if fields is None:
        fields = ['id', 'name', 'node_id', 'status', 'hostname', 'cluster_id', 'gpus']
    payload = _build_execute_payload(
        model="gpu.node",
        method="search_read",
        args=[domain, fields],
        kwargs={"limit": limit},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


def gpu_cluster_search(domain: List[Any], fields: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search for GPU clusters.

    Args:
        domain: Odoo domain list
        fields: List of fields

    Returns:
        List of GPU cluster records.
    """
    if fields is None:
        fields = ['id', 'name', 'company_id', 'trust_mode', 'gpustack_server_url']
    payload = _build_execute_payload(
        model="gpu.cluster",
        method="search_read",
        args=[domain, fields],
        kwargs={},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


def ft_dataset_search(domain: List[Any], fields: List[str] = None) -> List[Dict[str, Any]]:
    """
    Search for fine-tuning datasets.

    Args:
        domain: Odoo domain list
        fields: List of fields

    Returns:
        List of dataset records.
    """
    if fields is None:
        fields = ['id', 'name', 'field_id', 'status', 'record_count', 'file_uri']
    payload = _build_execute_payload(
        model="ft.dataset",
        method="search_read",
        args=[domain, fields],
        kwargs={},
    )
    result = _call_odoo_jsonrpc(payload)
    return result.get("result", [])


# -----------------------------------------------------------------------------
# Generic Tool (for unhandled cases)
# -----------------------------------------------------------------------------

def call_odoo_generic(model: str, method: str, args: List[Any], kwargs: Dict[str, Any] = None) -> Any:
    """
    Generic Odoo RPC call for any model/method.

    WARNING: This is a powerful primitive; use with care.
    It is not recommended to expose this directly to LLMs without
    proper method allowlisting.

    Args:
        model: Odoo model name
        method: Method name (e.g., 'search', 'write', 'create', 'unlink')
        args: Positional arguments for the method
        kwargs: Keyword arguments

    Returns:
        Result of the RPC call.
    """
    if kwargs is None:
        kwargs = {}
    payload = _build_execute_payload(model, method, args, kwargs)
    result = _call_odoo_jsonrpc(payload)
    return result.get("result")