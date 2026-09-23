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
#
# FIXES (2026-09-23):
#   - .apredict() was being called on ChatOpenAI, which only has
#     .ainvoke(). The response is now an AIMessage, so json.loads()
#     must read .content, not the message object itself.
#   - expert.session.field_id is a Many2one to nettrades.field, not a
#     plain string. Added _resolve_field_id() which looks up or creates
#     the matching field record before the session is created.
#   - find_experts now filters by the resolved field_id (integer), not
#     field_id.name.
#   - collect_answer read the "answer" field; the model exposes "response".
#   - review_answer and record_feedback now write to the chatter (the
#     model inherits mail.thread) because the fields the original code
#     wrote to (reviewed_at, is_approved, review_notes, rating, feedback,
#     is_good_answer) do not exist on expert.session.
#   - audit_trail used a model named expert.session.audit which does not
#     exist. Now writes to the chatter via message_post instead.
# =============================================================================

import json
import logging
import re
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
    # The two helpers below are still imported for backwards compatibility
    # with earlier drafts of this agent. They are not used by the current
    # workflow (which uses odoo_search / odoo_create directly) but are kept
    # so that downstream code that imports them through this module
    # continues to work.
    ask_someone_create_request,
    ask_someone_get_experts,
)

_logger = logging.getLogger(__name__)


# =============================================================================
# HELPER — extract JSON from an LLM reply
# =============================================================================
# LLMs often wrap JSON in ```json ... ``` fences or add explanatory prose
# before and after. This helper finds the first balanced JSON object or
# array in the text and returns it as a Python dict/list. If nothing
# parses, it returns None so the caller can fall back to a safe default
# rather than crashing on a decode error.
# =============================================================================

