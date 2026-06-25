#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Supervisor Agent
# =============================================================================
# FILE: src/core/supervisor.py
#
# PURPOSE:
#   The supervisor agent is the orchestrator for all LangGraph agents.
#   It routes requests to the appropriate sub-agent based on intent,
#   handles error recovery, and integrates with the bridge and self-improving
#   systems.
#
# EXISTING FUNCTIONALITY (PRESERVED):
#   1. Intent classification (recruitment, freelance, lead_gen, gpu_management,
#      medical, legal, action, vision, general)
#   2. Medical/legal multi-turn screening with follow-up questions
#   3. Routing to sub-agents (recruitment_agent, freelance_agent, etc.)
#   4. LangGraph workflow with conditional edges
#
# NEW FUNCTIONALITY (ADDED):
#   1. Bridge integration for hub-and-spoke routing
#   2. Self-improving loop integration for continuous learning
#   3. Episode recording for training data
#   4. Bridge route decision before local processing
#   5. Post-processing for self-improving loop after routing
#
# =============================================================================

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, START
from langgraph.checkpoint import PostgresSaver

# -----------------------------------------------------------------------------
# Import sub-agent creators (EXISTING – all agent files exist)
# -----------------------------------------------------------------------------
from .agents.recruitment_agent import create_recruitment_agent
from .agents.freelance_agent import create_freelance_agent
from .agents.lead_gen_agent import create_lead_gen_agent
from .agents.gpu_management_agent import create_gpu_management_agent
from .agents.vision_agent import create_vision_agent
from .agents.action_agent import create_action_agent

# -----------------------------------------------------------------------------
# Import LLM for intent classification and medical screening
# -----------------------------------------------------------------------------
from langgraph.llm import create_llm

# -----------------------------------------------------------------------------
# Import bridge integration (NEW)
# -----------------------------------------------------------------------------
try:
    from .bridge_integration import BridgeService
except ImportError:
    # Fallback if the module doesn't exist yet
    class BridgeService:
        async def route_request(self, intent, data, company_id=None):
            return None

# -----------------------------------------------------------------------------
# Import self-improving integration (NEW)
# -----------------------------------------------------------------------------
try:
    from .self_improving_integration import SelfImprovingService
except ImportError:
    # Fallback if the module doesn't exist yet
    class SelfImprovingService:
        async def record_episode(self, intent, input_data, output_data, quality_score=0.5, feedback=None):
            pass

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
_logger = logging.getLogger(__name__)

# Maximum follow-up rounds for medical/legal screening
MAX_FOLLOWUP_ROUNDS = 3

# -----------------------------------------------------------------------------
# Create the LLM for intent classification and medical screening
# -----------------------------------------------------------------------------
llm = create_llm(provider="openai", model="gpt-4o-mini")


# =============================================================================
# CREATE SUB-AGENTS (EXISTING – all files exist and are complete)
# =============================================================================
recruitment_agent = create_recruitment_agent()
freelance_agent = create_freelance_agent()
lead_gen_agent = create_lead_gen_agent()
gpu_management_agent = create_gpu_management_agent()
vision_agent = create_vision_agent()
action_agent = create_action_agent()

_logger.info("✅ All sub-agents loaded successfully")


# =============================================================================
# NODE 1: CLASSIFY INTENT (EXISTING – PRESERVED)
# =============================================================================

async def classify(state: dict) -> dict:
    """
    Classify the user's intent using an LLM.

    This node:
    1. Extracts the last user message from the state
    2. Checks if an image was uploaded (for vision agent)
    3. Constructs a prompt for intent classification
    4. Calls the LLM to classify the intent
    5. Stores the intent and initialises followup_count in the state

    Returns:
        dict: Updated state with 'intent' and 'followup_count' keys.
    """
    # Get the last user message
    user_msg = state.get("messages", [{}])[-1].get("content", "")

    # Check if an image was uploaded (from the chat UI)
    has_image = bool(state.get("image_base64", ""))

    # If an image is present, route directly to the vision agent
    if has_image:
        state["intent"] = "vision"
        state["followup_count"] = 0
        _logger.info("Image detected – routing to vision agent")
        return state

    # Construct the classification prompt
    # The LLM must choose from a predefined set of intents
    prompt = (
        f"Classify the intent of the following message into one of: "
        f"recruitment, freelance, lead_gen, gpu_management, medical, legal, "
        f"action (robotic control), vision (image analysis), general. "
        f"Message: {user_msg}"
    )

    # Call the LLM for classification
    try:
        response = await llm.ainvoke(prompt)
        intent = response.content.strip().lower()
        _logger.info(f"Classified intent: {intent}")
        state["intent"] = intent
    except Exception as e:
        _logger.error(f"Intent classification failed: {e}")
        state["intent"] = "general"

    # Initialise follow-up count for medical/legal screening
    state["followup_count"] = 0
    state["screening_done"] = False

    return state


