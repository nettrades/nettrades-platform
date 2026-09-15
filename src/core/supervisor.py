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
#  10. NEW: Hardware-aware inference routing (Dynamo vs RPC cluster vs local)
#  11. NEW: Session-to-backend affinity binding
#  12. NEW: Graceful drain-and-restart on RPC node failure
#
# INTEGRATION POINTS:
#   - Odoo: Reads company-specific LLM configuration via LLMFactory
#   - Bridge: Routes requests to local or remote brain based on company settings
#   - Self-Improving: Records episodes for fine-tuning models
#   - Dynamo: Primary inference for GPU data centre nodes
#   - llama.cpp RPC: Distributed inference for office PCs
#   - Hardware detection: src/core/hardware_detection.py
#   - Node health: src/core/node_health.py
#
# UPDATES (2026-08-10):
#   - Added resolution detection in post_process
#   - Added track system integration
#   - Enhanced episode recording with full metadata
#
# UPDATES (2026-09-15):
#   - Added hardware-aware routing: the supervisor now checks whether the
#     requested model fits on a Dynamo node, an RPC cluster, or local inference.
#   - Added session-to-backend affinity: once a conversation starts on a
#     backend, all subsequent turns stay on that backend (KV cache locality).
#   - Added drain-and-restart integration: when the health monitor detects
#     that an RPC node has failed, the supervisor drains the affected cluster.
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
from self_improving_integration import SelfImprovingService, EpisodeData

# -----------------------------------------------------------------------------
# Import node health monitor (src/core/node_health.py)
# -----------------------------------------------------------------------------
from node_health import get_health_monitor, NodeHealth

# -----------------------------------------------------------------------------
# Import hardware detection (src/core/hardware_detection.py)
# -----------------------------------------------------------------------------
from hardware_detection import detect_system_profile, SystemProfile

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

# Default thresholds for hardware-aware routing
MODEL_SIZE_THRESHOLD_BYTES = 40 * 1024 * 1024 * 1024   # 40 GB (roughly 70B params at Q4)
VRAM_HEADROOM_FACTOR = 0.85                              # Reserve 15% VRAM

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
# The supervisor uses these sub-agents to handle specific domains.
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

_logger.info("All sub-agents loaded successfully")


# =============================================================================
# HARDWARE-AWARE ROUTING HELPERS
# =============================================================================

async def _get_available_hardware(company_id: int) -> Dict[str, Any]:
    """
    Query the available hardware for a company.

    This calls the Odoo `gpu.cluster` model to get the company's GPU
    inventory, and combines it with the health monitor's live data.

    Returns a dict with:
      - dynamo_vram_mb: total VRAM available on Dynamo-capable nodes
      - rpc_vram_mb:    total VRAM available on RPC-capable nodes
      - rpc_nodes:      list of healthy RPC node IDs
      - local_profile:  the local machine's SystemProfile
    """
    result = {
        'dynamo_vram_mb': 0,
        'rpc_vram_mb': 0,
        'rpc_nodes': [],
        'local_profile': None,
    }

    # Local hardware profile (always available, no Odoo needed)
    try:
        result['local_profile'] = detect_system_profile()
    except Exception as e:
        _logger.warning(f"Local hardware detection failed: {e}")

    # Query Odoo for cluster inventory
    try:
        import requests
        import os
        odoo_url = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
        api_key = os.getenv("ODOO_API_KEY", "")

        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    os.getenv("ODOO_DB", "odoo"),
                    os.getenv("ODOO_USER", 1),
                    os.getenv("ODOO_PASSWORD", "admin"),
                    "gpu.cluster",
                    "search_read",
                    [[("company_id", "=", company_id)]],
                    {"fields": ["id", "trust_mode", "total_vram_gb", "available_vram_gb"]},
                ]
            },
            "id": 1,
        }
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        resp = requests.post(f"{odoo_url}/jsonrpc", json=payload, headers=headers, timeout=5)
        if resp.ok:
            clusters = resp.json().get("result", [])
            for c in clusters:
                vram_mb = int(c.get("available_vram_gb", 0) * 1024)
                if c.get("trust_mode") == "company_multi_gpu":
                    result['dynamo_vram_mb'] += vram_mb
                else:
                    result['rpc_vram_mb'] += vram_mb
    except Exception as e:
        _logger.warning(f"Failed to query Odoo GPU clusters: {e}")

    # Query the health monitor for healthy RPC nodes
    monitor = get_health_monitor()
    for node in monitor.get_healthy_nodes_by_role('rpc_worker'):
        result['rpc_nodes'].append(node.node_id)
        # Add this node's VRAM to the pool
        for mem in node.gpu_memory_used_mb.values():
            result['rpc_vram_mb'] += 0  # TODO: use total VRAM not used
    return result


