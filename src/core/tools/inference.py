#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Inference Backend
# =============================================================================
# FILE: src/core/tools/inference.py
#
# PURPOSE:
#   This module provides a unified interface for LLM inference across
#   multiple backends (OpenAI, Ollama, LiteLLM, local models).
#
#   It is used by all LangGraph agents to generate responses and perform
#   reasoning tasks. The backend is configurable via environment variables
#   and can be switched at runtime.
#
# USAGE:
#   from src.core.tools import get_inference_backend
#
#   backend = get_inference_backend()
#   response = await backend.generate(
#       messages=[{"role": "user", "content": "Hello"}],
#       model="gpt-4",
#       temperature=0.7,
#   )
#
# =============================================================================

import os
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field

# -----------------------------------------------------------------------------
# Optional imports – each backend is optional so we can fall back gracefully
# -----------------------------------------------------------------------------
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. Data Classes
# =============================================================================

@dataclass
class InferenceResponse:
    """
    Standardised response from any inference backend.

    Attributes:
        content: The generated text content.
        model: The model used for generation.
        usage: Token usage (prompt_tokens, completion_tokens, total_tokens).
        finish_reason: Reason for stopping (stop, length, etc.).
        raw: The raw response object (backend-specific).
    """
    content: str
    model: str = "unknown"
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: Optional[str] = None
    raw: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialisation."""
        return {
            'content': self.content,
            'model': self.model,
            'usage': self.usage,
            'finish_reason': self.finish_reason,
        }


# =============================================================================
# 2. Inference Backend Base Class
# =============================================================================

class InferenceBackend:
    """
    Abstract base class for inference backends.

    All backends must implement the `generate()` method.
    """

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs
    ) -> InferenceResponse:
        """
        Generate a response from the model.

        Args:
            messages: List of message dicts with "role" and "content".
            model: The model identifier (e.g., "gpt-4").
            temperature: Sampling temperature (0.0 to 1.0).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional backend-specific parameters.

        Returns:
            InferenceResponse: The generated response.
        """
        raise NotImplementedError("Subclasses must implement generate()")


# =============================================================================
# 3. OpenAI Backend
# =============================================================================

class OpenAIBackend(InferenceBackend):
    """
    Inference backend using OpenAI's API.
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        if not HAS_OPENAI:
            _logger.warning("OpenAI library not installed – OpenAI backend will not work")
        self.client = None
        if HAS_OPENAI and self.api_key:
            self.client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs
    ) -> InferenceResponse:
        if not self.client:
            raise RuntimeError("OpenAI client not initialised. Check API key and library.")

        try:
            response = await self.client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return InferenceResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage={
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens,
                },
                finish_reason=response.choices[0].finish_reason,
                raw=response,
            )
        except Exception as e:
            _logger.error(f"OpenAI generation failed: {e}")
            raise


# =============================================================================
# 4. Ollama Backend (Local Models)
# =============================================================================

class OllamaBackend(InferenceBackend):
    """
    Inference backend using a local Ollama instance.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        if not HAS_AIOHTTP:
            _logger.warning("aiohttp not installed – Ollama backend may not work")

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs
    ) -> InferenceResponse:
        if not HAS_AIOHTTP:
            raise RuntimeError("aiohttp is required for Ollama backend")

        # Convert messages to a single prompt (Ollama's chat API is also available)
        # Here we use the /api/generate endpoint with a system prompt and prompt.
        # For simplicity, we construct a prompt from messages.
        prompt = ""
        for msg in messages:
            if msg["role"] == "system":
                prompt += f"System: {msg['content']}\n"
            elif msg["role"] == "user":
                prompt += f"User: {msg['content']}\n"
            elif msg["role"] == "assistant":
                prompt += f"Assistant: {msg['content']}\n"
        prompt += "Assistant: "

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": model or "llama3.2",
                    "prompt": prompt,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return InferenceResponse(
                            content=result.get('response', ''),
                            model=result.get('model', 'ollama'),
                            usage={'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                            finish_reason='stop',
                            raw=result,
                        )
                    else:
                        error_text = await response.text()
                        raise RuntimeError(f"Ollama error {response.status}: {error_text}")
        except Exception as e:
            _logger.error(f"Ollama generation failed: {e}")
            raise


# =============================================================================
# 5. Factory Function to Get the Backend
# =============================================================================

def get_inference_backend() -> InferenceBackend:
    """
    Get the configured inference backend based on environment variables.

    The backend is determined by the `INFERENCE_BACKEND` environment variable:
        - "openai" → OpenAIBackend (default if OPENAI_API_KEY is set)
        - "ollama" → OllamaBackend
        - If not set, tries OpenAI first, then Ollama.

    Returns:
        InferenceBackend: An instance of the selected backend.

    Example:
        backend = get_inference_backend()
        response = await backend.generate(
            messages=[{"role": "user", "content": "Hello"}]
        )
    """
    backend_type = os.environ.get("INFERENCE_BACKEND", "").lower()

    if backend_type == "openai" or (backend_type == "" and os.environ.get("OPENAI_API_KEY")):
        if HAS_OPENAI:
            _logger.info("Using OpenAI inference backend")
            return OpenAIBackend()
        else:
            _logger.warning("OpenAI backend requested but openai library not installed")

    if backend_type == "ollama" or (backend_type == "" and os.environ.get("OLLAMA_BASE_URL")):
        _logger.info("Using Ollama inference backend")
        return OllamaBackend()

    # Default fallback: try OpenAI if available, else Ollama
    if HAS_OPENAI and os.environ.get("OPENAI_API_KEY"):
        _logger.info("Falling back to OpenAI backend")
        return OpenAIBackend()

    _logger.info("Falling back to Ollama backend (default)")
    return OllamaBackend()