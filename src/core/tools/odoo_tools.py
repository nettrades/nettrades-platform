# =============================================================================
# LangGraph Odoo Tools – wrap MCP-Odoo JSON-RPC calls as Python functions.
# =============================================================================
# Each function is a tool that the LangGraph agent can invoke.
# The MCP-Odoo bridge (http://mcp-odoo:3000/jsonrpc) is used for all calls.
# =============================================================================
import os, httpx, json, logging

_logger = logging.getLogger(__name__)

MCP_URL = os.getenv("MCP_ODOO_URL", "http://mcp-odoo:3000/jsonrpc")
REQUEST_TIMEOUT = int(os.getenv("ODOO_REQUEST_TIMEOUT", "30"))


async def _call_odoo(method: str, model: str, params: dict, args: list = None):
    """Low-level JSON-RPC call to the MCP-Odoo bridge."""
    async with httpx.AsyncClient() as client:
        payload = {
            "method": method,
            "params": {
                "model": model,
                "method": params.get("odoo_method", "search_read"),
                "args": args or params.get("args", []),
                "kwargs": params.get("kwargs", {})
            }
        }
        resp = await client.post(MCP_URL, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()


# ---------- CRM (Leads) ----------
async def crm_lead_search(domain: list = None, fields: list = None, limit: int = 100):
    """Search CRM leads."""
    return await _call_odoo("call", "crm.lead", {"odoo_method": "search_read", "args": [domain or [], fields or ["name", "description"], 0, limit]})

async def crm_lead_create(values: dict):
    """Create a CRM lead."""
    return await _call_odoo("call", "crm.lead", {"odoo_method": "create", "args": [values]})


# ---------- HR / Recruitment ----------
async def hr_job_search(domain: list = None, fields: list = None, limit: int = 100):
    """Search job postings."""
    return await _call_odoo("call", "hr.job", {"odoo_method": "search_read", "args": [domain or [], fields or ["name", "description", "required_skills"], 0, limit]})

async def hr_applicant_create(values: dict):
    """Create an applicant."""
    return await _call_odoo("call", "hr.applicant", {"odoo_method": "create", "args": [values]})


# ---------- Partners (companies, freelancers) ----------
async def res_partner_search(domain: list = None, fields: list = None, limit: int = 100):
    """Search partners."""
    return await _call_odoo("call", "res.partner", {"odoo_method": "search_read", "args": [domain or [], fields or ["name", "email", "user_type", "skill_ids", "hourly_rate"], 0, limit]})


# ---------- Projects ----------
async def project_search(domain: list = None, fields: list = None, limit: int = 100):
    """Search projects."""
    return await _call_odoo("call", "project.project", {"odoo_method": "search_read", "args": [domain or [], fields or ["name", "description"], 0, limit]})


# ---------- GPU Management ----------
async def gpu_cluster_search(domain: list = None, fields: list = None, limit: int = 10):
    return await _call_odoo("call", "gpu.cluster", {"odoo_method": "search_read", "args": [domain or [], fields or ["name", "status", "total_vram_gb"], 0, limit]})

async def gpu_node_search(domain: list = None, fields: list = None, limit: int = 100):
    return await _call_odoo("call", "gpu.node", {"odoo_method": "search_read", "args": [domain or [], fields or ["hostname", "status", "pool", "gpus", "gpu_utilisation_pct"], 0, limit]})

async def gpu_node_write(node_id: int, values: dict):
    return await _call_odoo("call", "gpu.node", {"odoo_method": "write", "args": [[node_id], values]})