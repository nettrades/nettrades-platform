# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving Config – Configuration Model
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving_config/models/self_improving_config.py
#
# PURPOSE:
#   This model stores the administration configuration for the self-improving
#   system. All settings are configurable via the Odoo admin interface.
#
#   The model is a singleton (only one record) that stores all settings.
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class SelfImprovingConfig(models.Model):
    """
    Self-Improving AI Configuration – Administration settings.

    This singleton model stores all configuration for the self-improving
    system, including loop settings, data quality, and A/B testing.
    """
    _name = 'self.improving.config'
    _description = 'Self-Improving AI Configuration'
    _rec_name = 'display_name'

    # =========================================================================
    # 1. Display Name
    # =========================================================================

    display_name = fields.Char(
        compute='_compute_display_name',
        store=True,
        help="Human-readable display name."
    )

    @api.depends('loop_enabled')
    def _compute_display_name(self):
        for record in self:
            status = "Enabled" if record.loop_enabled else "Disabled"
            record.display_name = f"Self-Improving AI – {status}"

    # =========================================================================
    # 2. Loop Control
    # =========================================================================

    loop_enabled = fields.Boolean(
        string='Enable Self-Improving Loop',
        default=True,
        help="Enable or disable the entire self-improving system."
    )

    loop_interval = fields.Integer(
        string='Loop Interval (hours)',
        default=24,
        help="How often the self-improving loop runs (in hours)."
    )

    auto_deploy = fields.Boolean(
        string='Auto-Deploy Improvements',
        default=True,
        help="Automatically deploy improvements to production."
    )

    auto_rollback = fields.Boolean(
        string='Auto-Rollback on Degradation',
        default=True,
        help="Automatically rollback if performance degrades."
    )

    # =========================================================================
    # 3. Data Quality
    # =========================================================================

    min_quality_score = fields.Float(
        string='Minimum Quality Score',
        default=5.0,
        help="Minimum quality score required for training data (0-10)."
    )

    min_votes_for_training = fields.Integer(
        string='Minimum Votes for Training',
        default=2,
        help="Minimum number of 'Good Answer' votes required for a sample."
    )

    max_samples_per_dataset = fields.Integer(
        string='Maximum Samples per Dataset',
        default=10000,
        help="Maximum number of samples in a training dataset."
    )

    include_expert_answers = fields.Boolean(
        string='Include Expert Answers',
        default=True,
        help="Include expert answers from 'Ask Someone' in training data."
    )

    # =========================================================================
    # 4. A/B Testing
    # =========================================================================

    ab_testing_enabled = fields.Boolean(
        string='Enable A/B Testing',
        default=True,
        help="Enable A/B testing for model deployment."
    )

    ab_traffic_split = fields.Float(
        string='A/B Traffic Split (%)',
        default=10.0,
        help="Percentage of traffic to route to the test model (0-100)."
    )

    promotion_threshold = fields.Float(
        string='Promotion Threshold (%)',
        default=5.0,
        help="Minimum improvement required to promote a test model."
    )

    evaluation_window_days = fields.Integer(
        string='Evaluation Window (days)',
        default=7,
        help="Number of days to evaluate a test model before promotion."
    )

    # =========================================================================
    # 5. Relationships
    # =========================================================================

    trigger_ids = fields.One2many(
        'trigger.config',
        string='Active Triggers',
        help="Triggers that are currently active.",
        domain=[('active', '=', True)],
    )

    last_cycle_id = fields.Many2one(
        'loop.cycle',
        string='Last Cycle',
        help="The most recent self-improvement cycle."
    )

    # =========================================================================
    # 6. Computed Status Fields
    # =========================================================================

    last_cycle_status = fields.Char(
        string='Last Cycle Status',
        compute='_compute_status_fields',
        store=True,
        help="Status of the last self-improvement cycle."
    )

    total_episodes = fields.Integer(
        string='Total Episodes',
        compute='_compute_status_fields',
        store=True,
        help="Total number of collected episodes."
    )

    qualified_episodes = fields.Integer(
        string='Qualified Episodes',
        compute='_compute_status_fields',
        store=True,
        help="Number of episodes qualified for training."
    )

    total_cycles = fields.Integer(
        string='Total Cycles',
        compute='_compute_status_fields',
        store=True,
        help="Total number of completed self-improvement cycles."
    )

    @api.depends('last_cycle_id')
    def _compute_status_fields(self):
        for record in self:
            if record.last_cycle_id:
                record.last_cycle_status = record.last_cycle_id.status
            else:
                record.last_cycle_status = 'No cycles yet'

            record.total_episodes = self.env['data.episode'].search_count([])
            record.qualified_episodes = self.env['data.episode'].search_count([
                ('is_qualified', '=', True),
            ])
            record.total_cycles = self.env['loop.cycle'].search_count([
                ('status', 'in', ['completed', 'failed']),
            ])

    # =========================================================================
    # 7. Actions
    # =========================================================================

    def action_run_cycle(self):
        """
        Manually run a self-improvement cycle.

        Returns:
            loop.cycle: The created cycle record.
        """
        orchestrator = self.env['loop.orchestrator']
        cycle = orchestrator.execute_cycle()

        self.last_cycle_id = cycle.id

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loop.cycle',
            'res_id': cycle.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # =========================================================================
    # 8. Singleton Constraints
    # =========================================================================

    @api.constrains('id')
    def _check_singleton(self):
        """
        Ensure that only one record exists.
        """
        if len(self) > 1:
            raise ValidationError(_("There can only be one self-improving configuration."))

    # =========================================================================
    # 9. Default Values
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        defaults.update({
            'loop_enabled': True,
            'loop_interval': 24,
            'auto_deploy': True,
            'auto_rollback': True,
            'min_quality_score': 5.0,
            'min_votes_for_training': 2,
            'max_samples_per_dataset': 10000,
            'include_expert_answers': True,
            'ab_testing_enabled': True,
            'ab_traffic_split': 10.0,
            'promotion_threshold': 5.0,
            'evaluation_window_days': 7,
        })
        return defaults

    # =========================================================================
    # 10. Helper Methods
    # =========================================================================

    @api.model
    def get_config(self):
        """
        Get the singleton configuration record. If it doesn't exist, create it.

        Returns:
            self.improving.config record
        """
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
            _logger.info("Created default self-improving configuration")
        return config