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
#
# UPDATES (2026-08-04):
#   - Corrected model names in Ask Someone, Good Answer, and GPU helpers
#     to match actual Odoo module definitions:
#       * expert.session          (was nettrades_ask_someone.request)
#       * qualified_professional  (was nettrades_ask_someone.expert)
#       * llm_feedback            (was nettrades_good_answer.answer / .best_answer)
#       * gpu.node                (was nettrades_gpu_admin.node)
#       * gpu_sharing_schedule    (was nettrades_gpu_admin.booking)
# =============================================================================

import datetime
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
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
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
            "args": [ODOO_DB, ODOO_USER, ODOO_PASSWORD, model, method, args, kwargs]
        }
    }


# -----------------------------------------------------------------------------
# Convenience Odoo CRUD wrappers
# -----------------------------------------------------------------------------
async def odoo_search(model: str, domain: List[Any], fields: Optional[List[str]] = None,
                      limit: Optional[int] = None, offset: Optional[int] = None,
                      order: Optional[str] = None, uid: Optional[int] = None,
                      password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Perform a search_read on an Odoo model.
    """
    kwargs = {}
    if fields:
        kwargs['fields'] = fields
    if limit is not None:
        kwargs['limit'] = limit
    if offset is not None:
        kwargs['offset'] = offset
    if order:
        kwargs['order'] = order
    payload = _build_execute_payload(model, 'search_read', [domain], kwargs)
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get('result', [])


async def odoo_create(model: str, values: Dict[str, Any],
                      uid: Optional[int] = None, password: Optional[str] = None) -> int:
    """
    Create a new record in an Odoo model.
    """
    payload = _build_execute_payload(model, 'create', [values])
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get('result', 0)


async def odoo_write(model: str, ids: List[int], values: Dict[str, Any],
                     uid: Optional[int] = None, password: Optional[str] = None) -> bool:
    """
    Update records in an Odoo model.
    """
    payload = _build_execute_payload(model, 'write', [ids, values])
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get('result', False)


async def odoo_call_method(
    model: str,
    method: str,
    args: List[Any] = None,
    kwargs: Dict[str, Any] = None,
    uid: Optional[int] = None,
    password: Optional[str] = None,
) -> Any:
    """
    Call any custom method on an Odoo model via JSON-RPC.

    This is a generic method caller that wraps _call_odoo_jsonrpc.
    Used by agents to invoke custom Odoo methods (e.g., from nettrades modules).
    """
    args = args or []
    kwargs = kwargs or {}

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                ODOO_DB,
                uid or ODOO_USER,
                password or ODOO_PASSWORD,
                model,
                method,
                args,
                kwargs,
            ],
        },
        "id": None,
    }

    result = await _call_odoo_jsonrpc(payload, uid, password)

    if result and isinstance(result, dict) and "result" in result:
        return result["result"]
    return result


# -----------------------------------------------------------------------------
# Public Tool Functions (async)
# -----------------------------------------------------------------------------

# --- Schema Discovery Tools ---

async def list_odoo_models(uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Discover all available Odoo models.

    Returns:
        List of dictionaries with keys: model (technical name), name (label), info (description)
    """
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
        raise


async def get_model_fields(model_name: str, uid: Optional[int] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Get the field definitions for a specific Odoo model.
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


# --- GPU Node Functions ---

async def gpu_node_read(node_id: int, uid: Optional[int] = None, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Read a specific GPU node by ID.
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
# Implemented Functions (previously stubs)
# -----------------------------------------------------------------------------

async def project_search(domain: List[Any] = None, fields: List[str] = None, limit: int = 10,
                         uid: Optional[int] = None, password: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search for projects in Odoo.

    Args:
        domain: Odoo domain list (e.g., [('state','=','open')])
        fields: List of field names to return (None = all)
        limit: Maximum number of records to return
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

    Returns:
        List of project dictionaries
    """
    if domain is None:
        domain = []
    if fields is None:
        fields = []
    payload = _build_execute_payload(
        "project.project",
        "search_read",
        args=[domain],
        kwargs={"fields": fields, "limit": limit}
    )
    result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
    return result.get("result", [])


async def crm_lead_create(values: Dict[str, Any],
                          uid: Optional[int] = None, password: Optional[str] = None) -> int:
    """
    Create a new CRM lead in Odoo.

    Args:
        values: Dictionary of field values for the new lead (name, description, etc.)
        uid: Optional Odoo user ID for permission enforcement
        password: Optional Odoo password for the user

    Returns:
        int: The ID of the created lead, or 0 if failed
    """
    payload = _build_execute_payload(
        "crm.lead",
        "create",
        args=[values],
        kwargs={}
    )
    try:
        result = await _call_odoo_jsonrpc(payload, uid=uid, password=password)
        return result.get("result", 0)
    except Exception as e:
        _logger.error(f"crm_lead_create failed: {e}")
        return 0


# =============================================================================
# PROJECT MATCH HELPER
# =============================================================================

async def project_match_create(values: Dict[str, Any],
                              uid: Optional[int] = None, password: Optional[str] = None) -> int:
    """
    Create a project match record in Odoo.

    Note: The model 'nettrades.user.match' must exist in Odoo.
    If it doesn't exist, you may need to create it or use an alternative model.

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


# =============================================================================
# UPDATED ASK SOMEONE HELPER FUNCTIONS (using actual Odoo models)
# =============================================================================

async def ask_someone_create_request(
    question: str,
    field_id: int,                       # ID of the professional field (nettrades_field)
    requester_id: int,
    urgency: str = "normal",             # low, normal, high, critical
    expert_id: Optional[int] = None,
) -> int:
    """
    Create a new Ask Someone expert session in Odoo.

    This creates an 'expert.session' record that tracks the requester,
    the selected professional field, the question/task summary, and status.

    Args:
        question: The user's question or task description
        field_id: The ID of the professional field (nettrades_field)
        requester_id: The ID of the user asking the question
        urgency: Urgency level (low, normal, high, critical)
        expert_id: Optional specific expert to route to (if known)

    Returns:
        int: The ID of the created expert.session
    """
    values = {
        "requester_id": requester_id,
        "field_id": field_id,
        "task_summary": question,
        "urgency": urgency,
        "status": "pending",
        "created_date": datetime.datetime.now().isoformat(),
    }
    if expert_id:
        values["expert_id"] = expert_id

    return await odoo_create("expert.session", values)


async def ask_someone_get_experts(field_id: Optional[int] = None) -> List[Dict]:
    """
    Get available verified professionals from Odoo.

    This queries the 'qualified_professional' model which stores
    verified experts for restricted fields.

    Args:
        field_id: Filter by professional field (optional)

    Returns:
        List[Dict]: List of qualified professional records
    """
    domain = [("is_verified", "=", True)]
    if field_id:
        domain.append(("field_id", "=", field_id))

    return await odoo_search(
        "qualified_professional",
        domain,
        ["id", "partner_id", "field_id", "reputation_score", "is_available"],
    )


# =============================================================================
# UPDATED GOOD ANSWER HELPER FUNCTIONS (using llm_feedback & good_answer_vote)
# =============================================================================

async def good_answer_create_vote(
    message_id: int,
    user_id: int,
    is_good: bool = True,
) -> int:
    """
    Record a "Good Answer" vote on an AI message.

    This creates a 'good_answer_vote' record linked to the llm.message.

    Args:
        message_id: The ID of the llm.message being voted on
        user_id: The ID of the user voting
        is_good: True for "Good Answer", False for "Bad Answer"

    Returns:
        int: The ID of the created good_answer_vote
    """
    vote_type = "positive" if is_good else "negative"
    return await odoo_create(
        "good_answer_vote",
        {
            "message_id": message_id,
            "user_id": user_id,
            "vote_type": vote_type,
        },
    )


async def good_answer_get_best_answer(question: str) -> Optional[Dict]:
    """
    Get the highest-quality answer for a question from llm_feedback records.

    Args:
        question: The question text to search for

    Returns:
        Optional[Dict]: The best answer record, or None
    """
    feedbacks = await odoo_search(
        "llm_feedback",
        [("question", "ilike", question[:100])],
        ["id", "answer", "quality_score", "is_verified"],
        order="quality_score DESC",
        limit=1,
    )
    return feedbacks[0] if feedbacks else None


async def good_answer_record_best(
    question: str,
    answer: str,
    quality_score: float = 0.0,
    is_verified: bool = False,
) -> int:
    """
    Record a high-quality answer for training purposes.

    This creates an llm_feedback record that can be used for fine-tuning.

    Args:
        question: The question
        answer: The answer text
        quality_score: Quality score (0-100)
        is_verified: Whether the answer has been verified

    Returns:
        int: The ID of the created llm_feedback
    """
    return await odoo_create(
        "llm_feedback",
        {
            "question": question,
            "answer": answer,
            "quality_score": quality_score,
            "is_verified": is_verified,
            "feedback_type": "expert_answer",
            "created_date": datetime.datetime.now().isoformat(),
        },
    )


# =============================================================================
# UPDATED GPU MARKETPLACE HELPER FUNCTIONS
# =============================================================================

async def gpu_marketplace_get_nodes(
    status: Optional[str] = "available",
    gpu_model: Optional[str] = None,
) -> List[Dict]:
    """
    Get GPU nodes from Odoo.

    This queries the 'gpu.node' model.

    Args:
        status: Filter by status (available, reserved, used)
        gpu_model: Filter by GPU model (optional)

    Returns:
        List[Dict]: List of GPU node records
    """
    domain = [("is_active", "=", True)]
    if status:
        domain.append(("status", "=", status))
    if gpu_model:
        domain.append(("gpu_model", "=", gpu_model))

    return await odoo_search(
        "gpu.node",
        domain,
        ["id", "name", "gpu_model", "vram_gb", "price_per_hour", "status"],
    )


async def gpu_marketplace_create_booking(
    node_id: int,
    user_id: int,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
) -> int:
    """
    Create a GPU booking in Odoo.

    This creates a 'gpu_sharing_schedule' record.

    Args:
        node_id: The ID of the GPU node
        user_id: The ID of the user making the booking
        start_time: The start time of the booking
        end_time: The end time of the booking

    Returns:
        int: The ID of the created booking
    """
    duration_hours = (end_time - start_time).total_seconds() / 3600

    # Get the node to calculate cost
    nodes = await odoo_search(
        "gpu.node",
        [("id", "=", node_id)],
        ["price_per_hour"],
    )
    price_per_hour = nodes[0].get("price_per_hour", 0) if nodes else 0
    total_cost = duration_hours * price_per_hour

    return await odoo_create(
        "gpu_sharing_schedule",
        {
            "node_id": node_id,
            "user_id": user_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_cost": total_cost,
            "status": "pending",
            "created_date": datetime.datetime.now().isoformat(),
        },
    )