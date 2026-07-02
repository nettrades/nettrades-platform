# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness - Configuration Models
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/models/fairness_config.py
#
# PURPOSE:
#   This file defines the configuration models for the fairness system.
#   It provides:
#     1. Global configuration (singleton) - system-wide defaults
#     2. Field-specific configuration - per-professional field overrides
#
#   The configuration is stored in the database and can be modified
#   through the Odoo admin interface.
#
# CONFIGURATION HIERARCHY:
#   1. Field-specific overrides (highest priority)
#   2. Global configuration (fallback)
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class FairnessGlobalConfig(models.Model):
    """
    Global Fairness Configuration - system-wide defaults.

    This model is a singleton (only one record) that stores the global
    fairness settings. These settings apply to all fields unless overridden
    by a field-specific configuration.
    """
    _name = 'nettrades.fairness.config'
    _description = 'Fairness Global Configuration'
    _rec_name = 'display_name'

    # =========================================================================
    # 1. Display Name (computed)
    # =========================================================================
    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
        help="Human-readable name showing the current status."
    )

    @api.depends('rationality_evaluation_enabled', 'bias_detection_enabled')
    def _compute_display_name(self):
        for record in self:
            status_parts = []
            if record.rationality_evaluation_enabled:
                status_parts.append("Rationality ON")
            if record.bias_detection_enabled:
                status_parts.append("Bias Detection ON")
            if not status_parts:
                status_parts.append("Disabled")
            record.display_name = f"Fairness - {' / '.join(status_parts)}"

    # =========================================================================
    # 2. Feature Controls (Enable/Disable)
    # =========================================================================
    rationality_evaluation_enabled = fields.Boolean(
        string='Enable Rationality Evaluation',
        default=True,
        help="When enabled, all AI responses are evaluated for logical "
             "coherence and reasoning quality using an LLM-as-Judge."
    )

    bias_detection_enabled = fields.Boolean(
        string='Enable Bias Detection',
        default=True,
        help="When enabled, all AI responses are evaluated for bias against "
             "protected attributes using an LLM-as-Judge."
    )

    auto_flag_for_review = fields.Boolean(
        string='Auto-Flag for Human Review',
        default=True,
        help="Automatically flag low-rationality or high-bias responses "
             "for human review. Flagged responses appear in the admin "
             "dashboard for manual inspection."
    )

    auto_filter_training = fields.Boolean(
        string='Auto-Filter Training Data',
        default=True,
        help="Automatically exclude low-rationality or high-bias responses "
             "from fine-tuning datasets. This ensures that only high-quality "
             "examples are used for training."
    )

    auto_audit_enabled = fields.Boolean(
        string='Enable Automated Audits',
        default=True,
        help="Automatically run fairness audits on a scheduled basis. "
             "Audit results are stored in the audit log for compliance "
             "and monitoring purposes."
    )

    # =========================================================================
    # 3. Quality Thresholds
    # =========================================================================
    rationality_threshold = fields.Float(
        string='Minimum Rationality Score',
        default=7.0,
        help="The minimum rationality score (0-10) required for a response "
             "to be considered high-quality. Responses below this threshold "
             "are flagged and filtered from training data. Higher scores "
             "indicate better logical coherence and reasoning."
    )

    bias_threshold = fields.Float(
        string='Maximum Bias Score',
        default=3.0,
        help="The maximum bias score (0-10) allowed for a response. "
             "Responses above this threshold are flagged and filtered "
             "from training data. Higher scores indicate more bias."
    )

    min_votes_for_training = fields.Integer(
        string='Minimum Votes for Training',
        default=2,
        help="The minimum number of 'Good Answer' votes required for a "
             "response to be eligible for inclusion in training data. "
             "This ensures that only responses that have been validated "
             "by users are used for fine-tuning."
    )

    # =========================================================================
    # 4. Evaluation Model Configuration
    # =========================================================================
    evaluation_model = fields.Selection(
        [
            ('gpt-4o-mini', 'GPT-4o Mini (Recommended)'),
            ('gpt-4o', 'GPT-4o'),
            ('claude-3.5-sonnet', 'Claude 3.5 Sonnet'),
            ('custom', 'Custom LLM'),
        ],
        string='Evaluation Model',
        default='gpt-4o-mini',
        help="The LLM model used as the judge for rationality and bias "
             "evaluations. GPT-4o Mini is recommended for its balance "
             "of quality and cost."
    )

    custom_evaluation_url = fields.Char(
        string='Custom Evaluation URL',
        help="The URL of the custom LLM endpoint to use for evaluations "
             "when 'Custom LLM' is selected as the evaluation model. "
             "The endpoint must be compatible with the OpenAI API format."
    )

    custom_evaluation_api_key = fields.Char(
        string='Custom Evaluation API Key',
        password=True,
        copy=False,
        help="The API key for the custom LLM endpoint. This is stored "
             "encrypted and never exposed in the UI."
    )

    # =========================================================================
    # 5. Fairness Metrics
    # =========================================================================
    protected_attributes = fields.Selection(
        [
            ('gender', 'Gender'),
            ('race', 'Race/Ethnicity'),
            ('age', 'Age'),
            ('disability', 'Disability'),
            ('religion', 'Religion'),
            ('all', 'All Protected Attributes'),
        ],
        string='Protected Attributes',
        default='all',
        help="The protected attributes to check for bias. These are used "
             "by the bias detection system to identify potential "
             "discrimination patterns."
    )

    fairness_metrics_enabled = fields.Boolean(
        string='Enable Fairness Metrics',
        default=True,
        help="When enabled, the system calculates and tracks fairness "
             "metrics including demographic parity, equal opportunity, "
             "and disparate impact."
    )

    # =========================================================================
    # 6. A/B Testing Configuration
    # =========================================================================
    ab_testing_enabled = fields.Boolean(
        string='Enable A/B Testing for Models',
        default=True,
        help="When enabled, new models are deployed in shadow mode for "
             "A/B testing before being promoted to production. This "
             "allows the system to evaluate improvements before full "
             "deployment."
    )

    ab_traffic_split = fields.Float(
        string='A/B Traffic Split (%)',
        default=10.0,
        help="The percentage of traffic to route to the test model during "
             "A/B testing. The remaining traffic goes to the production "
             "model. A value of 10% means 10% of requests use the test "
             "model and 90% use the production model."
    )

    promotion_threshold = fields.Float(
        string='Promotion Threshold (%)',
        default=5.0,
        help="The minimum performance improvement required to promote a "
             "test model to production. The improvement is measured as "
             "the percentage increase in rationality scores or other "
             "quality metrics."
    )

    evaluation_window_days = fields.Integer(
        string='Evaluation Window (days)',
        default=7,
        help="The number of days to evaluate a test model before deciding "
             "whether to promote it to production. A longer window provides "
             "more statistical confidence but delays deployment."
    )

    # =========================================================================
    # 7. Singleton Constraints
    # =========================================================================
    @api.constrains('id')
    def _check_singleton(self):
        """
        Ensure that only one global configuration record exists.
        """
        if len(self) > 1:
            raise ValidationError(_("There can only be one global fairness configuration."))

    # =========================================================================
    # 8. Helper Methods
    # =========================================================================
    @api.model
    def get_config(self):
        """
        Get the singleton configuration record. If it doesn't exist, create it.

        Returns:
            FairnessGlobalConfig record
        """
        config = self.search([], limit=1)
        if not config:
            config = self.create({
                'rationality_evaluation_enabled': True,
                'bias_detection_enabled': True,
                'auto_flag_for_review': True,
                'auto_filter_training': True,
                'auto_audit_enabled': True,
                'rationality_threshold': 7.0,
                'bias_threshold': 3.0,
                'min_votes_for_training': 2,
                'evaluation_model': 'gpt-4o-mini',
                'protected_attributes': 'all',
                'fairness_metrics_enabled': True,
                'ab_testing_enabled': True,
                'ab_traffic_split': 10.0,
                'promotion_threshold': 5.0,
                'evaluation_window_days': 7,
            })
            _logger.info("Created default fairness configuration")
        return config

    @api.model
    def get_effective_config(self, field_id=None):
        """
        Get the effective configuration for a field, merging global
        and field-specific settings.

        Args:
            field_id (int, optional): The ID of the professional field.

        Returns:
            dict: Effective configuration.
        """
        global_config = self.get_config()

        # Start with global values
        effective = {
            'rationality_evaluation_enabled': global_config.rationality_evaluation_enabled,
            'bias_detection_enabled': global_config.bias_detection_enabled,
            'auto_flag_for_review': global_config.auto_flag_for_review,
            'auto_filter_training': global_config.auto_filter_training,
            'rationality_threshold': global_config.rationality_threshold,
            'bias_threshold': global_config.bias_threshold,
            'min_votes_for_training': global_config.min_votes_for_training,
            'protected_attributes': global_config.protected_attributes,
        }

        # Override with field-specific configuration if available
        if field_id:
            field_config = self.env['nettrades.fairness.field.config'].search([
                ('field_id', '=', field_id),
            ], limit=1)

            if field_config and field_config.override_global:
                if field_config.rationality_threshold:
                    effective['rationality_threshold'] = field_config.rationality_threshold
                if field_config.bias_threshold:
                    effective['bias_threshold'] = field_config.bias_threshold
                if field_config.min_votes_for_training is not None:
                    effective['min_votes_for_training'] = field_config.min_votes_for_training
                if field_config.protected_attributes:
                    effective['protected_attributes'] = field_config.protected_attributes

        return effective


