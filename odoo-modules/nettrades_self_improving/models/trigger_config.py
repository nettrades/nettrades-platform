# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class TriggerConfig(models.Model):
    _name = 'trigger.config'
    _description = 'Self-Improving Trigger Configuration'
    _rec_name = 'name'

    name = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)

    trigger_type = fields.Selection(
        [
            ('quality_drop', 'Quality Score Drop'),
            ('success_rate', 'Task Success Rate Decline'),
            ('data_volume', 'Data Volume Threshold'),
            ('edge_case', 'New Edge Case Detected'),
            ('manual', 'Manual Trigger'),
        ],
        required=True,
        default='quality_drop',
    )

    threshold_value = fields.Float(default=5.0)
    comparison_operator = fields.Selection(
        [('below', 'Below Threshold'), ('above', 'Above Threshold')],
        default='below',
    )
    time_window_hours = fields.Integer(default=24)
    min_samples = fields.Integer(default=10)

    field_id = fields.Many2one('nettrades.field', string='Professional Field')

    config_id = fields.Many2one(
        'self.improving.config',
        string='Configuration',
        ondelete='set null',
    )

    # -- Evaluation -----------------------------------------------------------

    def evaluate(self):
        self.ensure_one()
        if not self.active:
            return False
        dispatch = {
            'quality_drop': self._evaluate_quality_drop,
            'success_rate': self._evaluate_success_rate,
            'data_volume': self._evaluate_data_volume,
            'edge_case': self._evaluate_edge_case,
            'manual': lambda: False,
        }
        fn = dispatch.get(self.trigger_type)
        return fn() if fn else False

    def _evaluate_quality_drop(self):
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)
        domain = [('create_date', '>=', cutoff)]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))
        episodes = self.env['data.episode'].search(domain)
        if len(episodes) < self.min_samples:
            return False
        avg = sum(e.quality_score for e in episodes) / len(episodes)
        return avg < self.threshold_value if self.comparison_operator == 'below' \
            else avg > self.threshold_value

    def _evaluate_success_rate(self):
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)
        domain = [('create_date', '>=', cutoff)]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))
        episodes = self.env['data.episode'].search(domain)
        if len(episodes) < self.min_samples:
            return False
        successful = len([e for e in episodes if e.quality_score >= 7.0])
        rate = (successful / len(episodes)) * 100
        return rate < self.threshold_value if self.comparison_operator == 'below' \
            else rate > self.threshold_value

    def _evaluate_data_volume(self):
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)
        domain = [
            ('create_date', '>=', cutoff),
            ('is_qualified', '=', True),
        ]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))
        count = self.env['data.episode'].search_count(domain)
        return count >= self.threshold_value if self.comparison_operator == 'above' \
            else count <= self.threshold_value

    def _evaluate_edge_case(self):
        # Placeholder: production would use pgvector similarity.
        return False

    # -- Firing ---------------------------------------------------------------

    def fire(self):
        """Create a trigger.event; the orchestrator picks it up."""
        self.ensure_one()
        event = self.env['trigger.event'].create({
            'trigger_id': self.id,
            'fired_at': fields.Datetime.now(),
            'status': 'pending',
        })
        _logger.info("Trigger '%s' fired, event %s created", self.name, event.id)
        # Hand the event to the orchestrator. The orchestrator creates a
        # loop.cycle and drives it forward.
        self.env['loop.orchestrator'].execute_cycle(event.id)
        return event

    # -- Cron -----------------------------------------------------------------

    @api.model
    def _cron_check_triggers(self):
        _logger.info("Checking self-improving triggers...")
        fired = []
        for trigger in self.search([('active', '=', True)]):
            if trigger.evaluate():
                event = trigger.fire()
                fired.append({'trigger': trigger.name, 'event': event.id})
        _logger.info("Fired %s trigger(s)", len(fired))
        return fired