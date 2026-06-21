# -*- coding: utf-8 -*-
# =============================================================================
# GPU MANAGEMENT AGENT – GPU Cluster Health & Scaling
# =============================================================================
# FILE: src/core/agents/gpu_management_agent.py
#
# PURPOSE:
#   This agent handles GPU management queries. It monitors GPU cluster
#   health, manages node lifecycles, and handles pool assignments.
#
# KEY FEATURES:
#   - Fetches GPU cluster status from Odoo
#   - Checks node health and utilisation
#   - Recommends scaling actions
#   - Manages pool assignments
#
# IMPORTANT:
#   This file was previously a PLACEHOLDER stub. It has been replaced
#   with the full implementation from src/agent/gpu_management_agent.py.
#
# =============================================================================

import json
import logging
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI

from ..tools.inference_tools import get_inference_backend
from ..tools.odoo_tools import (
    gpu_cluster_search,
    gpu_node_search,
    gpu_node_write,
)

_logger = logging.getLogger(__name__)


class GPUManagementState(dict):
    """
    State carried through the GPU management workflow.

    Keys:
        - cluster_id: The ID of the GPU cluster
        - cluster: The cluster data from Odoo
        - nodes: List of node records from Odoo
        - health_status: Overall health status
        - recommendations: List of recommended actions
    """
    pass


def create_gpu_management_agent() -> StateGraph:
    """
    Build and return a compiled GPU management sub-graph.

    The workflow consists of three nodes:
    1. fetch_cluster – Get the cluster details from Odoo
    2. check_health – Check node health and utilisation
    3. generate_recommendations – Generate scaling recommendations

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"GPU Management agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: Fetch Cluster
    # =========================================================================

    async def fetch_cluster(state: GPUManagementState):
        """
        Fetch the GPU cluster details from Odoo.
        """
        cluster_id = state.get("cluster_id")
        _logger.info(f"Fetching GPU cluster with ID: {cluster_id}")

        if cluster_id:
            clusters = await gpu_cluster_search([("id", "=", cluster_id)])
            state["cluster"] = clusters[0] if clusters else {}
            _logger.info(f"Found cluster: {state['cluster'].get('name', 'Unknown')}")
        else:
            # If no cluster_id provided, get the first available cluster
            clusters = await gpu_cluster_search([])
            if clusters:
                state["cluster"] = clusters[0]
                _logger.info(f"Using default cluster: {state['cluster'].get('name', 'Unknown')}")
            else:
                _logger.warning("No GPU cluster found")
                state["cluster"] = {}

        return state

    # =========================================================================
    # NODE 2: Check Health
    # =========================================================================

    async def check_health(state: GPUManagementState):
        """
        Check the health of the GPU cluster and its nodes.
        """
        cluster = state.get("cluster", {})
        cluster_id = cluster.get("id")

        if not cluster_id:
            _logger.warning("No cluster ID available for health check")
            state["nodes"] = []
            state["health_status"] = "unknown"
            return state

        # Fetch all nodes in the cluster
        nodes = await gpu_node_search([("cluster_id", "=", cluster_id)])
        state["nodes"] = nodes

        _logger.info(f"Found {len(nodes)} nodes in cluster")

        # Calculate health status
        online_count = len([n for n in nodes if n.get("status") == "online"])
        total_count = len(nodes)

        if total_count == 0:
            state["health_status"] = "no_nodes"
        elif online_count == total_count:
            state["health_status"] = "healthy"
        elif online_count >= total_count / 2:
            state["health_status"] = "degraded"
        else:
            state["health_status"] = "critical"

        _logger.info(f"Health status: {state['health_status']} ({online_count}/{total_count} online)")

        return state

    # =========================================================================
    # NODE 3: Generate Recommendations
    # =========================================================================

    async def generate_recommendations(state: GPUManagementState):
        """
        Generate scaling and management recommendations using the LLM.
        """
        cluster = state.get("cluster", {})
        nodes = state.get("nodes", [])
        health_status = state.get("health_status", "unknown")

        _logger.info(f"Generating recommendations for cluster (health: {health_status})")

        # Construct the prompt
        prompt = f"""
        Analyse the following GPU cluster and provide management recommendations.

        Cluster: {json.dumps(cluster, indent=2)}

        Nodes: {json.dumps(nodes, indent=2)}

        Health Status: {health_status}

        Provide recommendations for:
        1. Scaling (should we add or remove nodes?)
        2. Maintenance (any nodes that need attention?)
        3. Optimisation (how to improve performance?)

        Return the recommendations as a JSON object with keys:
        'scaling', 'maintenance', 'optimisation', and 'priority_actions'.
        """

        try:
            response = await llm.ainvoke(prompt)
            _logger.debug(f"LLM response: {response.content}")

            import re
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                recommendations = json.loads(json_match.group())
            else:
                recommendations = json.loads(response.content)

            state["recommendations"] = recommendations
            _logger.info("Generated recommendations successfully")

        except Exception as e:
            _logger.error(f"Recommendation generation failed: {e}")
            state["recommendations"] = {
                "scaling": "Unable to generate scaling recommendations",
                "maintenance": "Unable to generate maintenance recommendations",
                "optimisation": "Unable to generate optimisation recommendations",
                "priority_actions": ["Check cluster health manually"],
            }

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(GPUManagementState)

    workflow.add_node("fetch_cluster", fetch_cluster)
    workflow.add_node("check_health", check_health)
    workflow.add_node("generate_recommendations", generate_recommendations)

    workflow.add_edge(START, "fetch_cluster")
    workflow.add_edge("fetch_cluster", "check_health")
    workflow.add_edge("check_health", "generate_recommendations")
    workflow.add_edge("generate_recommendations", END)

    return workflow.compile()