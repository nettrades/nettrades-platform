#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ASK SOMEONE AGENT – Expert Marketplace Integration
# =============================================================================
# FILE: src/core/agents/ask_someone_agent.py
#
# PURPOSE:
#   This agent handles the "Ask Someone" expert marketplace functionality.
#   It allows users to ask questions that are routed to domain experts.
#   The agent integrates with the nettrades_ask_someone Odoo module.
#
# KEY FEATURES:
#   - Classifies questions by category and urgency
#   - Finds matching experts based on expertise and availability
#   - Routes questions to experts and tracks responses
#   - Handles expert ratings and feedback
#
# INTEGRATION:
#   - Uses odoo_tools.py to interact with Odoo's nettrades_ask_someone models
#   - Reports back to the supervisor with the expert's answer
#
# UPDATES (2026-08-04):
#   - Updated model names to match actual Odoo models:
#       * expert.session (was nettrades_ask_someone.request)
#       * qualified_professional (was nettrades_ask_someone.expert)
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
    ask_someone_create_request,
    ask_someone_get_experts,
)

_logger = logging.getLogger(__name__)


class AskSomeoneState(dict):
    """
    State carried through the Ask Someone workflow.

    Keys:
        - question: The user's question
        - category: The category of the question (technical, business, legal, etc.)
        - urgency: The urgency level (low, medium, high, critical)
        - experts: List of matching experts from Odoo
        - selected_expert: The expert who was selected to answer
        - request_id: The Odoo ID of the ask_someone request
        - answer: The expert's answer
        - rating: The user's rating of the answer
        - feedback: Additional feedback from the user
    """
    pass


