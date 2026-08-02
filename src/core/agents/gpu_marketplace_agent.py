#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# GPU MARKETPLACE AGENT – GPU Booking & Marketplace
# =============================================================================
# FILE: src/core/agents/gpu_marketplace_agent.py
#
# PURPOSE:
#   This agent handles GPU marketplace functionality.
#   It allows users to browse available GPU nodes, create bookings,
#   and manage GPU usage.
#
# KEY FEATURES:
#   - Lists available GPU nodes with pricing and specs
#   - Creates GPU bookings with start/end times
#   - Tracks GPU usage and billing
#   - Handles GPU release and termination
#
# INTEGRATION:
#   - Uses odoo_tools.py to interact with Odoo's nettrades_gpu_admin models
#   - Reports back to the supervisor with booking status
# =============================================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI

from tools import get_inference_backend
from tools.odoo_tools import (
    odoo_search,
    odoo_create,
    odoo_write,
    odoo_call_method,
)

_logger = logging.getLogger(__name__)


class GPUMarketplaceState(dict):
    """
    State carried through the GPU Marketplace workflow.

    Keys:
        - action: The action to perform (list, book, release, status)
        - gpu_nodes: List of available GPU nodes
        - selected_node: The selected GPU node
        - booking_id: The Odoo ID of the booking
        - start_time: Booking start time
        - end_time: Booking end time
        - total_cost: The total cost of the booking
        - status: The current status (pending, confirmed, running, completed, cancelled)
    """
    pass


