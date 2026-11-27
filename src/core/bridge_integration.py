#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Bridge Integration Service
# =============================================================================
# FILE: src/core/bridge_integration.py
#
# PURPOSE:
#   Provides the BridgeService class that communicates with the
#   nettrades_bridge Odoo module over HTTP. This is the path that
#   actually runs inside the LangGraph container, which has no Odoo
#   environment.
#
#   The previous version also had a direct-Odoo branch behind
#   `self.odoo_env`, but the supervisor never supplied an env and the
#   branch was dead code. It has been removed to avoid confusion.
#
# KEY FEATURES:
#   - Routes requests to the remote brain based on configuration
#   - Handles GPU overflow detection
#   - Integrates with Odoo's nettrades_bridge module
#
# DEPENDENCIES:
#   - aiohttp for HTTP requests
#
# USAGE:
#   from bridge_integration import BridgeService
#   bridge = BridgeService()
#   result = await bridge.route_request(intent, data, company_id)
#
# FIXES (2026-11-16):
#   * Both HTTP calls now send X-API-Key with ODOO_API_KEY. The odoo-proxy
#     requires it on every route (see odoo_proxy/main.py::authenticate);
#     without it the bridge calls have been 401ing silently.
#   * Added explicit Content-Type header. aiohttp's `json=` parameter sets
#     it automatically, but making it explicit prevents any future wrapper
#     (like the ASGI middleware in app.py) from stripping it.
#   * Added logging of the response body on non-200 responses so that a
#     misconfigured URL is diagnosable from the LangGraph logs rather than
#     silently returning None on every call.
#
# KNOWN REMAINING ISSUE (needs a follow-up):
#   The `bridge_url` still points at `{ODOO_PROXY_URL}/api/bridge/route`,
#   but the odoo-proxy does not expose any `/api/bridge/*` routes. The
#   Odoo controller for the bridge lives at (presumably)
#   `nettrades_bridge/controllers/*.py`, and the correct invocation is
#   either:
#     (a) add an `/api/bridge/*` passthrough route to odoo_proxy/main.py
#         that forwards to Odoo's controller, or
#     (b) rewrite this class to call `/jsonrpc` with a JSON-RPC envelope
#         targeting the bridge model.
#   Until one of those is done, every bridge call will return 404 (or
#   the current 401 if the URL were fixed without the header). The P2
#   fix below is necessary but not sufficient.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

import os
import json
import logging
from typing import Dict, Any, Optional

# -----------------------------------------------------------------------------
# Optional imports - fallback if aiohttp is not available
# -----------------------------------------------------------------------------
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

_logger = logging.getLogger(__name__)

# Auth key used by the odoo-proxy. Read at module load because the
# environment is set at container start and does not change.
_ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")


class BridgeService:
    """
    Service for communicating with the nettrades_bridge module over HTTP.

    This service handles the hub-and-spoke routing between local LangGraph
    agents and the remote NETTRADES.AI brain. It checks the bridge
    configuration and determines whether a request should be processed
    locally or forwarded to the remote brain.
    """

    def __init__(self):
        odoo_base = os.getenv(
            "ODOO_PROXY_URL",
            os.getenv("ODOO_URL", "http://odoo:8069"),
        ).rstrip("/")
        # If we are pointed at the odoo-proxy, the route path is /jsonrpc;
        # the bridge is an Odoo JSON-RPC method, so we call it via /jsonrpc
        # and let the controller route it.
        self.bridge_url = f"{odoo_base}/api/bridge/route"
        if not _ODOO_API_KEY:
            _logger.warning(
                "ODOO_API_KEY is not set — bridge HTTP calls will 401. "
                "Set ODOO_API_KEY in the langgraph-server environment."
            )
        _logger.info(f"BridgeService initialised (bridge_url={self.bridge_url})")

    def _headers(self) -> Dict[str, str]:
        """
        Build the standard headers for a bridge call.

        X-API-Key is the credential the odoo-proxy requires. Without it,
        every call is rejected by odoo_proxy/main.py::authenticate.
        """
        return {
            "X-API-Key": _ODOO_API_KEY,
            "Content-Type": "application/json",
        }

    async def route_request(
        self,
        intent: str,
        data: Dict[str, Any],
        company_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Route a request through the bridge to determine the processing target.
        """
        _logger.info(f"Bridge routing request for intent: {intent}, company: {company_id}")

        if not HAS_AIOHTTP:
            _logger.warning("aiohttp not available - bridge routing disabled")
            return None

        try:
            payload = {
                "intent": intent,
                "data": data,
                "company_id": company_id,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.bridge_url,
                    json=payload,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        _logger.info(f"Bridge responded with status: {response.status}")

                        if result.get('status') == 'success':
                            bridge_data = result.get('data', {})
                            if bridge_data.get('source') != 'local':
                                _logger.info(
                                    f"Bridge routed remotely for intent: {intent}"
                                )
                                return bridge_data
                            _logger.info(
                                f"Bridge routed locally for intent: {intent}"
                            )
                            return None
                    else:
                        # Include the response body in the log. Without it,
                        # a 401 (bad key) and a 404 (wrong URL) look
                        # identical from the caller's perspective.
                        try:
                            body_snippet = (await response.text())[:200]
                        except Exception:
                            body_snippet = "<unreadable>"
                        _logger.warning(
                            "Bridge HTTP error: %s %s (url=%s, body=%r)",
                            response.status, response.reason,
                            self.bridge_url, body_snippet,
                        )
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
        """
        _logger.info(f"Fetching bridge configuration for company: {company_id}")

        if not HAS_AIOHTTP:
            return None

        try:
            config_url = f"{self.bridge_url.replace('route', 'config')}"
            if company_id:
                config_url += f"?company_id={company_id}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    config_url,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('data', {})
                    # Same diagnostic improvement as route_request.
                    try:
                        body_snippet = (await response.text())[:200]
                    except Exception:
                        body_snippet = "<unreadable>"
                    _logger.warning(
                        "Bridge config HTTP error: %s %s (url=%s, body=%r)",
                        response.status, response.reason,
                        config_url, body_snippet,
                    )
                    return None
        except Exception as e:
            _logger.warning(f"Failed to fetch bridge configuration: {e}")
            return None