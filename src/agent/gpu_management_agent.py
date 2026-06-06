# =============================================================================
# GPU-Management Agent – monitors GPU health, suggests scaling actions.
# =============================================================================
import json, logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from ..tools.inference_tools import get_inference_backend
from ..tools.odoo_tools import gpu_cluster_search, gpu_node_search, gpu_node_write

_logger = logging.getLogger(__name__)

class GPUManagementState(dict):
    pass


def create_gpu_management_agent() -> StateGraph:
    backend = get_inference_backend()
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    async def check_health(state: GPUManagementState):
        nodes = await gpu_node_search([("status", "=", "offline")])
        state["offline_nodes"] = nodes
        return state

    async def suggest_actions(state: GPUManagementState):
        offline = state.get("offline_nodes", [])
        if offline:
            # For each offline node, create an Odoo activity (simplified)
            for node in offline:
                await gpu_node_write(node["id"], {"scheduled_share": False})  # placeholder
        return state

    workflow = StateGraph(GPUManagementState)
    workflow.add_node("check_health", check_health)
    workflow.add_node("suggest_actions", suggest_actions)
    workflow.add_edge(START, "check_health")
    workflow.add_edge("check_health", "suggest_actions")
    workflow.add_edge("suggest_actions", END)
    return workflow.compile()