#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Inference Backend Detection
# =============================================================================
# FILE: src/core/tools/inference.py
#
# PURPOSE:
#   This module provides a unified interface for detecting the available
#   inference backend (GPU via NVIDIA Dynamo or CPU via llama.cpp).
#   It runs a background health check thread and returns the current
#   backend status as a dictionary.
#
# USAGE:
#   from tools import get_inference_backend
#
#   backend = get_inference_backend()
#   if backend["type"] == "gpu":
#       # Use GPU backend
#   else:
#       # Use CPU fallback
#
# =============================================================================

import os
import time
import logging
import threading
import httpx
from typing import Dict, Any

_logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Global health status (updated by background thread)
# -----------------------------------------------------------------------------
_health_status = {
    "gpu_healthy": False,
    "last_checked": 0
}
_health_lock = threading.Lock()


def _health_check_loop():
    """
    Background thread that periodically checks Dynamo health.
    Runs every 30 seconds, completely independent of user requests.
    """
    gpu_url = os.getenv("LLM_BASE_URL", "http://dynamo:8000/v1")
    gpu_api_key = os.getenv("DYNAMO_API_KEY", os.getenv("OPENAI_API_KEY", "dummy"))

    while True:
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{gpu_url}/models",
                    headers={"Authorization": f"Bearer {gpu_api_key}"}
                )
                is_healthy = (response.status_code == 200)
        except Exception as e:
            _logger.debug(f"Dynamo health check failed: {e}")
            is_healthy = False

        with _health_lock:
            _health_status["gpu_healthy"] = is_healthy
            _health_status["last_checked"] = time.time()

        _logger.debug(f"Dynamo health status updated: {is_healthy}")
        time.sleep(30)


# -----------------------------------------------------------------------------
# Start the background thread when the module loads
# -----------------------------------------------------------------------------
_thread = threading.Thread(target=_health_check_loop, daemon=True)
_thread.start()
_logger.info("Dynamo health check background thread started.")


# -----------------------------------------------------------------------------
# Public API: get_inference_backend (Zero-Latency)
# -----------------------------------------------------------------------------
def get_inference_backend() -> Dict[str, Any]:
    """
    Returns the best available inference backend.

    This function performs ZERO network I/O. It simply reads the cached
    health status updated by the background thread.
    - If Dynamo is healthy: returns GPU backend.
    - If Dynamo is unhealthy: returns CPU (llama.cpp) fallback.
    """
    gpu_url = os.getenv("LLM_BASE_URL", "http://dynamo:8000/v1")
    gpu_api_key = os.getenv("DYNAMO_API_KEY", os.getenv("OPENAI_API_KEY", "dummy"))
    cpu_url = os.getenv("LLM_CPU_URL", "http://llama-cpp:8080/v1")
    cpu_api_key = os.getenv("LLM_CPU_API_KEY", "dummy")

    with _health_lock:
        is_gpu_healthy = _health_status["gpu_healthy"]

    if is_gpu_healthy:
        return {
            "type": "gpu",
            "base_url": gpu_url,
            "api_key": gpu_api_key,
            "model_name": os.getenv("MODEL_NAME", "Qwen2.5-1.5B-Instruct")
        }
    else:
        return {
            "type": "cpu",
            "base_url": cpu_url,
            "api_key": cpu_api_key,
            "model_name": "llama-cpp-model"
        }

# -----------------------------------------------------------------------------
# Public API: make_llm_for_track (per-invocation backend selection)
# -----------------------------------------------------------------------------
def make_llm_for_track(track: str = None, temperature: float = 0.1):
    """
    Construct a ChatOpenAI client for the given inference track.

    Agents call this per-invocation (inside their node functions), so that
    the supervisor's track selection — state["inference_track"] — actually
    determines which backend serves the request.

    If track is None or unknown, falls back to the currently healthy backend
    reported by get_inference_backend().

    Tracks:
      - 'dynamo' : NVIDIA Dynamo / vLLM (data centre GPU)
      - 'rpc'    : llama.cpp RPC master (office distributed cluster)
      - 'local'  : llama.cpp single-node (CPU or single GPU)
      - None     : whatever get_inference_backend() currently returns
    """
    import os
    from langchain_openai import ChatOpenAI

    if track == "dynamo":
        return ChatOpenAI(
            base_url=os.getenv("LLM_BASE_URL", "http://dynamo:8000/v1"),
            api_key=os.getenv("DYNAMO_API_KEY", "dummy"),
            model=os.getenv("MODEL_NAME", "deepseek-7b"),
            temperature=temperature,
        )
    if track == "rpc":
        return ChatOpenAI(
            base_url="http://llama-rpc-master:8082/v1",
            api_key="dummy",
            model=os.getenv("RPC_MASTER_MODEL", "rpc-master"),
            temperature=temperature,
        )
    if track == "local":
        return ChatOpenAI(
            base_url=os.getenv("LLM_CPU_URL", "http://llama-cpp:8080/v1"),
            api_key="dummy",
            model="llama-cpp-model",
            temperature=temperature,
        )

    # Fallback: current health state.
    backend = get_inference_backend()
    return ChatOpenAI(
        base_url=backend["base_url"],
        api_key=backend["api_key"],
        model=backend["model_name"],
        temperature=temperature,
    )