def _model_fits_in_vram(model_size_bytes: int, available_vram_mb: int) -> bool:
    """Check whether a model fits in the available VRAM with headroom."""
    if available_vram_mb <= 0:
        return False
    available_bytes = available_vram_mb * 1024 * 1024 * VRAM_HEADROOM_FACTOR
    return model_size_bytes <= available_bytes


def _select_inference_track(state: dict, hardware: Dict[str, Any]) -> str:
    """
    Decide which inference track should handle this request.

    The decision tree is:
      1. If the conversation has a pinned backend, use it (session affinity).
      2. If the model fits on a Dynamo node with NVLink, use Dynamo.
      3. If the model fits on the RPC cluster, use RPC.
      4. If the model fits locally, use local inference.
      5. Otherwise, fall back to remote (NETTRADES.AI hub).

    Returns one of: 'dynamo', 'rpc', 'local', 'remote'.
    """
    # 1. Session affinity: never switch mid-conversation
    pinned = state.get("inference_track")
    if pinned:
        _logger.info(f"Using pinned inference track: {pinned}")
        return pinned

    model_size = state.get("model_size_bytes", 0)

    # 2. Try Dynamo first (lowest latency, highest throughput)
    if model_size and _model_fits_in_vram(model_size, hardware['dynamo_vram_mb']):
        return 'dynamo'

    # 3. Try RPC cluster
    if model_size and _model_fits_in_vram(model_size, hardware['rpc_vram_mb']):
        return 'rpc'

    # 4. Try local
    local = hardware.get('local_profile')
    if local and model_size:
        local_vram = local.total_vram_mb
        if _model_fits_in_vram(model_size, local_vram):
            return 'local'

    # 5. Fall back to remote
    return 'remote'


async def _on_rpc_node_failure(node: NodeHealth) -> None:
    """
    Callback fired by the health monitor when an RPC node becomes unhealthy.

    This implements the drain-and-restart pattern from Ghostlink:
      1. Find any active RPC cluster that includes this node
      2. Drain the cluster (unload the master llama-server)
      3. Fail in-flight requests with a clear error
      4. Reassign layers to exclude the failed node
      5. Relaunch the cluster

    The conversation transcript is preserved by the LangGraph checkpointer,
    so the user can retry with full context.
    """
    _logger.warning(
        f"RPC node {node.node_id} ({node.hostname}) failed — draining affected clusters"
    )
    try:
        import requests, os
        odoo_url = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
        api_key = os.getenv("ODOO_API_KEY", "")

        # Ask Odoo to drain and restart any cluster that includes this node
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    os.getenv("ODOO_DB", "odoo"),
                    os.getenv("ODOO_USER", 1),
                    os.getenv("ODOO_PASSWORD", "admin"),
                    "gpu.cluster",
                    "drain_and_restart_for_node",
                    [node.node_id],
                    {},
                ]
            },
            "id": 1,
        }
        headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
        resp = requests.post(f"{odoo_url}/jsonrpc", json=payload, headers=headers, timeout=10)
        if resp.ok:
            _logger.info(f"Drain-and-restart triggered for node {node.node_id}")
        else:
            _logger.error(f"Drain-and-restart failed: HTTP {resp.status_code}")
    except Exception as e:
        _logger.error(f"Drain-and-restart callback error: {e}")


# Register the callback with the global health monitor
try:
    get_health_monitor().on_node_unhealthy(_on_rpc_node_failure)
