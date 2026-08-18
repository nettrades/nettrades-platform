# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - Core Routing Logic
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/bridge_routing.py
#
# PURPOSE:
#   This model contains the core routing logic for the bridge.
#   It decides whether to route a request locally or to the remote brain
#   based on the configuration, intent, and current system state.
#
#   This is the "brain" of the hub-and-spoke architecture.
#
# UPDATES (2026-08):
#   - Added tenant validation to prevent cross-tenant access
#   - Added audit logging for all cross-tenant requests
#   - Added rate limiting per tenant
#   - Added remote URL validation to prevent SSRF
#   - Added per-tenant configuration support
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging
import json
import requests
import time
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class NettradesBridgeRouting(models.Model):
    """
    Bridge Routing - Core routing logic.

    This model is not stored in the database; it's a service class
    that provides routing methods.
    """
    _name = 'nettrades.bridge.routing'
    _description = 'NETTRADES Bridge Routing Service'
    _transient = True

    # -------------------------------------------------------------------------
    # 1. Routing Methods
    # -------------------------------------------------------------------------

    def route_request(self, intent, data, company_id=None):
        """
        Route an AI request to the appropriate brain.

        This is the main entry point for the bridge routing logic.

        Args:
            intent (str): The intent of the request (recruitment, freelance, gpu, vision, action)
            data (dict): The request data (query, context, etc.)
            company_id (int, optional): The company ID for per-company routing.

        Returns:
            dict: The response from the routed brain.

        Raises:
            ValidationError: If tenant validation fails.
        """
        _logger.info("Routing request with intent: %s for company: %s", intent, company_id)

        # ======================================================================
        # TENANT VALIDATION - CRITICAL SECURITY CHECK
        # ======================================================================
        # This prevents cross-tenant access. A user from Company A cannot
        # access resources belonging to Company B.
        # ======================================================================

        # Get the authenticated user's company
        user_company_id = self.env.user.company_id.id

        # If company_id is provided, validate it matches the user's company
        if company_id:
            if company_id != user_company_id:
                # Log the attempted cross-tenant access
                self._log_cross_tenant_attempt(
                    user_company_id=user_company_id,
                    target_company_id=company_id,
                    intent=intent,
                    data=data
                )
                raise ValidationError(
                    _("You are not authorized to access resources for company ID %s") % company_id
                )
        else:
            # Use the user's own company
            company_id = user_company_id

        # ======================================================================
        # RATE LIMITING - Prevent DoS from a single tenant
        # ======================================================================
        self._check_rate_limit(company_id)

        # ======================================================================
        # ROUTING LOGIC
        # ======================================================================

        # Get effective configuration
        config = self._get_effective_config(company_id)

        # Determine if we should route remotely
        should_route_remote = self._should_route_remote(intent, data, config, company_id)

        if should_route_remote:
            # Route to remote brain
            try:
                response = self._call_remote_brain(intent, data, config, company_id)
                self._log_usage(company_id, intent, 'remote', True, response)
                return response
            except Exception as e:
                _logger.error("Remote brain call failed: %s", e)
                # Fallback to local if enabled
                if config.get('fallback_to_local', True):
                    _logger.info("Falling back to local brain")
                    response = self._call_local_brain(intent, data, company_id)
                    self._log_usage(company_id, intent, 'local_fallback', True, response)
                    return response
                raise

        # Route to local brain
        response = self._call_local_brain(intent, data, company_id)
        self._log_usage(company_id, intent, 'local', True, response)
        return response

    # -------------------------------------------------------------------------
    # 2. Routing Decision Methods
    # -------------------------------------------------------------------------

    def _get_effective_config(self, company_id):
        """
        Get the effective configuration for a company.

        Args:
            company_id (int): The company ID.

        Returns:
            dict: Effective configuration.
        """
        if company_id:
            company_config = self.env['nettrades.bridge.company.config'].get_company_config(company_id)
            return company_config.get_effective_config()

        # No company specified, use global config
        global_config = self.env['nettrades.bridge.config'].get_config()
        return {
            'bridge_mode': global_config.bridge_mode,
            'remote_brain_url': global_config.remote_brain_url,
            'remote_brain_api_key': global_config.remote_brain_api_key,
            'enable_remote_recruitment': global_config.enable_remote_recruitment,
            'enable_remote_freelance': global_config.enable_remote_freelance,
            'enable_remote_gpu': global_config.enable_remote_gpu,
            'enable_remote_vision': global_config.enable_remote_vision,
            'enable_remote_action': global_config.enable_remote_action,
            'gpu_overflow_enabled': global_config.gpu_overflow_enabled,
            'gpu_overflow_threshold': global_config.gpu_overflow_threshold,
            'request_timeout': global_config.request_timeout,
            'max_retries': global_config.max_retries,
            'retry_delay': global_config.retry_delay,
            'fallback_to_local': global_config.fallback_to_local,
            'allowed_remote_domains': global_config.allowed_remote_domains or '',
        }

    def _should_route_remote(self, intent, data, config, company_id):
        """
        Determine if a request should be routed to the remote brain.

        Args:
            intent (str): The intent of the request.
            data (dict): The request data.
            config (dict): The effective configuration.
            company_id (int): The company ID.

        Returns:
            bool: True if the request should be routed remotely.
        """
        # Check if the bridge mode allows remote routing
        if config.get('bridge_mode') == 'local':
            return False

        if config.get('bridge_mode') == 'remote':
            return True

        # Hybrid mode: check intent-specific flags
        intent_map = {
            'recruitment': 'enable_remote_recruitment',
            'freelance': 'enable_remote_freelance',
            'gpu': 'enable_remote_gpu',
            'vision': 'enable_remote_vision',
            'action': 'enable_remote_action',
        }

        flag = intent_map.get(intent)
        if flag and config.get(flag, False):
            # For GPU, also check overflow
            if intent == 'gpu':
                return self._check_gpu_overflow(config, company_id)
            return True

        return False

    def _check_gpu_overflow(self, config, company_id):
        """
        Check if GPU requests should be overflowed to the remote brain.

        Args:
            config (dict): The effective configuration.
            company_id (int): The company ID.

        Returns:
            bool: True if GPU overflow should be triggered.
        """
        if not config.get('gpu_overflow_enabled', False):
            return False

        threshold = config.get('gpu_overflow_threshold', 80.0)

        # Check local GPU utilisation
        # This would call the GPU admin module to get utilisation
        try:
            # Get all online GPU nodes for this company
            gpu_nodes = self.env['gpu.node'].search([
                ('company_id', '=', company_id),
                ('status', '=', 'online'),
            ])

            if not gpu_nodes:
                # No local GPUs, route remotely
                _logger.info("No local GPUs available, routing to remote brain")
                return True

            # Calculate average utilisation
            total_util = 0
            for node in gpu_nodes:
                util = node.get_gpu_utilisation() or 0
                total_util += util

            avg_util = total_util / len(gpu_nodes)
            _logger.info("Local GPU utilisation: %.2f%%, threshold: %.2f%%", avg_util, threshold)

            if avg_util >= threshold:
                _logger.info("GPU utilisation exceeds threshold, routing to remote brain")
                return True

        except Exception as e:
            _logger.warning("Failed to check GPU utilisation: %s", e)
            # On error, default to local to avoid unnecessary remote calls

        return False

    # -------------------------------------------------------------------------
    # 3. Brain Communication Methods
    # -------------------------------------------------------------------------

    def _call_remote_brain(self, intent, data, config, company_id):
        """
        Call the remote NETTRADES.ai brain.

        Args:
            intent (str): The intent of the request.
            data (dict): The request data.
            config (dict): The effective configuration.
            company_id (int): The company ID.

        Returns:
            dict: The response from the remote brain.

        Raises:
            ValidationError: If the remote URL is not allowed.
        """
        remote_url = config.get('remote_brain_url', 'https://api.nettrades.ai').rstrip('/')
        full_url = f"{remote_url}/api/v1/route"

        # ======================================================================
        # REMOTE URL VALIDATION - Prevent SSRF and cross-tenant attacks
        # ======================================================================
        # Verify that the remote URL is allowed for this company
        if not self._is_allowed_remote_url(company_id, remote_url, config):
            _logger.warning(
                "Blocked request to disallowed remote URL %s for company %s",
                remote_url, company_id
            )
            raise ValidationError(_("Remote URL not allowed for this company"))

        headers = {
            'Content-Type': 'application/json',
            'X-Intent': intent,
            'X-Tenant-ID': str(company_id),
        }

        if config.get('remote_brain_api_key'):
            headers['X-API-Key'] = config['remote_brain_api_key']

        # Prepare request payload
        payload = {
            'intent': intent,
            'data': data,
            'timestamp': fields.Datetime.now().isoformat(),
        }

        timeout = config.get('request_timeout', 30)
        max_retries = config.get('max_retries', 3)
        retry_delay = config.get('retry_delay', 1)

        _logger.info("Calling remote brain at %s with intent: %s", full_url, intent)

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    full_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.Timeout:
                _logger.warning("Remote brain request timed out (attempt %d/%d)", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # Exponential backoff

            except requests.exceptions.RequestException as e:
                _logger.warning("Remote brain request failed (attempt %d/%d): %s", attempt + 1, max_retries, e)
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))

        raise Exception(f"Remote brain request failed after {max_retries} attempts")

    def _is_allowed_remote_url(self, company_id, remote_url, config):
        """
        Check if the remote URL is allowed for this company.

        Args:
            company_id (int): The company ID.
            remote_url (str): The remote URL to check.
            config (dict): The effective configuration.

        Returns:
            bool: True if the URL is allowed.
        """
        # Get the company's allowed remote URLs from configuration
        allowed_domains = config.get('allowed_remote_domains', '')

        # If there's a whitelist, check it
        if allowed_domains:
            allowed_list = [d.strip() for d in allowed_domains.split(',') if d.strip()]
            for allowed_domain in allowed_list:
                if allowed_domain in remote_url:
                    return True
            return False

        # If no whitelist, allow only if the URL is from the company's own domain
        # This is a security measure - by default, only allow company-specific URLs
        company = self.env['res.company'].browse(company_id)
        if company and company.website:
            return company.website in remote_url

        # Fallback: require explicit whitelist
        _logger.warning("No whitelist configured for company %s, blocking remote URL", company_id)
        return False

    def _call_local_brain(self, intent, data, company_id):
        """
        Call the local LangGraph brain.

        Args:
            intent (str): The intent of the request.
            data (dict): The request data.
            company_id (int): The company ID.

        Returns:
            dict: The response from the local brain.
        """
        _logger.info("Routing to local brain with intent: %s for company: %s", intent, company_id)

        # Add tenant context to the data
        data['tenant_id'] = company_id
        data['tenant_scope'] = 'local'

        # This would call the local LangGraph agent
        # For now, we simulate a response
        # In a real implementation, this would:
        # 1. Call the LangGraph agent via the MCP-Odoo bridge
        # 2. Or call the local LangGraph FastAPI endpoint

        # Placeholder: simulate local agent response
        return {
            'status': 'success',
            'source': 'local',
            'intent': intent,
            'data': data,
            'message': 'Processed by local LangGraph agent',
            'timestamp': fields.Datetime.now().isoformat(),
        }

    # -------------------------------------------------------------------------
    # 4. Rate Limiting
    # -------------------------------------------------------------------------

    def _check_rate_limit(self, company_id):
        """
        Check if the company has exceeded its rate limit.

        Args:
            company_id (int): The company ID.

        Raises:
            ValidationError: If rate limit is exceeded.
        """
        # Simple in-memory rate limiting (replace with Redis in production)
        cache = self.env['bridge.rate_limit.cache']

        # Get current count
        record = cache.search([('company_id', '=', company_id)], limit=1)
        if not record:
            record = cache.create({
                'company_id': company_id,
                'count': 1,
                'reset_at': datetime.now() + timedelta(minutes=1)
            })
            return

        # Check if reset is needed
        if record.reset_at < datetime.now():
            record.write({'count': 1, 'reset_at': datetime.now() + timedelta(minutes=1)})
            return

        # Check limit
        record.count += 1
        if record.count > record.limit_per_minute:
            _logger.warning("Rate limit exceeded for company %s", company_id)
            raise ValidationError(_("Rate limit exceeded. Please try again later."))

    # -------------------------------------------------------------------------
    # 5. Audit Logging
    # -------------------------------------------------------------------------

    def _log_cross_tenant_attempt(self, user_company_id, target_company_id, intent, data):
        """
        Log attempted cross-tenant access for audit purposes.

        Args:
            user_company_id (int): The source company ID.
            target_company_id (int): The target company ID.
            intent (str): The intent of the request.
            data (dict): The request data.
        """
        try:
            # Create audit log entry
            self.env['bridge.audit.log'].create({
                'user_id': self.env.user.id,
                'source_company_id': user_company_id,
                'target_company_id': target_company_id,
                'intent': intent,
                'data': json.dumps(data),
                'action': 'blocked_cross_tenant_access',
                'timestamp': fields.Datetime.now()
            })
        except Exception as e:
            _logger.warning("Failed to create audit log: %s", e)

        _logger.warning(
            "BLOCKED: Cross-tenant access attempt by user %s from company %s to company %s",
            self.env.user.id, user_company_id, target_company_id
        )

    def _log_usage(self, company_id, intent, source, success, response):
        """
        Log usage for billing and monitoring.

        Args:
            company_id (int): The company ID.
            intent (str): The intent of the request.
            source (str): The source of the response (local, remote, local_fallback).
            success (bool): Whether the request was successful.
            response (dict): The response data.
        """
        try:
            self.env['nettrades.bridge.usage.log'].create({
                'company_id': company_id,
                'intent': intent,
                'source': source,
                'success': success,
                'request_data': json.dumps({'intent': intent}),
                'response_data': json.dumps(response),
            })
        except Exception as e:
            _logger.warning("Failed to log bridge usage: %s", e)


