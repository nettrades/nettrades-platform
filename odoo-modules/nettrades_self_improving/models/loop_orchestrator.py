# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
import logging
import json

_logger = logging.getLogger(__name__)


class LoopOrchestrator(models.TransientModel):
    """
    Resumable state machine driving a self-improvement cycle.

    The cycle's `status` field is the state. `execute_cycle()` creates
    the cycle and drives it forward via `_drive_cycle()`, which loops
    dispatching to `_state_<status>()` handlers.

    Handlers that need external work (e.g. training) leave the cycle in
    the same state. The `_cron_resume_pending_cycles` cron picks up
    stalled cycles and drives them again.
    """
    _name = 'loop.orchestrator'
    _description = 'Self-Improving Loop Orchestrator'

    MAX_STEPS_PER_RUN = 50  # safety valve; prevents infinite loops

    # -------------------------------------------------------------------------
    # Entry points
    # -------------------------------------------------------------------------
    @api.model
    def execute_cycle(self, trigger_event_id=None):
        """Create a cycle and drive it forward."""
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
        """Advance the cycle through states until terminal or waiting."""
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
    # State handlers — one per state. Each advances or holds.
    # -------------------------------------------------------------------------
    def _state_pending(self, cycle):
        cycle.status = 'evaluating_triggers'

    def _state_evaluating_triggers(self, cycle):
        """Decide if there's work to do."""
        # If the cycle came from a trigger, we already know a trigger fired.
        # If manual, evaluate all active triggers now.
        if cycle.trigger_event_id:
            cycle.status = 'collecting_data'
            return

        triggers = self.env['trigger.config'].search([('active', '=', True)])
        fired = [t for t in triggers if t.evaluate()]
        if not fired:
            _logger.info("No triggers fired. Cycle %s skipped.", cycle.id)
            self._finish(cycle, 'skipped')
            return

        # Store which triggers fired so later states can use them.
        cycle.state_data = {'fired_trigger_ids': [t.id for t in fired]}
        cycle.status = 'collecting_data'

    def _state_collecting_data(self, cycle):
        """Ensure data collection has run."""
        try:
            if 'data.collector' in self.env:
                self.env['data.collector']._cron_collect_unprocessed()
        except Exception as e:
            # Data collection failing is not fatal — we may already have
            # enough qualified episodes from prior collections.
            _logger.warning("Data collection raised, continuing: %s", e)
        cycle.status = 'building_dataset'

    def _state_building_dataset(self, cycle):
        """Create a training dataset from the pipeline."""
        pipeline = self._pick_pipeline(cycle)
        if not pipeline:
            _logger.info("No pipeline available for cycle %s", cycle.id)
            self._finish(cycle, 'skipped')
            return

        dataset = pipeline.create_dataset()
        if not dataset or dataset.record_count == 0:
            _logger.info("No data available for cycle %s", cycle.id)
            self._finish(cycle, 'skipped')
            return

        cycle.write({
            'dataset_id': dataset.id,
            'episode_count': dataset.record_count,
            'status': 'training',
        })

    def _state_training(self, cycle):
        """Submit (once) and wait for the training job to complete."""
        if not cycle.training_job_id:
            pipeline = self._pick_pipeline(cycle)
            if not pipeline:
                self._fail(cycle, "Pipeline missing when entering training state")
                return
            job = pipeline.submit_training_job(cycle.dataset_id.id)
            if not job:
                self._fail(cycle, "Failed to submit training job")
                return
            cycle.training_job_id = job.id
            # Stay in 'training' — next cron run will check job status.
            return

        job = cycle.training_job_id
        if job.status == 'completed':
            cycle.status = 'evaluating_model'
        elif job.status == 'failed':
            self._fail(cycle, f"Training job {job.id} failed")
        # else: still running, hold.

    def _state_evaluating_model(self, cycle):
        """Measure the trained model's quality."""
        # Placeholder: in production this would run the model against a
        # held-out set and compute quality metrics. For now, record that
        # evaluation has happened and move on.
        cycle.metrics = {
            'evaluated_at': fields.Datetime.now().isoformat(),
            'note': 'Placeholder evaluation — wire up real metrics here',
        }
        cycle.status = 'deploying'

    def _state_deploying(self, cycle):
        """Deploy the model to production (directly or as shadow)."""
        pipeline = self._pick_pipeline(cycle)
        if not pipeline:
            self._fail(cycle, "Pipeline missing when entering deploying state")
            return

        if pipeline.ab_testing_enabled:
            deployment = pipeline.deploy_as_shadow(cycle.training_job_id.id)
        else:
            deployment = pipeline.deploy_model(cycle.training_job_id.id)

        if not deployment:
            self._fail(cycle, "Deployment returned no provider record")
            return

        cycle.write({
            'deployment_id': deployment.id,
            'status': 'completed',
        })
        self._finish(cycle, 'completed')

        # Update the trigger event if this cycle came from one.
        if cycle.trigger_event_id:
            cycle.trigger_event_id.write({
                'status': 'processed',
                'processed_at': fields.Datetime.now(),
                'cycle_id': cycle.id,
            })

    # Terminal-state handlers don't exist because _drive_cycle returns
    # early on terminal states.

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _pick_pipeline(self, cycle):
        """Choose a training.pipeline. Prefer the field of the trigger,
        fall back to the first active pipeline."""
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
        """Drive any cycle that isn't in a terminal state."""
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