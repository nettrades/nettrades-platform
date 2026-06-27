#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – LLM Factory
# =============================================================================
# FILE: src/core/tools/llm_factory.py
#
# PURPOSE:
#   This module provides a factory pattern for creating LLM instances based on
#   configuration stored in Odoo. It supports multiple providers (OpenAI,
#   Anthropic, DeepSeek, Ollama, NETTRADES.AI) and handles:
#     - Dynamic provider switching based on company configuration
#     - GPU overflow detection and routing to NETTRADES.AI
#     - Provider caching for performance
#     - Fallback provider support
#
# KEY FEATURES:
#   - get_llm(company_id, intent) -> BaseChatModel
#   - Unified interface using langchain.init_chat_model()
#   - Automatic provider detection and switching
#   - GPU overflow detection
#   - Provider caching
#
# =============================================================================

import os
import logging
import time
from typing import Dict, Any, Optional, Union
from functools import lru_cache

import requests
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ODOO_PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:3000")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "change_me_in_production")

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. LLM Factory Class
# =============================================================================

class LLMFactory:
    """
    Factory for creating LLM instances based on Odoo configuration.

    This class provides a unified interface for creating LLM instances
    from various providers. It reads configuration from Odoo and dynamically
    creates the appropriate LLM instance using langchain.init_chat_model().

    The factory caches providers for performance and handles fallback
    scenarios when the primary provider is unavailable.
    """

    _instance = None
    _cache: Dict[str, BaseChatModel] = {}

    def __new__(cls):
        """Singleton pattern to share the cache across all instances."""
        if cls._instance is None:
            cls._instance = super(LLMFactory, cls).__new__(cls)
            cls._instance._cache = {}
        return cls._instance

    # -------------------------------------------------------------------------
    # 2. Public Methods
    # -------------------------------------------------------------------------

    def get_llm(
        self,
        company_id: int,
        intent: Optional[str] = None,
        use_fallback: bool = False
    ) -> Optional[BaseChatModel]:
        """
        Get an LLM instance for a company based on its configuration.

        This is the main entry point for the LLM factory. It reads the
        company's LLM configuration from Odoo and creates the appropriate
        LLM instance.

        Args:
            company_id (int): The ID of the company.
            intent (str, optional): The intent of the request (e.g., 'recruitment').
                                    Used for intent-specific routing.
            use_fallback (bool): Whether to use the fallback provider.

        Returns:
            Optional[BaseChatModel]: The configured LLM instance, or None if
                                     configuration is invalid.

        Example:
            llm = LLMFactory().get_llm(company_id=1, intent="recruitment")
            response = await llm.ainvoke(messages)
        """
        # Build cache key
        cache_key = f"{company_id}_{intent or 'default'}_{use_fallback}"

        # Check cache
        if cache_key in self._cache:
            _logger.debug(f"Returning cached LLM for company {company_id}")
            return self._cache[cache_key]

        # Get configuration from Odoo
        config = self._get_config(company_id)
        if not config:
            _logger.error(f"No LLM configuration found for company {company_id}")
            return None

        # Check GPU overflow (for inference intents)
        if self._check_gpu_overflow(config, company_id):
            _logger.info(f"GPU overflow triggered for company {company_id}, routing to NETTRADES.AI")
            llm = self._create_nettrades_ai_llm(config)
        else:
            # Create the primary or fallback LLM
            if use_fallback and config.get('fallback_provider'):
                llm = self._create_llm_from_config(config['fallback_provider'])
            else:
                llm = self._create_llm_from_config(config)

        if llm:
            self._cache[cache_key] = llm
            _logger.info(f"Created LLM instance for company {company_id}: {config.get('provider_type')}")

        return llm

    def clear_cache(self):
        """Clear the LLM cache. Useful after configuration changes."""
        self._cache.clear()
        _logger.info("LLM cache cleared")

    # -------------------------------------------------------------------------
    # 3. Configuration Retrieval
    # -------------------------------------------------------------------------

    def _get_config(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve LLM configuration from Odoo for a company.

        This method calls the Odoo JSON-RPC proxy to fetch the company's
        LLM configuration from the nettrades.llm.company.config model.

        Args:
            company_id (int): The ID of the company.

        Returns:
            Optional[Dict[str, Any]]: The configuration dictionary, or None if
                                       the configuration cannot be retrieved.
        """
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "service": "object",
                    "method": "execute_kw",
                    "args": [
                        os.getenv("ODOO_DB", "odoo"),  # Database name
                        os.getenv("ODOO_USER", 1),    # User ID
                        os.getenv("ODOO_PASSWORD", "admin"),  # Password
                        "nettrades.llm.company.config",
                        "get_effective_config",
                        [company_id],
                        {}
                    ]
                },
                "id": 1
            }

            headers = {
                "X-API-Key": ODOO_API_KEY,
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{ODOO_PROXY_URL}/jsonrpc",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            if result.get("result"):
                return result["result"]
            else:
                _logger.error(f"Odoo returned no result: {result}")
                return None

        except Exception as e:
            _logger.error(f"Failed to retrieve LLM config for company {company_id}: {e}")
            # Fallback to environment variables
            return self._get_fallback_config()

    def _get_fallback_config(self) -> Dict[str, Any]:
        """
        Get fallback configuration from environment variables.

        Returns:
            Dict[str, Any]: Fallback configuration.
        """
        provider_type = os.getenv("LLM_PROVIDER", "openai")
        model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
        api_key = os.getenv(f"{provider_type.upper()}_API_KEY", "")

        return {
            'provider_type': provider_type,
            'model_name': model_name,
            'api_key': api_key,
            'api_base_url': os.getenv(f"{provider_type.upper()}_BASE_URL", ""),
        }

    # -------------------------------------------------------------------------
    # 4. LLM Creation
    # -------------------------------------------------------------------------

    def _create_llm_from_config(self, config: Dict[str, Any]) -> Optional[BaseChatModel]:
        """
        Create an LLM instance from configuration using init_chat_model().

        Args:
            config (Dict[str, Any]): Configuration dictionary with provider_type,
                                     model_name, api_key, and api_base_url.

        Returns:
            Optional[BaseChatModel]: The configured LLM instance, or None if
                                     creation fails.
        """
        provider_type = config.get('provider_type')
        model_name = config.get('model_name')
        api_key = config.get('api_key')
        api_base_url = config.get('api_base_url')

        if not provider_type or not model_name:
            _logger.error(f"Invalid provider configuration: {config}")
            return None

        # Handle OpenAI-compatible providers (NETTRADES.AI, DeepSeek via OpenAI API)
        if provider_type in ['openai', 'nettrades_ai']:
            # NETTRADES.AI uses OpenAI-compatible API
            return self._create_openai_compatible_llm(model_name, api_key, api_base_url, config)

        # Use init_chat_model for all other providers
        try:
            # Build the provider:model string for init_chat_model
            # Format: "provider:model" e.g., "openai:gpt-4", "anthropic:claude-3-5-sonnet"
            provider_model = f"{provider_type}:{model_name}"

            # Prepare kwargs for init_chat_model
            kwargs = {
                "model": provider_model,
                "temperature": config.get('temperature', 0.7),
                "timeout": config.get('request_timeout', 30),
                "max_retries": config.get('max_retries', 3),
            }

            # Add API key if provided
            if api_key:
                kwargs["api_key"] = api_key

            # Add base URL if provided
            if api_base_url:
                kwargs["base_url"] = api_base_url

            # For Ollama, we need to use the ChatOllama class directly
            if provider_type == 'ollama':
                from langchain_ollama import ChatOllama
                return ChatOllama(
                    model=model_name,
                    temperature=config.get('temperature', 0.7),
                    base_url=api_base_url or "http://localhost:11434",
                )

            # For Anthropic, use ChatAnthropic directly
            if provider_type == 'anthropic':
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(
                    model=model_name,
                    temperature=config.get('temperature', 0.7),
                    api_key=api_key,
                    max_tokens=4096,
                )

            # For DeepSeek, use ChatDeepSeek directly
            if provider_type == 'deepseek':
                from langchain_deepseek import ChatDeepSeek
                return ChatDeepSeek(
                    model=model_name,
                    temperature=config.get('temperature', 0.7),
                    api_key=api_key,
                )

            # For all other providers, use init_chat_model
            return init_chat_model(**kwargs)

        except ImportError as e:
            _logger.error(f"Missing provider package for {provider_type}: {e}")
            _logger.info(f"Install: pip install langchain-{provider_type}")
            return None
        except Exception as e:
            _logger.error(f"Failed to create LLM from config: {e}")
            return None

    def _create_openai_compatible_llm(
        self,
        model_name: str,
        api_key: str,
        api_base_url: str,
        config: Dict[str, Any]
    ) -> Optional[BaseChatModel]:
        """
        Create an LLM using the OpenAI-compatible API.

        This is used for NETTRADES.AI and other providers that support the
        OpenAI API format (like DeepSeek when using the OpenAI-compatible endpoint).

        Args:
            model_name (str): The model name.
            api_key (str): The API key.
            api_base_url (str): The API base URL.
            config (Dict[str, Any]): Full configuration.

        Returns:
            Optional[BaseChatModel]: The configured LLM instance.
        """
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model_name,
                temperature=config.get('temperature', 0.7),
                api_key=api_key,
                base_url=api_base_url,
                timeout=config.get('request_timeout', 30),
                max_retries=config.get('max_retries', 3),
            )
        except ImportError:
            _logger.error("langchain-openai not installed")
            return None
        except Exception as e:
            _logger.error(f"Failed to create OpenAI-compatible LLM: {e}")
            return None

    # -------------------------------------------------------------------------
    # 5. NETTRADES.AI Integration
    # -------------------------------------------------------------------------

    def _create_nettrades_ai_llm(self, config: Dict[str, Any]) -> Optional[BaseChatModel]:
        """
        Create an LLM instance for NETTRADES.AI.

        NETTRADES.AI uses an OpenAI-compatible API, so we use ChatOpenAI
        with a custom base URL.

        Args:
            config (Dict[str, Any]): The configuration dictionary.

        Returns:
            Optional[BaseChatModel]: The NETTRADES.AI LLM instance.
        """
        try:
            from langchain_openai import ChatOpenAI

            api_key = config.get('nettrades_ai_api_key')
            base_url = config.get('nettrades_ai_url', 'https://api.nettrades.ai')
            model_name = config.get('model_name', 'nettrades-ai')

            return ChatOpenAI(
                model=model_name,
                temperature=config.get('temperature', 0.7),
                api_key=api_key,
                base_url=f"{base_url}/v1",
                timeout=config.get('request_timeout', 30),
                max_retries=config.get('max_retries', 3),
            )
        except Exception as e:
            _logger.error(f"Failed to create NETTRADES.AI LLM: {e}")
            return None

    # -------------------------------------------------------------------------
    # 6. GPU Overflow Detection
    # -------------------------------------------------------------------------

    def _check_gpu_overflow(self, config: Dict[str, Any], company_id: int) -> bool:
        """
        Check if GPU overflow should be triggered.

        Args:
            config (Dict[str, Any]): The company configuration.
            company_id (int): The company ID.

        Returns:
            bool: True if GPU overflow should be triggered.
        """
        if not config.get('gpu_overflow_enabled', False):
            return False

        threshold = config.get('gpu_overflow_threshold', 80.0)

        # Check local GPU utilisation via Odoo
        try:
            utilisation = self._get_gpu_utilisation(company_id)
            if utilisation is None:
                return False

            if utilisation >= threshold:
                _logger.info(f"GPU utilisation {utilisation:.2f}% >= threshold {threshold}%")
                return True

        except Exception as e:
            _logger.warning(f"Failed to check GPU utilisation: {e}")

        return False

    def _get_gpu_utilisation(self, company_id: int) -> Optional[float]:
        """
        Get the average GPU utilisation for a company.

        Args:
            company_id (int): The company ID.

        Returns:
            Optional[float]: The average utilisation percentage, or None if
                             it cannot be retrieved.
        """
        try:
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
                        "get_gpu_utilisation",
                        [company_id],
                        {}
                    ]
                },
                "id": 1
            }

            headers = {
                "X-API-Key": ODOO_API_KEY,
                "Content-Type": "application/json"
            }

            response = requests.post(
                f"{ODOO_PROXY_URL}/jsonrpc",
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            return result.get("result", 0.0)

        except Exception as e:
            _logger.warning(f"Failed to get GPU utilisation for company {company_id}: {e}")
            return None


# =============================================================================
# 6. Convenience Function
# =============================================================================

def get_llm(company_id: int, intent: Optional[str] = None) -> Optional[BaseChatModel]:
    """
    Convenience function to get an LLM instance for a company.

    Args:
        company_id (int): The ID of the company.
        intent (str, optional): The intent of the request.

    Returns:
        Optional[BaseChatModel]: The configured LLM instance.

    Example:
        from src.core.tools.llm_factory import get_llm

        llm = get_llm(company_id=1, intent="recruitment")
        response = await llm.ainvoke(messages)
    """
    return LLMFactory().get_llm(company_id, intent)


def clear_llm_cache():
    """Clear the LLM cache."""
    LLMFactory().clear_cache()