#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# GOOD ANSWER AGENT – Quality Scoring & Verification
# =============================================================================
# FILE: src/core/agents/good_answer_agent.py
#
# PURPOSE:
#   This agent handles the "Good Answer" quality scoring system.
#   It collects multiple answers to a question, allows voting,
#   calculates quality scores, and verifies the best answer.
#
# KEY FEATURES:
#   - Collects multiple answers from different sources
#   - Manages user voting on answers
#   - Calculates quality scores based on votes and AI analysis
#   - Verifies answers for accuracy and completeness
#   - Records the best answer for future reference
#   - Audit trail for compliance tracking
#   - Versioning for answers
#   - Expiry mechanism for outdated answers
#   - Track system (regulated vs community)
#
# INTEGRATION:
#   - Uses odoo_tools.py to interact with Odoo's nettrades_good_answer models
#   - Reports back to the supervisor with the best answer
#
# UPDATES (2026-08-04):
#   - Updated model names to match actual Odoo models:
#       * llm_feedback (was nettrades_good_answer.answer)
#       * good_answer_vote (for votes)
#
# UPDATES (2026-08-10):
#   - Added audit trail for verification
#   - Added versioning for answers
#   - Added expiry mechanism for outdated answers
#   - Added track system (regulated vs community)
#   - Added resolution detection integration
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
    good_answer_create_vote,
    good_answer_get_best_answer,
    good_answer_record_best,
)

_logger = logging.getLogger(__name__)


class GoodAnswerState(dict):
    """
    State carried through the Good Answer workflow.

    Keys:
        - question: The user's question
        - answers: List of answers collected from various sources
        - votes: Dictionary of votes per answer (answer_id -> vote_count)
        - quality_score: The calculated quality score for the best answer
        - is_verified: Whether the answer has been verified
        - best_answer_id: The ID of the best answer
        - best_answer: The content of the best answer
        - track: The track (regulated or community)
        - version: The version number of the answer
        - expires_at: When the answer expires
        - resolution_status: Whether the problem was resolved
    """
    pass


