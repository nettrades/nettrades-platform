# -*- coding: utf-8 -*-
# =============================================================================
# Action Agent - translates natural language into robotic actions.
# FILE: src/core/agents/action_agent.py
# =============================================================================
# This agent is a LangGraph sub-graph.  It receives a command (e.g.
# "move the arm to position X"), calls a Vision-Language-Action model
# to generate a robot trajectory, and dispatches it via ROS 2 or an
# MCP-Robotics bridge.
#
# REQUIREMENTS:
#   1. The administrator must enable "Robotics Integration" in the
#      GPU Admin -> Multi-Modal & Edge Settings screen.
#   2. A VLA model must be deployed in GPUStack/vLLM.
#   3. The ROS2 master URI must be reachable from the LangGraph container.
#
# FUTURE ENHANCEMENT: Support for multi-step task planning, feedback
# loops, and real-time sensor fusion.
#
# UPDATES (2026-09-29):
#   - LLM is now constructed per-invocation inside plan_action(). The
#     optional vla_model_name override is passed through to the helper
#     so that a specific VLA model name can still be selected for this
#     agent, but the base URL and API key come from the runtime track.
# =============================================================================
import json, logging
from langgraph.graph import StateGraph, END, START
from tools import make_llm_for_track

_logger = logging.getLogger(__name__)

class ActionState(dict):
    pass


def create_action_agent(vla_model_name: str = None):
    """
    Build and return a compiled Action agent.

    Args:
        vla_model_name: optional VLA model name override. If provided, it is
            passed through to make_llm_for_track() so the request targets
            that specific model instead of the default for the selected
            track.
    """

    async def plan_action(state: ActionState):
        try:
            user_msg = state.get("messages", [{}])[-1].get("content", "")
            prompt = (
                f"You are a robot control system. The user says: '{user_msg}'.\n"
                f"Generate a JSON action plan with keys 'action' (string), "
                f"'parameters' (object), and 'reasoning' (string).\n"
                f"Supported actions: move_arm, navigate, grasp, release, speak.\n"
            )
            # Construct the LLM per invocation. Pass the VLA model override
            # (if any) so a specific model is targeted when configured.
            llm = make_llm_for_track(
                state.get("inference_track"),
                temperature=0.0,
                model=vla_model_name,
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