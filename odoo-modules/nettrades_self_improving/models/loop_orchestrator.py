# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving - Loop Orchestrator
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving/models/loop_orchestrator.py
#
# UPDATES (2026-09-21):
#   - _state_training: uses llm.training.job.action_submit() and
#     action_check_status(), and looks at job.state (not job.status).
#   - _state_evaluating_model: reads job.training_metrics.
#   - _state_deploying: no-op. The fine-tuned model is created by the
#     provider as job.result_model_id. We just record it on the cycle.
# =============================================================================

from odoo import fields, models, api, _
import logging
import json

_logger = logging.getLogger(__name__)


class LoopOrchestrator(models.TransientModel):
    """
    Resumable state machine driving a self-improvement cycle.
    """
    _name = 'loop.orchestrator'
    _description = 'Self-Improving Loop Orchestrator'

    MAX_STEPS_PER_RUN = 50

    # -------------------------------------------------------------------------
    # Entry point
    # -------------------------------------------------------------------------
    @api.model
    def execute_cycle(self, trigger_event_id=None):
        trigger_event = None
        origin = 'manual'
        if trigger_event_id:
            trigger_event = self.env['trigger.event'].browse(trigger_event_id)
            origin = 'trigger'

        cycle = self.env['loop.cycle'].create({
            'name': f"Cycle {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'trigger_event_id': trigger_event.id if trigger_event else None,
            'origin': origin,
            'started_at': fields.Datetime.now(),
            'status': 'pending',
        })

        if trigger_event:
            trigger_event.write({'status': 'processing'})

        return self._drive_cycle(cycle)

    # -------------------------------------------------------------------------
    # State-machine driver
    # -------------------------------------------------------------------------
    @api.model
    def _drive_cycle(self, cycle):
        for _ in range(self.MAX_STEPS_PER_RUN):
            if cycle.is_terminal():
                return cycle

            handler = getattr(self, f'_state_{cycle.status}', None)
            if handler is None:
                self._fail(cycle, f"Unknown state: '{cycle.status}'")
                return cycle

            try:
                handler(cycle)
            except Exception as e:
                _logger.exception("Handler for state '%s' raised: %s", cycle.status, e)
                self._fail(cycle, str(e))
                return cycle

        _logger.info("Cycle %s paused in state '%s' (waiting for external work)",
                     cycle.id, cycle.status)
        return cycle

    def _fail(self, cycle, message):
        _logger.error("Cycle %s failed: %s", cycle.id, message)
        cycle.write({
            'status': 'failed',
            'error_message': message,
            'completed_at': fields.Datetime.now(),
        })

    def _finish(self, cycle, status='completed'):
        cycle.write({
            'status': status,
            'completed_at': fields.Datetime.now(),
        })

    # -------------------------------------------------------------------------
    # State handlers
    # -------------------------------------------------------------------------
    def _state_pending(self, cycle):
        cycle.status = 'evaluating_triggers'

    def _state_evaluating_triggers(self, cycle):
        if cycle.trigger_event_id:
            cycle.status = 'collecting_data'
            return

        triggers = self.env['trigger.config'].search([('active', '=', True)])
        fired = [t for t in triggers if t.evaluate()]
        if not fired:
            _logger.info("No triggers fired. Cycle %s skipped.", cycle.id)
            self._finish(cycle, 'skipped')
            return

        cycle.state_data = {'fired_trigger_ids': [t.id for t in fired]}
        cycle.status = 'collecting_data'

    def _state_collecting_data(self, cycle):
        try:
            if 'data.collector' in self.env:
                self.env['data.collector']._cron_collect_unprocessed()
        except Exception as e:
            _logger.warning("Data collection raised, continuing: %s", e)
        cycle.status = 'building_dataset'

    def _state_building_dataset(self, cycle):
        pipeline = self._pick_pipeline(cycle)
        if not pipeline:
            _logger.info("No pipeline available for cycle %s", cycle.id)
            self._finish(cycle, 'skipped')
            return

        dataset, count = pipeline.create_dataset()
        if not dataset or count == 0:
            _logger.info("No data available for cycle %s", cycle.id)
            self._finish(cycle, 'skipped')
            return

        cycle.write({
            'dataset_id': dataset.id,
            'episode_count': count,
            'status': 'training',
        })

    def _state_training(self, cycle):
        """
        Submit the training job once, then poll its state on each pass.

        The job's state transitions are driven by the provider:
            draft -> validating -> preparing -> queued -> training
                  -> completed | failed | cancelled
        """
        # ------------------------------------------------------------------
        # First entry: submit a job.
        # ------------------------------------------------------------------
        if not cycle.training_job_id:
            pipeline = self._pick_pipeline(cycle)
            if not pipeline:
                self._fail(cycle, "Pipeline missing when entering training state")
                return

            job = pipeline.submit_training_job(cycle.dataset_id.id)
            if not job:
                self._fail(
                    cycle,
                    "Training job submission returned None. "
                    "Check that the training pipeline has a provider "
                    "and a base model configured.",
                )
                return

            cycle.training_job_id = job.id
            # Hold in 'training'; the resume cron will poll again.
            return

        # ------------------------------------------------------------------
        # Subsequent passes: poll status.
        # ------------------------------------------------------------------
        job = cycle.training_job_id

        # Ask the provider for the current state.
        try:
            job.action_check_status()
        except Exception as e:
            _logger.warning("Status check for job %s failed: %s", job.id, e)
            # Don't fail the cycle — the provider may just be unreachable
            # this poll. Try again on the next pass.
            return

        # Refresh cached state after the call.
        job.invalidate_recordset(['state', 'result_model_id', 'trained_model_name'])

        if job.state == 'completed':
            cycle.result_model_id = job.result_model_id.id if job.result_model_id else False
            cycle.model_id = job.trained_model_name or False
            cycle.status = 'evaluating_model'
        elif job.state in ('failed', 'cancelled'):
            self._fail(cycle, f"Training job {job.id} ended in state '{job.state}'")
        # else: still running, hold.

    def _state_evaluating_model(self, cycle):
        """Read the training metrics reported by the provider."""
        job = cycle.training_job_id
        metrics = {
            'evaluated_at': fields.Datetime.now().isoformat(),
        }
        if job:
            if job.training_metrics:
                metrics['training_metrics'] = job.training_metrics
            if job.result_model_id:
                metrics['result_model_id'] = job.result_model_id.id
                metrics['result_model_name'] = job.result_model_id.name
            if job.final_cost:
                metrics['final_cost'] = job.final_cost

        cycle.metrics = metrics
        cycle.status = 'deploying'

    def _state_deploying(self, cycle):
        """
        Deployment is a no-op in the llm_training architecture.

        The fine-tuned model exists as `cycle.result_model_id` (an
        llm.model). To "deploy" it, an administrator edits the provider
        configuration to point at the new model — that is a manual step.
        If the platform later gains an automated deployment mechanism,
        wire it in here.
        """
        self._finish(cycle, 'completed')

        if cycle.trigger_event_id:
            cycle.trigger_event_id.write({
                'status': 'processed',
                'processed_at': fields.Datetime.now(),
                'cycle_id': cycle.id,
            })

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _pick_pipeline(self, cycle):
        if cycle.trigger_event_id and cycle.trigger_event_id.trigger_id.field_id:
            field = cycle.trigger_event_id.trigger_id.field_id
            pipeline = self.env['training.pipeline'].search([
                ('field_id', '=', field.id),
                ('active', '=', True),
            ], limit=1)
            if pipeline:
                return pipeline

        return self.env['training.pipeline'].search([('active', '=', True)], limit=1)

    # -------------------------------------------------------------------------
    # Cron: resume stalled cycles
    # -------------------------------------------------------------------------
    @api.model
    def _cron_resume_pending_cycles(self):
        pending = self.env['loop.cycle'].search([
            ('status', 'not in', list(self.env['loop.cycle'].TERMINAL_STATES)),
        ])
        if not pending:
            return
        _logger.info("Resuming %s pending cycle(s)", len(pending))
        for cycle in pending:
            try:
                self._drive_cycle(cycle)
            except Exception as e:
                _logger.exception("Failed to resume cycle %s: %s", cycle.id, e)