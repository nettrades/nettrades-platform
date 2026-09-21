# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving - Loop Orchestrator
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving/models/loop_orchestrator.py
#
# UPDATES (2026-09-22):
#   - Per-trigger pipeline execution. When multiple triggers fire, each is
#     processed sequentially: build dataset, submit job, poll, record
#     result, advance queue.
#   - Wait signalling uses RETURN VALUES, not instance attributes. Odoo
#     recordsets do not reliably support arbitrary instance attributes
#     across method calls, so `self._should_wait` was replaced with
#     `return 'wait'` from the handler.
#   - Per-trigger results accumulate in cycle.results.
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class LoopOrchestrator(models.TransientModel):
    """
    Resumable state machine driving a self-improvement cycle.

    A single cycle may process multiple fired triggers. Each trigger
    gets its own dataset, its own training job, and its own entry in
    cycle.results. The cycle completes when every fired trigger has
    been processed.
    """
    _name = 'loop.orchestrator'
    _description = 'Self-Improving Loop Orchestrator'

    MAX_STEPS_PER_RUN = 200

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
            'state_data': {},
            'results': [],
        })

        if trigger_event:
            trigger_event.write({'status': 'processing'})

        return self._drive_cycle(cycle)

    # -------------------------------------------------------------------------
    # State-machine driver
    # -------------------------------------------------------------------------
    @api.model
    def _drive_cycle(self, cycle):
        """
        Advance the cycle until a terminal state, a wait signal, or the
        step budget is exhausted.

        A handler returns the string 'wait' to signal "external work is
        in progress; stop driving now". Anything else (including None)
        means "continue immediately".
        """
        for step in range(self.MAX_STEPS_PER_RUN):
            if cycle.is_terminal():
                return cycle

            handler = getattr(self, f'_state_{cycle.status}', None)
            if handler is None:
                self._fail(cycle, f"Unknown state: '{cycle.status}'")
                return cycle

            try:
                result = handler(cycle)
            except Exception as e:
                _logger.exception(
                    "Handler for state '%s' raised: %s", cycle.status, e,
                )
                self._fail(cycle, str(e))
                return cycle

            if result == 'wait':
                _logger.info(
                    "Cycle %s paused in state '%s' (waiting for external work)",
                    cycle.id, cycle.status,
                )
                return cycle

        _logger.warning(
            "Cycle %s hit MAX_STEPS_PER_RUN=%s in state '%s' — "
            "state machine may be stuck",
            cycle.id, self.MAX_STEPS_PER_RUN, cycle.status,
        )
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
    # State: pending
    # -------------------------------------------------------------------------
    def _state_pending(self, cycle):
        cycle.status = 'evaluating_triggers'

    # -------------------------------------------------------------------------
    # State: evaluating_triggers
    # -------------------------------------------------------------------------
    def _state_evaluating_triggers(self, cycle):
        """
        Determine which triggers fired and seed the per-trigger queue.

        If this cycle came from a specific trigger.event, we use that one
        trigger only. Otherwise we evaluate every active trigger.
        """
        if cycle.trigger_event_id:
            trigger = cycle.trigger_event_id.trigger_id
            if not trigger:
                self._fail(cycle, "Trigger event has no trigger")
                return
            cycle.state_data = {
                'queue': [trigger.id],
                'results': [],
            }
            cycle.status = 'collecting_data'
            return

        triggers = self.env['trigger.config'].search([('active', '=', True)])
        fired = [t for t in triggers if t.evaluate()]
        if not fired:
            _logger.info("No triggers fired. Cycle %s skipped.", cycle.id)
            self._finish(cycle, 'skipped')
            return

        cycle.state_data = {
            'queue': [t.id for t in fired],
            'results': [],
        }
        _logger.info(
            "Cycle %s: %s trigger(s) fired — queue: %s",
            cycle.id, len(fired), [t.name for t in fired],
        )
        cycle.status = 'collecting_data'

    # -------------------------------------------------------------------------
    # State: collecting_data
    # -------------------------------------------------------------------------
    def _state_collecting_data(self, cycle):
        try:
            if 'data.collector' in self.env:
                self.env['data.collector']._cron_collect_unprocessed()
        except Exception as e:
            _logger.warning("Data collection raised, continuing: %s", e)
        cycle.status = 'building_dataset'

    # -------------------------------------------------------------------------
    # State: building_dataset (one trigger per entry)
    # -------------------------------------------------------------------------
    def _state_building_dataset(self, cycle):
        """
        Pop the next trigger from the queue, build its dataset, and move
        to training. If the queue is empty, advance to evaluating_model.

        Triggers that can't produce a dataset (no pipeline, no data) are
        recorded as 'skipped' in cycle.results, and the queue advances.
        """
        state_data = dict(cycle.state_data or {})
        queue = list(state_data.get('queue', []))

        if not queue:
            _logger.info("Cycle %s: queue empty, advancing to evaluation", cycle.id)
            cycle.status = 'evaluating_model'
            return

        trigger_id = queue.pop(0)
        trigger = self.env['trigger.config'].browse(trigger_id)
        if not trigger.exists():
            self._record_result(
                cycle, trigger_id, 'skipped',
                error='Trigger no longer exists',
            )
            state_data['queue'] = queue
            cycle.state_data = state_data
            return

        # Commit the popped queue to state before doing any work.
        state_data['queue'] = queue
        state_data['current_trigger_id'] = trigger_id
        cycle.state_data = state_data

        pipeline = self._pick_pipeline_for_trigger(trigger)
        if not pipeline:
            _logger.info(
                "Cycle %s: no pipeline for trigger '%s'",
                cycle.id, trigger.name,
            )
            self._record_result(
                cycle, trigger_id, 'skipped',
                error='No pipeline available for this field',
            )
            self._clear_current(cycle)
            return

        dataset, count = pipeline.create_dataset()
        if not dataset or count == 0:
            _logger.info(
                "Cycle %s: no data for trigger '%s'",
                cycle.id, trigger.name,
            )
            self._record_result(
                cycle, trigger_id, 'skipped',
                error='No qualifying data',
            )
            self._clear_current(cycle)
            return

        # Persist the pipeline/dataset for the training state.
        state_data = dict(cycle.state_data or {})
        state_data['current_pipeline_id'] = pipeline.id
        state_data['current_dataset_id'] = dataset.id
        cycle.state_data = state_data

        cycle.write({
            'dataset_id': dataset.id,
            'episode_count': (cycle.episode_count or 0) + count,
            'training_job_id': False,
            'status': 'training',
        })

    # -------------------------------------------------------------------------
    # State: training (one trigger's job per entry)
    # -------------------------------------------------------------------------
    def _state_training(self, cycle):
        """
        First entry: submit a job for the current trigger.
        Subsequent entries: poll until the job finishes.
        On completion or failure: record result, advance queue.
        """
        # ------------------------------------------------------------------
        # Submit phase
        # ------------------------------------------------------------------
        if not cycle.training_job_id:
            state_data = cycle.state_data or {}
            pipeline_id = state_data.get('current_pipeline_id')
            dataset_id = state_data.get('current_dataset_id')
            trigger_id = state_data.get('current_trigger_id')

            if not pipeline_id or not dataset_id or not trigger_id:
                self._record_result(
                    cycle, trigger_id, 'failed',
                    error='Missing pipeline/dataset reference in state_data',
                )
                self._clear_current(cycle)
                return

            pipeline = self.env['training.pipeline'].browse(pipeline_id)
            job = pipeline.submit_training_job(dataset_id)
            if not job:
                self._record_result(
                    cycle, trigger_id, 'failed',
                    error='Job submission returned None',
                )
                self._clear_current(cycle)
                return

            cycle.training_job_id = job.id
            # Hold — next pass will poll.
            return 'wait'

        # ------------------------------------------------------------------
        # Poll phase
        # ------------------------------------------------------------------
        job = cycle.training_job_id
        state_data = cycle.state_data or {}
        trigger_id = state_data.get('current_trigger_id')

        try:
            job.action_check_status()
        except Exception as e:
            _logger.warning("Status check for job %s failed: %s", job.id, e)
            return 'wait'

        job.invalidate_recordset(['state', 'result_model_id', 'trained_model_name'])

        if job.state == 'completed':
            entry_extra = {
                'job_id': job.id,
                'job_state': job.state,
                'result_model_id': job.result_model_id.id if job.result_model_id else None,
                'result_model_name': job.trained_model_name or None,
            }
            self._record_result(cycle, trigger_id, 'completed', **entry_extra)
            self._clear_current(cycle)
            return

        if job.state in ('failed', 'cancelled'):
            self._record_result(
                cycle, trigger_id, 'failed',
                error=f"Job ended in state '{job.state}'",
                job_id=job.id,
                job_state=job.state,
            )
            self._clear_current(cycle)
            return

        # Still running — wait for the next cron pass.
        return 'wait'

    # -------------------------------------------------------------------------
    # State: evaluating_model
    # -------------------------------------------------------------------------
    def _state_evaluating_model(self, cycle):
        """
        Aggregate per-trigger results and decide the cycle's final status.
        """
        results = list(cycle.results or [])
        completed = [r for r in results if r.get('status') == 'completed']
        failed = [r for r in results if r.get('status') == 'failed']
        skipped = [r for r in results if r.get('status') == 'skipped']

        if not completed and not failed and skipped:
            _logger.info("Cycle %s: all triggers skipped", cycle.id)
            self._finish(cycle, 'skipped')
            return

        if not completed and failed:
            _logger.info(
                "Cycle %s: all %s attempted job(s) failed",
                cycle.id, len(failed),
            )
            self._fail(
                cycle,
                f"All {len(failed)} job(s) failed. See results for details.",
            )
            return

        metrics = {
            'evaluated_at': fields.Datetime.now().isoformat(),
            'completed_count': len(completed),
            'failed_count': len(failed),
            'skipped_count': len(skipped),
            'total_triggers': len(results),
        }

        last_completed = completed[-1] if completed else None
        if last_completed and last_completed.get('job_id'):
            job = self.env['llm.training.job'].browse(last_completed['job_id'])
            if job.exists():
                if job.training_metrics:
                    metrics['training_metrics'] = job.training_metrics
                if job.final_cost:
                    metrics['final_cost'] = job.final_cost

        cycle.metrics = metrics
        cycle.status = 'deploying'

    # -------------------------------------------------------------------------
    # State: deploying
    # -------------------------------------------------------------------------
    def _state_deploying(self, cycle):
        """
        Deployment is a no-op in the llm_training architecture. The
        fine-tuned models exist as `llm.model` records. Promoting them
        to production is an administrator action.
        """
        results = cycle.results or []
        completed = [r for r in results if r.get('status') == 'completed']
        if completed:
            last = completed[-1]
            if last.get('result_model_id'):
                cycle.result_model_id = last['result_model_id']
            if last.get('result_model_name'):
                cycle.model_id = last['result_model_name']

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
    def _pick_pipeline_for_trigger(self, trigger):
        if trigger.field_id:
            pipeline = self.env['training.pipeline'].search([
                ('field_id', '=', trigger.field_id.id),
                ('active', '=', True),
            ], limit=1)
            if pipeline:
                return pipeline

        return self.env['training.pipeline'].search(
            [('active', '=', True)], limit=1,
        )

    def _record_result(self, cycle, trigger_id, status, error=None, **extra):
        """
        Append a per-trigger result to cycle.results.
        """
        trigger_name = ''
        if trigger_id:
            trigger = self.env['trigger.config'].browse(trigger_id)
            if trigger.exists():
                trigger_name = trigger.name

        entry = {
            'trigger_id': trigger_id,
            'trigger_name': trigger_name,
            'status': status,
        }
        if error:
            entry['error'] = error
        entry.update({k: v for k, v in extra.items() if v is not None})

        results = list(cycle.results or [])
        results.append(entry)
        cycle.results = results

    def _clear_current(self, cycle):
        """
        Clear the current-trigger pointers and return to building_dataset
        to process the next item in the queue.
        """
        state_data = dict(cycle.state_data or {})
        state_data.pop('current_trigger_id', None)
        state_data.pop('current_dataset_id', None)
        state_data.pop('current_pipeline_id', None)
        cycle.state_data = state_data

        cycle.training_job_id = False
        cycle.status = 'building_dataset'

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