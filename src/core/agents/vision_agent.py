#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Vision Agent
# =============================================================================
# FILE: src/core/agents/vision_agent.py
#
# PURPOSE:
#   This agent processes visual and multimodal input from cameras, sensors,
#   and other vision sources. It integrates with ROS2 for robotics applications
#   and with the self-improving loop for continuous learning.
#
# KEY FEATURES:
#   - Multimodal (Vision-Language) processing
#   - ROS2 integration for robotics
#   - VLA (Vision-Language-Action) support
#   - Fine-tuning pipeline integration
#   - Edge case detection
#   - Self-improving loop integration
#   - Bridge integration for hub-and-spoke routing
# =============================================================================

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import cv2

# -----------------------------------------------------------------------------
# LangGraph imports
# -----------------------------------------------------------------------------
from langgraph.graph import StateGraph, START
# FIXED: State removed (not needed)
from langgraph.checkpoint.postgres import PostgresSaver
# FIXED: Correct import path

# -----------------------------------------------------------------------------
# ROS2 imports (optional)
# -----------------------------------------------------------------------------
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import Image as ROSImage
    from cv_bridge import CvBridge
    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False
    # Create dummy classes for type hints
    class Node: pass
    class ROSImage: pass

# -----------------------------------------------------------------------------
# VLM/VLA imports (optional)
# -----------------------------------------------------------------------------
try:
    import torch
    from transformers import AutoProcessor, AutoModelForVision2Seq
    HAS_VLM = True
except ImportError:
    HAS_VLM = False

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# =============================================================================
# 1. Data Classes & Enums
# =============================================================================

class VisionMode(Enum):
    """Operation modes for the vision agent."""
    CLASSIFICATION = "classification"
    DETECTION = "detection"
    SEGMENTATION = "segmentation"
    VLM = "vision_language"
    VLA = "vision_language_action"
    MULTIMODAL = "multimodal"
    ROS2 = "ros2"


@dataclass
class VisionInput:
    """Input data for the vision agent."""
    image: Optional[np.ndarray] = None
    image_path: Optional[str] = None
    ros_topic: Optional[str] = None
    text_query: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    mode: VisionMode = VisionMode.VLM
    timestamp: float = field(default_factory=time.time)


@dataclass
class VisionOutput:
    """Output data from the vision agent."""
    results: Dict[str, Any]
    confidence: float = 0.0
    action: Optional[Dict[str, Any]] = None
    processed_image: Optional[np.ndarray] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

# =============================================================================
# 2. Vision Agent Class
# =============================================================================

