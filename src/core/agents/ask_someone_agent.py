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
#   - Two-track system: regulated (medical/legal) vs community
#   - Finds matching experts based on expertise and availability
#   - Verifies expert qualifications for regulated questions
#   - Routes questions to experts and tracks responses
#   - Handles expert ratings and feedback
#   - Full audit trail for compliance
#   - Idempotency protection
#
# INTEGRATION:
#   - Uses odoo_tools.py to interact with Odoo's nettrades_ask_someone models
#   - Reports back to the supervisor with the expert's answer
#
# UPDATES (2026-08):
#   - Added two-track system (regulated/community)
#   - Added verify_expert_qualification node
#   - Added audit_trail node
#   - Added idempotency protection
#   - Added review workflow for regulated answers
# =============================================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import uuid

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
    """State carried through the Ask Someone workflow.

    Keys:
        - question: The user's question
        - category: The category of the question (technical, business, legal, etc.)
        - urgency: The urgency level (low, medium, high, critical)
        - track: The track (regulated or community)
        - experts: List of matching experts from Odoo
        - selected_expert: The expert who was selected to answer
        - request_id: The Odoo ID of the ask_someone request
        - answer: The expert's answer
        - rating: The user's rating of the answer
        - feedback: Additional feedback from the user
        - idempotency_key: Unique key to prevent duplicate requests
    """
    pass


