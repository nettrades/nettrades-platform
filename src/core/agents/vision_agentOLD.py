# -*- coding: utf-8 -*-
# =============================================================================
# Vision Agent – handles image + text queries using a VLM.
# =============================================================================
# This agent is a LangGraph sub-graph.  It receives a user message that
# contains an image, sends it to a Vision-Language Model (VLM) via the
# auto-detected inference backend, and returns the analysis.
#
# REQUIREMENTS:
#   1. The administrator must enable "Multi-Modal Inferencing" in the
#      GPU Admin → Multi-Modal & Edge Settings screen.
#   2. A VLM (e.g. Qwen2-VL, LLaVA, InternVL 3.5) must be deployed
#      in GPUStack or vLLM.
#   3. GPUStack handles multimodal projector files automatically.
#
# FUTURE ENHANCEMENT: Support for video frames, audio clips, and
# multi-turn visual conversations.
# =============================================================================
import base64, json, logging
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from ..tools.inference_tools import get_inference_backend

_logger = logging.getLogger(__name__)

class VisionState(dict):
    pass


def create_vision_agent(vlm_model_name: str = None):
    backend = get_inference_backend()
    if vlm_model_name:
        backend["model_name"] = vlm_model_name

    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    async def analyse(state: VisionState):
        try:
            image_b64 = state.get("image_base64", "")
            user_text = state.get("messages", [{}])[-1].get("content", "")
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }]
            response = await llm.ainvoke(messages)
            state["analysis"] = response.content
            state["vision_complete"] = True
        except Exception as e:
            _logger.error("Vision agent failed: %s", e)
            state["analysis"] = f"Error analysing image: {str(e)}"
        return state

    workflow = StateGraph(VisionState)
    workflow.add_node("analyse", analyse)
    workflow.add_edge(START, "analyse")
    workflow.add_edge("analyse", END)
    return workflow.compile()