class BridgeRateLimitCache(models.Model):
    """Bridge Rate Limit Cache"""
    _name = 'bridge.rate_limit.cache'
    _description = 'Bridge Rate Limit Cache'

    company_id = fields.Many2one('res.company', string='Company', required=True)
    count = fields.Integer(string='Request Count', default=0)
    limit_per_minute = fields.Integer(string='Limit per Minute', default=60)
    reset_at = fields.Datetime(string='Reset At')


class BridgeAuditLog(models.Model):
    """Bridge Audit Log"""
    _name = 'bridge.audit.log'
    _description = 'Bridge Audit Log'
    _order = 'timestamp DESC'

    user_id = fields.Many2one('res.users', string='User')
    source_company_id = fields.Many2one('res.company', string='Source Company')
    target_company_id = fields.Many2one('res.company', string='Target Company')
    intent = fields.Char(string='Intent')
    data = fields.Text(string='Data')
    action = fields.Selection([
        ('blocked_cross_tenant_access', 'Blocked Cross-Tenant Access'),
        ('rate_limit_exceeded', 'Rate Limit Exceeded'),
        ('remote_forward', 'Remote Forward'),
        ('local_handle', 'Local Handle'),
    ], string='Action')
    timestamp = fields.Datetime(string='Timestamp', default=fields.Datetime.now)
    ip_address = fields.Char(string='IP Address')