# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - Global Configuration Model
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/bridge_config.py
#
# PURPOSE:
#   This model stores the global (system-wide) configuration for the bridge.
#   It defines the default bridge mode, remote brain URL, API key, feature
#   flags, performance settings, and fallback behaviour.
#
#   The administrator can configure these settings via the Odoo admin
#   interface, providing a user-friendly way to control the routing logic.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class NettradesBridgeConfig(models.Model):
    """
    Global Bridge Configuration - system-wide defaults.

    This model is a singleton (only one record) that stores the global
    bridge settings. These settings apply to all companies unless a company
    has its own override configuration.
    """
    _name = 'nettrades.bridge.config'
    _description = 'NETTRADES Bridge Global Configuration'
    _rec_name = 'display_name'

    # -------------------------------------------------------------------------
    # 1. Display Name (computed)
    # -------------------------------------------------------------------------
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
        help="Human-readable name showing the current mode."
    )

    @api.depends('bridge_mode')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"Bridge - {record.bridge_mode or 'local'}"

    # -------------------------------------------------------------------------
    # 2. Bridge Mode (main switch)
    # -------------------------------------------------------------------------
    bridge_mode = fields.Selection(
        [
            ('local', 'Local Only - All AI runs locally'),
            ('remote', 'Remote Only - All AI runs via Remote Brain'),
            ('hybrid', 'Hybrid - Local first, fallback to Remote on failure'),
        ],
        string='Bridge Mode',
        required=True,
        default='local',
        help="""Determines how AI requests are routed:
            - Local Only: All requests are processed by the local LangGraph agents.
            - Remote Only: All requests are forwarded to the remote NETTRADES.ai brain.
            - Hybrid: Requests try local first; if that fails, they fall back to remote.
        """
    )

    # -------------------------------------------------------------------------
    # 3. Remote Brain Connection
    # -------------------------------------------------------------------------
    remote_brain_url = fields.Char(
        string='Remote Brain URL',
        default='https://api.nettrades.ai',
        help="The base URL of the remote NETTRADES.ai brain."
    )

    remote_brain_api_key = fields.Char(
        string='Remote Brain API Key',
        help="The API key for authenticating with the remote brain.",
        copy=False,
    )

    # -------------------------------------------------------------------------
    # 4. Feature Flags (per intent)
    # -------------------------------------------------------------------------
    enable_remote_recruitment = fields.Boolean(
        string='Remote Recruitment',
        default=False,
        help="If enabled, recruitment queries are routed to the remote brain."
    )

    enable_remote_freelance = fields.Boolean(
        string='Remote Freelance',
        default=False,
        help="If enabled, freelance queries are routed to the remote brain."
    )

    enable_remote_gpu = fields.Boolean(
        string='Remote GPU Management',
        default=False,
        help="If enabled, GPU management queries are routed to the remote brain."
    )

    enable_remote_vision = fields.Boolean(
        string='Remote Vision',
        default=False,
        help="If enabled, vision/image queries are routed to the remote brain."
    )

    enable_remote_action = fields.Boolean(
        string='Remote Action',
        default=False,
        help="If enabled, robotic action queries are routed to the remote brain."
    )

    # -------------------------------------------------------------------------
    # 5. GPU Overflow Configuration
    # -------------------------------------------------------------------------
    gpu_overflow_enabled = fields.Boolean(
        string='Enable GPU Overflow',
        default=False,
        help="If enabled, when local GPU capacity is insufficient, the system "
             "will automatically route inference requests to the remote "
             "NETTRADES.ai GPU marketplace."
    )

    gpu_overflow_threshold = fields.Float(
        string='GPU Overflow Threshold (%)',
        default=80.0,
        help="The GPU utilisation threshold (0-100) above which requests are "
             "considered for overflow routing. For example, if set to 80%, "
             "requests will be routed to the remote brain when local GPU "
             "utilisation exceeds 80%."
    )

    # -------------------------------------------------------------------------
    # 6. Performance Settings
    # -------------------------------------------------------------------------
    request_timeout = fields.Integer(
        string='Request Timeout (seconds)',
        default=30,
        help="Maximum time to wait for a response from the remote brain."
    )

    max_retries = fields.Integer(
        string='Maximum Retries',
        default=3,
        help="Number of retry attempts for failed remote requests."
    )

    retry_delay = fields.Integer(
        string='Retry Delay (seconds)',
        default=1,
        help="Initial delay between retries (exponential backoff)."
    )

    # -------------------------------------------------------------------------
    # 7. Fallback Settings
    # -------------------------------------------------------------------------
    fallback_to_local = fields.Boolean(
        string='Fallback to Local on Remote Failure',
        default=True,
        help="If the remote brain is unreachable or returns an error, automatically "
             "fall back to local processing (if the bridge mode permits)."
    )

    # -------------------------------------------------------------------------
    # 8. Health Check
    # -------------------------------------------------------------------------
    health_check_enabled = fields.Boolean(
        string='Enable Health Check',
        default=True,
        help="Periodically check if the remote brain is healthy."
    )

    health_check_interval = fields.Integer(
        string='Health Check Interval (minutes)',
        default=5,
        help="How often to check the remote brain health."
    )

    # -------------------------------------------------------------------------
    # 9. Singleton Constraints
    # -------------------------------------------------------------------------
    @api.constrains('id')
    def _check_singleton(self):
        """
        Ensure that only one record exists.
        """
        if len(self) > 1:
            raise ValidationError(_("There can only be one global bridge configuration."))

    # -------------------------------------------------------------------------
    # 10. Helper Methods
    # -------------------------------------------------------------------------
    @api.model
    def get_config(self):
        """
        Get the singleton configuration record. If it doesn't exist, create it.

        Returns:
            NettradesBridgeConfig record
        """
        config = self.search([], limit=1)
        if not config:
            config = self.create({
                'bridge_mode': 'local',
                'remote_brain_url': 'https://api.nettrades.ai',
            })
            _logger.info("Created default bridge configuration")
        return config

    def action_test_connection(self):
        """
        Test the remote brain connection using the configured URL and API key.

        Returns:
            dict: A notification to display in the Odoo UI.
        """
        self.ensure_one()
        if self.bridge_mode == 'local':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Test Connection'),
                    'message': _('Local mode is active. No remote connection to test.'),
                    'type': 'info',
                    'sticky': False,
                }
            }

        try:
            import requests
            url = f"{self.remote_brain_url.rstrip('/')}/health"
            headers = {}
            if self.remote_brain_api_key:
                headers['X-API-Key'] = self.remote_brain_api_key

            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to remote brain at {}').format(
                            self.remote_brain_url),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Failed'),
                        'message': _('Remote brain returned status code {}').format(
                            response.status_code),
                        'type': 'danger',
                        'sticky': False,
                    }
                }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': False,
                }
            }

    # -------------------------------------------------------------------------
    # 11. Scheduled Health Check
    # -------------------------------------------------------------------------
    def _cron_health_check(self):
        """
        Scheduled health check for the remote brain.

        Called every 5 minutes by the ir.cron record defined in
        `data/bridge_cron_data.xml`. Since the bridge config is a
        singleton, the loop below iterates over exactly one record.

        Behaviour:
          - If `bridge_mode` is `local`, returns immediately. There is
            nothing remote to check, and this is the default state, so
            the common case is a fast no-op.
          - If `health_check_enabled` is False, returns immediately.
          - If `remote_brain_url` is empty, logs a warning once and
            returns.
          - Otherwise, sends a GET request to
            `<remote_brain_url>/health` with a short timeout and logs
            the result at INFO (healthy) or WARNING (unhealthy,
            timeout, connection error).

        Failure handling:
          Every network exception is caught and logged. The cron will
          never raise. This is deliberate: a transient network outage
          should not abort the cron job or spam the Odoo error log.

        Future work:
          When you have a notification channel (email, internal
          notification, or an on-screen status indicator), this method
          should also record the outcome on the config record so the
          UI can display "last checked: <time>, status: healthy/error".
          That requires a couple of new fields on the model
          (`last_health_check`, `last_health_status`). Not added yet.
        """
        # Imported lazily so that a missing `requests` package does not
        # break module loading on install.
        import requests

        for config in self:
            # Fast path: local mode never talks to a remote brain.
            if config.bridge_mode == 'local':
                _logger.debug(
                    "Bridge health check: skipped (bridge_mode is 'local')"
                )
                continue

            # Operator has explicitly disabled health checking.
            if not config.health_check_enabled:
                _logger.debug(
                    "Bridge health check: skipped (health_check_enabled=False)"
                )
                continue

            # Nothing to probe without a URL.
            if not config.remote_brain_url:
                _logger.warning(
                    "Bridge health check: skipped (no remote_brain_url set)"
                )
                continue

            url = f"{config.remote_brain_url.rstrip('/')}/health"
            headers = {}
            if config.remote_brain_api_key:
                headers['X-API-Key'] = config.remote_brain_api_key

            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    _logger.info(
                        "Bridge health check: remote brain at %s is healthy",
                        config.remote_brain_url,
                    )
                else:
                    _logger.warning(
                        "Bridge health check: remote brain at %s returned %s",
                        config.remote_brain_url,
                        response.status_code,
                    )
            except requests.exceptions.Timeout:
                _logger.warning(
                    "Bridge health check: remote brain at %s timed out",
                    config.remote_brain_url,
                )
            except requests.exceptions.RequestException as e:
                _logger.warning(
                    "Bridge health check: remote brain at %s unreachable: %s",
                    config.remote_brain_url,
                    e,
                )

        return True