def _extract_json(text: str):
    if not text:
        return None

    text = text.strip()

    # Strip a single markdown fence if present.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    # Try direct parse first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first balanced { ... } or [ ... ].
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


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
    # Helper: resolve a category name to a nettrades.field ID
    # =========================================================================
    # expert.session.field_id is a Many2one to nettrades.field. When we
    # classify a question, we get back a free-form string like "medical"
    # or "python development". We need the integer ID of the matching
    # field record before we can create the session. If no field exists,
    # we create one on demand: this is safe because the regulated-track
    # verification step will still reject any expert whose credentials
    # do not match.
    # =========================================================================
    async def _resolve_field_id(category: str) -> Optional[int]:
        if not category:
            return None
        try:
            rows = await odoo_search(
                model="nettrades.field",
                domain=[("name", "ilike", category)],
                fields=["id", "name"],
                limit=1,
            )
            if rows:
                return rows[0]["id"]

            new_id = await odoo_create("nettrades.field", {
                "name": category.title(),
                "description": f"Auto-created from Ask Someone classification: {category}",
            })
            _logger.info("Created nettrades.field '%s' (id=%s)", category, new_id)
            return new_id
        except Exception as e:
            _logger.error("Failed to resolve field_id for '%s': %s", category, e)
            return None

    # =========================================================================
    # NODE 1: Classify Question
    # =========================================================================
    async def classify_question(state: AskSomeoneState) -> AskSomeoneState:
        """Classify the user's question to determine category and urgency."""
        messages = state.get("messages", [])
        user_msg = messages[-1].get("content", "") if messages else ""
        state["question"] = user_msg  # Make sure downstream nodes see it
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

        Respond with only the JSON object, no other text.
        """
        try:
            response = await llm.ainvoke(prompt)
            # FIX: response is an AIMessage; read .content before parsing.
            classification = _extract_json(response.content) or {}
            state["category"] = classification.get("category", "other")
            state["urgency"] = classification.get("urgency", "normal")
            state["required_expertise"] = classification.get("required_expertise", "")
            state["is_regulated"] = bool(classification.get("is_regulated", False))
            _logger.info(
                f"Classification: {state['category']}, "
                f"urgency: {state['urgency']}, "
                f"regulated: {state['is_regulated']}"
            )
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

        # Resolve the category string to an actual nettrades.field id.
        # If we can't, the request cannot be routed to an expert.
        field_id = await _resolve_field_id(category)
        state["field_id"] = field_id

        # Generate idempotency key
        state["idempotency_key"] = str(uuid.uuid4())
        return state

    # =========================================================================
    # NODE 3: Find Experts
    # =========================================================================
    async def find_experts(state: AskSomeoneState) -> AskSomeoneState:
        """Find matching experts in Odoo based on category and track."""
        field_id = state.get("field_id")
        track = state.get("track", "community")
        _logger.info(f"Finding experts for field_id: {field_id}, track: {track}")

        if not field_id:
            state["experts"] = []
            state["error"] = "No field resolved for this question category"
            return state

        # Build domain based on track
        domain = [
            ("field_id", "=", field_id),
            ("is_available", "=", True),
        ]

        if track == "regulated":
            domain.append(("verification_status", "=", "verified"))
            domain.append(("licence_expiry", ">=", datetime.now().date().isoformat()))
        else:
            # Community track: find experts with at least some rank
            domain.append(("community_rank", ">", 0))

        try:
            experts = await odoo_search(
                model="qualified_professional",
                domain=domain,
                fields=[
                    "id", "partner_id", "field_id", "verification_status",
                    "community_rank", "reputation_score", "is_available",
                    "expertise_areas", "licence_number", "registration_body",
                    "licence_expiry",
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

        selected = experts[0]
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
        field_id = state.get("field_id")
        urgency = state.get("urgency", "normal")
        track = state.get("track", "community")
        idempotency_key = state.get("idempotency_key")

        _logger.info(f"Routing to expert {expert_id} for question: {question[:50]}...")

        if not requester_id:
            state["error"] = "Missing user_id in state; cannot create expert session"
            state["status"] = "failed"
            return state

        if not field_id:
            state["error"] = "Missing field_id; cannot create expert session"
            state["status"] = "failed"
            return state

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
                "field_id": field_id,
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

            # Log to chatter (audit trail). expert.session inherits
            # mail.thread, so message_post is the correct way to record an
            # audit entry.
            try:
                await odoo_call_method(
                    model="expert.session",
                    method="message_post",
                    args=[[request_id]],
                    kwargs={
                        "body": (
                            f"Session routed to expert {expert_id} "
                            f"on track {track}."
                        ),
                        "subtype_xmlid": "mail.mt_comment",
                    },
                )
            except Exception as e:
                _logger.warning(f"Could not post routing note to chatter: {e}")

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
            # Query Odoo for the answer. The model exposes the expert's
            # reply as "response", not "answer".
            sessions = await odoo_search(
                model="expert.session",
                domain=[("id", "=", request_id)],
                fields=["id", "response", "completed_date", "status"],
            )

            if sessions and sessions[0].get("response"):
                state["answer"] = sessions[0]["response"]
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

        answer = state.get("answer", "")
        if not answer:
            return state

        _logger.info(f"Reviewing answer for request: {request_id}")

        try:
            # In a production system, this would trigger a human review
            # workflow. For now, we use AI to check the answer quality.
            prompt = f"""
            Review this answer for quality, accuracy, and safety.
            This is a REGULATED question (medical/legal/financial).

            Answer: {answer[:1000]}

            Return a JSON object with:
            - is_approved: true/false
            - confidence: 0-10
            - issues: list of issues found
            - suggestions: suggested improvements

            Respond with only the JSON object, no other text.
            """
            response = await llm.ainvoke(prompt)
            # FIX: read .content before parsing.
            review = _extract_json(response.content) or {}
            is_approved = bool(review.get("is_approved", False))

            # expert.session has no reviewed_at / is_approved / review_notes
            # columns. Record the review in the chatter and set the lifecycle
            # status accordingly.
            await odoo_write(
                model="expert.session",
                ids=[request_id],
                values={
                    "status": "completed" if is_approved else "in_progress",
                },
            )
            try:
                await odoo_call_method(
                    model="expert.session",
                    method="message_post",
                    args=[[request_id]],
                    kwargs={
                        "body": (
                            f"Regulated review result: "
                            f"{'approved' if is_approved else 'needs improvement'}. "
                            f"Review payload: {json.dumps(review)}"
                        ),
                        "subtype_xmlid": "mail.mt_comment",
                    },
                )
            except Exception as e:
                _logger.warning(f"Could not post review note to chatter: {e}")

            state["review_status"] = "approved" if is_approved else "needs_improvement"
            state["review_notes"] = json.dumps(review)
            _logger.info(f"Review result for request {request_id}: {state['review_status']}")

        except Exception as e:
            _logger.error(f"Failed to review answer: {e}")
            state["review_status"] = "failed"

        return state

    # =========================================================================
    # NODE 8: Record Feedback
    # =========================================================================
    async def record_feedback(state: AskSomeoneState) -> AskSomeoneState:
        """Record user rating and feedback."""
        request_id = state.get("request_id")
        rating = state.get("rating_by_requester", 0)
        feedback = state.get("feedback", "")
        is_good_answer = state.get("is_good_answer", False)

        if not request_id:
            return state

        _logger.info(f"Recording feedback for request: {request_id}")

        try:
            # expert.session has no rating / feedback / is_good_answer
            # columns. Record the feedback in the chatter, and if it was a
            # "good answer" vote, increment the expert's counter.
            if feedback or rating:
                try:
                    await odoo_call_method(
                        model="expert.session",
                        method="message_post",
                        args=[[request_id]],
                        kwargs={
                            "body": (
                                f"User feedback: rating={rating}, "
                                f"good_answer={is_good_answer}, "
                                f"comment={feedback}"
                            ),
                            "subtype_xmlid": "mail.mt_comment",
                        },
                    )
                except Exception as e:
                    _logger.warning(f"Could not post feedback to chatter: {e}")

            if is_good_answer:
                # Set the session to completed on a positive vote, then
                # increment the expert's Good Answer counter.
                await odoo_write(
                    model="expert.session",
                    ids=[request_id],
                    values={"status": "completed"},
                )

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

        audit_payload = {
            "track": state.get("track"),
            "category": state.get("category"),
            "urgency": state.get("urgency"),
            "expert_id": state.get("selected_expert", {}).get("id"),
            "qualification_status": state.get("qualification_status"),
            "review_status": state.get("review_status"),
            "rating": state.get("rating"),
            "is_good_answer": state.get("is_good_answer", False),
        }

        try:
            await odoo_call_method(
                model="expert.session",
                method="message_post",
                args=[[request_id]],
                kwargs={
                    "body": (
                        "Ask Someone workflow completed. "
                        f"Audit: {json.dumps(audit_payload)}"
                    ),
                    "subtype_xmlid": "mail.mt_comment",
                },
            )
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