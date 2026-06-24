# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge – Global Configuration Model
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
    Global Bridge Configuration – system-wide defaults.

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
            record.display_name = f"Bridge – {record.bridge_mode or 'local'}"

    # -------------------------------------------------------------------------
    # 2. Bridge Mode (main switch)
    # -------------------------------------------------------------------------
    bridge_mode = fields.Selection(
        [
            ('local', 'Local Only – All AI runs locally'),
            ('remote', 'Remote Only – All AI runs via Remote Brain'),
            ('hybrid', 'Hybrid – Local first, fallback to Remote on failure'),
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
        password=True,
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