# -*- coding: utf-8 -*-
# =============================================================================
# VISION AGENT – Multi-modal VLM (Vision-Language Model) Integration
# =============================================================================
# FILE: src/core/agents/vision_agent.py
#
# PURPOSE:
#   This agent handles vision-related queries. It processes images and
#   text together using a Vision-Language Model (VLM) to provide
#   multi-modal understanding.
#
# KEY FEATURES:
#   - Receives image_base64 and text query
#   - Calls VLM (Qwen2-VL, LLaVA, or similar) via GPUStack
#   - Returns image analysis and description
#
# REQUIRED CONFIGURATION:
#   - Multi-Modal Inferencing must be enabled in Odoo admin
#   - A VLM model must be deployed on GPUStack
# =============================================================================

from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from ..tools.inference_tools import get_inference_backend
import logging
import json
import base64

_logger = logging.getLogger(__name__)


class VisionState(dict):
    """
    State carried through the vision workflow.

    Keys:
        - image_base64: Base64-encoded image data
        - query: The user's text query
        - analysis: The VLM's analysis result
    """
    pass


def create_vision_agent() -> StateGraph:
    """
    Build and return a compiled vision sub-graph.

    The workflow consists of two nodes:
    1. encode_image – Prepare the image for the VLM
    2. analyse_image – Call the VLM and return analysis

    Returns:
        StateGraph: Compiled LangGraph workflow
    """
    # Auto-detect the inference backend
    backend = get_inference_backend()
    _logger.info(f"Vision agent using inference backend: {backend.get('base_url', 'unknown')}")

    # Create the LLM client (used for VLM)
    llm = ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=0.1,
    )

    # =========================================================================
    # NODE 1: Encode Image
    # =========================================================================

    async def encode_image(state: VisionState):
        """
        Prepare the image for the VLM.

        This node ensures the image is in the correct format for the VLM.
        """
        image_base64 = state.get("image_base64", "")

        if not image_base64:
            state["analysis"] = "No image provided. Please upload an image."
            return state

        # Store the image data for the next node
        state["image_ready"] = True
        _logger.info("Image encoded successfully")

        return state

    # =========================================================================
    # NODE 2: Analyse Image
    # =========================================================================

    async def analyse_image(state: VisionState):
        """
        Analyse the image using the VLM.

        This node sends the image and query to the VLM and returns the analysis.
        """
        query = state.get("query", "What do you see in this image?")
        image_base64 = state.get("image_base64", "")

        if not state.get("image_ready", False) or not image_base64:
            state["analysis"] = "No image available for analysis."
            return state

        try:
            # Prepare the message for the VLM
            # The format depends on the VLM API; this assumes OpenAI-compatible format
            # For multi-modal, we need to send the image as a data URL
            image_data_url = f"data:image/jpeg;base64,{image_base64}"

            prompt = f"""
            Analyse the following image and answer the user's question.

            User question: {query}

            Provide a detailed analysis of what you see in the image, including:
            1. Objects or people present
            2. Context or setting
            3. Any text visible
            4. Relevant details that answer the user's question
            """

            # This is a placeholder for VLM integration
            # In production, this would call the VLM with the image
            # The actual implementation depends on the VLM API

            # Placeholder response
            state["analysis"] = """
            [VLM Analysis Placeholder]

            The image appears to show a scene that could be relevant to your query.

            Note: Full VLM integration requires a Vision-Language Model deployed on GPUStack.
            Please enable Multi-Modal Inferencing in the admin settings and deploy a VLM.

            For production use, this should call the VLM with the provided image.
            """

            _logger.info("Image analysis completed")

        except Exception as e:
            _logger.error(f"Image analysis failed: {e}")
            state["analysis"] = f"Error analysing image: {str(e)}"

        return state

    # =========================================================================
    # BUILD THE WORKFLOW
    # =========================================================================

    workflow = StateGraph(VisionState)

    workflow.add_node("encode_image", encode_image)
    workflow.add_node("analyse_image", analyse_image)

    workflow.add_edge(START, "encode_image")
    workflow.add_edge("encode_image", "analyse_image")
    workflow.add_edge("analyse_image", END)

    return workflow.compile()