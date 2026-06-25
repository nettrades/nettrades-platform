# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop – Self-Improving Loop Model
# =============================================================================
# FILE: odoo-modules/nettrades_loop/models/self_improving_loop.py
#
# PURPOSE:
#   This model tracks a single self-improvement cycle in the closed-loop
#   system. It stores the status, progress, and results of the cycle.
#
#   Each loop goes through the following stages:
#   1. Pending – Triggered but not yet started
#   2. Running – Currently executing
#   3. Training – Fine-tuning in progress
#   4. Deploying – Model being deployed
#   5. Completed – Cycle successfully completed
#   6. Failed – Cycle failed
#
# KEY FEATURES:
#   - Tracks the complete lifecycle of a self-improvement cycle
#   - Links to triggers, datasets, and training jobs
#   - Stores performance metrics for analysis
#   - Supports manual triggering and monitoring
#
# DEPENDENCIES:
#   - Odoo 19 CE
#   - nettrades_core module
#   - nettrades_trigger module
#   - llm_training module (Apexive)
#
# USAGE:
#   Loops are automatically created when triggers fire, or can be
#   created manually from the Odoo admin interface for testing.
#
# =============================================================================

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class SelfImprovingLoop(models.Model):
    """
    Self-Improving Loop – tracks a single improvement cycle.

    Each loop represents one complete pass through the closed-loop
    system: Monitor → Analyze → Plan → Execute.

    The loop is orchestrated by the LangGraph supervisor and tracked
    in Odoo for monitoring and audit purposes.
    """
    _name = 'self_improving.loop'
    _description = 'Self-Improving Loop'
    _order = 'create_date DESC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Name',
        required=True,
        help="A human-readable name for this loop."
    )

    description = fields.Text(
        string='Description',
        help="Detailed description of the loop's purpose and scope."
    )

    # -------------------------------------------------------------------------
    # 2. STATUS
    # -------------------------------------------------------------------------
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
        help="Current status of the self-improvement loop."
    )

    # -------------------------------------------------------------------------
    # 3. TRIGGER INFORMATION
    # -------------------------------------------------------------------------
    trigger_id = fields.Many2one(
        'self_improving.trigger',
        string='Trigger',
        help="The trigger that initiated this loop."
    )

    trigger_type = fields.Selection(
        related='trigger_id.trigger_type',
        string='Trigger Type',
        help="The type of trigger that initiated this loop."
    )

    # -------------------------------------------------------------------------
    # 4. TRAINING INFORMATION
    # -------------------------------------------------------------------------
    dataset_id = fields.Many2one(
        'simulation.dataset',
        string='Training Dataset',
        help="The dataset used for fine-tuning in this loop."
    )

    training_job_id = fields.Many2one(
        'llm.training.job',
        string='Training Job',
        help="The fine-tuning job associated with this loop.",
        domain="[('status', 'in', ['pending', 'running', 'completed'])]"
    )

    model_version = fields.Char(
        string='Model Version',
        help="The version of the fine-tuned model."
    )

    # -------------------------------------------------------------------------
    # 5. DEPLOYMENT INFORMATION
    # -------------------------------------------------------------------------
    deployment_target = fields.Selection(
        [
            ('langgraph', 'LangGraph Agents'),
            ('llm_assistant', 'LLM Assistants'),
            ('both', 'Both'),
        ],
        string='Deployment Target',
        default='langgraph',
        help="Where the improved model was deployed."
    )

    deployment_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('deploying', 'Deploying'),
            ('deployed', 'Deployed'),
            ('failed', 'Failed'),
            ('rolled_back', 'Rolled Back'),
        ],
        string='Deployment Status',
        default='pending',
        help="Status of the model deployment."
    )

    # -------------------------------------------------------------------------
    # 6. METRICS
    # -------------------------------------------------------------------------
    metrics = fields.Json(
        string='Metrics',
        help="JSON blob containing performance metrics for this loop."
    )

    # Performance metrics (extracted from JSON for display)
    quality_before = fields.Float(
        string='Quality Before',
        help="Quality score before the improvement."
    )

    quality_after = fields.Float(
        string='Quality After',
        help="Quality score after the improvement."
    )

    improvement_pct = fields.Float(
        string='Improvement (%)',
        compute='_compute_improvement',
        store=True,
        help="Percentage improvement in quality score."
    )

    @api.depends('quality_before', 'quality_after')
    def _compute_improvement(self):
        """Calculate the percentage improvement."""
        for record in self:
            if record.quality_before and record.quality_before > 0:
                record.improvement_pct = (
                    (record.quality_after - record.quality_before) /
                    record.quality_before * 100
                )
            else:
                record.improvement_pct = 0.0

    # -------------------------------------------------------------------------
    # 7. ERROR HANDLING
    # -------------------------------------------------------------------------
    error_message = fields.Text(
        string='Error Message',
        help="Error message if the loop failed."
    )

    # -------------------------------------------------------------------------
    # 8. TIMESTAMPS
    # -------------------------------------------------------------------------
    started_at = fields.Datetime(
        string='Started At',
        help="Timestamp when the loop started."
    )

    training_started_at = fields.Datetime(
        string='Training Started At',
        help="Timestamp when training started."
    )

    training_completed_at = fields.Datetime(
        string='Training Completed At',
        help="Timestamp when training completed."
    )

    deployment_started_at = fields.Datetime(
        string='Deployment Started At',
        help="Timestamp when deployment started."
    )

    completed_at = fields.Datetime(
        string='Completed At',
        help="Timestamp when the loop completed."
    )

    # -------------------------------------------------------------------------
    # 9. ACTIONS
    # -------------------------------------------------------------------------
    def action_trigger_loop(self):
        """
        Manually trigger a self-improvement cycle.

        This method initiates a new loop, which will be processed by
        the LangGraph orchestrator.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()

        if self.status not in ('pending', 'failed'):
            raise UserError(_("Only pending or failed loops can be triggered."))

        try:
            # Update status
            self.status = 'running'
            self.started_at = fields.Datetime.now()

            # Call the LangGraph orchestrator
            # In production, this would call the FastAPI `/invoke` endpoint
            # or a local LangGraph agent
            #
            # Example:
            # from ..controllers.orchestrator import Orchestrator
            # orchestrator = Orchestrator()
            # orchestrator.run_cycle(self.id)

            _logger.info(f"Self-improving loop {self.id} triggered manually.")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Loop Started'),
                    'message': _('The self-improving loop has been started.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self.status = 'failed'
            self.error_message = str(e)
            _logger.error(f"Self-improving loop {self.id} failed: {e}")
            raise UserError(_("Failed to start loop: {}").format(str(e)))

    def action_retry(self):
        """
        Retry a failed loop.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()

        if self.status != 'failed':
            raise UserError(_("Only failed loops can be retried."))

        # Reset the loop
        self.status = 'pending'
        self.error_message = False

        return self.action_trigger_loop()

    def action_view_metrics(self):
        """
        View the metrics for this loop.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()

        if not self.metrics:
            raise UserError(_("No metrics available for this loop."))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'self_improving.metrics',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_loop_id': self.id,
                'default_metrics': self.metrics,
            }
        }

    # -------------------------------------------------------------------------
    # 10. STATISTICS METHODS
    # -------------------------------------------------------------------------
    @api.model
    def get_statistics(self):
        """
        Get statistics for all self-improving loops.

        Returns:
            dict: Statistics including counts and average metrics.
        """
        total = self.search_count([])
        completed = self.search_count([('status', '=', 'completed')])
        failed = self.search_count([('status', '=', 'failed')])

        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'success_rate': (completed / total * 100) if total > 0 else 0,
        }

    # -------------------------------------------------------------------------
    # 11. CRON JOBS
    # -------------------------------------------------------------------------
    @api.model
    def _cron_cleanup_loops(self):
        """
        Scheduled cron job to clean up old loops.

        This method archives or deletes old loops to keep the database
        manageable.
        """
        _logger.info("Starting self-improving loop cleanup...")

        # Delete loops older than 90 days that are completed
        cutoff = fields.Datetime.now() - timedelta(days=90)
        old_loops = self.search([
            ('status', '=', 'completed'),
            ('completed_at', '<', cutoff)
        ])

        if old_loops:
            _logger.info(f"Archiving {len(old_loops)} old loops...")
            # In production, you might want to archive instead of delete
            old_loops.unlink()

        _logger.info("Self-improving loop cleanup completed.")