def create_gpu_marketplace_agent() -> StateGraph:
    """
    Build and return a compiled GPU Marketplace sub-graph.

    The workflow consists of five nodes:
    1. list_gpus - List available GPU nodes with pricing and specs
    2. select_gpu - Select a GPU node for booking
    3. create_booking - Create a booking in Odoo
    4. process_payment - Process payment for the booking
    5. release_gpu - Release the GPU after use

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"GPU Marketplace agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: List GPUs
    # =========================================================================

    async def list_gpus(state: GPUMarketplaceState) -> GPUMarketplaceState:
        """
        List available GPU nodes with pricing and specifications.
        """
        _logger.info("Listing available GPU nodes")

        try:
            # Search for available GPU nodes in Odoo
            nodes = await odoo_search(
                model="nettrades_gpu_admin.node",
                domain=[
                    ("status", "=", "available"),
                    ("is_active", "=", True),
                ],
                fields=[
                    "id", "name", "gpu_model", "vram_gb",
                    "compute_capability", "price_per_hour",
                    "availability", "provider_id",
                ],
                limit=20,
            )

            state["gpu_nodes"] = nodes
            _logger.info(f"Found {len(nodes)} available GPU nodes")

            # Format the response for the user
            if nodes:
                response = "**Available GPU Nodes:**\n\n"
                for node in nodes[:5]:
                    response += (
                        f"- **{node.get('name')}**: {node.get('gpu_model')} "
                        f"({node.get('vram_gb')}GB VRAM) - "
                        f"${node.get('price_per_hour', 0):.2f}/hour\n"
                    )
                if len(nodes) > 5:
                    response += f"\n... and {len(nodes) - 5} more nodes available."
                state["analysis"] = response
            else:
                state["analysis"] = "No GPU nodes are currently available."

        except Exception as e:
            _logger.error(f"GPU listing failed: {e}")
            state["analysis"] = "Failed to retrieve GPU nodes. Please try again later."

        return state

    # =========================================================================
    # NODE 2: Select GPU
    # =========================================================================

    async def select_gpu(state: GPUMarketplaceState) -> GPUMarketplaceState:
        """
        Select a GPU node for booking based on user criteria.
        """
        nodes = state.get("gpu_nodes", [])
        user_criteria = state.get("criteria", {})

        if not nodes:
            _logger.warning("No GPU nodes available for selection")
            return state

        _logger.info(f"Selecting GPU based on criteria: {user_criteria}")

        # Use LLM to select the best GPU based on user criteria
        try:
            prompt = f"""
            Select the best GPU node from the following options based on the user's criteria.

            User Criteria: {json.dumps(user_criteria)}

            Available GPU Nodes: {json.dumps(nodes, indent=2)}

            Respond with the ID of the selected GPU node, or "none" if no suitable node is found.
            """

            response = await llm.ainvoke(prompt)
            selected_id = response.content.strip()

            if selected_id != "none":
                selected_node = next((n for n in nodes if str(n.get("id")) == selected_id), None)
                if selected_node:
                    state["selected_node"] = selected_node
                    state["analysis"] = (
                        f"Selected GPU: {selected_node.get('name')} "
                        f"({selected_node.get('gpu_model')}) - "
                        f"${selected_node.get('price_per_hour', 0):.2f}/hour"
                    )
                    _logger.info(f"Selected GPU node: {selected_node.get('id')}")
                else:
                    state["analysis"] = "Could not find the selected GPU node."
            else:
                state["analysis"] = "No suitable GPU node found matching your criteria."

        except Exception as e:
            _logger.error(f"GPU selection failed: {e}")
            state["analysis"] = "Failed to select a GPU node."

        return state

    # =========================================================================
    # NODE 3: Create Booking
    # =========================================================================

    async def create_booking(state: GPUMarketplaceState) -> GPUMarketplaceState:
        """
        Create a GPU booking in Odoo.
        """
        selected_node = state.get("selected_node")
        start_time = state.get("start_time")
        end_time = state.get("end_time")
        user_id = state.get("user_id")

        if not selected_node:
            _logger.warning("No GPU node selected for booking")
            return state

        if not start_time or not end_time:
            _logger.warning("Missing start or end time for booking")
            return state

        _logger.info(f"Creating booking for GPU node: {selected_node.get('id')}")

        try:
            # Calculate total cost
            duration_hours = (end_time - start_time).total_seconds() / 3600
            total_cost = duration_hours * selected_node.get("price_per_hour", 0)

            # Create booking in Odoo
            booking_data = {
                "node_id": selected_node.get("id"),
                "user_id": user_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_cost": total_cost,
                "status": "pending",
                "created_date": datetime.now().isoformat(),
            }

            booking_id = await odoo_create(
                model="nettrades_gpu_admin.booking",
                values=booking_data,
            )

            state["booking_id"] = booking_id
            state["total_cost"] = total_cost
            state["status"] = "pending"

            # Update node status to "reserved"
            await odoo_write(
                model="nettrades_gpu_admin.node",
                ids=[selected_node.get("id")],
                values={"status": "reserved"},
            )

            _logger.info(f"Booking created with ID: {booking_id}")

            state["analysis"] = (
                f"✅ Booking created!\n"
                f"GPU: {selected_node.get('name')}\n"
                f"Duration: {duration_hours:.1f} hours\n"
                f"Total Cost: ${total_cost:.2f}\n"
                f"Status: Pending confirmation"
            )

        except Exception as e:
            _logger.error(f"Booking creation failed: {e}")
            state["analysis"] = f"Failed to create booking: {str(e)}"

        return state

    # =========================================================================
    # NODE 4: Process Payment
    # =========================================================================

    async def process_payment(state: GPUMarketplaceState) -> GPUMarketplaceState:
        """
        Process payment for the booking.
        """
        booking_id = state.get("booking_id")
        total_cost = state.get("total_cost", 0)

        if not booking_id:
            _logger.warning("No booking ID available for payment")
            return state

        _logger.info(f"Processing payment for booking: {booking_id}")

        try:
            # In a real implementation, this would call a payment gateway
            # For now, we mark the payment as successful
            payment_successful = True

            if payment_successful:
                await odoo_write(
                    model="nettrades_gpu_admin.booking",
                    ids=[booking_id],
                    values={
                        "status": "confirmed",
                        "payment_status": "paid",
                        "payment_date": datetime.now().isoformat(),
                    },
                )
                state["status"] = "confirmed"
                state["analysis"] = (
                    f"✅ Payment successful! Your GPU has been reserved.\n"
                    f"Booking ID: {booking_id}\n"
                    f"Total Paid: ${total_cost:.2f}\n"
                    f"Your GPU will be available for the requested duration."
                )
                _logger.info(f"Payment processed successfully for booking: {booking_id}")
            else:
                state["analysis"] = "❌ Payment failed. Please try again."

        except Exception as e:
            _logger.error(f"Payment processing failed: {e}")
            state["analysis"] = f"Payment processing failed: {str(e)}"

        return state

    # =========================================================================
    # NODE 5: Release GPU
    # =========================================================================

    async def release_gpu(state: GPUMarketplaceState) -> GPUMarketplaceState:
        """
        Release the GPU after use.
        """
        selected_node = state.get("selected_node")
        booking_id = state.get("booking_id")

        if not selected_node or not booking_id:
            _logger.warning("No node or booking to release")
            return state

        _logger.info(f"Releasing GPU node: {selected_node.get('id')}")

        try:
            # Update node status to "available"
            await odoo_write(
                model="nettrades_gpu_admin.node",
                ids=[selected_node.get("id")],
                values={"status": "available"},
            )

            # Update booking status
            await odoo_write(
                model="nettrades_gpu_admin.booking",
                ids=[booking_id],
                values={"status": "completed"},
            )

            state["status"] = "completed"
            state["analysis"] = (
                f"✅ GPU released successfully.\n"
                f"Booking ID: {booking_id}\n"
                f"Thank you for using NETTRADES GPU Marketplace."
            )
            _logger.info(f"GPU released for booking: {booking_id}")

        except Exception as e:
            _logger.error(f"GPU release failed: {e}")
            state["analysis"] = f"Failed to release GPU: {str(e)}"

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(GPUMarketplaceState)

    workflow.add_node("list_gpus", list_gpus)
    workflow.add_node("select_gpu", select_gpu)
    workflow.add_node("create_booking", create_booking)
    workflow.add_node("process_payment", process_payment)
    workflow.add_node("release_gpu", release_gpu)

    workflow.add_edge(START, "list_gpus")
    workflow.add_edge("list_gpus", "select_gpu")
    workflow.add_edge("select_gpu", "create_booking")
    workflow.add_edge("create_booking", "process_payment")
    workflow.add_edge("process_payment", "release_gpu")
    workflow.add_edge("release_gpu", END)

    return workflow.compile()