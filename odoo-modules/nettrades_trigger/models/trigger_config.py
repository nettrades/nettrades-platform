# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Trigger – Trigger Configuration Model
# =============================================================================
# FILE: odoo-modules/nettrades_trigger/models/trigger_config.py
#
# PURPOSE:
#   This model stores the configuration for trigger conditions. Triggers are
#   conditions that, when met, initiate a self-improvement cycle.
#
#   The administrator can configure these triggers via the Odoo admin
#   interface, providing full control over when the system should
#   automatically improve itself.
#
# TRIGGER TYPES:
#   1. quality_drop: Quality score falls below threshold
#   2. success_rate: Task success rate declines
#   3. data_volume: Enough data accumulated
#   4. edge_case: New edge case detected
#   5. manual: Administrator manually triggers
#
# EVALUATION:
#   Triggers are evaluated periodically by a cron job. When a trigger
#   fires, it creates a trigger.event record and initiates a
#   self-improvement cycle.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class TriggerConfig(models.Model):
    """
    Trigger Configuration – defines conditions for self-improvement.

    Each trigger specifies a condition that, when met, initiates a
    self-improvement cycle.
    """
    _name = 'trigger.config'
    _description = 'Self-Improving Trigger Configuration'
    _rec_name = 'name'

    # =========================================================================
    # 1. BASIC FIELDS
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        help="A human-readable name for this trigger (e.g., 'Quality Drop')."
    )

    description = fields.Text(
        string='Description',
        help="Detailed description of what this trigger monitors."
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help="Whether this trigger is currently active."
    )

    # =========================================================================
    # 2. TRIGGER TYPE
    # =========================================================================

    trigger_type = fields.Selection(
        [
            ('quality_drop', 'Quality Score Drop'),
            ('success_rate', 'Task Success Rate Decline'),
            ('data_volume', 'Data Volume Threshold'),
            ('edge_case', 'New Edge Case Detected'),
            ('manual', 'Manual Trigger'),
        ],
        string='Trigger Type',
        required=True,
        default='quality_drop',
        help="""The type of condition that triggers self-improvement:
            - Quality Drop: When average quality score falls below threshold
            - Success Rate: When task success rate declines
            - Data Volume: When enough data has been collected
            - Edge Case: When a new edge case is detected
            - Manual: Only triggered by administrator action
        """
    )

    # =========================================================================
    # 3. THRESHOLD VALUES
    # =========================================================================

    threshold_value = fields.Float(
        string='Threshold Value',
        default=5.0,
        help="""The threshold value for the trigger condition.
            For quality_drop: minimum quality score (0-10)
            For data_volume: minimum number of episodes
            For success_rate: minimum success rate (0-100%)
        """
    )

    comparison_operator = fields.Selection(
        [
            ('below', 'Below Threshold'),
            ('above', 'Above Threshold'),
        ],
        string='Comparison Operator',
        default='below',
        help="Whether to trigger when the metric is below or above the threshold."
    )

    # =========================================================================
    # 4. TIME WINDOW
    # =========================================================================

    time_window_hours = fields.Integer(
        string='Time Window (hours)',
        default=24,
        help="The time window over which to evaluate the trigger condition."
    )

    min_samples = fields.Integer(
        string='Minimum Samples',
        default=10,
        help="Minimum number of samples required for evaluation."
    )

    # =========================================================================
    # 5. FIELD FILTER
    # =========================================================================

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The professional field this trigger applies to. If empty, "
             "applies to all fields."
    )

    # =========================================================================
    # 6. EVALUATION LOGIC
    # =========================================================================

    def evaluate(self):
        """
        Evaluate this trigger condition.

        Returns:
            bool: True if the trigger condition is met, False otherwise.
        """
        self.ensure_one()

        if not self.active:
            return False

        # Different evaluation logic based on trigger type
        if self.trigger_type == 'quality_drop':
            return self._evaluate_quality_drop()
        elif self.trigger_type == 'success_rate':
            return self._evaluate_success_rate()
        elif self.trigger_type == 'data_volume':
            return self._evaluate_data_volume()
        elif self.trigger_type == 'edge_case':
            return self._evaluate_edge_case()
        elif self.trigger_type == 'manual':
            return self._evaluate_manual()

        return False

    def _evaluate_quality_drop(self):
        """
        Evaluate whether the quality score has dropped below the threshold.
        """
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)

        # Get recent episodes
        domain = [('create_date', '>=', cutoff)]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        episodes = self.env['data.episode'].search(domain)

        if len(episodes) < self.min_samples:
            return False

        # Calculate average quality score
        avg_quality = sum(e.quality_score for e in episodes) / len(episodes)

        if self.comparison_operator == 'below':
            return avg_quality < self.threshold_value
        else:
            return avg_quality > self.threshold_value

    def _evaluate_success_rate(self):
        """
        Evaluate whether the task success rate has declined.
        """
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)

        # Get recent episodes with success information
        # This assumes episodes have a success field or can be inferred
        domain = [
            ('create_date', '>=', cutoff),
        ]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        episodes = self.env['data.episode'].search(domain)

        if len(episodes) < self.min_samples:
            return False

        # Calculate success rate (quality_score >= 7 is considered success)
        successful = len([e for e in episodes if e.quality_score >= 7.0])
        success_rate = (successful / len(episodes)) * 100

        if self.comparison_operator == 'below':
            return success_rate < self.threshold_value
        else:
            return success_rate > self.threshold_value

    def _evaluate_data_volume(self):
        """
        Evaluate whether enough data has been accumulated.
        """
        cutoff = fields.Datetime.now() - timedelta(hours=self.time_window_hours)

        domain = [
            ('create_date', '>=', cutoff),
            ('is_qualified', '=', True),
        ]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        count = self.env['data.episode'].search_count(domain)

        if self.comparison_operator == 'above':
            return count >= self.threshold_value
        else:
            return count <= self.threshold_value

    def _evaluate_edge_case(self):
        """
        Evaluate whether a new edge case has been detected.

        This uses vector similarity (pgvector) to detect novel patterns
        that are significantly different from existing episodes.
        """
        # Placeholder implementation
        # In production, this would use pgvector to find episodes with
        # low similarity to existing patterns
        return False

    def _evaluate_manual(self):
        """
        Evaluate manual triggers (always returns False; triggered by user action).
        """
        return False

    # =========================================================================
    # 7. TRIGGER FIRING
    # =========================================================================

    def fire(self):
        """
        Fire this trigger, creating a trigger.event and initiating a
        self-improvement cycle.

        Returns:
            trigger.event: The created trigger event record.
        """
        self.ensure_one()

        # Create trigger event
        event = self.env['trigger.event'].create({
            'trigger_id': self.id,
            'fired_at': fields.Datetime.now(),
            'status': 'pending',
        })

        _logger.info("Trigger %s fired, event %s created", self.name, event.id)

        # Initiate self-improvement cycle via the loop orchestrator
        orchestrator = self.env['loop.orchestrator']
        orchestrator.execute_cycle(event.id)

        return event

    # =========================================================================
    # 8. CRON JOBS
    # =========================================================================

    @api.model
    def _cron_check_triggers(self):
        """
        Scheduled cron job to check all active triggers.

        This method evaluates all active triggers and fires any that meet
        their conditions.

        The cron runs every hour by default.
        """
        _logger.info("Checking self-improving triggers...")

        triggers = self.search([('active', '=', True)])
        fired = []

        for trigger in triggers:
            if trigger.evaluate():
                event = trigger.fire()
                fired.append({
                    'trigger': trigger.name,
                    'event': event.id,
                })
                _logger.info("Trigger %s fired, event %s", trigger.name, event.id)

        if fired:
            _logger.info("Fired %s triggers", len(fired))
        else:
            _logger.info("No triggers fired")

        return fired