class FairnessFieldConfig(models.Model):
    """
    Field-Specific Fairness Configuration.

    Each professional field can override the global fairness settings.
    This allows different thresholds and sensitivity levels for different
    domains (e.g., medical fields may have stricter thresholds than
    technical fields).
    """
    _name = 'nettrades.fairness.field.config'
    _description = 'Fairness Field-Specific Configuration'
    _rec_name = 'field_id'

    # =========================================================================
    # 1. Field Reference
    # =========================================================================
    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        required=True,
        ondelete='cascade',
        help="The professional field this configuration applies to."
    )

    # =========================================================================
    # 2. Override Controls
    # =========================================================================
    override_global = fields.Boolean(
        string='Override Global Settings',
        default=False,
        help="If checked, use field-specific values instead of global defaults."
    )

    # =========================================================================
    # 3. Threshold Overrides
    # =========================================================================
    rationality_threshold = fields.Float(
        string='Minimum Rationality Score',
        help="Override the global rationality threshold for this field."
    )

    bias_threshold = fields.Float(
        string='Maximum Bias Score',
        help="Override the global bias threshold for this field."
    )

    min_votes_for_training = fields.Integer(
        string='Minimum Votes for Training',
        help="Override the global minimum votes for this field."
    )

    # =========================================================================
    # 4. Sensitivity Level
    # =========================================================================
    sensitivity_level = fields.Selection(
        [
            ('low', 'Low (General)'),
            ('medium', 'Medium (Professional)'),
            ('high', 'High (Medical/Legal)'),
        ],
        string='Sensitivity Level',
        default='medium',
        help="The sensitivity level of the field. Higher sensitivity fields "
             "have stricter bias detection and require more scrutiny."
    )

    # =========================================================================
    # 5. Protected Attributes
    # =========================================================================
    protected_attributes = fields.Selection(
        [
            ('gender', 'Gender'),
            ('race', 'Race/Ethnicity'),
            ('age', 'Age'),
            ('disability', 'Disability'),
            ('religion', 'Religion'),
            ('all', 'All Protected Attributes'),
        ],
        string='Protected Attributes',
        help="The protected attributes to check for bias in this field."
    )

    # =========================================================================
    # 6. Active Status
    # =========================================================================
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If inactive, the field uses global settings regardless of "
             "override settings."
    )

    # =========================================================================
    # 7. Helper Methods
    # =========================================================================
    @api.model
    def get_field_config(self, field_id):
        """
        Get the field-specific configuration for a field.

        Args:
            field_id (int): The ID of the professional field.

        Returns:
            FairnessFieldConfig record or None.
        """
        return self.search([
            ('field_id', '=', field_id),
            ('active', '=', True),
        ], limit=1)

    @api.constrains('rationality_threshold', 'bias_threshold')
    def _check_thresholds(self):
        """
        Ensure thresholds are within valid ranges.
        """
        for record in self:
            if record.rationality_threshold and not (0 <= record.rationality_threshold <= 10):
                raise ValidationError(_("Rationality threshold must be between 0 and 10."))
            if record.bias_threshold and not (0 <= record.bias_threshold <= 10):
                raise ValidationError(_("Bias threshold must be between 0 and 10."))