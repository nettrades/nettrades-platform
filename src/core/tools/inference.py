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