# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop - Self-Improving Loop Cycle Model
# =============================================================================
# FILE: odoo-modules/nettrades_loop/models/loop_cycle.py
#
# PURPOSE:
#   This model tracks a single self-improvement cycle.
#   It stores the status, progress, and results of the cycle.
#
#   Each cycle goes through the following stages:
#   1. pending - Triggered but not yet started
#   2. running - Currently executing
#   3. training - Fine-tuning in progress
#   4. deploying - Model being deployed
#   5. completed - Cycle successfully completed
#   6. failed - Cycle failed
#
#   The cycle record provides traceability for the self-improving system,
#   allowing administrators to see what changes were made, when, and why.
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class LoopCycle(models.Model):
    """
    Self-Improving Loop Cycle - tracks a single improvement cycle.
    """
    _name = 'loop.cycle'
    _description = 'Self-Improving Loop Cycle'
    _order = 'create_date DESC'
    _rec_name = 'name'

    # =========================================================================
    # 1. BASIC FIELDS
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        default=lambda self: f"Cycle {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}",
        help="A human-readable name for this cycle."
    )

    description = fields.Text(
        string='Description',
        help="Detailed description of the cycle's purpose."
    )

    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('training', 'Training'),
            ('deploying', 'Deploying'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        string='Status',
        default='pending',
        help="Current status of the self-improvement cycle."
    )

    # =========================================================================
    # 2. TRIGGER INFORMATION
    # =========================================================================

    trigger_event_id = fields.Many2one(
        'trigger.event',
        string='Trigger Event',
        help="The trigger event that initiated this cycle."
    )

    trigger_name = fields.Char(
        string='Trigger Name',
        related='trigger_event_id.trigger_id.name',
        store=True,
        help="Name of the trigger that initiated this cycle."
    )

    # =========================================================================
    # 3. TRAINING INFORMATION
    # =========================================================================

    dataset_id = fields.Many2one(
        'llm.training.dataset',
        string='Training Dataset',
        help="The dataset used for fine-tuning in this cycle."
    )

    training_job_id = fields.Many2one(
        'llm.training.job',
        string='Training Job',
        help="The fine-tuning job associated with this cycle."
    )

    dataset_record_count = fields.Integer(
        string='Dataset Records',
        related='dataset_id.record_count',
        store=True,
        help="Number of records in the training dataset."
    )

    # =========================================================================
    # 4. DEPLOYMENT INFORMATION
    # =========================================================================

    model_id = fields.Char(
        string='Model ID',
        help="The ID of the fine-tuned model (from GPUStack)."
    )

    deployment_id = fields.Many2one(
        'llm.provider',
        string='Deployed Model',
        help="The LLM provider record for the deployed model."
    )

    deployed_agents = fields.Text(
        string='Deployed Agents',
        help="List of agents that were updated with the new model."
    )

    # =========================================================================
    # 5. METRICS AND RESULTS
    # =========================================================================

    metrics = fields.Json(
        string='Metrics',
        help="JSON blob containing performance metrics for this cycle."
    )

    results = fields.Json(
        string='Results',
        help="JSON blob containing the results of the cycle."
    )

    episode_count = fields.Integer(
        string='Episodes Collected',
        help="Number of episodes collected during this cycle."
    )

    improvement = fields.Float(
        string='Improvement (%)',
        help="Percentage improvement in performance metrics."
    )

    error_message = fields.Text(
        string='Error Message',
        help="Error message if the cycle failed."
    )

    # =========================================================================
    # 6. TIMESTAMPS
    # =========================================================================

    started_at = fields.Datetime(
        string='Started At',
        help="Timestamp when the cycle started."
    )

    completed_at = fields.Datetime(
        string='Completed At',
        help="Timestamp when the cycle completed."
    )

    # =========================================================================
    # 7. COMPUTED FIELDS
    # =========================================================================

    duration_seconds = fields.Float(
        string='Duration (seconds)',
        compute='_compute_duration',
        store=True,
        help="Duration of the cycle in seconds."
    )

    @api.depends('started_at', 'completed_at')
    def _compute_duration(self):
        for record in self:
            if record.started_at and record.completed_at:
                delta = record.completed_at - record.started_at
                record.duration_seconds = delta.total_seconds()
            else:
                record.duration_seconds = 0.0

    # =========================================================================
    # 8. ACTIONS
    # =========================================================================

    def action_view_details(self):
        """
        Open a detailed view of this cycle.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'loop.cycle',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_rerun(self):
        """
        Re-run this cycle (clone and execute).
        """
        self.ensure_one()

        # Create a new cycle with the same configuration
        new_cycle = self.env['loop.cycle'].create({
            'name': f"Re-run of {self.name}",
            'description': self.description,
            'trigger_event_id': self.trigger_event_id.id,
            'status': 'pending',
            'started_at': fields.Datetime.now(),
        })

        # Execute the cycle
        orchestrator = self.env['loop.orchestrator']
        result = orchestrator.execute_cycle(new_cycle.id)

        return result