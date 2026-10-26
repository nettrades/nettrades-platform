#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Supervisor Agent
# =============================================================================
# FILE: src/core/supervisor.py
#
# PURPOSE:
#   The supervisor agent is the orchestrator for all LangGraph agents.
#   It routes requests to the appropriate sub-agent based on intent,
#   handles error recovery, and integrates with the bridge and self-improving
#   systems.
#
# KEY FUNCTIONALITY:
#   1. Intent classification (recruitment, freelance, lead_gen, gpu_management,
#      medical, legal, action, vision, general)
#   2. Medical/legal multi-turn screening with follow-up questions
#   3. Routing to sub-agents (recruitment_agent, freelance_agent, etc.)
#   4. Bridge integration for hub-and-spoke routing
#   5. Self-improving loop integration for continuous learning
#   6. Episode recording for training data
#   7. Post-processing for self-improving loop after routing
#   8. Fallback detection: automatically notifies the user when the CPU model is used
#   9. Resolution detection: identifies when user problems are solved
#
# INTEGRATION POINTS:
#   - Odoo: Reads company-specific LLM configuration via LLMFactory
#   - Bridge: Routes requests to local or remote brain based on company settings
#   - Self-Improving: Records episodes for fine-tuning models
#
# =============================================================================

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any

from langgraph.graph import StateGraph, START

# -----------------------------------------------------------------------------
# Import sub-agent creators
# -----------------------------------------------------------------------------
from agents.recruitment_agent import create_recruitment_agent
from agents.freelance_agent import create_freelance_agent
from agents.lead_gen_agent import create_lead_gen_agent
from agents.gpu_management_agent import create_gpu_management_agent
from agents.vision_agent import create_vision_agent
from agents.action_agent import create_action_agent
from agents.ask_someone_agent import create_ask_someone_agent
from agents.good_answer_agent import create_good_answer_agent
from agents.gpu_marketplace_agent import create_gpu_marketplace_agent

# -----------------------------------------------------------------------------
# Import LLM Factory for dynamic provider selection
# -----------------------------------------------------------------------------
from tools.llm_factory import get_llm

# -----------------------------------------------------------------------------
# Import inference backend detection (unified module)
# -----------------------------------------------------------------------------
from tools import get_inference_backend

# -----------------------------------------------------------------------------
# Import bridge integration (hub-and-spoke routing)
# -----------------------------------------------------------------------------
from bridge_integration import BridgeService

# -----------------------------------------------------------------------------
# Import self-improving integration (continuous learning)
# -----------------------------------------------------------------------------
from self_improving_integration import SelfImprovingService, EpisodeData

# -----------------------------------------------------------------------------
# Import resilience utilities (retry and circuit breaker)
# -----------------------------------------------------------------------------
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from circuitbreaker import CircuitBreaker, CircuitBreakerError

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
_logger = logging.getLogger(__name__)

# Maximum follow-up rounds for medical/legal screening.
# This prevents infinite loops when the user is not providing enough information.
MAX_FOLLOWUP_ROUNDS = 3


# =============================================================================
# CIRCUIT BREAKER FOR SUPERVISOR INVOCATION
# =============================================================================
class SupervisorCircuitBreaker(CircuitBreaker):
    """Custom circuit breaker for supervisor graph calls."""
    pass


_supervisor_breaker = SupervisorCircuitBreaker(failure_threshold=5, recovery_timeout=30)