# =============================================================================
# NODE 2: MEDICAL SCREENING (EXISTING – PRESERVED)
# =============================================================================

async def medical_screening(state: dict) -> dict:
    """
    Conduct medical/legal screening with follow-up questions.

    This node:
    1. Checks if the intent is medical or legal
    2. If not, returns the state unchanged
    3. If the follow-up count has reached the maximum, marks screening as done
    4. Otherwise, asks the user a follow-up question if more information is needed
    5. If the question is complete, marks screening as done

    The screening is multi-turn: if the LLM determines that more information
    is needed, it asks a follow-up question and the graph loops back to
    this node (via a conditional edge in the graph).

    Returns:
        dict: Updated state with 'screening_done' and possibly a follow-up message.
    """
    intent = state.get("intent", "general")

    # Only screen medical and legal intents
    if intent not in ("medical", "legal"):
        state["screening_done"] = True
        return state

    # Check if we've reached the maximum follow-up rounds
    followup_count = state.get("followup_count", 0)
    if followup_count >= MAX_FOLLOWUP_ROUNDS:
        state["screening_done"] = True
        _logger.info(f"Maximum follow-up rounds reached ({MAX_FOLLOWUP_ROUNDS})")
        return state

    # Get the last user message for screening
    user_msg = state["messages"][-1]["content"]

    # Construct the screening prompt
    prompt = (
        f"You are a clinical screening assistant. The user has asked: '{user_msg}'.\n"
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
            _logger.info("Medical screening complete – sufficient information")
        else:
            # More information is needed; ask a follow-up question
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
# NODE 3: BRIDGE ROUTE (NEW – ADDED AFTER CLASSIFY)
# =============================================================================

async def bridge_route(state: dict) -> dict:
    """
    Check if the request should be routed to the remote brain via the bridge.

    This node:
    1. Gets the company ID from the state
    2. Calls the bridge service to determine routing
    3. If the bridge decides to route remotely, it stores the response
    4. If not, it marks the request for local processing

    Returns:
        dict: Updated state with 'bridge_response' and 'route_source' keys.
    """
    intent = state.get("intent", "general")
    company_id = state.get("company_id")

    # Get the bridge service
    bridge = BridgeService()

    try:
        # Call the bridge to determine routing
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
        # If bridge fails, fallback to local
        _logger.warning(f"Bridge route failed: {e}. Falling back to local.")
        state["route_source"] = "local"
        state["bridge_response"] = None

    return state


# =============================================================================
# NODE 4: ROUTE (EXISTING – MODIFIED TO HANDLE BRIDGE RESPONSE)
# =============================================================================

async def route(state: dict) -> dict:
    """
    Route the request to the appropriate sub-agent based on intent.

    This node:
    1. Checks if screening is complete (for medical/legal)
    2. If not, returns the state unchanged (the graph will loop back)
    3. If the bridge already handled the request, uses the bridge response
    4. Otherwise, dispatches to the appropriate sub-agent

    Returns:
        dict: Updated state with the result from the sub-agent.
    """
    # If screening is not complete, don't route yet
    if not state.get("screening_done", True):
        return state

    # If the bridge already handled it, use that response
    if state.get("route_source") == "remote" and state.get("bridge_response"):
        _logger.info("Using bridge response for intent: %s", state.get("intent"))
        state.update(state["bridge_response"])
        return state

    intent = state.get("intent", "general")
    _logger.info(f"Routing intent: {intent}")

    try:
        # Route to the appropriate sub-agent based on intent
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
        else:
            # Fallback to the general LLM for unclassified intents
            _logger.info(f"General intent fallback for: {intent}")
            user_msg = state.get("messages", [{}])[-1].get("content", "")
            response = await llm.ainvoke(user_msg)
            result = {"analysis": response.content}

        # Merge the result into the state
        state.update(result)
        _logger.info(f"Routing completed for intent: {intent}")

    except Exception as e:
        _logger.error(f"Routing failed: {e}")
        state["error"] = str(e)
        state["analysis"] = f"An error occurred: {str(e)}"

    return state


# =============================================================================
# NODE 5: POST-PROCESS (NEW – FOR SELF-IMPROVING LOOP)
# =============================================================================

async def post_process(state: dict) -> dict:
    """
    Post-process the response and record for the self-improving loop.

    This node:
    1. Extracts the intent and input/output data from the state
    2. Calculates a quality score (if not already present)
    3. Records the episode for the self-improving loop

    Returns:
        dict: Updated state (unchanged, but episode is recorded).
    """
    # Only record local requests for self-improving
    if state.get("route_source") == "remote":
        _logger.info("Skipping self-improving recording for remote request")
        return state

    intent = state.get("intent", "general")

    # Calculate a quality score (simplified)
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

    # Get the self-improving service
    self_improving = SelfImprovingService()

    try:
        await self_improving.record_episode(
            intent=intent,
            input_data=state.get("messages", [{}])[-1],
            output_data={
                "analysis": state.get("analysis", ""),
                "intent": intent,
                "route_source": state.get("route_source", "local")
            },
            quality_score=quality_score,
            feedback=state.get("feedback", {})
        )
        _logger.info(f"Episode recorded for self-improving loop (intent: {intent}, quality: {quality_score:.2f})")
    except Exception as e:
        _logger.warning(f"Failed to record episode for self-improving: {e}")

    return state


# =============================================================================
# CONDITIONAL EDGE FOR MEDICAL SCREENING (EXISTING – PRESERVED)
# =============================================================================

def should_continue_screening(state: dict) -> str:
    """
    Determine whether to continue medical screening or proceed to routing.

    This conditional edge is used to loop back to medical_screening
    when follow-up is needed, or proceed to route when screening is done.

    Returns:
        str: 'medical_screening' to continue screening, or 'route' to proceed.
    """
    # If screening is done, proceed to bridge_route
    if state.get("screening_done", True):
        return "bridge_route"

    # If we're still screening, loop back
    return "medical_screening"


# =============================================================================
# BUILD THE WORKFLOW (EXISTING + NEW NODES)
# =============================================================================

def build_supervisor_workflow():
    """
    Build the complete LangGraph workflow for the supervisor.

    The workflow flow:
    1. classify → classify the user's intent
    2. medical_screening → multi-turn screening for medical/legal (loops back if needed)
    3. bridge_route → check if request should go remote (NEW)
    4. route → route to appropriate sub-agent
    5. post_process → record for self-improving loop (NEW)

    Returns:
        StateGraph: The compiled LangGraph workflow.
    """
    # Create the state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("bridge_route", bridge_route)  # NEW
    workflow.add_node("route", route)
    workflow.add_node("post_process", post_process)  # NEW

    # Add edges
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "medical_screening")

    # Add conditional edge from medical_screening
    workflow.add_conditional_edges(
        "medical_screening",
        should_continue_screening,
        {
            "medical_screening": "medical_screening",  # Loop back for follow-up
            "bridge_route": "bridge_route",  # Proceed to bridge when done (UPDATED)
        }
    )

    # Add edges from bridge_route
    workflow.add_edge("bridge_route", "route")

    # Add edge from route to post_process
    workflow.add_edge("route", "post_process")

    # Add edge from post_process to END
    workflow.add_edge("post_process", "__end__")

    return workflow


# =============================================================================
# CREATE THE SUPERVISOR AGENT
# =============================================================================

def create_supervisor_agent():
    """
    Create and compile the supervisor agent.

    Returns:
        CompiledGraph: The compiled LangGraph workflow with checkpointing.
    """
    workflow = build_supervisor_workflow()

    # Compile with checkpointing for persistence
    # In production, this would use a real PostgreSQL connection
    # For development, we use the PostgresSaver with a connection string
    # app = workflow.compile(checkpointer=PostgresSaver())

    # For now, compile without checkpointing for simplicity
    app = workflow.compile()

    return app


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Example usage
    import asyncio

    async def main():
        supervisor = create_supervisor_agent()

        # Test request
        state = {
            "messages": [
                {"role": "user", "content": "I need a Python developer for a project"}
            ],
            "company_id": 1
        }

        result = await supervisor.ainvoke(state)
        print(json.dumps(result, indent=2))

    asyncio.run(main())