def create_ask_someone_agent() -> StateGraph:
    """Build and return a compiled Ask Someone sub-graph.

    The workflow consists of eight nodes:
    1. classify_question - Determine category, urgency, and required expertise
    2. determine_track - Determine if this is regulated or community
    3. find_experts - Find matching experts in Odoo
    4. verify_expert_qualification - Verify expert qualifications (regulated only)
    5. route_to_expert - Create a request and route to the best expert
    6. collect_answer - Collect the expert's answer (via Odoo or callback)
    7. review_answer - Review the answer (regulated only)
    8. record_feedback - Record user rating and feedback
    9. audit_trail - Record audit trail for compliance

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
        """Classify the user's question to determine category and urgency."""
        messages = state.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        _logger.info(f"Classifying Ask Someone question: {user_msg[:100]}...")

        prompt = f"""
        Classify the following question and determine the best expert category and urgency.

        Question: {user_msg}

        Categories: technical, business, legal, medical, financial, educational, creative, other

        Urgency levels: low, normal, high, critical

        Return a JSON object with:
        - category: the best matching category
        - urgency: the urgency level
        - required_expertise: a brief description of the expertise needed
        - is_regulated: true if this falls under medical, legal, or financial regulation
        """
        try:
            response = await llm.apredict(prompt)
            classification = json.loads(response)
            state["category"] = classification.get("category", "other")
            state["urgency"] = classification.get("urgency", "normal")
            state["required_expertise"] = classification.get("required_expertise", "")
            state["is_regulated"] = classification.get("is_regulated", False)
            _logger.info(f"Classification: {state['category']}, urgency: {state['urgency']}, regulated: {state['is_regulated']}")
        except Exception as e:
            _logger.error(f"Failed to classify question: {e}")
            state["category"] = "other"
            state["urgency"] = "normal"
            state["is_regulated"] = False
            state["required_expertise"] = "General expertise"
        return state

    # =========================================================================
    # NODE 2: Determine Track
    # =========================================================================
    async def determine_track(state: AskSomeoneState) -> AskSomeoneState:
        """Determine if this request should use the regulated or community track."""
        is_regulated = state.get("is_regulated", False)
        category = state.get("category", "")

        # Categories that always require regulated track
        regulated_categories = ["medical", "legal", "financial"]

        if category in regulated_categories or is_regulated:
            state["track"] = "regulated"
            _logger.info("Using regulated track for question")
        else:
            state["track"] = "community"
            _logger.info("Using community track for question")

        # Generate idempotency key
        state["idempotency_key"] = str(uuid.uuid4())
        return state

    # =========================================================================
    # NODE 3: Find Experts
    # =========================================================================
    async def find_experts(state: AskSomeoneState) -> AskSomeoneState:
        """Find matching experts in Odoo based on category and track."""
        category = state.get("category", "")
        track = state.get("track", "community")
        _logger.info(f"Finding experts for category: {category}, track: {track}")

        # Build domain based on track
        domain = [
            ("field_id.name", "ilike", category),
            ("is_available", "=", True),
        ]

        if track == "regulated":
            domain.append(("verification_status", "=", "verified"))
            domain.append(("licence_expiry", ">=", datetime.now().date().isoformat()))
        else:
            # Community track: find experts with high community rank
            domain.append(("community_rank", ">", 10))

        try:
            experts = await odoo_search(
                model="qualified_professional",
                domain=domain,
                fields=[
                    "id", "partner_id", "field_id", "verification_status",
                    "community_rank", "reputation_score", "is_available",
                    "expertise_areas", "licence_number", "registration_body",
                ],
                limit=20,
                order="reputation_score DESC" if track == "regulated" else "community_rank DESC",
            )
            state["experts"] = experts
            _logger.info(f"Found {len(experts)} experts")
        except Exception as e:
            _logger.error(f"Failed to find experts: {e}")
            state["experts"] = []
        return state

    # =========================================================================
    # NODE 4: Verify Expert Qualification (Regulated Only)
    # =========================================================================
    async def verify_expert_qualification(state: AskSomeoneState) -> AskSomeoneState:
        """Verify that the selected expert meets qualification requirements."""
        track = state.get("track", "community")

        # Only verify for regulated track
        if track != "regulated":
            state["qualification_status"] = "not_required"
            return state

        experts = state.get("experts", [])
        if not experts:
            state["qualification_status"] = "no_experts_found"
            state["error"] = "No verified experts available for this regulated question"
            return state

        selected = experts[0] if experts else {}
        state["selected_expert"] = selected

        # Check verification status
        if selected.get("verification_status") != "verified":
            state["qualification_status"] = "verification_failed"
            state["error"] = "Selected expert is not verified"
            return state

        # Check licence expiry
        # licence_expiry is stored as string in Odoo
        licence_expiry = selected.get("licence_expiry")
        if licence_expiry:
            try:
                expiry_date = datetime.strptime(licence_expiry, "%Y-%m-%d").date()
                if expiry_date < datetime.now().date():
                    state["qualification_status"] = "licence_expired"
                    state["error"] = "Expert licence has expired"
                    return state
            except (ValueError, TypeError):
                _logger.warning(f"Could not parse licence expiry: {licence_expiry}")

        state["qualification_status"] = "verified"
        _logger.info(f"Expert verified: {selected.get('id')}")
        return state

    # =========================================================================
    # NODE 5: Route to Expert
    # =========================================================================
    async def route_to_expert(state: AskSomeoneState) -> AskSomeoneState:
        """Create a request and route to the best expert."""
        selected = state.get("selected_expert", {})
        if not selected:
            # Try to find the best expert from the list
            experts = state.get("experts", [])
            if experts:
                selected = experts[0]
                state["selected_expert"] = selected
            else:
                state["error"] = "No expert available"
                state["status"] = "failed"
                return state

        expert_id = selected.get("id")
        requester_id = state.get("user_id")
        question = state.get("question", "")
        category = state.get("category", "")
        urgency = state.get("urgency", "normal")
        track = state.get("track", "community")
        idempotency_key = state.get("idempotency_key")

        _logger.info(f"Routing to expert {expert_id} for question: {question[:50]}...")

        try:
            # Check for existing request with same idempotency key
            existing = await odoo_search(
                model="expert.session",
                domain=[("idempotency_key", "=", idempotency_key)],
                fields=["id"],
            )
            if existing:
                state["request_id"] = existing[0]["id"]
                _logger.info(f"Found existing request with idempotency key: {idempotency_key}")
                return state

            # Create the expert session
            values = {
                "requester_id": requester_id,
                "field_id": category,  # Will be resolved by Odoo
                "task_summary": question,
                "urgency": urgency,
                "track": track,
                "status": "assigned",
                "expert_id": expert_id,
                "assigned_at": datetime.now().isoformat(),
                "idempotency_key": idempotency_key,
                "data_classification": "restricted" if track == "regulated" else "confidential",
                "consent_given": state.get("consent_given", False),
                "consent_given_at": datetime.now().isoformat() if state.get("consent_given") else None,
            }

            request_id = await odoo_create("expert.session", values)
            state["request_id"] = request_id
            _logger.info(f"Created expert session with ID: {request_id}")

            # Log audit
            await odoo_create("expert.session.audit", {
                "session_id": request_id,
                "action": "route_to_expert",
                "user_id": requester_id,
                "details": json.dumps({"expert_id": expert_id, "track": track}),
                "timestamp": datetime.now().isoformat(),
            })

        except Exception as e:
            _logger.error(f"Failed to route to expert: {e}")
            state["error"] = str(e)
            state["status"] = "failed"

        return state

    # =========================================================================
    # NODE 6: Collect Answer
    # =========================================================================
    async def collect_answer(state: AskSomeoneState) -> AskSomeoneState:
        """Collect the expert's answer."""
        request_id = state.get("request_id")
        if not request_id:
            state["error"] = "No request ID available"
            return state

        _logger.info(f"Collecting answer for request: {request_id}")

        try:
            # Query Odoo for the answer
            sessions = await odoo_search(
                model="expert.session",
                domain=[("id", "=", request_id)],
                fields=["id", "answer", "answered_at", "status"],
            )

            if sessions and sessions[0].get("answer"):
                state["answer"] = sessions[0]["answer"]
                state["status"] = "answered"
                _logger.info(f"Answer collected for request: {request_id}")
            else:
                # Not answered yet - could implement polling or callback
                state["status"] = "waiting_for_answer"
                _logger.info(f"Waiting for answer on request: {request_id}")

        except Exception as e:
            _logger.error(f"Failed to collect answer: {e}")
            state["error"] = str(e)

        return state

    # =========================================================================
    # NODE 7: Review Answer (Regulated Only)
    # =========================================================================
    async def review_answer(state: AskSomeoneState) -> AskSomeoneState:
        """Review the answer for regulated track."""
        track = state.get("track", "community")
        if track != "regulated":
            state["review_status"] = "not_required"
            return state

        request_id = state.get("request_id")
        if not request_id:
            return state

        _logger.info(f"Reviewing answer for request: {request_id}")

        try:
            # In a production system, this would trigger a human review workflow
            # For now, we use AI to check the answer quality
            answer = state.get("answer", "")
            if not answer:
                return state

            prompt = f"""
            Review this answer for quality, accuracy, and safety.
            This is a REGULATED question (medical/legal/financial).

            Answer: {answer[:500]}...

            Return a JSON object with:
            - is_approved: true/false
            - confidence: 0-10
            - issues: list of issues found
            - suggestions: suggested improvements
            """
            try:
                response = await llm.apredict(prompt)
                review = json.loads(response)
                is_approved = review.get("is_approved", False)

                # Update the session
                await odoo_write(
                    model="expert.session",
                    ids=[request_id],
                    values={
                        "reviewed_at": datetime.now().isoformat(),
                        "is_approved": is_approved,
                        "review_notes": json.dumps(review),
                        "status": "reviewed" if is_approved else "answered",
                    }
                )
                state["review_status"] = "approved" if is_approved else "needs_improvement"

                # Log audit
                await odoo_create("expert.session.audit", {
                    "session_id": request_id,
                    "action": "review_answer",
                    "user_id": state.get("user_id"),
                    "details": json.dumps(review),
                    "timestamp": datetime.now().isoformat(),
                })

            except Exception as e:
                _logger.error(f"Failed to review answer: {e}")
                state["review_status"] = "failed"

        except Exception as e:
            _logger.error(f"Failed to review answer: {e}")

        return state

    # =========================================================================
    # NODE 8: Record Feedback
    # =========================================================================
    async def record_feedback(state: AskSomeoneState) -> AskSomeoneState:
        """Record user rating and feedback."""
        request_id = state.get("request_id")
        rating = state.get("rating", 0)
        feedback = state.get("feedback", "")
        is_good_answer = state.get("is_good_answer", False)

        if not request_id:
            return state

        _logger.info(f"Recording feedback for request: {request_id}")

        try:
            values = {
                "rating": rating,
                "feedback": feedback,
                "is_good_answer": is_good_answer,
            }
            if is_good_answer:
                values["status"] = "closed"
                # Increment expert's Good Answer count
                sessions = await odoo_search(
                    model="expert.session",
                    domain=[("id", "=", request_id)],
                    fields=["expert_id"],
                )
                if sessions and sessions[0].get("expert_id"):
                    await odoo_call_method(
                        model="qualified_professional",
                        method="add_good_answer",
                        args=[sessions[0]["expert_id"]],
                    )

            await odoo_write("expert.session", [request_id], values)
            state["feedback_recorded"] = True
            _logger.info(f"Feedback recorded for request: {request_id}")

        except Exception as e:
            _logger.error(f"Failed to record feedback: {e}")
            state["error"] = str(e)

        return state

    # =========================================================================
    # NODE 9: Audit Trail
    # =========================================================================
    async def audit_trail(state: AskSomeoneState) -> AskSomeoneState:
        """Record audit trail for compliance."""
        request_id = state.get("request_id")
        if not request_id:
            return state

        audit_entry = {
            "session_id": request_id,
            "action": "complete",
            "user_id": state.get("user_id"),
            "details": json.dumps({
                "track": state.get("track"),
                "category": state.get("category"),
                "urgency": state.get("urgency"),
                "expert_id": state.get("selected_expert", {}).get("id"),
                "qualification_status": state.get("qualification_status"),
                "review_status": state.get("review_status"),
                "rating": state.get("rating"),
                "is_good_answer": state.get("is_good_answer", False),
            }),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            await odoo_create("expert.session.audit", audit_entry)
            _logger.info(f"Audit trail recorded for request: {request_id}")
        except Exception as e:
            _logger.error(f"Failed to record audit trail: {e}")

        return state

    # =========================================================================
    # Build the Graph
    # =========================================================================
    workflow = StateGraph(AskSomeoneState)

    # Add nodes
    workflow.add_node("classify_question", classify_question)
    workflow.add_node("determine_track", determine_track)
    workflow.add_node("find_experts", find_experts)
    workflow.add_node("verify_expert_qualification", verify_expert_qualification)
    workflow.add_node("route_to_expert", route_to_expert)
    workflow.add_node("collect_answer", collect_answer)
    workflow.add_node("review_answer", review_answer)
    workflow.add_node("record_feedback", record_feedback)
    workflow.add_node("audit_trail", audit_trail)

    # Add edges
    workflow.add_edge(START, "classify_question")
    workflow.add_edge("classify_question", "determine_track")
    workflow.add_edge("determine_track", "find_experts")
    workflow.add_edge("find_experts", "verify_expert_qualification")
    workflow.add_edge("verify_expert_qualification", "route_to_expert")
    workflow.add_edge("route_to_expert", "collect_answer")
    workflow.add_edge("collect_answer", "review_answer")
    workflow.add_edge("review_answer", "record_feedback")
    workflow.add_edge("record_feedback", "audit_trail")
    workflow.add_edge("audit_trail", END)

    # Compile and return
    return workflow.compile()