class VisionAgent:
    """
    Vision Agent for processing visual and multimodal input.

    This agent can operate in multiple modes:
    - Vision-Language: Understand images with text queries
    - Vision-Language-Action: Understand images and take actions
    - ROS2: Process ROS2 camera topics
    - Multimodal: Combine multiple input types

    Integration points:
    - ROS2: For robotics applications
    - Bridge: For hub-and-spoke routing
    - Self-Improving Loop: For continuous learning
    - Fine-Tuning Pipeline: For model improvement
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the Vision Agent.

        Args:
            config: Configuration dictionary with the following keys:
                - mode: VisionMode
                - model_name: str (e.g., "llava-hf/llava-1.5-7b-hf")
                - device: str ("cuda" or "cpu")
                - ros_topic: str (for ROS2 mode)
                - bridge_enabled: bool
                - self_improving_enabled: bool
                - fine_tuning_enabled: bool
        """
        self.config = config or {}
        self.mode = self.config.get('mode', VisionMode.VLM)
        self.model = None
        self.processor = None
        self.bridge_enabled = self.config.get('bridge_enabled', True)
        self.self_improving_enabled = self.config.get('self_improving_enabled', True)
        self.fine_tuning_enabled = self.config.get('fine_tuning_enabled', True)

        # ROS2 setup
        self.ros_node = None
        self.ros_bridge = None
        self.ros_topic = self.config.get('ros_topic', '/camera/image_raw')

        # Bridge integration
        self.bridge_url = self.config.get('bridge_url', 'http://localhost:8069/api/bridge/route')

        # Initialize the model
        self._init_model()

        # Initialize ROS2 if enabled
        if self.config.get('ros2_enabled', False):
            self._init_ros2()

        logger.info(f"VisionAgent initialized in mode: {self.mode}")

    # =========================================================================
    # 3. Model Initialization
    # =========================================================================

    def _init_model(self):
        """Initialize the VLM/VLA model."""
        if not HAS_VLM:
            logger.warning("VLM/VLA libraries not available. Running in fallback mode.")
            return

        model_name = self.config.get('model_name', 'llava-hf/llava-1.5-7b-hf')
        device = self.config.get('device', 'cuda' if torch.cuda.is_available() else 'cpu')

        try:
            logger.info(f"Loading model: {model_name} on {device}")
            self.processor = AutoProcessor.from_pretrained(model_name)
            self.model = AutoModelForVision2Seq.from_pretrained(
                model_name,
                torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
                device_map="auto" if device == 'cuda' else None
            )
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None

    # =========================================================================
    # 4. ROS2 Integration
    # =========================================================================

    def _init_ros2(self):
        """Initialize ROS2 node and bridge."""
        if not HAS_ROS2:
            logger.warning("ROS2 not available. ROS2 features disabled.")
            return

        try:
            rclpy.init()
            self.ros_node = Node('vision_agent')
            self.ros_bridge = CvBridge()

            # Subscribe to camera topic
            self.ros_node.create_subscription(
                ROSImage,
                self.ros_topic,
                self._ros_callback,
                10
            )
            logger.info(f"ROS2 initialized, subscribed to {self.ros_topic}")
        except Exception as e:
            logger.error(f"Failed to initialize ROS2: {e}")

    def _ros_callback(self, msg: ROSImage):
        """Callback for ROS2 camera messages."""
        if not self.ros_bridge:
            return

        try:
            cv_image = self.ros_bridge.imgmsg_to_cv2(msg, 'bgr8')
            # Process the image
            input_data = VisionInput(
                image=cv_image,
                mode=VisionMode.ROS2
            )
            # Process asynchronously
            asyncio.create_task(self.process(input_data))
        except Exception as e:
            logger.error(f"ROS2 callback error: {e}")

    # =========================================================================
    # 5. Core Processing
    # =========================================================================

    async def process(self, input_data: VisionInput) -> VisionOutput:
        """
        Process visual input and return results.

        This is the main entry point for the vision agent. It handles:
        1. Input validation and preprocessing
        2. Model inference
        3. Post-processing
        4. Bridge routing (if enabled)
        5. Self-improving loop integration
        6. Edge case detection
        """
        logger.info(f"Processing vision input in mode: {input_data.mode}")

        # ---------------------------------------------------------------------
        # Step 1: Input validation
        # ---------------------------------------------------------------------
        image = self._load_image(input_data)
        if image is None and not input_data.image_path:
            return VisionOutput(
                results={"error": "No valid image provided"},
                confidence=0.0
            )

        # ---------------------------------------------------------------------
        # Step 2: Bridge routing (if enabled)
        # ---------------------------------------------------------------------
        if self.bridge_enabled:
            bridge_result = await self._call_bridge(input_data)
            if bridge_result:
                return bridge_result

        # ---------------------------------------------------------------------
        # Step 3: Local processing
        # ---------------------------------------------------------------------
        if self.mode == VisionMode.VLM or input_data.mode == VisionMode.VLM:
            result = await self._process_vlm(input_data, image)
        elif self.mode == VisionMode.VLA or input_data.mode == VisionMode.VLA:
            result = await self._process_vla(input_data, image)
        elif self.mode == VisionMode.ROS2 or input_data.mode == VisionMode.ROS2:
            result = await self._process_ros2(input_data, image)
        else:
            # Default: classification mode
            result = await self._process_classification(input_data, image)

        # ---------------------------------------------------------------------
        # Step 4: Edge case detection
        # ---------------------------------------------------------------------
        if self.self_improving_enabled:
            edge_case = await self._detect_edge_case(result)
            if edge_case:
                await self._record_edge_case(result, edge_case)

        # ---------------------------------------------------------------------
        # Step 5: Fine-tuning integration
        # ---------------------------------------------------------------------
        if self.fine_tuning_enabled:
            await self._record_for_fine_tuning(input_data, result)

        return result

    # =========================================================================
    # 6. Processing Methods
    # =========================================================================

    async def _process_vlm(self, input_data: VisionInput, image: np.ndarray) -> VisionOutput:
        """Process using Vision-Language Model."""
        if not self.model or not self.processor:
            return VisionOutput(
                results={"error": "VLM model not available"},
                confidence=0.0
            )

        try:
            # Prepare inputs
            text = input_data.text_query or "Describe what you see in this image."
            # Process image
            inputs = self.processor(
                images=image,
                text=text,
                return_tensors="pt"
            )
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=True,
                    temperature=0.7
                )
            # Decode
            response = self.processor.decode(outputs[0], skip_special_tokens=True)

            return VisionOutput(
                results={
                    "description": response,
                    "text": text,
                    "model": self.config.get('model_name', 'unknown')
                },
                confidence=0.85,
                processed_image=image,
                metadata={
                    "mode": "vlm",
                    "timestamp": time.time()
                }
            )
        except Exception as e:
            logger.error(f"VLM processing error: {e}")
            return VisionOutput(
                results={"error": str(e)},
                confidence=0.0
            )

    async def _process_vla(self, input_data: VisionInput, image: np.ndarray) -> VisionOutput:
        """Process using Vision-Language-Action Model."""
        # Similar to VLM but with action output
        result = await self._process_vlm(input_data, image)
        # Add action interpretation
        if result.results and "description" in result.results:
            action = self._interpret_action(result.results["description"])
            result.action = action
        return result

    async def _process_ros2(self, input_data: VisionInput, image: np.ndarray) -> VisionOutput:
        """Process ROS2 camera data."""
        # Use VLM on ROS2 images
        input_data.mode = VisionMode.VLM
        return await self._process_vlm(input_data, image)

    async def _process_classification(self, input_data: VisionInput, image: np.ndarray) -> VisionOutput:
        """Process using classification (fallback)."""
        # Simple classification fallback
        # In a real implementation, this would use a classifier
        return VisionOutput(
            results={
                "classification": "object_detected",
                "confidence": 0.5
            },
            confidence=0.5,
            processed_image=image
        )

    # =========================================================================
    # 7. Action Interpretation
    # =========================================================================

    def _interpret_action(self, description: str) -> Dict[str, Any]:
        """
        Interpret a description and extract action commands.

        This method parses the VLM output to extract actionable commands
        for robotics or automation.

        Args:
            description: The text description from the VLM.

        Returns:
            Dict[str, Any]: A dictionary containing extracted actions.
        """
        # Simple action extraction
        actions = []

        if "move" in description.lower():
            actions.append({"type": "move", "direction": "forward"})
        if "grasp" in description.lower():
            actions.append({"type": "grasp", "object": "unknown"})
        if "navigate" in description.lower():
            actions.append({"type": "navigate", "target": "unknown"})

        return {
            "actions": actions,
            "interpretation": description
        }

    # =========================================================================
    # 8. Image Loading
    # =========================================================================

    def _load_image(self, input_data: VisionInput) -> Optional[np.ndarray]:
        """Load image from various sources."""
        if input_data.image is not None:
            return input_data.image

        if input_data.image_path:
            try:
                image = cv2.imread(input_data.image_path)
                if image is not None:
                    return image
            except Exception as e:
                logger.error(f"Failed to load image from path: {e}")
                return None

        return None

    # =========================================================================
    # 9. Bridge Integration
    # =========================================================================

    async def _call_bridge(self, input_data: VisionInput) -> Optional[VisionOutput]:
        """
        Call the bridge to route to remote brain if needed.

        This method sends the vision request to the remote NETTRADES.AI brain
        via the bridge service. If the bridge returns a successful response,
        it is used directly.

        Returns:
            Optional[VisionOutput]: The bridge response, or None if not routed.
        """
        try:
            import aiohttp
            payload = {
                "intent": "vision",
                "data": {
                    "mode": input_data.mode.value,
                    "text_query": input_data.text_query,
                    "image": input_data.image_path,  # Or base64 encoded image
                    "context": input_data.context
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.bridge_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get('status') == 'success':
                            return VisionOutput(
                                results=result.get('data', {}),
                                confidence=result.get('confidence', 0.8),
                                metadata={"source": "remote_bridge"}
                            )
        except Exception as e:
            logger.warning(f"Bridge call failed: {e}")

        return None

    # =========================================================================
    # 10. Self-Improving Loop Integration
    # =========================================================================

    async def _detect_edge_case(self, result: VisionOutput) -> Optional[str]:
        """
        Detect if this result represents an edge case.

        Edge cases are flagged for the self-improving loop to trigger
        fine-tuning or model updates.

        Args:
            result: The vision output to evaluate.

        Returns:
            Optional[str]: The edge case type, or None if not an edge case.
        """
        if result.confidence < 0.3:
            return "low_confidence"
        if "error" in result.results:
            return "processing_error"
        if "unknown" in str(result.results).lower():
            return "unknown_object"
        return None

    async def _record_edge_case(self, result: VisionOutput, edge_case: str):
        """
        Record edge case for the self-improving loop.

        This sends the edge case data to the data collection module for
        later analysis and fine-tuning.

        Args:
            result: The vision output that triggered the edge case.
            edge_case: The type of edge case detected.
        """
        try:
            # Call the data collection module
            # This would be an Odoo RPC call or HTTP request
            logger.info(f"Recording edge case: {edge_case}")
            # In production: call Odoo's data.episode model
            # payload = {
            #     "input": result.metadata,
            #     "output": result.results,
            #     "edge_case": edge_case,
            #     "confidence": result.confidence
            # }
            # await self._call_odoo("/api/data/record_edge_case", payload)
        except Exception as e:
            logger.error(f"Failed to record edge case: {e}")

    async def _record_for_fine_tuning(self, input_data: VisionInput, result: VisionOutput):
        """
        Record data for fine-tuning pipeline.

        This collects high-quality vision data for the fine-tuning pipeline
        to improve model performance.

        Args:
            input_data: The original vision input.
            result: The vision output.
        """
        try:
            # Filter low-quality results
            if result.confidence < 0.5:
                return

            # Record for fine-tuning
            logger.info(f"Recording data for fine-tuning: confidence={result.confidence}")
            # In production: call Odoo's training dataset model
            # payload = {
            #     "input": {
            #         "text": input_data.text_query,
            #         "image_ref": input_data.image_path
            #     },
            #     "output": result.results,
            #     "confidence": result.confidence
            # }
            # await self._call_odoo("/api/training/record", payload)
        except Exception as e:
            logger.error(f"Failed to record for fine-tuning: {e}")

    # =========================================================================
    # 11. Shutdown
    # =========================================================================

    def shutdown(self):
        """Clean shutdown of the vision agent."""
        if self.ros_node:
            self.ros_node.destroy_node()
            rclpy.shutdown()
        logger.info("VisionAgent shutdown complete")

# =============================================================================
# 12. FACTORY FUNCTION - This is what supervisor.py imports
# =============================================================================

def create_vision_agent():
    """
    Create and return a compiled LangGraph vision agent.

    This function provides the contract that the supervisor expects: a
    compiled LangGraph graph with .ainvoke().

    The graph is a simple wrapper around the VisionAgent class that routes
    input through the agent's process() method.

    Returns:
        CompiledGraph: A compiled LangGraph workflow for vision processing.
    """
    # Create a simple LangGraph workflow that wraps the VisionAgent
    workflow = StateGraph(dict)

    # Create the agent instance
    agent = VisionAgent()

    # Define the vision processing node
    async def vision_node(state: dict) -> dict:
        """
        Vision processing node for LangGraph.

        This node takes a state dict with 'image' and 'text_query' keys,
        processes them through the VisionAgent, and returns the results.
        """
        # Extract input from state
        image = state.get('image')
        text_query = state.get('text_query', 'Describe what you see')
        mode_str = state.get('mode', 'vlm')

        # Map mode string to VisionMode
        mode_map = {
            'vlm': VisionMode.VLM,
            'vla': VisionMode.VLA,
            'ros2': VisionMode.ROS2,
            'classification': VisionMode.CLASSIFICATION,
            'detection': VisionMode.DETECTION,
        }
        mode = mode_map.get(mode_str, VisionMode.VLM)

        # Create input
        input_data = VisionInput(
            image=image,
            text_query=text_query,
            mode=mode
        )

        # Process through agent
        output = await agent.process(input_data)

        # Update state with results
        state['vision_output'] = output.results
        state['confidence'] = output.confidence
        if output.action:
            state['action'] = output.action
        state['processed_image'] = output.processed_image

        return state

    # Add node and edge
    workflow.add_node("vision", vision_node)
    workflow.add_edge(START, "vision")

    # Compile and return
    return workflow.compile()

# =============================================================================
# 13. MAIN ENTRY POINT (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio
    import json

    async def main():
        """Test the vision agent with a sample request."""
        agent = create_vision_agent()

        # Test with a dummy state
        state = {
            "image": None,  # Would be a numpy array in practice
            "text_query": "What objects are in this image?",
            "mode": "vlm"
        }

        result = await agent.ainvoke(state)
        print(json.dumps(result, indent=2))

    asyncio.run(main())