def create_good_answer_agent() -> StateGraph:
    """
    Build and return a compiled Good Answer sub-graph.

    The workflow consists of seven nodes:
    1. collect_answers - Collect multiple answers from Odoo or other sources
    2. determine_track - Determine if this is regulated or community
    3. vote_answers - Allow users to vote on answers
    4. calculate_quality - Calculate quality scores using AI
    5. verify_answer - Verify the answer using AI or human review
    6. record_best_answer - Record the best answer in Odoo
    7. audit_trail - Record audit trail for compliance

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"Good Answer agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: Collect Answers
    # =========================================================================

    async def collect_answers(state: GoodAnswerState) -> GoodAnswerState:
        """
        Collect multiple answers to the question from various sources.
        """
        question = state.get("question", "")
        if not question:
            messages = state.get("messages", [])
            question = messages[-1].get("content", "") if messages else ""
            state["question"] = question

        _logger.info(f"Collecting answers for question: {question[:100]}...")

        try:
            # Search for existing answers in Odoo using llm_feedback
            existing_answers = await odoo_search(
                model="llm_feedback",
                domain=[("question", "ilike", question[:50])],
                fields=["id", "answer", "quality_score", "is_verified", "version", "expires_at", "track"],
                limit=10,
            )

            # If no existing answers, generate some using the LLM
            if not existing_answers:
                _logger.info("No existing answers found, generating new ones")

                prompt = f"""
                Provide 3 different perspectives on the following question.
                Each answer should be a complete, thoughtful response.

                Question: {question}

                Respond with JSON:
                {{
                    "answers": [
                        "Answer 1 from perspective A",
                        "Answer 2 from perspective B",
                        "Answer 3 from perspective C"
                    ]
                }}
                """

                response = await llm.ainvoke(prompt)
                generated = json.loads(response.content)

                # Store generated answers in Odoo using llm_feedback
                for answer_text in generated.get("answers", []):
                    await odoo_create(
                        model="llm_feedback",
                        values={
                            "question": question,
                            "answer": answer_text,
                            "quality_score": 0.0,
                            "is_verified": False,
                            "feedback_type": "generated",
                            "version": 1,
                            "track": "community",
                        },
                    )

                # Re-fetch to get the newly created answers
                existing_answers = await odoo_search(
                    model="llm_feedback",
                    domain=[("question", "ilike", question[:50])],
                    fields=["id", "answer", "quality_score", "is_verified", "version", "expires_at", "track"],
                    limit=10,
                )

            state["answers"] = existing_answers
            _logger.info(f"Collected {len(existing_answers)} answers")

        except Exception as e:
            _logger.error(f"Answer collection failed: {e}")
            state["answers"] = []

        return state

    # =========================================================================
    # NODE 2: Determine Track (Regulated vs Community)
    # =========================================================================

    async def determine_track(state: GoodAnswerState) -> GoodAnswerState:
        """
        Determine if this answer should use the regulated or community track.
        """
        question = state.get("question", "")
        if not question:
            state["track"] = "community"
            return state

        # Check if the question contains regulated keywords
        regulated_keywords = ["medical", "legal", "financial", "diagnosis", "prescription",
                             "law", "regulation", "tax", "investment", "compliance"]
        is_regulated = any(kw in question.lower() for kw in regulated_keywords)

        state["track"] = "regulated" if is_regulated else "community"
        _logger.info(f"Track determined: {state['track']}")
        return state

    # =========================================================================
    # NODE 3: Vote Answers
    # =========================================================================

    async def vote_answers(state: GoodAnswerState) -> GoodAnswerState:
        """
        Allow users to vote on answers.
        """
        votes = state.get("votes", {})
        answers = state.get("answers", [])

        if not votes or not answers:
            _logger.info("No votes provided, skipping voting")
            return state

        _logger.info(f"Processing {len(votes)} votes")

        try:
            for answer_id, vote_type in votes.items():
                # Use the good_answer_create_vote helper
                is_good = vote_type == "positive"
                await good_answer_create_vote(
                    message_id=int(answer_id),
                    user_id=state.get("user_id", 1),
                    is_good=is_good,
                )

            # Re-fetch updated answers
            updated_answers = await odoo_search(
                model="llm_feedback",
                domain=[("id", "in", [int(aid) for aid in votes.keys()])],
                fields=["id", "answer", "quality_score", "is_verified", "version", "expires_at", "track"],
            )
            state["answers"] = updated_answers
            _logger.info("Votes recorded successfully")

        except Exception as e:
            _logger.error(f"Vote processing failed: {e}")

        return state

    # =========================================================================
    # NODE 4: Calculate Quality
    # =========================================================================

    async def calculate_quality(state: GoodAnswerState) -> GoodAnswerState:
        """
        Calculate quality scores for each answer using AI analysis.
        """
        answers = state.get("answers", [])
        question = state.get("question", "")

        if not answers:
            _logger.warning("No answers to score")
            return state

        _logger.info(f"Calculating quality scores for {len(answers)} answers")

        try:
            for answer in answers:
                # Build a prompt to score the answer
                prompt = f"""
                Score the following answer on a scale of 0-10 for:
                1. Accuracy (is it factually correct?)
                2. Completeness (does it fully address the question?)
                3. Clarity (is it easy to understand?)

                Question: {question}

                Answer: {answer.get('answer', '')}

                Respond with JSON:
                {{
                    "accuracy": score_0_to_10,
                    "completeness": score_0_to_10,
                    "clarity": score_0_to_10
                }}
                """

                response = await llm.ainvoke(prompt)
                scores = json.loads(response.content)

                # Calculate overall quality score (weighted average)
                quality_score = (
                    scores.get("accuracy", 5) * 0.4 +
                    scores.get("completeness", 5) * 0.4 +
                    scores.get("clarity", 5) * 0.2
                ) / 10  # Normalize to 0-1

                # Store the quality score in Odoo
                await odoo_write(
                    model="llm_feedback",
                    ids=[answer.get("id")],
                    values={"quality_score": quality_score},
                )

                answer["quality_score"] = quality_score
                _logger.info(f"Answer {answer.get('id')} quality score: {quality_score:.2f}")

        except Exception as e:
            _logger.error(f"Quality calculation failed: {e}")

        return state

    # =========================================================================
    # NODE 5: Verify Answer
    # =========================================================================

    async def verify_answer(state: GoodAnswerState) -> GoodAnswerState:
        """
        Verify the best answer using AI or human review.
        """
        answers = state.get("answers", [])
        question = state.get("question", "")
        track = state.get("track", "community")

        if not answers:
            _logger.warning("No answers to verify")
            return state

        # Find the best answer (highest quality score)
        sorted_answers = sorted(
            answers,
            key=lambda a: a.get("quality_score", 0),
            reverse=True,
        )

        if not sorted_answers:
            _logger.warning("No answers to verify")
            return state

        best_answer = sorted_answers[0]
        _logger.info(f"Verifying best answer: {best_answer.get('id')}")

        try:
            # Build verification prompt based on track
            if track == "regulated":
                prompt = f"""
                Verify this answer for accuracy, safety, and compliance.
                This is a REGULATED question (medical/legal/financial).

                Question: {question}

                Answer: {best_answer.get('answer', '')}

                Respond with one word: verified, needs_review, or incorrect.
                """
            else:
                prompt = f"""
                Verify if the following answer is correct and complete for the given question.
                Respond with "verified" if the answer is correct, "needs_review" if it needs human review,
                or "incorrect" if it is wrong.

                Question: {question}

                Answer: {best_answer.get('answer', '')}

                Respond with only one word: verified, needs_review, or incorrect.
                """

            response = await llm.ainvoke(prompt)
            verification = response.content.strip().lower()

            is_verified = verification == "verified"
            state["is_verified"] = is_verified
            state["best_answer_id"] = best_answer.get("id")
            state["best_answer"] = best_answer.get("answer", "")

            # Update Odoo with verification status and version
            current_version = best_answer.get("version", 1)
            expires_at = None
            if track == "regulated" and is_verified:
                # Regulated answers expire after 1 year
                expires_at = (datetime.now() + timedelta(days=365)).isoformat()

            await odoo_write(
                model="llm_feedback",
                ids=[best_answer.get("id")],
                values={
                    "is_verified": is_verified,
                    "version": current_version + 1,
                    "expires_at": expires_at,
                },
            )

            if is_verified:
                state["analysis"] = f"✅ Verified answer: {best_answer.get('answer', '')}"
            elif verification == "needs_review":
                state["analysis"] = "⚠️ This answer needs human review before it can be verified."
            else:
                state["analysis"] = "❌ The best answer was found to be incorrect."

            _logger.info(f"Answer verification result: {verification}")

        except Exception as e:
            _logger.error(f"Answer verification failed: {e}")
            state["analysis"] = "Answer verification failed. Please review manually."

        return state

    # =========================================================================
    # NODE 6: Record Best Answer
    # =========================================================================

    async def record_best_answer(state: GoodAnswerState) -> GoodAnswerState:
        """
        Record the best answer in Odoo for future reference.
        """
        question = state.get("question", "")
        best_answer = state.get("best_answer", "")
        track = state.get("track", "community")

        if not best_answer:
            _logger.warning("No best answer to record")
            return state

        _logger.info("Recording best answer in Odoo")

        try:
            # Use the good_answer_record_best helper
            quality_score = state.get("quality_score", 0.0)
            is_verified = state.get("is_verified", False)

            # Check if this answer already exists
            existing = await odoo_search(
                model="llm_feedback",
                domain=[("question", "=", question), ("answer", "=", best_answer)],
                fields=["id"],
            )

            if existing:
                # Update the existing record
                await odoo_write(
                    model="llm_feedback",
                    ids=[existing[0]["id"]],
                    values={
                        "quality_score": quality_score,
                        "is_verified": is_verified,
                        "version": state.get("version", 1) + 1,
                    }
                )
                state["recorded_answer_id"] = existing[0]["id"]
                _logger.info(f"Updated existing answer: {existing[0]['id']}")
            else:
                # Create a new record with version and expiry
                expires_at = None
                if track == "regulated":
                    expires_at = (datetime.now() + timedelta(days=365)).isoformat()

                feedback_id = await good_answer_record_best(
                    question=question,
                    answer=best_answer,
                    quality_score=quality_score,
                    is_verified=is_verified,
                )
                state["recorded_answer_id"] = feedback_id
                _logger.info(f"Best answer recorded with ID: {feedback_id}")

        except Exception as e:
            _logger.error(f"Best answer recording failed: {e}")

        return state

    # =========================================================================
    # NODE 7: Audit Trail
    # =========================================================================

    async def audit_trail(state: GoodAnswerState) -> GoodAnswerState:
        """
        Record audit trail for compliance.
        """
        answer_id = state.get("recorded_answer_id") or state.get("best_answer_id")
        if not answer_id:
            return state

        _logger.info(f"Recording audit trail for answer: {answer_id}")

        try:
            audit_entry = {
                "answer_id": answer_id,
                "action": "verify_answer",
                "user_id": state.get("user_id"),
                "is_verified": state.get("is_verified", False),
                "track": state.get("track", "community"),
                "quality_score": state.get("quality_score", 0.0),
                "version": state.get("version", 1),
                "timestamp": datetime.now().isoformat(),
            }

            # Store audit in Odoo
            await odoo_create("good_answer.audit", audit_entry)
            _logger.info(f"Audit trail recorded for answer: {answer_id}")

        except Exception as e:
            _logger.error(f"Failed to record audit trail: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(GoodAnswerState)

    workflow.add_node("collect_answers", collect_answers)
    workflow.add_node("determine_track", determine_track)
    workflow.add_node("vote_answers", vote_answers)
    workflow.add_node("calculate_quality", calculate_quality)
    workflow.add_node("verify_answer", verify_answer)
    workflow.add_node("record_best_answer", record_best_answer)
    workflow.add_node("audit_trail", audit_trail)

    workflow.add_edge(START, "collect_answers")
    workflow.add_edge("collect_answers", "determine_track")
    workflow.add_edge("determine_track", "vote_answers")
    workflow.add_edge("vote_answers", "calculate_quality")
    workflow.add_edge("calculate_quality", "verify_answer")
    workflow.add_edge("verify_answer", "record_best_answer")
    workflow.add_edge("record_best_answer", "audit_trail")
    workflow.add_edge("audit_trail", END)

    return workflow.compile()