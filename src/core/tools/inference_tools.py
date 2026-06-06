# =============================================================================
# Inference Backend Auto-Detection
# =============================================================================
# Detects whether the system is running on a single VM (llama.cpp / vLLM) or
# using GPUStack (Sections G-H).  Returns the appropriate OpenAI-compatible
# client for the LangChain ChatOpenAI wrapper.
# =============================================================================
import os, logging

_logger = logging.getLogger(__name__)


def get_inference_backend() -> dict:
    """
    Detect the available inference backend and return a dict with 'base_url',
    'api_key', and 'model_name' suitable for ChatOpenAI.
    
    Priority:
        1. GPUStack server if GPUSTACK_SERVER_URL is set.
        2. vLLM if VLLM_BASE_URL is set.
        3. llama.cpp (LLM_BASE_URL default).
    """
    # GPUStack detection
    gpustack_url = os.getenv("GPUSTACK_SERVER_URL")
    if gpustack_url:
        _logger.info("Inference backend: GPUStack at %s", gpustack_url)
        return {
            "base_url": gpustack_url.rstrip("/") + "/v1-openai",
            "api_key": os.getenv("GPUSTACK_API_KEY", "dummy"),
            "model_name": os.getenv("LLM_MODEL", "deepseek-r1:1.5b"),
        }

    # vLLM detection
    vllm_url = os.getenv("VLLM_BASE_URL")
    if vllm_url:
        _logger.info("Inference backend: vLLM at %s", vllm_url)
        return {
            "base_url": vllm_url.rstrip("/") + "/v1",
            "api_key": os.getenv("VLLM_API_KEY", "dummy"),
            "model_name": os.getenv("VLLM_MODEL", "deepseek-r1:1.5b"),
        }

    # Fallback: llama.cpp (CPU inference)
    llama_url = os.getenv("LLM_BASE_URL", "http://llama-cpp:8080/v1")
    _logger.info("Inference backend: llama.cpp at %s", llama_url)
    return {
        "base_url": llama_url,
        "api_key": os.getenv("LLAMA_API_KEY", "dummy"),
        "model_name": os.getenv("LLM_MODEL", "deepseek-r1:1.5b"),
    }