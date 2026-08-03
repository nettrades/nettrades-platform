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
#
# INTEGRATION POINTS:
#   - Odoo: Reads company-specific LLM configuration via LLMFactory
#   - Bridge: Routes requests to local or remote brain based on company settings
#   - Self-Improving: Records episodes for fine-tuning models
#   - GPUStack: Uses configured LLM provider (OpenAI, Anthropic, DeepSeek, Ollama,
#     NETTRADES.AI)
#   - llama.cpp: Used as fallback when GPUStack is unavailable
#
# =============================================================================

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any

from langgraph.graph import StateGraph, START
from langgraph.checkpoint.postgres import PostgresSaver

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
from self_improving_integration import SelfImprovingService

# -----------------------------------------------------------------------------
# Import resilience utilities (retry and circuit breaker)
# -----------------------------------------------------------------------------
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from circuitbreaker import CircuitBreaker, CircuitBreakerError

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
_logger = logging.getLogger(__name__)

# Maximum follow-up rounds for medical/legal screening
# This prevents infinite loops when the user is not providing enough information.
MAX_FOLLOWUP_ROUNDS = 3

# =============================================================================
# CIRCUIT BREAKER FOR SUPERVISOR INVOCATION
# =============================================================================
class SupervisorCircuitBreaker(CircuitBreaker):
    """Custom circuit breaker for supervisor graph calls."""
    pass

# Create a singleton circuit breaker with default settings
# (failure threshold = 5, recovery timeout = 30 seconds)
_supervisor_breaker = SupervisorCircuitBreaker(failure_threshold=5, recovery_timeout=30)