except Exception as e:
    _logger.warning(f"Could not register drain-and-restart callback: {e}")

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
# NODE 3: BRIDGE ROUTE (now hardware-aware)
# =============================================================================
async def bridge_route(state: dict) -> dict:
    """
    Check if the request should be routed to the remote brain via the bridge,
    AND decide which inference track should handle it.

    This node now performs two routing decisions:
      1. Hub-and-spoke routing (existing): local vs remote brain
      2. Inference track selection (new): dynamo vs rpc vs local

    The inference track decision is stored in state["inference_track"] and
    is used by the `route` node to dispatch to the correct backend.
    """
    intent = state.get("intent", "general")
    company_id = state.get("company_id")
    model_size = state.get("model_size_bytes", 0)

    # --- NEW: Hardware-aware inference track selection ---
    try:
        hardware = await _get_available_hardware(company_id)
        track = _select_inference_track(state, hardware)
        state["inference_track"] = track
        _logger.info(
            f"Selected inference track: {track} "
            f"(dynamo_vram={hardware['dynamo_vram_mb']}MB, "
            f"rpc_vram={hardware['rpc_vram_mb']}MB, "
            f"rpc_nodes={len(hardware['rpc_nodes'])})"
        )
    except Exception as e:
        _logger.warning(f"Hardware-aware routing failed, defaulting to local: {e}")
        state["inference_track"] = "local"

    # --- Existing: Hub-and-spoke routing via bridge ---
    bridge = BridgeService()
    try:
        bridge_result = await bridge.route_request(intent, state, company_id)
        if bridge_result and bridge_result.get('source') != 'local':
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
    Route the request to the appropriate sub-agent based on intent,
    AND set up the correct inference backend based on inference_track.

    The inference_track determines which API endpoint the LLMFactory
    should use:
      - 'dynamo' -> http://dynamo:8000/v1  (vLLM, tensor parallelism)
      - 'rpc'    -> http://llama-rpc-master:8080/v1  (llama.cpp pipeline)
      - 'local'  -> http://llama-cpp:8080/v1  (local CPU fallback)
      - 'remote' -> https://api.nettrades.ai/v1  (hub brain)

    Additionally, it detects if the inference backend is a CPU fallback
       and notifies the user accordingly.
       
    This node is the main dispatcher. It checks:
    1. If screening is complete (for medical/legal intents)
    2. If the bridge already handled the request (use bridge_response)
    3. If not, it dispatches to the appropriate sub-agent based on intent

    The mapping of intents to sub-agents is:
    - recruitment -> Recruitment Agent
    - freelance -> Freelance Agent
    - lead_gen -> Lead Gen Agent
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
                "I'm using a smaller CPU-based model for now. This may affect the quality of responses. "
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
    track = state.get("inference_track", "local")
    _logger.info(f"Routing intent: {intent} on track: {track}")

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
        _logger.info(f"Routing completed for intent: {intent} on track: {track}")
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
    3. Detects if the problem was resolved based on conversation patterns
    4. Records the episode via SelfImprovingService with full metadata

    The recorded episodes are used to:
    - Build training datasets for fine-tuning
    - Detect edge cases and low-quality responses
    - Trigger the self-improving loop when thresholds are met

    Returns:
        dict: Updated state (unchanged, but episode is recorded asynchronously).
        
    It also records which inference_track was used, so the loop can
    learn which track works best for which intent.
 
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

    # =========================================================================
    # NEW: Detect resolution
    # =========================================================================
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

    # =========================================================================
    # NEW: Determine track and data classification
    # =========================================================================
    track = state.get("track", "community")
    data_classification = state.get("data_classification", "public")

    # Auto-classify if not set
    if not state.get("track"):
        intent = state.get("intent", "general")
        regulated_intents = ["medical", "legal", "financial"]
        track = "regulated" if intent in regulated_intents else "community"

    if not state.get("data_classification"):
        if track == "regulated":
            data_classification = "restricted"
        elif "gpu" in intent or "cluster" in intent:
            data_classification = "confidential"
        else:
            data_classification = "public"

    # =========================================================================
    # Record the episode with full metadata
    # =========================================================================
    self_improving = SelfImprovingService()

    try:
        # Get the last user message
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

        # Create episode data
        episode = EpisodeData(
            partner_id=state.get("user_id", 1),
            field_id=state.get("field_id"),
            input_text=input_text,
            output_text=output_text,
            quality_score=quality_score,
            context_data={
                "intent": intent,
                "route_source": state.get("route_source", "local"),
                "inference_track": state.get("inference_track", "local"),
                "fallback_used": state.get("fallback_used", False),
                "thread_id": thread_id,
            },
            source="auto",
            track=track,
            data_classification=data_classification,
            is_verified=state.get("is_verified", False),
            resolution_status=resolution_status,
            model_used=state.get("model_used"),
            inference_time_ms=state.get("inference_time_ms"),
            token_count=state.get("token_count"),
        )

        # Record the episode
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
                f"(intent: {intent}, track: {state.get('inference_track')}, "
                f"quality: {quality_score:.2f}, resolution: {resolution_status})"
              #  f"(intent: {intent}, quality: {quality_score:.2f}, "
              #  f"resolution: {resolution_status}, track: {track})"
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