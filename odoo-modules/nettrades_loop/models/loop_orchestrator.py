# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop – Self-Improving Loop Orchestrator
# =============================================================================
# FILE: odoo-modules/nettrades_loop/models/loop_orchestrator.py
#
# PURPOSE:
#   This module orchestrates the complete self-improving loop.
#   It connects the Monitor, Analyze, Plan, and Execute phases.
#
#   The orchestrator executes a complete self-improvement cycle when a
#   trigger fires. It:
#     1. Collects data from the data collection module
#     2. Creates a training dataset
#     3. Submits a training job to GPUStack
#     4. Deploys the trained model
#     5. Tracks the cycle and its results
#
# USAGE:
#   orchestrator = self.env['loop.orchestrator']
#   orchestrator.execute_cycle(trigger_event_id)
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging
from datetime import datetime, timedelta
import json

_logger = logging.getLogger(__name__)


class LoopOrchestrator(models.TransientModel):
    """
    Self-Improving Loop Orchestrator.

    This service orchestrates the complete self-improving loop.
    """
    _name = 'loop.orchestrator'
    _description = 'Self-Improving Loop Orchestrator'
    _transient = True

    # =========================================================================
    # 1. MAIN ORCHESTRATION METHOD
    # =========================================================================

    @api.model
    def execute_cycle(self, trigger_event_id=None):
        """
        Execute one complete self-improvement cycle.

        This is the main entry point for the self-improving loop.

        Args:
            trigger_event_id (int, optional): The ID of the trigger event
                that initiated this cycle.

        Returns:
            loop.cycle: The created cycle record.
        """
        _logger.info("Starting self-improvement cycle...")

        # Get trigger event if provided
        trigger_event = None
        if trigger_event_id:
            trigger_event = self.env['trigger.event'].browse(trigger_event_id)

        # Create a cycle record
        cycle = self.env['loop.cycle'].create({
            'name': f"Cycle {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'trigger_event_id': trigger_event.id if trigger_event else None,
            'started_at': fields.Datetime.now(),
            'status': 'running',
        })

        try:
            # Step 1: Check triggers (Analyze phase)
            _logger.info("Step 1: Checking triggers...")
            triggers = self.env['trigger.config'].search([('active', '=', True)])
            fired_triggers = []

            for trigger in triggers:
                if trigger.evaluate():
                    fired_triggers.append(trigger)

            if not fired_triggers:
                _logger.info("No triggers fired. Skipping cycle.")
                cycle.status = 'completed'
                cycle.completed_at = fields.Datetime.now()
                return cycle

            # Step 2: Collect data (Monitor phase)
            _logger.info("Step 2: Collecting data...")
            self.env['data.collector']._cron_collect_unprocessed()

            # Step 3: For each trigger, execute the pipeline
            results = []
            for trigger in fired_triggers:
                try:
                    result = self._execute_pipeline_for_trigger(trigger, cycle)
                    results.append(result)
                except Exception as e:
                    _logger.error("Pipeline failed for trigger %s: %s", trigger.name, e)
                    results.append({
                        'trigger': trigger.name,
                        'status': 'failed',
                        'error': str(e),
                    })

            # Step 4: Complete the cycle
            cycle.write({
                'status': 'completed',
                'completed_at': fields.Datetime.now(),
                'results': json.dumps(results),
                'episode_count': len(self.env['data.episode'].search([])),
            })

            _logger.info("Self-improvement cycle %s completed", cycle.id)

            # Update trigger event
            if trigger_event:
                trigger_event.write({
                    'status': 'processed',
                    'processed_at': fields.Datetime.now(),
                    'cycle_id': cycle.id,
                })

            return cycle

        except Exception as e:
            _logger.error("Self-improvement cycle failed: %s", e)
            cycle.write({
                'status': 'failed',
                'error_message': str(e),
                'completed_at': fields.Datetime.now(),
            })
            raise

    # =========================================================================
    # 2. PIPELINE EXECUTION
    # =========================================================================

    def _execute_pipeline_for_trigger(self, trigger, cycle):
        """
        Execute the training pipeline for a specific trigger.

        This method:
        1. Gets or creates a training pipeline for the field
        2. Creates a training dataset
        3. Submits a training job to GPUStack
        4. Evaluates and deploys the trained model

        Args:
            trigger (trigger.config): The trigger that fired.
            cycle (loop.cycle): The current cycle record.

        Returns:
            dict: Results of the pipeline execution.
        """
        _logger.info("Executing pipeline for trigger: %s", trigger.name)

        result = {
            'trigger': trigger.name,
            'status': 'started',
        }

        # Get or create pipeline for the field
        field = trigger.field_id
        pipeline = self.env['training.pipeline'].search([
            ('field_id', '=', field.id if field else None),
        ], limit=1)

        if not pipeline and field:
            pipeline = self.env['training.pipeline'].create({
                'name': f"Pipeline for {field.name}",
                'field_id': field.id,
            })
            _logger.info("Created new pipeline for field %s", field.name)

        if not pipeline:
            _logger.warning("No pipeline available for trigger %s", trigger.name)
            result['status'] = 'skipped'
            result['reason'] = 'No pipeline available'
            return result

        # Create dataset
        try:
            dataset = pipeline.create_dataset()
            result['dataset_id'] = dataset.id if dataset else None

            if not dataset or dataset.record_count == 0:
                _logger.info("No data for training in field %s", field.name if field else 'global')
                result['status'] = 'skipped'
                result['reason'] = 'No data available'
                return result

            result['dataset_records'] = dataset.record_count
            _logger.info("Created dataset with %s records", dataset.record_count)

        except Exception as e:
            _logger.error("Dataset creation failed: %s", e)
            result['status'] = 'failed'
            result['error'] = str(e)
            return result

        # Submit training job
        try:
            job = pipeline.submit_training_job(dataset.id)
            result['job_id'] = job.id if job else None

            if not job or job.status != 'running':
                result['status'] = 'failed'
                result['error'] = 'Training job submission failed'
                return result

            _logger.info("Submitted training job %s", job.id)

        except Exception as e:
            _logger.error("Training job submission failed: %s", e)
            result['status'] = 'failed'
            result['error'] = str(e)
            return result

        # Wait for job completion (async)
        # In a real implementation, this would use the job queue
        # For now, we check the job status periodically

        # Evaluate and deploy
        try:
            if pipeline.ab_testing_enabled:
                # Deploy as shadow for A/B testing
                deployment = pipeline.deploy_as_shadow(job.id)
                result['deployment_id'] = deployment.id if deployment else None
                _logger.info("Deployed model as shadow for A/B testing")
            else:
                # Deploy directly
                deployment = pipeline.deploy_model(job.id)
                result['deployment_id'] = deployment.id if deployment else None
                _logger.info("Deployed model directly")

            # Update cycle
            cycle.write({
                'training_job_id': job.id,
                'dataset_id': dataset.id,
                'deployment_id': deployment.id if deployment else None,
            })

            result['status'] = 'completed'

        except Exception as e:
            _logger.error("Model deployment failed: %s", e)
            result['status'] = 'failed'
            result['error'] = str(e)

        return result

    # =========================================================================
    # 3. CRON JOBS
    # =========================================================================

    @api.model
    def _cron_run_loop(self):
        """
        Scheduled cron job to run the self-improving loop.

        This method is called periodically to check triggers and execute
        the self-improving loop if conditions are met.

        The cron runs every hour by default.
        """
        _logger.info("Running self-improving loop cron job...")

        try:
            cycle = self.execute_cycle()
            _logger.info("Self-improving loop completed: %s", cycle.id)
            return cycle
        except Exception as e:
            _logger.error("Self-improving loop cron job failed: %s", e)
            return None