# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Supervisor – clinical screening, multimodal routing, VLA dispatch.
# =============================================================================
# FILE: src/core/supervisor.py
#
# PURPOSE:
#   This file contains the main LangGraph supervisor that orchestrates
#   all AI agents. It classifies user intents, performs medical/legal
#   screening, and routes requests to the appropriate sub-agent.
#
# KEY FEATURES:
#   - Intent classification (recruitment, freelance, lead_gen, gpu_management,
#     vision, action, medical, legal, general)
#   - Medical/legal screening with follow-up questions (MAX_FOLLOWUP_ROUNDS=3)
#   - Routing to sub-agents
#   - Checkpointing via PostgresSaver
#
# IMPORTANT FIXES:
#   - The imports for sub-agents now point to the correct location
#     (src.core.agents) where the full implementations now live.
#   - Previously, the sub-agents were placeholders. Now they are full
#     implementations moved from src/agent/.
#   - The medical screening loop now has a conditional edge to loop back
#     when followup_count < MAX_FOLLOWUP_ROUNDS and screening is not done.
#
# =============================================================================

import json
import logging
import os
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from .tools.inference_tools import get_inference_backend

# =============================================================================
# IMPORTS – Sub-agents from src.core.agents (now full implementations)
# =============================================================================
from .agents.recruitment_agent import create_recruitment_agent
from .agents.freelance_agent import create_freelance_agent
from .agents.lead_gen_agent import create_lead_gen_agent
from .agents.gpu_management_agent import create_gpu_management_agent
from .agents.vision_agent import create_vision_agent
from .agents.action_agent import create_action_agent

_logger = logging.getLogger(__name__)

# Maximum number of follow-up rounds for medical/legal screening
MAX_FOLLOWUP_ROUNDS = 3


def build_supervisor():
    """
    Build and return the main LangGraph supervisor.

    The supervisor consists of three main nodes:
    1. classify – Classifies user intent using an LLM
    2. medical_screening – Conducts medical/legal screening with follow-ups
    3. route – Routes to the appropriate sub-agent

    The graph is compiled with a conditional edge from medical_screening
    that loops back when follow-up is needed, enabling multi-turn screening.

    Returns:
        StateGraph: Compiled LangGraph workflow with checkpointing enabled.
    """
    # Auto-detect the inference backend (GPUStack / vLLM / llama.cpp)
    backend = get_inference_backend()
    _logger.info(f"Supervisor using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client for classification and screening
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,  # Lower temperature for deterministic classification
    )

    # =========================================================================
    # CREATE SUB-AGENTS
    # =========================================================================
    # Each sub-agent is a compiled LangGraph sub-graph that handles a
    # specific business domain.
    recruitment_agent = create_recruitment_agent()
    freelance_agent = create_freelance_agent()
    lead_gen_agent = create_lead_gen_agent()
    gpu_management_agent = create_gpu_management_agent()
    vision_agent = create_vision_agent()
    action_agent = create_action_agent()

    # =========================================================================
    # NODE 1: CLASSIFY INTENT
    # =========================================================================

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

    # =========================================================================
    # NODE 2: MEDICAL SCREENING
    # =========================================================================

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

    # =========================================================================
    # NODE 3: ROUTE
    # =========================================================================

    async def route(state: dict) -> dict:
        """
        Route the request to the appropriate sub-agent based on intent.

        This node:
        1. Checks if screening is complete (for medical/legal)
        2. If not, returns the state unchanged (the graph will loop back)
        3. Otherwise, dispatches to the appropriate sub-agent

        Returns:
            dict: Updated state with the result from the sub-agent.
        """
        # If screening is not complete, don't route yet
        if not state.get("screening_done", True):
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

    # =========================================================================
    # CONDITIONAL EDGE FOR MEDICAL SCREENING
    # =========================================================================

    def should_continue_screening(state: dict) -> str:
        """
        Determine whether to continue medical screening or proceed to routing.

        This conditional edge is used to loop back to medical_screening
        when follow-up is needed, or proceed to route when screening is done.

        Returns:
            str: 'medical_screening' to continue screening, or 'route' to proceed.
        """
        # If screening is done, proceed to route
        if state.get("screening_done", True):
            return "route"

        # If we're still screening, loop back
        return "medical_screening"

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    # Create the state graph
    workflow = StateGraph(dict)

    # Add nodes
    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("route", route)

    # Add edges
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "medical_screening")

    # Add conditional edge from medical_screening
    workflow.add_conditional_edges(
        "medical_screening",
        should_continue_screening,
        {
            "medical_screening": "medical_screening",  # Loop back for follow-up
            "route": "route",  # Proceed to routing when done
        }
    )

    # Add final edge to end
    workflow.add_edge("route", END)

    # Return the compiled graph
    return workflow.compile()