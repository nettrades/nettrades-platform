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
    # Dynamo uses the same OpenAI-compatible API endpoint as vLLM
    gpu_url = os.getenv("LLM_BASE_URL", "http://dynamo:8000/v1")
    gpu_api_key = os.getenv("DYNAMO_API_KEY", os.getenv("OPENAI_API_KEY", "dummy"))

    while True:
        try:
            # Perform the health check
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{gpu_url}/models",
                    headers={"Authorization": f"Bearer {gpu_api_key}"}
                )
                is_healthy = (response.status_code == 200)
        except Exception as e:
            _logger.debug(f"Dynamo health check failed: {e}")
            is_healthy = False

        # Update the global status atomically
        with _health_lock:
            _health_status["gpu_healthy"] = is_healthy
            _health_status["last_checked"] = time.time()

        _logger.debug(f"Dynamo health status updated: {is_healthy}")

        # Wait 30 seconds before the next check
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

    # Read the cached health status (lock-free read, boolean is atomic in Python)
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