# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - REST API Controller
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/controllers/bridge_controller.py
#
# PURPOSE:
#   This controller provides REST API endpoints for external services to
#   interact with the bridge. It enables:
#   - Routing requests from LangGraph agents
#   - Health checks for monitoring
#   - Configuration retrieval and updates
#
# =============================================================================

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError
import json
import logging

_logger = logging.getLogger(__name__)


class BridgeController(http.Controller):

    # -------------------------------------------------------------------------
    # 1. Health Check
    # -------------------------------------------------------------------------

    @http.route('/api/bridge/health', type='json', auth='public', methods=['GET'], csrf=False)
    def health_check(self):
        """
        Health check endpoint for monitoring.

        Returns:
            dict: Health status of the bridge.
        """
        return {
            'status': 'healthy',
            'version': '1.0.0',
            'timestamp': fields.Datetime.now().isoformat(),
        }

    # -------------------------------------------------------------------------
    # 2. Routing Endpoint
    # -------------------------------------------------------------------------

    @http.route('/api/bridge/route', type='json', auth='user', methods=['POST'], csrf=False)
    def route_request(self):
        """
        Route a request to the appropriate brain.

        This is the main API endpoint for the bridge. It receives a request
        with an intent and data, and returns the response from the routed brain.

        Request format:
        {
            "intent": "recruitment|freelance|gpu|vision|action|general",
            "data": { ... },
            "company_id": 1  # optional
        }

        Returns:
            dict: The response from the routed brain.
        """
        try:
            # Parse request
            params = request.json or {}
            intent = params.get('intent', 'general')
            data = params.get('data', {})
            company_id = params.get('company_id')

            _logger.info("Bridge route request: intent=%s, company=%s", intent, company_id)

            # Get the routing service
            routing = request.env['nettrades.bridge.routing']

            # Route the request
            response = routing.route_request(intent, data, company_id)

            return {
                'status': 'success',
                'data': response,
            }

        except Exception as e:
            _logger.error("Bridge route error: %s", e)
            return {
                'status': 'error',
                'message': str(e),
            }

    # -------------------------------------------------------------------------
    # 3. Configuration Endpoint
    # -------------------------------------------------------------------------

    @http.route('/api/bridge/config', type='json', auth='user', methods=['GET'], csrf=False)
    def get_config(self):
        """
        Get the effective bridge configuration for the current company.

        Returns:
            dict: The effective configuration.
        """
        company_id = request.env.user.company_id.id
        config = request.env['nettrades.bridge.company.config'].get_company_config(company_id)
        effective = config.get_effective_config()

        # Remove sensitive data
        effective.pop('remote_brain_api_key', None)

        return {
            'status': 'success',
            'data': effective,
        }

    # -------------------------------------------------------------------------
    # 4. Usage Logs Endpoint
    # -------------------------------------------------------------------------

    @http.route('/api/bridge/usage', type='json', auth='user', methods=['GET'], csrf=False)
    def get_usage(self):
        """
        Get usage logs for the current company.

        Query parameters:
            - limit: Maximum number of records to return (default 100)
            - offset: Pagination offset (default 0)
            - intent: Filter by intent

        Returns:
            dict: Usage log entries.
        """
        company_id = request.env.user.company_id.id

        # Build domain
        domain = [('company_id', '=', company_id)]

        intent = request.params.get('intent')
        if intent:
            domain.append(('intent', '=', intent))

        limit = int(request.params.get('limit', 100))
        offset = int(request.params.get('offset', 0))

        logs = request.env['nettrades.bridge.usage.log'].search(
            domain,
            order='create_date DESC',
            limit=limit,
            offset=offset
        )

        return {
            'status': 'success',
            'data': [{
                'id': log.id,
                'intent': log.intent,
                'source': log.source,
                'success': log.success,
                'response_time_ms': log.response_time_ms,
                'tokens_used': log.tokens_used,
                'create_date': log.create_date.isoformat() if log.create_date else None,
            } for log in logs],
            'total': request.env['nettrades.bridge.usage.log'].search_count(domain),
        }