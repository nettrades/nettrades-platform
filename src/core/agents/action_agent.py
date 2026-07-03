# -*- coding: utf-8 -*-
# =============================================================================
# Action Agent - translates natural language into robotic actions.
# =============================================================================
# This agent is a LangGraph sub-graph.  It receives a command (e.g.
# "move the arm to position X"), calls a Vision-Language-Action model
# to generate a robot trajectory, and dispatches it via ROS???2 or an
# MCP-Robotics bridge.
#
# REQUIREMENTS:
#   1. The administrator must enable "Robotics Integration" in the
#      GPU Admin -> Multi-Modal & Edge Settings screen.
#   2. A VLA model must be deployed in GPUStack/vLLM.
#   3. The ROS???2 master URI must be reachable from the LangGraph container.
#
# FUTURE ENHANCEMENT: Support for multi-step task planning, feedback
# loops, and real-time sensor fusion.
# =============================================================================
import json, logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from tools.inference_tools import get_inference_backend

_logger = logging.getLogger(__name__)

class ActionState(dict):
    pass


def create_action_agent(vla_model_name: str = None):
    backend = get_inference_backend()
    if vla_model_name:
        backend["model_name"] = vla_model_name

    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.0,
    )

    async def plan_action(state: ActionState):
        try:
            user_msg = state.get("messages", [{}])[-1].get("content", "")
            prompt = (
                f"You are a robot control system. The user says: '{user_msg}'.\n"
                f"Generate a JSON action plan with keys 'action' (string), "
                f"'parameters' (object), and 'reasoning' (string).\n"
                f"Supported actions: move_arm, navigate, grasp, release, speak.\n"
            )
            response = await llm.ainvoke(prompt)
            plan = json.loads(response.content)
            state["action_plan"] = plan
        except Exception as e:
            _logger.error("Action planning failed: %s", e)
            state["action_plan"] = {"action": "error", "parameters": {}, "reasoning": str(e)}
        return state

    async def dispatch(state: ActionState):
        plan = state.get("action_plan", {})
        if plan.get("action") == "error":
            state["dispatch_status"] = "failed"
            return state
        _logger.info("Robot action plan: %s", json.dumps(plan))
        state["dispatch_status"] = "planned"
        return state

    workflow = StateGraph(ActionState)
    workflow.add_node("plan_action", plan_action)
    workflow.add_node("dispatch", dispatch)
    workflow.add_edge(START, "plan_action")
    workflow.add_edge("plan_action", "dispatch")
    workflow.add_edge("dispatch", END)
    return workflow.compile()