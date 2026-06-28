#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Bridge Integration Service
# =============================================================================
# FILE: src/core/bridge_integration.py
#
# PURPOSE:
#   This module provides the BridgeService class that communicates with the
#   nettrades_bridge Odoo module. It handles the hub-and-spoke routing
#   between local LangGraph agents and the remote NETTRADES.AI brain.
#
#   This is an OPTIONAL module. If it is not present, the supervisor will
#   fall back to local-only processing using a dummy implementation.
#   However, having it fully implemented enables the commercial hub-and-spoke
#   model where companies can offload work to the central NETTRADES.AI
#   platform.
#
# KEY FEATURES:
#   - Routes requests to remote brain based on configuration
#   - Handles GPU overflow detection
#   - Integrates with Odoo's nettrades_bridge module
#
# DEPENDENCIES:
#   - aiohttp for HTTP requests
#   - Odoo environment (optional, for direct RPC)
#
# USAGE:
#   from bridge_integration import BridgeService
#   bridge = BridgeService()
#   result = await bridge.route_request(intent, data, company_id)
# =============================================================================

import json
import logging
from typing import Dict, Any, Optional

# -----------------------------------------------------------------------------
# Optional imports – fallback if aiohttp is not available
# -----------------------------------------------------------------------------
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

_logger = logging.getLogger(__name__)


class BridgeService:
    """
    Service for communicating with the nettrades_bridge module.

    This service handles the hub-and-spoke routing between local LangGraph
    agents and the remote NETTRADES.AI brain. It checks the bridge
    configuration and determines whether a request should be processed
    locally or forwarded to the remote brain.

    The service can operate in two modes:
    1. Direct Odoo RPC (if an Odoo environment is provided)
    2. HTTP API call to Odoo's bridge endpoint

    If neither mode is available, the service returns None (local-only fallback).

    Attributes:
        odoo_env: An Odoo environment for direct RPC calls.
        bridge_url: The URL of the Odoo bridge API endpoint.
    """

    def __init__(self, odoo_env=None):
        """
        Initialise the BridgeService.

        Args:
            odoo_env: An Odoo environment (optional). If provided, the service
                uses direct RPC to call the bridge. Otherwise, it uses HTTP API calls.
        """
        self.odoo_env = odoo_env
        self.bridge_url = "http://localhost:8069/api/bridge/route"
        _logger.info("BridgeService initialised")

    async def route_request(
        self,
        intent: str,
        data: Dict[str, Any],
        company_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Route a request through the bridge to determine the processing target.

        This method checks the bridge configuration and returns a routing decision.
        If the bridge decides to route remotely, it returns the remote brain's response.
        Otherwise, it returns None to indicate local processing.

        Args:
            intent: The intent of the request (recruitment, freelance, gpu, vision, action, general, etc.)
            data: The request data (messages, user_id, context, etc.)
            company_id: The company ID for per-company routing configuration.

        Returns:
            Optional[Dict[str, Any]]:
                - If routed remotely: the remote brain's response
                - If routed locally: None (fallback to local processing)
                - If bridge is unavailable: None (fallback to local processing)

        Example:
            # In supervisor.py:
            bridge = BridgeService()
            result = await bridge.route_request(
                intent="recruitment",
                data={"messages": [{"role": "user", "content": "Find a developer"}]},
                company_id=1
            )
            if result:
                # Use remote response
                state.update(result)
            else:
                # Process locally
                ...
        """
        _logger.info(f"Bridge routing request for intent: {intent}, company: {company_id}")

        # =====================================================================
        # Option 1: Direct Odoo RPC (if environment is available)
        # =====================================================================
        if self.odoo_env:
            try:
                _logger.debug("Using Odoo RPC for bridge routing")
                routing = self.odoo_env['nettrades.bridge.routing']
                result = routing.route_request(intent, data, company_id)

                # Check if the bridge decided to route remotely
                if result and result.get('source') != 'local':
                    _logger.info(f"Bridge routed remotely via RPC for intent: {intent}")
                    return result
                _logger.info(f"Bridge routed locally via RPC for intent: {intent}")
                return None
            except Exception as e:
                _logger.warning(f"Bridge RPC failed: {e}. Falling back to HTTP API.")

        # =====================================================================
        # Option 2: HTTP API call to Odoo
        # =====================================================================
        if not HAS_AIOHTTP:
            _logger.warning("aiohttp not available – bridge routing disabled")
            return None

        try:
            _logger.debug(f"Using HTTP API for bridge routing: {self.bridge_url}")
            payload = {
                "intent": intent,
                "data": data,
                "company_id": company_id
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.bridge_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        _logger.info(f"Bridge responded with status: {response.status}")

                        # Check if the bridge decided to route remotely
                        if result.get('status') == 'success':
                            bridge_data = result.get('data', {})
                            if bridge_data.get('source') != 'local':
                                _logger.info(f"Bridge routed remotely via HTTP for intent: {intent}")
                                return bridge_data
                            _logger.info(f"Bridge routed locally via HTTP for intent: {intent}")
                            return None
                    else:
                        _logger.warning(f"Bridge HTTP error: {response.status}")
                        return None
        except aiohttp.ClientError as e:
            _logger.warning(f"Bridge HTTP client error: {e}")
            return None
        except TimeoutError as e:
            _logger.warning(f"Bridge HTTP timeout: {e}")
            return None
        except Exception as e:
            _logger.warning(f"Bridge HTTP unexpected error: {e}")
            return None

    async def get_config(self, company_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get the effective bridge configuration for a company.

        This method retrieves the bridge configuration from Odoo, including
        feature flags, GPU overflow settings, and routing rules.

        Args:
            company_id: The company ID (optional). If provided, returns the
                company-specific configuration; otherwise, returns the global configuration.

        Returns:
            Optional[Dict[str, Any]]: The bridge configuration, or None if the bridge is unavailable.
        """
        _logger.info(f"Fetching bridge configuration for company: {company_id}")

        try:
            # Try Odoo RPC first
            if self.odoo_env:
                try:
                    if company_id:
                        company_config = self.odoo_env[
                            'nettrades.bridge.company.config'
                        ].get_company_config(company_id)
                        config = company_config.get_effective_config()
                    else:
                        config = self.odoo_env[
                            'nettrades.bridge.config'
                        ].get_config()
                    return config
                except Exception as e:
                    _logger.warning(f"RPC config fetch failed: {e}")

            # Fallback to HTTP API
            if HAS_AIOHTTP:
                config_url = f"{self.bridge_url.replace('route', 'config')}"
                if company_id:
                    config_url += f"?company_id={company_id}"

                async with aiohttp.ClientSession() as session:
                    async with session.get(config_url, timeout=10) as response:
                        if response.status == 200:
                            result = await response.json()
                            return result.get('data', {})
                return None
        except Exception as e:
            _logger.warning(f"Failed to fetch bridge configuration: {e}")
            return None

# =============================================================================
# MAIN ENTRY POINT (for testing)
# =============================================================================
if __name__ == "__main__":
    import asyncio

    async def test_bridge():
        """Test the BridgeService."""
        bridge = BridgeService()
        result = await bridge.route_request(
            intent="recruitment",
            data={"messages": [{"role": "user", "content": "Find a developer"}]},
            company_id=1
        )
        print(f"Bridge result: {result}")

        config = await bridge.get_config(1)
        print(f"Bridge config: {config}")

    asyncio.run(test_bridge())