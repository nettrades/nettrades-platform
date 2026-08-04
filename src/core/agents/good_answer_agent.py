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
#
# INTEGRATION:
#   - Uses odoo_tools.py to interact with Odoo's nettrades_good_answer models
#   - Reports back to the supervisor with the best answer
#
# UPDATES (2026-08-04):
#   - Updated model names to match actual Odoo models:
#       * llm_feedback (was nettrades_good_answer.answer)
#       * good_answer_vote (for votes)
# =============================================================================

import json
import logging
from datetime import datetime
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
    """
    pass


def create_good_answer_agent() -> StateGraph:
    """
    Build and return a compiled Good Answer sub-graph.

    The workflow consists of five nodes:
    1. collect_answers - Collect multiple answers from Odoo or other sources
    2. vote_answers - Allow users to vote on answers
    3. calculate_quality - Calculate quality scores using AI
    4. verify_answer - Verify the answer using AI or human review
    5. record_best_answer - Record the best answer in Odoo

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
                fields=["id", "answer", "quality_score", "is_verified"],
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
                        },
                    )

                # Re-fetch to get the newly created answers
                existing_answers = await odoo_search(
                    model="llm_feedback",
                    domain=[("question", "ilike", question[:50])],
                    fields=["id", "answer", "quality_score", "is_verified"],
                    limit=10,
                )

            state["answers"] = existing_answers
            _logger.info(f"Collected {len(existing_answers)} answers")

        except Exception as e:
            _logger.error(f"Answer collection failed: {e}")
            state["answers"] = []

        return state

    # =========================================================================
    # NODE 2: Vote Answers
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
                fields=["id", "answer", "quality_score", "is_verified"],
            )
            state["answers"] = updated_answers
            _logger.info("Votes recorded successfully")

        except Exception as e:
            _logger.error(f"Vote processing failed: {e}")

        return state

    # =========================================================================
    # NODE 3: Calculate Quality
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
    # NODE 4: Verify Answer
    # =========================================================================

    async def verify_answer(state: GoodAnswerState) -> GoodAnswerState:
        """
        Verify the best answer using AI or human review.
        """
        answers = state.get("answers", [])
        question = state.get("question", "")

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
            # Use AI to verify the answer
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

            # Update Odoo
            await odoo_write(
                model="llm_feedback",
                ids=[best_answer.get("id")],
                values={"is_verified": is_verified},
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
    # NODE 5: Record Best Answer
    # =========================================================================

    async def record_best_answer(state: GoodAnswerState) -> GoodAnswerState:
        """
        Record the best answer in Odoo for future reference.
        """
        question = state.get("question", "")
        best_answer = state.get("best_answer", "")

        if not best_answer:
            _logger.warning("No best answer to record")
            return state

        _logger.info("Recording best answer in Odoo")

        try:
            # Use the good_answer_record_best helper
            quality_score = state.get("quality_score", 0.0)
            is_verified = state.get("is_verified", False)

            feedback_id = await good_answer_record_best(
                question=question,
                answer=best_answer,
                quality_score=quality_score,
                is_verified=is_verified,
            )

            _logger.info(f"Best answer recorded with ID: {feedback_id}")

        except Exception as e:
            _logger.error(f"Best answer recording failed: {e}")

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(GoodAnswerState)

    workflow.add_node("collect_answers", collect_answers)
    workflow.add_node("vote_answers", vote_answers)
    workflow.add_node("calculate_quality", calculate_quality)
    workflow.add_node("verify_answer", verify_answer)
    workflow.add_node("record_best_answer", record_best_answer)

    workflow.add_edge(START, "collect_answers")
    workflow.add_edge("collect_answers", "vote_answers")
    workflow.add_edge("vote_answers", "calculate_quality")
    workflow.add_edge("calculate_quality", "verify_answer")
    workflow.add_edge("verify_answer", "record_best_answer")
    workflow.add_edge("record_best_answer", END)

    return workflow.compile()