def create_ask_someone_agent() -> StateGraph:
    """
    Build and return a compiled Ask Someone sub-graph.

    The workflow consists of five nodes:
    1. classify_question - Determine category, urgency, and required expertise
    2. find_experts - Find matching experts in Odoo
    3. route_to_expert - Create a request and route to the best expert
    4. collect_answer - Collect the expert's answer (via Odoo or callback)
    5. record_feedback - Record user rating and feedback

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"Ask Someone agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: Classify Question
    # =========================================================================

    async def classify_question(state: AskSomeoneState) -> AskSomeoneState:
        """
        Classify the user's question to determine category and urgency.
        """
        messages = state.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""

        _logger.info(f"Classifying Ask Someone question: {user_msg[:100]}...")

        prompt = f"""
        Classify the following question and determine the best expert category and urgency.

        Question: {user_msg}

        Categories: technical, business, legal, financial, medical, education, general
        Urgency: low, medium, high, critical

        Respond with JSON:
        {{
            "category": "category_name",
            "urgency": "urgency_level",
            "expertise_required": ["skill1", "skill2"],
            "estimated_time": "estimated_time_in_minutes"
        }}
        """

        try:
            response = await llm.ainvoke(prompt)
            classification = json.loads(response.content)
            state["question"] = user_msg
            state["category"] = classification.get("category", "general")
            state["urgency"] = classification.get("urgency", "medium")
            state["expertise_required"] = classification.get("expertise_required", [])
            _logger.info(f"Question classified as: {state['category']} (urgency: {state['urgency']})")
        except Exception as e:
            _logger.error(f"Question classification failed: {e}")
            state["category"] = "general"
            state["urgency"] = "medium"
            state["expertise_required"] = []

        return state

    # =========================================================================
    # NODE 2: Find Experts
    # =========================================================================

    async def find_experts(state: AskSomeoneState) -> AskSomeoneState:
        """
        Find matching experts in Odoo based on category and required expertise.
        """
        field_id = state.get("field_id")
        expertise_required = state.get("expertise_required", [])

        _logger.info(f"Searching for experts with field_id: {field_id}")

        try:
            # Use the updated ask_someone_get_experts helper
            experts = await ask_someone_get_experts(field_id=field_id)

            state["experts"] = experts
            _logger.info(f"Found {len(experts)} matching experts")
        except Exception as e:
            _logger.error(f"Expert search failed: {e}")
            state["experts"] = []

        return state

    # =========================================================================
    # NODE 3: Route to Expert
    # =========================================================================

    async def route_to_expert(state: AskSomeoneState) -> AskSomeoneState:
        """
        Create a request in Odoo and route it to the best matching expert.
        """
        question = state.get("question", "")
        field_id = state.get("field_id")
        urgency = state.get("urgency", "medium")
        experts = state.get("experts", [])
        requester_id = state.get("requester_id") or 1  # Default to admin if not provided

        if not field_id:
            _logger.warning("No field_id provided for routing")
            state["error"] = "No professional field selected"
            return state

        if not experts:
            _logger.warning("No experts found for routing")
            state["error"] = "No matching experts available"
            return state

        # Select the best expert (highest rating, or first if no rating)
        best_expert = max(experts, key=lambda e: e.get("reputation_score", 0)) if experts else experts[0]
        state["selected_expert"] = best_expert

        _logger.info(f"Routing to expert: {best_expert.get('partner_id', 'Unknown')}")

        try:
            # Use the updated ask_someone_create_request helper
            request_id = await ask_someone_create_request(
                question=question,
                field_id=field_id,
                requester_id=requester_id,
                urgency=urgency,
                expert_id=best_expert.get("id"),
            )

            state["request_id"] = request_id
            _logger.info(f"Ask Someone request created with ID: {request_id}")

            # Notify the expert (via Odoo's notification system)
            await odoo_call_method(
                model="expert.session",
                method="notify_expert",
                args=[request_id],
            )

            state["analysis"] = (
                f"Your question has been routed to an expert. "
                f"You will receive a response shortly."
            )
        except Exception as e:
            _logger.error(f"Expert routing failed: {e}")
            state["error"] = f"Failed to route to expert: {str(e)}"

        return state

    # =========================================================================
    # NODE 4: Collect Answer
    # =========================================================================

    async def collect_answer(state: AskSomeoneState) -> AskSomeoneState:
        """
        Collect the expert's answer from Odoo or via callback.
        """
        request_id = state.get("request_id")
        if not request_id:
            _logger.warning("No request ID available for collecting answer")
            return state

        _logger.info(f"Collecting answer for request: {request_id}")

        try:
            # Get the request from Odoo using the correct model
            request = await odoo_search(
                model="expert.session",
                domain=[("id", "=", request_id)],
                fields=["id", "task_summary", "status", "expert_id"],
                limit=1,
            )

            if request and request[0].get("task_summary"):
                state["answer"] = request[0]["task_summary"]
                state["analysis"] = request[0]["task_summary"]
                _logger.info("Answer collected successfully")
            else:
                # If no answer yet, check if we should wait or return a status
                status = request[0].get("status", "pending") if request else "unknown"
                state["analysis"] = (
                    f"Your question is still being processed (status: {status}). "
                    f"You will be notified when an expert responds."
                )
                _logger.info(f"Request status: {status}")
        except Exception as e:
            _logger.error(f"Answer collection failed: {e}")
            state["analysis"] = "There was an error retrieving the expert's answer."

        return state

    # =========================================================================
    # NODE 5: Record Feedback
    # =========================================================================

    async def record_feedback(state: AskSomeoneState) -> AskSomeoneState:
        """
        Record user rating and feedback for the expert.
        """
        request_id = state.get("request_id")
        rating = state.get("rating")
        feedback = state.get("feedback", "")

        if not request_id or not rating:
            _logger.info("No rating provided, skipping feedback recording")
            return state

        _logger.info(f"Recording feedback for request: {request_id}")

        try:
            await odoo_write(
                model="expert.session",
                ids=[request_id],
                values={
                    "rating_by_requester": rating,
                    "status": "completed",
                },
            )
            _logger.info("Feedback recorded successfully")
        except Exception as e:
            _logger.error(f"Feedback recording failed: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(AskSomeoneState)

    workflow.add_node("classify_question", classify_question)
    workflow.add_node("find_experts", find_experts)
    workflow.add_node("route_to_expert", route_to_expert)
    workflow.add_node("collect_answer", collect_answer)
    workflow.add_node("record_feedback", record_feedback)

    workflow.add_edge(START, "classify_question")
    workflow.add_edge("classify_question", "find_experts")
    workflow.add_edge("find_experts", "route_to_expert")
    workflow.add_edge("route_to_expert", "collect_answer")
    workflow.add_edge("collect_answer", "record_feedback")
    workflow.add_edge("record_feedback", END)

    return workflow.compile()