# =============================================================================
# RESILIENT INVOCATION WRAPPER
# =============================================================================
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, asyncio.TimeoutError)),
    reraise=True,
)
async def invoke_supervisor_with_retry(
    supervisor,
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Wrapper that adds retries and circuit breaker protection to supervisor.ainvoke.

    Args:
        supervisor: The compiled LangGraph supervisor graph.
        state: The state dictionary to pass to the graph.
        config: Optional config dictionary (e.g., {"configurable": {"thread_id": "..."}})
                for checkpointing.

    Returns:
        Dict[str, Any]: The result from the supervisor graph.

    Raises:
        CircuitBreakerError: If the circuit breaker is open.
        Exception: Any other exception from the graph invocation.
    """
    async def _invoke():
        return await supervisor.ainvoke(state, config=config)

    try:
        return await _supervisor_breaker.call_async(_invoke)
    except CircuitBreakerError:
        _logger.error("Circuit breaker is open - supervisor invocation temporarily blocked.")
        raise


# =============================================================================
# CREATE SUB-AGENTS (Each is a compiled LangGraph sub-graph)
# =============================================================================
recruitment_agent = create_recruitment_agent()
freelance_agent = create_freelance_agent()
lead_gen_agent = create_lead_gen_agent()
gpu_management_agent = create_gpu_management_agent()
vision_agent = create_vision_agent()
action_agent = create_action_agent()
ask_someone_agent = create_ask_someone_agent()
good_answer_agent = create_good_answer_agent()
gpu_marketplace_agent = create_gpu_marketplace_agent()

_logger.info("All sub-agents loaded successfully")


# =============================================================================
# NODE 1: CLASSIFY INTENT
# =============================================================================
async def classify(state: dict) -> dict:
    """
    Classify the user's intent using the company's configured LLM.

    If an image is present in state, route directly to 'vision' without
    calling the LLM.

    Returns:
        dict: Updated state with 'intent' and 'followup_count' keys.
    """
    user_msg = state.get("messages", [{}])[-1].get("content", "")

    has_image = bool(state.get("image_base64", ""))
    if has_image:
        state["intent"] = "vision"
        state["followup_count"] = 0
        _logger.info("Image detected - routing to vision agent")
        return state

    company_id = state.get("company_id", 1)
    llm = get_llm(company_id=company_id, intent="classification")

    if not llm:
        _logger.error(f"No LLM available for company {company_id}")
        state["intent"] = "general"
        state["followup_count"] = 0
        state["screening_done"] = True
        return state

    prompt = (
        f"Classify the intent of the following message into one of: "
        f"recruitment, freelance, lead_gen, gpu_management, medical, legal, "
        f"action (robotic control), vision (image analysis), ask_someone "
        f"(expert consultation), good_answer (quality scoring), "
        f"gpu_marketplace (GPU booking), general. "
        f"Message: {user_msg}"
    )

    try:
        response = await llm.ainvoke(prompt)
        intent = response.content.strip().lower()
        _logger.info(f"Classified intent: {intent} (using company {company_id} LLM)")
        state["intent"] = intent
    except Exception as e:
        _logger.error(f"Intent classification failed: {e}")
        state["intent"] = "general"

    state["followup_count"] = 0
    state["screening_done"] = False
    return state


# =============================================================================
# NODE 2: MEDICAL SCREENING
# =============================================================================
async def medical_screening(state: dict) -> dict:
    """
    Conduct medical/legal screening with follow-up questions.

    Loops back to this node via the conditional edge until screening is
    done or the maximum follow-up rounds are reached.
    """
    intent = state.get("intent", "general")

    if intent not in ("medical", "legal"):
        state["screening_done"] = True
        return state

    followup_count = state.get("followup_count", 0)
    if followup_count >= MAX_FOLLOWUP_ROUNDS:
        state["screening_done"] = True
        _logger.info(f"Maximum follow-up rounds reached ({MAX_FOLLOWUP_ROUNDS})")
        return state

    user_msg = state["messages"][-1]["content"]

    company_id = state.get("company_id", 1)
    llm = get_llm(company_id=company_id, intent="screening")

    if not llm:
        _logger.error(f"No LLM available for company {company_id}")
        state["screening_done"] = True
        return state

    prompt = (
        f"You are a clinical screening assistant. The user has asked: '{user_msg}'\n"
        f"Determine whether enough information is present to provide a safe answer. "
        f"If comorbidities or medication interactions might be relevant, ask the user "
        f"about them. If the question is clear and complete, respond with 'SUFFICIENT'."
    )

    try:
        response = await llm.ainvoke(prompt)
        answer = response.content.strip()

        if "SUFFICIENT" in answer.upper():
            state["screening_done"] = True
            _logger.info("Medical screening complete - sufficient information")
        else:
            state["messages"].append({"role": "assistant", "content": answer})
            state["followup_count"] = followup_count + 1
            state["screening_done"] = False
            _logger.info(f"Medical screening follow-up {state['followup_count']}")
    except Exception as e:
        _logger.error(f"Medical screening failed: {e}")
        state["screening_done"] = True

    return state


# =============================================================================
# NODE 3: BRIDGE ROUTE
# =============================================================================
async def bridge_route(state: dict) -> dict:
    """
    Check if the request should be routed to the remote brain via the bridge.
    """
    intent = state.get("intent", "general")
    company_id = state.get("company_id")

    bridge = BridgeService()
    try:
        bridge_result = await bridge.route_request(intent, state, company_id)
        if bridge_result and bridge_result.get("source") != "local":
            state["route_source"] = "remote"
            state["bridge_response"] = bridge_result
            _logger.info(f"Request routed remotely via bridge for intent: {intent}")
        else:
            state["route_source"] = "local"
            state["bridge_response"] = None
            _logger.info(f"Request routed locally for intent: {intent}")
    except Exception as e:
        _logger.warning(f"Bridge route failed: {e}. Falling back to local.")
        state["route_source"] = "local"
        state["bridge_response"] = None

    return state


# =============================================================================
# NODE 4: ROUTE (Dispatch to Sub-Agent)
# =============================================================================
async def route(state: dict) -> dict:
    """
    Route the request to the appropriate sub-agent based on intent.

    If the bridge already provided a response, that is used directly.
    Otherwise the request is dispatched to the sub-agent that matches the
    intent, with a general-LLM fallback for unclassified intents.
    """
    if not state.get("screening_done", True):
        return state

    if state.get("route_source") == "remote" and state.get("bridge_response"):
        _logger.info("Using bridge response for intent: %s", state.get("intent"))
        state.update(state["bridge_response"])
        return state

    backend_info = get_inference_backend()
    if backend_info.get("type") == "cpu":
        if not state.get("fallback_notified", False):
            fallback_msg = (
                " **Note:** The primary GPU accelerated AI model is currently unavailable. "
                "I'm using a smaller CPU-based model for now. This may affect the quality of responses. "
                "If you need a more accurate answer, you can ask a human expert."
            )
            state["messages"].append({"role": "assistant", "content": fallback_msg})
            state["fallback_notified"] = True
            state["fallback_used"] = True
            _logger.info("Fallback backend notification added to conversation.")
    else:
        if state.get("fallback_notified", False):
            state["fallback_notified"] = False
            state["fallback_used"] = False

    intent = state.get("intent", "general")
    _logger.info(f"Routing intent: {intent}")

    try:
        # Marketplace must be checked before the generic GPU branch,
        # otherwise "gpu_marketplace" matches "gpu" and never reaches
        # the marketplace agent.
        if "marketplace" in intent or ("gpu" in intent and "book" in intent):
            result = await gpu_marketplace_agent.ainvoke(state)
        elif "recruit" in intent:
            result = await recruitment_agent.ainvoke(state)
        elif "freelance" in intent or "project" in intent:
            result = await freelance_agent.ainvoke(state)
        elif "lead" in intent:
            result = await lead_gen_agent.ainvoke(state)
        elif "gpu" in intent or "cluster" in intent:
            result = await gpu_management_agent.ainvoke(state)
        elif "vision" in intent:
            result = await vision_agent.ainvoke(state)
        elif "action" in intent:
            result = await action_agent.ainvoke(state)
        elif "ask" in intent and ("someone" in intent or "expert" in intent):
            result = await ask_someone_agent.ainvoke(state)
        elif "good" in intent and "answer" in intent:
            result = await good_answer_agent.ainvoke(state)
        else:
            company_id = state.get("company_id", 1)
            llm = get_llm(company_id=company_id, intent="general")
            if llm:
                user_msg = state.get("messages", [{}])[-1].get("content", "")
                response = await llm.ainvoke(user_msg)
                result = {"analysis": response.content}
            else:
                result = {"analysis": "I'm sorry, I couldn't process your request."}

        state.update(result)
        _logger.info(f"Routing completed for intent: {intent}")
    except Exception as e:
        _logger.error(f"Routing failed: {e}")
        state["error"] = str(e)
        state["analysis"] = f"An error occurred: {str(e)}"

    return state


# =============================================================================
# NODE 5: POST-PROCESS (Self-Improving Loop Integration)
# =============================================================================
async def post_process(state: dict) -> dict:
    """
    Post-process the response and record an episode for the self-improving loop.
    """
    if state.get("route_source") == "remote":
        _logger.info("Skipping self-improving recording for remote request")
        return state

    intent = state.get("intent", "general")

    quality_score = 0.5
    if "confidence" in state:
        quality_score = state.get("confidence", 0.5)
    elif "analysis" in state:
        analysis = state.get("analysis", "")
        if len(analysis) > 100:
            quality_score = 0.7
        elif len(analysis) > 50:
            quality_score = 0.5
        else:
            quality_score = 0.3

    if state.get("fallback_used", False):
        quality_score = min(quality_score, 0.6)

    thread_id = state.get("thread_id", "")
    resolution_status = None
    conversation = state.get("messages", [])

    if thread_id and conversation:
        self_improving = SelfImprovingService()
        if self_improving.detect_resolution(thread_id, conversation):
            resolution_status = "resolved"
            _logger.info(f"Problem resolved for thread: {thread_id}")
        else:
            resolution_status = "unresolved"

    track = state.get("track", "community")
    data_classification = state.get("data_classification", "public")

    if not state.get("track"):
        regulated_intents = ["medical", "legal", "financial"]
        track = "regulated" if intent in regulated_intents else "community"

    if not state.get("data_classification"):
        if track == "regulated":
            data_classification = "restricted"
        elif "gpu" in intent or "cluster" in intent:
            data_classification = "confidential"
        else:
            data_classification = "public"

    self_improving = SelfImprovingService()

    try:
        messages = state.get("messages", [])
        input_text = ""
        output_text = state.get("analysis", "")

        if messages:
            last_user_msg = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_msg = msg
                    break
            if last_user_msg:
                input_text = last_user_msg.get("content", "")

        episode_id = await self_improving.record_episode(
            intent=intent,
            input_data={"messages": messages, "user_id": state.get("user_id")},
            output_data={"analysis": output_text},
            quality_score=quality_score,
            feedback=state.get("feedback", {}),
            partner_id=state.get("user_id"),
            track=track,
            data_classification=data_classification,
        )

        if episode_id:
            _logger.info(
                f"Episode recorded for self-improving loop "
                f"(intent: {intent}, quality: {quality_score:.2f}, "
                f"resolution: {resolution_status})"
            )
        else:
            _logger.warning("Failed to record episode for self-improving")

    except Exception as e:
        _logger.warning(f"Failed to record episode for self-improving: {e}")

    return state


# =============================================================================
# CONDITIONAL EDGE FOR MEDICAL SCREENING
# =============================================================================
def should_continue_screening(state: dict) -> str:
    """Decide whether to loop back to medical_screening or proceed to bridge_route."""
    if state.get("screening_done", True):
        return "bridge_route"
    return "medical_screening"


# =============================================================================
# BUILD THE WORKFLOW
# =============================================================================
def build_supervisor_workflow():
    """
    Build the complete LangGraph workflow for the supervisor.

    Flow:
      1. classify -> classify the user's intent
      2. medical_screening -> multi-turn screening for medical/legal
      3. bridge_route -> local vs remote brain
      4. route -> dispatch to the appropriate sub-agent
      5. post_process -> record for the self-improving loop
    """
    workflow = StateGraph(dict)

    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("bridge_route", bridge_route)
    workflow.add_node("route", route)
    workflow.add_node("post_process", post_process)

    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "medical_screening")
    workflow.add_conditional_edges(
        "medical_screening",
        should_continue_screening,
        {
            "medical_screening": "medical_screening",
            "bridge_route": "bridge_route",
        },
    )
    workflow.add_edge("bridge_route", "route")
    workflow.add_edge("route", "post_process")
    workflow.add_edge("post_process", "__end__")

    return workflow


# =============================================================================
# PUBLIC API: build_supervisor (for app.py)
# =============================================================================
def build_supervisor(checkpointer=None):
    """
    Public API for building the supervisor.

    Args:
        checkpointer: Optional checkpointer instance. If provided, it is
                      passed to compile(). If None, the graph is compiled
                      without a checkpointer.

    Returns:
        StateGraph: The compiled supervisor workflow.
    """
    workflow = build_supervisor_workflow()
    return workflow.compile(checkpointer=checkpointer)


# =============================================================================
# MAIN ENTRY POINT (for testing)
# =============================================================================
if __name__ == "__main__":
    print("Building supervisor...")
    supervisor = build_supervisor()
    print("Supervisor built successfully!")