# =============================================================================
# RESILIENT INVOCATION WRAPPER (FIXED: added config parameter)
# =============================================================================
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, asyncio.TimeoutError)),
    reraise=True
)
async def invoke_supervisor_with_retry(
    supervisor,
    state: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Wrapper that adds retries and circuit breaker protection to supervisor.ainvoke.

    This function is used by the `/invoke` endpoint in app.py to provide resilience.

    Args:
        supervisor: The compiled LangGraph supervisor graph.
        state: The state dictionary to pass to the graph.
        config: Optional config dictionary (e.g., {"configurable": {"thread_id": "..."}})
                for checkpointing. This is required when using a checkpointer.

    Returns:
        Dict[str, Any]: The result from the supervisor graph.

    Raises:
        CircuitBreakerError: If the circuit breaker is open.
        Exception: Any other exception from the graph invocation.
    """
    async def _invoke():
        return await supervisor.ainvoke(state, config=config)

    try:
        result = await _supervisor_breaker.call_async(_invoke)
        return result
    except CircuitBreakerError:
        _logger.error("Circuit breaker is open - supervisor invocation temporarily blocked.")
        raise

# =============================================================================
# CREATE SUB-AGENTS (Each is a compiled LangGraph sub-graph)
# =============================================================================
# The supervisor uses these sub-agents to handle specific business domains.
# Each sub-agent is created by its factory function and returns a compiled
# graph with an .ainvoke() method.
recruitment_agent = create_recruitment_agent()
freelance_agent = create_freelance_agent()
lead_gen_agent = create_lead_gen_agent()
gpu_management_agent = create_gpu_management_agent()
vision_agent = create_vision_agent()
action_agent = create_action_agent()
ask_someone_agent = create_ask_someone_agent()
good_answer_agent = create_good_answer_agent()
gpu_marketplace_agent = create_gpu_marketplace_agent()

_logger.info("??? All sub-agents loaded successfully")

# =============================================================================
# NODE 1: CLASSIFY INTENT
# =============================================================================
async def classify(state: dict) -> dict:
    """
    Classify the user's intent using the company's configured LLM.

    This node:
    1. Extracts the last user message from the state
    2. Checks if an image was uploaded (for vision agent)
    3. Gets the company-specific LLM from the factory
    4. Constructs a prompt for intent classification
    5. Calls the LLM to classify the intent
    6. Stores the intent and initialises followup_count in the state

    The possible intents are:
    - recruitment: job recruitment and candidate search
    - freelance: freelance project matching
    - lead_gen: lead generation from external feeds
    - gpu_management: GPU cluster management
    - medical: medical consultation (requires screening)
    - legal: legal consultation (requires screening)
    - action: robotic action control (VLA)
    - vision: image analysis (VLM)
    - general: general conversation (fallback)

    If an image is present, the intent is forced to 'vision' without calling the LLM.

    Returns:
        dict: Updated state with 'intent' and 'followup_count' keys.
    """
    # Get the last user message from the conversation history
    # The state['messages'] list contains all messages in the conversation.
    user_msg = state.get("messages", [{}])[-1].get("content", "")

    # Check if an image was uploaded (from the chat UI via base64 encoding)
    has_image = bool(state.get("image_base64", ""))

    # If an image is present, route directly to the vision agent without classification
    if has_image:
        state["intent"] = "vision"
        state["followup_count"] = 0
        _logger.info("Image detected - routing to vision agent")
        return state

    # Retrieve the company-specific LLM using the LLMFactory.
    # The LLM is selected based on the company's configuration in Odoo.
    company_id = state.get("company_id", 1)  # Default to ID 1 if not provided
    llm = get_llm(company_id=company_id, intent="classification")

    # If no LLM is available, fallback to general intent.
    if not llm:
        _logger.error(f"No LLM available for company {company_id}")
        state["intent"] = "general"
        state["followup_count"] = 0
        state["screening_done"] = True
        return state

    # Build the classification prompt
    # The LLM must choose from a predefined set of intents.
    prompt = (
        f"Classify the intent of the following message into one of: "
        f"recruitment, freelance, lead_gen, gpu_management, medical, legal, "
        f"action (robotic control), vision (image analysis), general. "
        f"ask_someone (expert consultation), good_answer (quality scoring), "
        f"gpu_marketplace (GPU booking), general. "
        f"Message: {user_msg}"    
    )

    # Call the LLM with the prompt and extract the intent.
    try:
        response = await llm.ainvoke(prompt)
        intent = response.content.strip().lower()
        _logger.info(f"Classified intent: {intent} (using company {company_id} LLM)")
        state["intent"] = intent
    except Exception as e:
        _logger.error(f"Intent classification failed: {e}")
        state["intent"] = "general"

    # Initialise follow-up count for medical/legal screening
    state["followup_count"] = 0
    state["screening_done"] = False
    return state

# =============================================================================
# NODE 2: MEDICAL SCREENING
# =============================================================================
async def medical_screening(state: dict) -> dict:
    """
    Conduct medical/legal screening with follow-up questions.

    This node handles multi-turn screening for medical and legal intents.
    It asks clarifying questions to ensure the user has provided enough
    information to give a safe and accurate response.

    The screening process:
    1. Check if the intent is medical or legal; if not, mark screening as done.
    2. Check if the maximum follow-up rounds (3) have been reached.
    3. Construct a prompt to determine if sufficient information is present.
    4. If the LLM responds with 'SUFFICIENT', mark screening as done.
    5. Otherwise, ask a follow-up question and increment the follow-up count.

    The graph loops back to this node when a follow-up is needed (via the
    conditional edge `should_continue_screening`).

    Returns:
        dict: Updated state with 'screening_done' and possibly a follow-up message.
    """
    intent = state.get("intent", "general")

    # Only screen medical and legal intents
    if intent not in ("medical", "legal"):
        state["screening_done"] = True
        return state

    # Check if we've reached the maximum allowed follow-up rounds
    followup_count = state.get("followup_count", 0)
    if followup_count >= MAX_FOLLOWUP_ROUNDS:
        state["screening_done"] = True
        _logger.info(f"Maximum follow-up rounds reached ({MAX_FOLLOWUP_ROUNDS})")
        return state

    # Get the last user message for screening
    user_msg = state["messages"][-1]["content"]

    # Get the company-specific LLM for screening
    company_id = state.get("company_id", 1)
    llm = get_llm(company_id=company_id, intent="screening")

    if not llm:
        _logger.error(f"No LLM available for company {company_id}")
        state["screening_done"] = True
        return state

    # Construct the screening prompt
    # The LLM is asked to determine if the user's question is complete enough.
    # If not, it should ask a follow-up question about comorbidities or interactions.
    prompt = (
        f"You are a clinical screening assistant. The user has asked: '{user_msg}'\n"
        f"Determine whether enough information is present to provide a safe answer. "
        f"If comorbidities or medication interactions might be relevant, ask the user "
        f"about them. If the question is clear and complete, respond with 'SUFFICIENT'."
    )

    # Call the LLM for screening
    try:
        response = await llm.ainvoke(prompt)
        answer = response.content.strip()

        if "SUFFICIENT" in answer.upper():
            # The question is complete; mark screening as done
            state["screening_done"] = True
            _logger.info("Medical screening complete - sufficient information")
        else:
            # More information is needed; ask a follow-up question
            # Append the assistant's follow-up message to the conversation
            state["messages"].append({
                "role": "assistant",
                "content": answer
            })
            state["followup_count"] = followup_count + 1
            state["screening_done"] = False
            _logger.info(f"Medical screening follow-up {state['followup_count']}")
    except Exception as e:
        _logger.error(f"Medical screening failed: {e}")
        # On error, mark screening as done to avoid infinite loops
        state["screening_done"] = True

    return state

# =============================================================================
# NODE 3: BRIDGE ROUTE (Hub-and-Spoke Routing)
# =============================================================================
async def bridge_route(state: dict) -> dict:
    """
    Check if the request should be routed to the remote brain via the bridge.

    This node integrates the nettrades_bridge module, which decides whether the
    current request should be processed locally (by the company's own LangGraph
    agents) or forwarded to the remote NETTRADES.AI brain.

    The decision is based on:
    - Company-specific feature flags (e.g., enable_remote_recruitment)
    - GPU overflow detection (local GPU utilisation > threshold)
    - Bridge mode (local, remote, hybrid)

    If the bridge decides to route remotely, it returns a bridge_response that
    is used directly by the route node, bypassing local sub-agents.

    Returns:
        dict: Updated state with 'bridge_response' and 'route_source' keys.
    """
    intent = state.get("intent", "general")
    company_id = state.get("company_id")

    # Instantiate the bridge service (fallback if module not found)
    bridge = BridgeService()

    try:
        # Call the bridge service to determine routing
        bridge_result = await bridge.route_request(intent, state, company_id)

        if bridge_result and bridge_result.get('source') != 'local':
            # The bridge decided to route remotely
            state["route_source"] = "remote"
            state["bridge_response"] = bridge_result
            _logger.info(f"Request routed remotely via bridge for intent: {intent}")
        else:
            # Process locally
            state["route_source"] = "local"
            state["bridge_response"] = None
            _logger.info(f"Request routed locally for intent: {intent}")
    except Exception as e:
        # If bridge fails, fallback to local processing
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

    This node is the main dispatcher. It checks:
    1. If screening is complete (for medical/legal intents)
    2. If the bridge already handled the request (use bridge_response)
    3. If not, it dispatches to the appropriate sub-agent based on intent
    4. Additionally, it detects if the inference backend is a CPU fallback
       and notifies the user accordingly.

    The mapping of intents to sub-agents is:
    - recruitment -> Recruitment Agent
    - freelance -> Freelance Agent
    - lead_gen -> Lead Generation Agent
    - gpu_management -> GPU Management Agent
    - vision -> Vision Agent
    - action -> Action Agent
    - medical/legal -> General LLM (after screening)
    - general -> General LLM (fallback)

    If the bridge already provided a response, it is used directly without
    calling a sub-agent.

    Returns:
        dict: Updated state with the result from the sub-agent or bridge.
    """
    # If screening is not complete, don't route yet (graph will loop back)
    if not state.get("screening_done", True):
        return state

    # If the bridge already handled it, use that response
    if state.get("route_source") == "remote" and state.get("bridge_response"):
        _logger.info("Using bridge response for intent: %s", state.get("intent"))
        state.update(state["bridge_response"])
        return state

    # --- Fallback detection and notification ---
    # Check the inference backend type
    backend_info = get_inference_backend()
    if backend_info.get("type") == "cpu":
        # If we haven't notified the user yet about the fallback, do so now
        if not state.get("fallback_notified", False):
            fallback_msg = (
                " **Note:** The primary GPU accelerated AI model is currently unavailable. "
                "I'm using a smaller CPU‑based model for now. This may affect the quality of responses. "
                "If you need a more accurate answer, you can ask a human expert."
            )
            state["messages"].append({
                "role": "assistant",
                "content": fallback_msg
            })
            state["fallback_notified"] = True
            state["fallback_used"] = True
            _logger.info("Fallback backend notification added to conversation.")
    else:
        # If GPUStack is healthy, ensure the fallback notification is cleared
        # (so that if it recovers, the message won't be shown again)
        if state.get("fallback_notified", False):
            # We could optionally remove the message, but it's okay to keep it.
            # Just reset the flag so that if it fails again, we will re-notify.
            state["fallback_notified"] = False
            state["fallback_used"] = False
        # We don't add a "GPU restored" message automatically; the user will see better responses.

    # Continue with normal routing
    intent = state.get("intent", "general")
    _logger.info(f"Routing intent: {intent}")

    try:
        # Dispatch to the appropriate sub-agent based on intent
        if "recruit" in intent:
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
	elif "marketplace" in intent or "gpu" in intent and "book" in intent:
            result = await gpu_marketplace_agent.ainvoke(state)
        else:
            # Fallback to the company-specific LLM for unclassified intents
            company_id = state.get("company_id", 1)
            llm = get_llm(company_id=company_id, intent="general")
            if llm:
                user_msg = state.get("messages", [{}])[-1].get("content", "")
                response = await llm.ainvoke(user_msg)
                result = {"analysis": response.content}
            else:
                result = {"analysis": "I'm sorry, I couldn't process your request."}

        # Merge the result into the state
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
    Post-process the response and record for the self-improving loop.

    This node records every interaction episode for the self-improving loop.
    It:
    1. Skips recording if the request was handled remotely (no local data)
    2. Calculates a quality score based on confidence or analysis length
    3. Records the episode via SelfImprovingService

    The recorded episodes are used to:
    - Build training datasets for fine-tuning
    - Detect edge cases and low-quality responses
    - Trigger the self-improving loop when thresholds are met

    Returns:
        dict: Updated state (unchanged, but episode is recorded asynchronously).
    """
    # Only record local requests for self-improving
    # (remote requests are recorded at the hub)
    if state.get("route_source") == "remote":
        _logger.info("Skipping self-improving recording for remote request")
        return state

    intent = state.get("intent", "general")

    # Calculate a quality score (simplified heuristic)
    quality_score = 0.5  # Default
    if "confidence" in state:
        quality_score = state.get("confidence", 0.5)
    elif "analysis" in state:
        # Simple heuristic: longer analysis = higher confidence
        analysis = state.get("analysis", "")
        if len(analysis) > 100:
            quality_score = 0.7
        elif len(analysis) > 50:
            quality_score = 0.5
        else:
            quality_score = 0.3

    # Optionally adjust quality down if fallback was used
    if state.get("fallback_used", False):
        quality_score = min(quality_score, 0.6)  # cap quality to reflect lower model capability

    # Get the self-improving service
    self_improving = SelfImprovingService()

    try:
        # Record the episode asynchronously
        await self_improving.record_episode(
            intent=intent,
            input_data=state.get("messages", [{}])[-1],
            output_data={
                "analysis": state.get("analysis", ""),
                "intent": intent,
                "route_source": state.get("route_source", "local"),
                "fallback_used": state.get("fallback_used", False)
            },
            quality_score=quality_score,
            feedback=state.get("feedback", {})
        )
        _logger.info(f"Episode recorded for self-improving loop (intent: {intent}, quality: {quality_score:.2f})")
    except Exception as e:
        _logger.warning(f"Failed to record episode for self-improving: {e}")

    return state

# =============================================================================
# CONDITIONAL EDGE FOR MEDICAL SCREENING
# =============================================================================
def should_continue_screening(state: dict) -> str:
    """
    Determine whether to continue medical screening or proceed to routing.

    This conditional edge is used by the LangGraph workflow to decide whether
    to loop back to medical_screening (if more information is needed) or
    proceed to bridge_route (if screening is complete).

    Args:
        state: The current state dictionary.

    Returns:
        str: 'medical_screening' to continue screening, or 'bridge_route' to proceed.
    """
    if state.get("screening_done", True):
        return "bridge_route"
    return "medical_screening"

# =============================================================================
# BUILD THE WORKFLOW
# =============================================================================
def build_supervisor_workflow():
    """
    Build the complete LangGraph workflow for the supervisor.

    The workflow flow:
    1. classify -> classify the user's intent
    2. medical_screening -> multi-turn screening for medical/legal (loops back if needed)
    3. bridge_route -> check if request should go remote (hub-and-spoke routing)
    4. route -> route to appropriate sub-agent (with fallback notification)
    5. post_process -> record for self-improving loop

    The graph uses a conditional edge from medical_screening to either loop back
    (follow-up) or proceed to bridge_route.

    Returns:
        StateGraph: The compiled LangGraph workflow.
    """
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("bridge_route", bridge_route)
    workflow.add_node("route", route)
    workflow.add_node("post_process", post_process)

    # Set entry point
    workflow.add_edge(START, "classify")

    # classify -> medical_screening
    workflow.add_edge("classify", "medical_screening")

    # medical_screening conditional: continue or done
    workflow.add_conditional_edges(
        "medical_screening",
        should_continue_screening,
        {
            "medical_screening": "medical_screening",
            "bridge_route": "bridge_route",
        }
    )

    # bridge_route -> route
    workflow.add_edge("bridge_route", "route")

    # route -> post_process
    workflow.add_edge("route", "post_process")

    # post_process -> END
    workflow.add_edge("post_process", "__end__")

    return workflow.compile()

# =============================================================================
# PUBLIC API: build_supervisor (for app.py)
# =============================================================================
def build_supervisor():
    """
    Public API for building the supervisor.

    This is the main entry point used by app.py to create the supervisor graph.

    Returns:
        StateGraph: The compiled supervisor workflow.
    """
    return build_supervisor_workflow()

# =============================================================================
# MAIN ENTRY POINT (for testing)
# =============================================================================
if __name__ == "__main__":
    # Simple test to verify the supervisor builds
    print("Building supervisor...")
    supervisor = build_supervisor()
    print("Supervisor built successfully!")