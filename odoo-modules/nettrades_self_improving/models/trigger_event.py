# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class TriggerEvent(models.Model):
    _name = 'trigger.event'
    _description = 'Trigger Event'
    _order = 'fired_at DESC'
    _rec_name = 'name'

    name = fields.Char(compute='_compute_name', store=True)

    trigger_id = fields.Many2one(
        'trigger.config', required=True, ondelete='cascade', index=True,
    )

    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('processed', 'Processed'),
            ('failed', 'Failed'),
        ],
        default='pending',
    )

    error_message = fields.Text()
    evaluation_data = fields.Json()

    cycle_id = fields.Many2one('loop.cycle', readonly=True)

    fired_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    processed_at = fields.Datetime(readonly=True)

    @api.depends('trigger_id', 'fired_at')
    def _compute_name(self):
        for rec in self:
            tname = rec.trigger_id.name if rec.trigger_id else 'Unknown'
            when = rec.fired_at.strftime('%Y-%m-%d %H:%M') if rec.fired_at else 'unscheduled'
            rec.name = f"{tname} / {when}"

    def action_process(self):
        """Manually run a self-improvement cycle for this event."""
        self.ensure_one()
        if self.status != 'pending':
            return
        self.status = 'processing'
        try:
            cycle = self.env['loop.orchestrator'].execute_cycle(self.id)
            self.write({
                'status': 'processed',
                'processed_at': fields.Datetime.now(),
                'cycle_id': cycle.id,
            })
        except Exception as e:
            self.write({
                'status': 'failed',
                'error_message': str(e),
            })
            _logger.error("Trigger event %s failed: %s", self.id, e)