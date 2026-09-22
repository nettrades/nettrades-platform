# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving - Loop Cycle Model
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving/models/loop_cycle.py
#
# UPDATES (2026-09-21):
#   - Removed `dataset_record_count` related field. It referenced
#     `llm.training.dataset.record_count`, which does not exist. The count
#     is carried on `episode_count` (local field, set by the orchestrator
#     when the dataset is built).
#   - Replaced `deployment_id` (Many2one llm.provider) with `result_model_id`
#     (Many2one llm.model). The fine-tuned artifact is an llm.model, not a
#     provider. The provider is already available via `training_job_id.provider_id`.
# =============================================================================

from odoo import fields, models, api

CYCLE_STATES = [
    ('pending',             'Pending'),
    ('evaluating_triggers', 'Evaluating Triggers'),
    ('collecting_data',     'Collecting Data'),
    ('building_dataset',    'Building Dataset'),
    ('training',            'Training'),
    ('evaluating_model',    'Evaluating Model'),
    ('deploying',           'Deploying'),
    ('completed',           'Completed'),
    ('failed',              'Failed'),
    ('skipped',             'Skipped'),
]


class LoopCycle(models.Model):
    """
    Self-Improving Loop Cycle - tracks a single improvement cycle.
    """
    _name = 'loop.cycle'
    _description = 'Self-Improving Loop Cycle'
    _order = 'create_date DESC'
    _rec_name = 'name'

    name = fields.Char(
        required=True,
        default=lambda self: f"Cycle {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    description = fields.Text()
    status = fields.Selection(CYCLE_STATES, default='pending', index=True)

    company_id = fields.Many2one(
        'res.company', required=True, index=True,
        default=lambda self: self.env.company,
    )

    trigger_event_id = fields.Many2one('trigger.event', string='Trigger Event')
    trigger_name = fields.Char(related='trigger_event_id.trigger_id.name', store=True)

    origin = fields.Selection(
        [('manual', 'Manual'), ('trigger', 'Trigger'), ('cron', 'Cron')],
        default='manual',
    )

    # Links to the artifacts produced by this cycle
    dataset_id = fields.Many2one('llm.training.dataset', string='Training Dataset')
    training_job_id = fields.Many2one('llm.training.job', string='Training Job')
    result_model_id = fields.Many2one(
        'llm.model',
        string='Fine-Tuned Model',
        readonly=True,
        help="The llm.model produced by the training job, if training completed.",
    )
    model_id = fields.Char(
        string='Model Name',
        readonly=True,
        help="Name of the resulting model as reported by the provider.",
    )
    deployed_agents = fields.Text()

    # JSON blobs
    state_data = fields.Json(
        help="State-machine scratch pad. Persists between resume runs.",
    )
    metrics = fields.Json()
    results = fields.Json()

    # Results
    episode_count = fields.Integer(
        string='Dataset Records',
        help="Number of episodes included in the training dataset.",
    )
    improvement = fields.Float(string='Improvement (%)')
    error_message = fields.Text()

    # Timestamps
    started_at = fields.Datetime()
    completed_at = fields.Datetime()
    duration_seconds = fields.Float(compute='_compute_duration', store=True)

    @api.depends('started_at', 'completed_at')
    def _compute_duration(self):
        for rec in self:
            if rec.started_at and rec.completed_at:
                rec.duration_seconds = (rec.completed_at - rec.started_at).total_seconds()
            else:
                rec.duration_seconds = 0.0

    TERMINAL_STATES = ('completed', 'failed', 'skipped')

    def is_terminal(self):
        return self.status in self.TERMINAL_STATES

    def action_view_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loop.cycle',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_rerun(self):
        """Start a fresh cycle based on this cycle's configuration."""
        self.ensure_one()
        return self.env['loop.orchestrator'].execute_cycle()