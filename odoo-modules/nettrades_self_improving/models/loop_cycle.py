# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

# States the cycle can be in. Order matters only for readability;
# the state machine in loop_orchestrator drives transitions.
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

    # What fired the cycle: 'manual' or 'trigger'
    origin = fields.Selection(
        [('manual', 'Manual'), ('trigger', 'Trigger'), ('cron', 'Cron')],
        default='manual',
    )

    dataset_id = fields.Many2one('llm.training.dataset')
    training_job_id = fields.Many2one('llm.training.job')
    deployment_id = fields.Many2one('llm.provider')
    model_id = fields.Char()
    deployed_agents = fields.Text()

    dataset_record_count = fields.Integer(related='dataset_id.record_count', store=True)

    # JSON blobs
    state_data = fields.Json(help="State-machine scratch pad. Persists between resume runs.")
    metrics = fields.Json()
    results = fields.Json()

    # Results
    episode_count = fields.Integer()
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

    # Terminal states — orchestrator stops driving the cycle here.
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