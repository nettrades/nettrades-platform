# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Supervisor – clinical screening, multimodal routing, VLA dispatch.
# =============================================================================
# Routes user intents to the correct sub-agent.  New intents added:
#   - "vision"  → vision_agent (VLM)
#   - "action"  → action_agent (VLA / robotics)
# =============================================================================
import json, logging, os
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from .tools.inference_tools import get_inference_backend

from .agents.recruitment_agent import create_recruitment_agent
from .agents.freelance_agent import create_freelance_agent
from .agents.lead_gen_agent import create_lead_gen_agent
from .agents.gpu_management_agent import create_gpu_management_agent
from .agents.vision_agent import create_vision_agent
from .agents.action_agent import create_action_agent

_logger = logging.getLogger(__name__)

MAX_FOLLOWUP_ROUNDS = 3


def build_supervisor():
    backend = get_inference_backend()
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    recruitment_agent = create_recruitment_agent()
    freelance_agent = create_freelance_agent()
    lead_gen_agent = create_lead_gen_agent()
    gpu_management_agent = create_gpu_management_agent()
    vision_agent = create_vision_agent()
    action_agent = create_action_agent()

    async def classify(state: dict) -> dict:
        user_msg = state.get("messages", [{}])[-1].get("content", "")
        # Check if an image was uploaded (from chat UI)
        has_image = bool(state.get("image_base64", ""))
        if has_image:
            state["intent"] = "vision"
            return state

        prompt = (
            f"Classify the intent of the following message into one of: "
            f"recruitment, freelance, lead_gen, gpu_management, medical, legal, "
            f"action (robotic control), vision (image analysis), general. "
            f"Message: {user_msg}"
        )
        response = await llm.ainvoke(prompt)
        state["intent"] = response.content.strip().lower()
        state["followup_count"] = 0
        return state

    async def medical_screening(state: dict) -> dict:
        intent = state.get("intent", "general")
        if intent not in ("medical", "legal"):
            return state
        followup_count = state.get("followup_count", 0)
        if followup_count >= MAX_FOLLOWUP_ROUNDS:
            state["screening_done"] = True
            return state
        user_msg = state["messages"][-1]["content"]
        prompt = (
            f"You are a clinical screening assistant. The user has asked: '{user_msg}'.\n"
            f"Determine whether enough information is present to provide a safe answer. "
            f"If comorbidities or medication interactions might be relevant, ask the user "
            f"about them.  If the question is clear and complete, respond with 'SUFFICIENT'."
        )
        response = await llm.ainvoke(prompt)
        answer = response.content.strip()
        if "SUFFICIENT" in answer.upper():
            state["screening_done"] = True
        else:
            state["messages"].append({"role": "assistant", "content": answer})
            state["followup_count"] = followup_count + 1
            state["screening_done"] = False
        return state

    async def route(state: dict) -> dict:
        intent = state.get("intent", "general")
        if not state.get("screening_done", True):
            return state

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
            response = await llm.ainvoke(state["messages"][-1]["content"])
            result = {"analysis": response.content}
        state.update(result)
        return state

    workflow = StateGraph(dict)
    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("route", route)
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "medical_screening")
    workflow.add_edge("medical_screening", "route")
    workflow.add_edge("route", END)
    return workflow.compile()