# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - Per-Company Configuration Model
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/bridge_company_config.py
#
# PURPOSE:
#   This model stores bridge configuration for individual companies.
#   Each company can override the global settings for their own needs.
#
#   This enables the hub-and-spoke model where each client company can
#   configure which services they want to run locally vs remotely.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class NettradesBridgeCompanyConfig(models.Model):
    """
    Per-Company Bridge Configuration.

    Each company can override the global bridge settings. If a company
    does not have a configuration, the global settings are used.
    """
    _name = 'nettrades.bridge.company.config'
    _description = 'NETTRADES Bridge Per-Company Configuration'
    _rec_name = 'company_id'

    # -------------------------------------------------------------------------
    # 1. Company Reference
    # -------------------------------------------------------------------------
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        help="The company this configuration applies to."
    )

    # -------------------------------------------------------------------------
    # 2. Override Settings (copied from global config)
    # -------------------------------------------------------------------------
    override_bridge_mode = fields.Boolean(
        string='Override Bridge Mode',
        default=False,
        help="If checked, use the company-specific bridge mode instead of the global one."
    )

    bridge_mode = fields.Selection(
        [
            ('local', 'Local Only'),
            ('remote', 'Remote Only'),
            ('hybrid', 'Hybrid - Local first, fallback to Remote'),
        ],
        string='Bridge Mode',
        help="Company-specific bridge mode."
    )

    # -------------------------------------------------------------------------
    # 3. Feature Flags Override
    # -------------------------------------------------------------------------
    override_features = fields.Boolean(
        string='Override Feature Flags',
        default=False,
        help="If checked, use company-specific feature flags."
    )

    enable_remote_recruitment = fields.Boolean(
        string='Remote Recruitment',
        help="Route recruitment queries to the remote brain."
    )

    enable_remote_freelance = fields.Boolean(
        string='Remote Freelance',
        help="Route freelance queries to the remote brain."
    )

    enable_remote_gpu = fields.Boolean(
        string='Remote GPU Management',
        help="Route GPU management queries to the remote brain."
    )

    enable_remote_vision = fields.Boolean(
        string='Remote Vision',
        help="Route vision/image queries to the remote brain."
    )

    enable_remote_action = fields.Boolean(
        string='Remote Action',
        help="Route robotic action queries to the remote brain."
    )

    # -------------------------------------------------------------------------
    # 4. GPU Overflow Override
    # -------------------------------------------------------------------------
    override_gpu_overflow = fields.Boolean(
        string='Override GPU Overflow',
        default=False,
        help="If checked, use company-specific GPU overflow settings."
    )

    gpu_overflow_enabled = fields.Boolean(
        string='Enable GPU Overflow',
        help="Automatically route GPU requests to remote marketplace when local capacity is insufficient."
    )

    gpu_overflow_threshold = fields.Float(
        string='GPU Overflow Threshold (%)',
        help="GPU utilisation threshold above which requests are overflowed."
    )

    # -------------------------------------------------------------------------
    # 5. Remote Connection Override
    # -------------------------------------------------------------------------
    override_remote_url = fields.Boolean(
        string='Override Remote URL',
        default=False,
        help="If checked, use company-specific remote brain URL."
    )

    remote_brain_url = fields.Char(
        string='Remote Brain URL',
        help="Company-specific remote brain URL."
    )

    remote_brain_api_key = fields.Char(
        string='Remote Brain API Key',
        password=True,
        copy=False,
        help="Company-specific API key for the remote brain."
    )

    # -------------------------------------------------------------------------
    # 6. Helper Methods
    # -------------------------------------------------------------------------
    @api.model
    def get_company_config(self, company_id):
        """
        Get or create a company configuration record.

        Args:
            company_id (int): The ID of the company.

        Returns:
            NettradesBridgeCompanyConfig record
        """
        config = self.search([('company_id', '=', company_id)], limit=1)
        if not config:
            config = self.create({
                'company_id': company_id,
            })
            _logger.info("Created default bridge configuration for company %s", company_id)
        return config

    def get_effective_config(self):
        """
        Get the effective configuration for this company, merging global
        and company-specific settings.

        Returns:
            dict: A dictionary with all effective settings.
        """
        self.ensure_one()

        # Start with global config
        global_config = self.env['nettrades.bridge.config'].get_config()

        # Build effective config
        effective = {
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
        }

        # Override with company settings
        if self.override_bridge_mode and self.bridge_mode:
            effective['bridge_mode'] = self.bridge_mode

        if self.override_features:
            if self.enable_remote_recruitment is not None:
                effective['enable_remote_recruitment'] = self.enable_remote_recruitment
            if self.enable_remote_freelance is not None:
                effective['enable_remote_freelance'] = self.enable_remote_freelance
            if self.enable_remote_gpu is not None:
                effective['enable_remote_gpu'] = self.enable_remote_gpu
            if self.enable_remote_vision is not None:
                effective['enable_remote_vision'] = self.enable_remote_vision
            if self.enable_remote_action is not None:
                effective['enable_remote_action'] = self.enable_remote_action

        if self.override_gpu_overflow:
            if self.gpu_overflow_enabled is not None:
                effective['gpu_overflow_enabled'] = self.gpu_overflow_enabled
            if self.gpu_overflow_threshold:
                effective['gpu_overflow_threshold'] = self.gpu_overflow_threshold

        if self.override_remote_url:
            if self.remote_brain_url:
                effective['remote_brain_url'] = self.remote_brain_url
            if self.remote_brain_api_key:
                effective['remote_brain_api_key'] = self.remote_brain_api_key

        return effective