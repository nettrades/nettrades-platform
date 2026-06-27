# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LLM Configuration – Company LLM Settings
# =============================================================================
# FILE: odoo-modules/nettrades_llm_config/models/llm_company_config.py
#
# PURPOSE:
#   This model stores LLM configuration settings for each company.
#   It determines which provider and model the LangGraph supervisor should use
#   for inference requests from that company.
#
# KEY FIELDS:
#   - provider_id: The primary LLM provider (OpenAI, Anthropic, DeepSeek, etc.)
#   - model_name: The specific model to use (gpt-4, claude-3-5-sonnet, etc.)
#   - api_key: The API key for the provider (stored securely)
#   - api_base_url: Custom API endpoint (for self-hosted or local LLMs)
#   - fallback_provider_id: Provider to use if primary fails
#   - gpu_overflow_enabled: Route to NETTRADES.AI GPU marketplace when local GPU full
#   - gpu_overflow_threshold: GPU utilisation threshold for overflow
#   - use_nettrades_ai_for_training: Use NETTRADES.AI for fine-tuning
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class LLMCompanyConfig(models.Model):
    """
    Company-specific LLM configuration.

    Each company can have its own LLM provider settings, allowing different
    companies to use different providers, models, and API keys.
    """
    _name = 'nettrades.llm.company.config'
    _description = 'Company LLM Configuration'
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

    active = fields.Boolean(
        string='Active',
        default=True,
        help="Whether this configuration is active."
    )

    # -------------------------------------------------------------------------
    # 2. Primary Provider Configuration
    # -------------------------------------------------------------------------

    provider_id = fields.Many2one(
        'llm.provider',
        string='Primary LLM Provider',
        required=True,
        help="The primary LLM provider for this company. "
             "This determines which LLM is used for agent inference."
    )

    # =========================================================================
    # FIX: This uses the existing llm.provider model from Apexive odoo-llm
    # The llm.provider model already stores provider_type, api_key, base_url,
    # and default_model. We extend it with company-specific overrides.
    # =========================================================================

    # Override provider fields with company-specific values
    override_api_key = fields.Boolean(
        string='Override API Key',
        default=False,
        help="If checked, use a company-specific API key instead of the provider's default."
    )

    api_key = fields.Char(
        string='API Key',
        password=True,
        copy=False,
        help="Company-specific API key for the provider. "
             "If not set, the provider's default API key is used."
    )

    override_api_base_url = fields.Boolean(
        string='Override API Base URL',
        default=False,
        help="If checked, use a company-specific API endpoint."
    )

    api_base_url = fields.Char(
        string='API Base URL',
        help="Company-specific API endpoint. "
             "Useful for self-hosted or local LLM instances."
    )

    override_model = fields.Boolean(
        string='Override Model',
        default=False,
        help="If checked, use a company-specific model name."
    )

    model_name = fields.Char(
        string='Model Name',
        help="Company-specific model name. "
             "Examples: 'gpt-4', 'claude-3-5-sonnet', 'deepseek-chat', 'llama3.2'"
    )

    # -------------------------------------------------------------------------
    # 3. Fallback Provider
    # -------------------------------------------------------------------------

    fallback_provider_id = fields.Many2one(
        'llm.provider',
        string='Fallback LLM Provider',
        help="Provider to use if the primary provider fails or is unavailable."
    )

    fallback_model_name = fields.Char(
        string='Fallback Model Name',
        help="Model to use with the fallback provider."
    )

    # -------------------------------------------------------------------------
    # 4. GPU Overflow Configuration
    # -------------------------------------------------------------------------

    gpu_overflow_enabled = fields.Boolean(
        string='Enable GPU Overflow',
        default=False,
        help="If enabled, when local GPU capacity is insufficient, "
             "inference requests are routed to NETTRADES.AI's GPU marketplace."
    )

    gpu_overflow_threshold = fields.Float(
        string='GPU Overflow Threshold (%)',
        default=80.0,
        help="GPU utilisation threshold (0-100) above which requests are "
             "routed to NETTRADES.AI's GPU marketplace."
    )

    use_nettrades_ai_for_training = fields.Boolean(
        string='Use NETTRADES.AI for Training',
        default=False,
        help="If enabled, fine-tuning jobs are submitted to NETTRADES.AI "
             "instead of local GPU resources."
    )

    # -------------------------------------------------------------------------
    # 5. NETTRADES.AI Configuration
    # -------------------------------------------------------------------------

    nettrades_ai_url = fields.Char(
        string='NETTRADES.AI URL',
        default='https://api.nettrades.ai',
        help="The URL of the NETTRADES.AI brain for overflow and global services."
    )

    nettrades_ai_api_key = fields.Char(
        string='NETTRADES.AI API Key',
        password=True,
        copy=False,
        help="API key for authenticating with NETTRADES.AI."
    )

    # -------------------------------------------------------------------------
    # 6. Performance Settings
    # -------------------------------------------------------------------------

    request_timeout = fields.Integer(
        string='Request Timeout (seconds)',
        default=30,
        help="Maximum time to wait for an LLM response."
    )

    max_retries = fields.Integer(
        string='Maximum Retries',
        default=3,
        help="Number of retry attempts for failed LLM requests."
    )

    temperature = fields.Float(
        string='Default Temperature',
        default=0.7,
        help="Default sampling temperature for the LLM."
    )

    # -------------------------------------------------------------------------
    # 7. Constraints
    # -------------------------------------------------------------------------

    @api.constrains('gpu_overflow_threshold')
    def _check_threshold(self):
        """Ensure GPU overflow threshold is between 0 and 100."""
        for record in self:
            if record.gpu_overflow_enabled and record.gpu_overflow_threshold:
                if record.gpu_overflow_threshold < 0 or record.gpu_overflow_threshold > 100:
                    raise ValidationError(_("GPU overflow threshold must be between 0 and 100."))

    # -------------------------------------------------------------------------
    # 8. Helper Methods
    # -------------------------------------------------------------------------

    @api.model
    def get_company_config(self, company_id):
        """
        Get or create the LLM configuration for a company.

        Args:
            company_id (int): The ID of the company.

        Returns:
            LLMCompanyConfig: The configuration record.
        """
        config = self.search([('company_id', '=', company_id)], limit=1)
        if not config:
            # Create a default configuration using the global provider
            default_provider = self.env['llm.provider'].search([
                ('active', '=', True)
            ], limit=1)

            config = self.create({
                'company_id': company_id,
                'provider_id': default_provider.id if default_provider else None,
                'active': True,
            })
            _logger.info(f"Created default LLM configuration for company {company_id}")

        return config

    def get_effective_config(self):
        """
        Get the effective configuration for this company, merging
        company-specific overrides with the provider's defaults.

        Returns:
            dict: A dictionary with all effective settings.
        """
        self.ensure_one()

        # Start with provider defaults
        provider = self.provider_id
        effective = {
            'provider_id': provider.id,
            'provider_type': provider.provider_type,
            'api_key': provider.api_key,
            'api_base_url': provider.api_base_url,
            'model_name': provider.default_model,
            'temperature': self.temperature or 0.7,
            'request_timeout': self.request_timeout or 30,
            'max_retries': self.max_retries or 3,
            'company_id': self.company_id.id,
        }

        # Override with company-specific settings
        if self.override_api_key and self.api_key:
            effective['api_key'] = self.api_key

        if self.override_api_base_url and self.api_base_url:
            effective['api_base_url'] = self.api_base_url

        if self.override_model and self.model_name:
            effective['model_name'] = self.model_name

        # Add fallback provider
        if self.fallback_provider_id:
            effective['fallback_provider'] = {
                'provider_id': self.fallback_provider_id.id,
                'provider_type': self.fallback_provider_id.provider_type,
                'api_key': self.fallback_provider_id.api_key,
                'model_name': self.fallback_model_name or self.fallback_provider_id.default_model,
            }

        # Add GPU overflow settings
        effective['gpu_overflow_enabled'] = self.gpu_overflow_enabled
        effective['gpu_overflow_threshold'] = self.gpu_overflow_threshold
        effective['use_nettrades_ai_for_training'] = self.use_nettrades_ai_for_training
        effective['nettrades_ai_url'] = self.nettrades_ai_url
        effective['nettrades_ai_api_key'] = self.nettrades_ai_api_key

        return effective

    def get_llm_provider_class(self, provider_type):
        """
        Get the appropriate LangChain provider class for a given provider type.

        Args:
            provider_type (str): The provider type (openai, anthropic, deepseek, ollama)

        Returns:
            str: The LangChain class name to use with init_chat_model.
        """
        provider_map = {
            'openai': 'openai',
            'anthropic': 'anthropic',
            'deepseek': 'deepseek',
            'ollama': 'ollama',
            'nettrades_ai': 'openai',  # NETTRADES.AI uses OpenAI-compatible API
        }
        return provider_map.get(provider_type, 'openai')