# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving Config - Configuration Model
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving/models/self_improving_config.py
#
# PURPOSE:
#   This model stores the administration configuration for the self-improving
#   system. All settings are configurable via the Odoo admin interface.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class SelfImprovingConfig(models.Model):
    """
    Self-Improving AI Configuration - Administration settings.
    """
    _name = 'self.improving.config'
    _description = 'Self-Improving AI Configuration'
    _rec_name = 'display_name'

    # Display Name
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('loop_enabled')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "Self-Improving AI - " + ("Enabled" if rec.loop_enabled else "Disabled")

    # Loop control
    loop_enabled = fields.Boolean(default=True)
    loop_interval = fields.Integer(default=24, help="Hours between cron-driven cycles.")
    auto_deploy = fields.Boolean(default=True)
    auto_rollback = fields.Boolean(default=True)

    # Data quality (defaults only — pipelines define their own filters)
    min_quality_score = fields.Float(default=5.0)
    min_votes_for_training = fields.Integer(default=2)
    max_samples_per_dataset = fields.Integer(default=10000)
    include_expert_answers = fields.Boolean(default=True)

    # A/B testing
    ab_testing_enabled = fields.Boolean(default=True)
    ab_traffic_split = fields.Float(default=10.0)
    promotion_threshold = fields.Float(default=5.0)
    evaluation_window_days = fields.Integer(default=7)

    # Relationships
    trigger_ids = fields.One2many(
        'trigger.config', 'config_id',
        string='Active Triggers',
        domain=[('active', '=', True)],
    )

    last_cycle_id = fields.Many2one('loop.cycle', readonly=True)

    # Computed status (non-stored; recomputed on read)
    last_cycle_status = fields.Char(compute='_compute_status')
    total_episodes = fields.Integer(compute='_compute_status')
    qualified_episodes = fields.Integer(compute='_compute_status')
    total_cycles = fields.Integer(compute='_compute_status')

    def _compute_status(self):
        for rec in self:
            rec.last_cycle_status = rec.last_cycle_id.status if rec.last_cycle_id else 'No cycles yet'
            rec.total_episodes = self.env['data.episode'].search_count([])
            rec.qualified_episodes = self.env['data.episode'].search_count([('is_qualified', '=', True)])
            rec.total_cycles = self.env['loop.cycle'].search_count(
                [('status', 'in', ('completed', 'failed'))]
            )

    # Actions
    def action_run_cycle(self):
        self.ensure_one()
        cycle = self.env['loop.orchestrator'].execute_cycle()
        self.last_cycle_id = cycle.id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loop.cycle',
            'res_id': cycle.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # Singleton enforcement
    @api.model_create_multi
    def create(self, vals_list):
        if self.search_count([]) + len(vals_list) > 1:
            raise ValidationError(_("Only one Self-Improving Configuration is allowed."))
        return super().create(vals_list)

    # Default Values
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

    # Helper Methods
    @api.model
    def get_config(self):
        config = self.search([], limit=1)
        if not config:
            config = self.create({})
        return config