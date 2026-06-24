# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Trigger – Trigger Event Model
# =============================================================================
# FILE: odoo-modules/nettrades_trigger/models/trigger_event.py
#
# PURPOSE:
#   This model tracks when a trigger fires. Each trigger event represents
#   a single occurrence of a trigger condition being met.
#
#   Trigger events are used to:
#     - Initiate self-improvement cycles
#     - Track trigger frequency
#     - Provide audit trail for compliance
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class TriggerEvent(models.Model):
    """
    Trigger Event – tracks when a trigger fires.

    Each event is linked to a trigger configuration and may be linked
    to a self-improvement cycle.
    """
    _name = 'trigger.event'
    _description = 'Trigger Event'
    _order = 'fired_at DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    trigger_id = fields.Many2one(
        'trigger.config',
        string='Trigger',
        required=True,
        ondelete='cascade',
        help="The trigger that fired."
    )

    # =========================================================================
    # 2. Event Status
    # =========================================================================
    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('processed', 'Processed'),
            ('failed', 'Failed'),
        ],
        string='Status',
        default='pending',
        help="Current status of the trigger event."
    )

    error_message = fields.Text(
        string='Error Message',
        help="Error message if the event failed."
    )

    # =========================================================================
    # 3. Evaluation Data
    # =========================================================================
    evaluation_data = fields.Json(
        string='Evaluation Data',
        help="JSON blob containing the evaluation data that triggered this event."
    )

    # =========================================================================
    # 4. Links
    # =========================================================================
    cycle_id = fields.Many2one(
        'loop.cycle',
        string='Cycle',
        help="The self-improvement cycle initiated by this event."
    )

    # =========================================================================
    # 5. Timestamps
    # =========================================================================
    fired_at = fields.Datetime(
        string='Fired At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the trigger fired."
    )

    processed_at = fields.Datetime(
        string='Processed At',
        help="Timestamp when the event was processed."
    )

    # =========================================================================
    # 6. Helper Methods
    # =========================================================================
    def action_process(self):
        """
        Process this trigger event by initiating a self-improvement cycle.
        """
        self.ensure_one()

        if self.status != 'pending':
            _logger.warning("Trigger event %s already processed", self.id)
            return

        self.status = 'processing'

        try:
            # Initiate self-improvement cycle via orchestrator
            orchestrator = self.env['loop.orchestrator']
            cycle = orchestrator.execute_cycle(self.id)

            self.write({
                'status': 'processed',
                'processed_at': fields.Datetime.now(),
                'cycle_id': cycle.id,
            })

            _logger.info("Trigger event %s processed, cycle %s created", self.id, cycle.id)

        except Exception as e:
            self.write({
                'status': 'failed',
                'error_message': str(e),
            })
            _logger.error("Trigger event %s failed: %s", self.id, e)