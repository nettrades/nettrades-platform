# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving - Training Pipeline
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving/models/training_pipeline.py
#
# UPDATES (2026-09-21):
#   - Rewrote create_dataset() against the real llm.training.dataset API.
#     Data lives in attachment_ids (JSONL file), not a `data` field. Count
#     is `example_count`, computed from the attached file.
#   - Rewrote submit_training_job() against the real llm.training.job API.
#     Jobs require provider_id, base_model_id, and dataset_ids. State is
#     called `state`, not `status`. Submission is via `job.action_submit()`,
#     which dispatches through llm.provider.start_training_job().
#   - Removed deploy_model() and deploy_as_shadow(). The fine-tuned model
#     is created by the provider as `result_model_id` on the job. There is
#     no separate deployment step in the llm_training architecture.
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import base64
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class TrainingPipeline(models.Model):
    _name = 'training.pipeline'
    _description = 'Training Pipeline'
    _rec_name = 'name'

    name = fields.Char(required=True)
    field_id = fields.Many2one('nettrades.field')
    active = fields.Boolean(default=True)

    # -------------------------------------------------------------------------
    # Required for job creation: which provider and which base model
    # -------------------------------------------------------------------------
    provider_id = fields.Many2one(
        'llm.provider',
        string='LLM Provider',
        help="Provider that will run the fine-tuning job.",
    )
    base_model_id = fields.Many2one(
        'llm.model',
        string='Base Model',
        domain="[('provider_id', '=', provider_id)]",
        help="Base model to fine-tune.",
    )

    # -------------------------------------------------------------------------
    # Declarative dataset filters
    # -------------------------------------------------------------------------
    dataset_config = fields.Json(
        default={
            'filters': [
                {'field': 'quality_score', 'op': '>=', 'value': 5.0},
                {'field': 'vote_count', 'op': '>=', 'value': 2},
                {'field': 'fairness_score', 'op': '>=', 'value': 4.0},
            ],
            'max_samples': 10000,
        },
    )

    training_config = fields.Json(
        default={
            'hyperparameters': {
                'n_epochs': 3,
                'batch_size': 4,
                'learning_rate_multiplier': 1.0,
            },
            'suffix': 'nettrades',
        },
        help="Passed to llm.training.job.hyperparameters verbatim.",
    )

    # -------------------------------------------------------------------------
    # A/B testing (reserved for future use — see loop_cycle.result_model_id)
    # -------------------------------------------------------------------------
    ab_testing_enabled = fields.Boolean(default=False)
    ab_traffic_split = fields.Float(default=10.0)
    ab_promotion_threshold = fields.Float(default=5.0)

    gpu_requirements = fields.Json(
        default={'min_vram_gb': 16, 'min_gpus': 1, 'max_gpus': 8},
    )

    # =========================================================================
    # Dataset creation
    # =========================================================================
    def create_dataset(self):
        """
        Build an llm.training.dataset from qualifying episodes.

        Returns:
            tuple: (dataset_record, record_count) or (None, 0) if no data.

        The JSONL format is one JSON object per line. The llm.training
        module validates that each non-empty line parses as JSON, and
        counts lines to compute example_count.
        """
        self.ensure_one()
        Episode = self.env['data.episode']
        available = set(Episode._fields.keys())

        domain = [('is_qualified', '=', True), ('processed', '=', False)]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        for flt in self.dataset_config.get('filters', []):
            fname = flt.get('field')
            op = flt.get('op')
            value = flt.get('value')
            if not fname or not op:
                continue
            if fname not in available:
                _logger.info(
                    "Filter field '%s' not present on data.episode — skipping", fname,
                )
                continue
            domain.append((fname, op, value))

        episodes = Episode.search(domain)
        if not episodes:
            _logger.info("No episodes matched filters for pipeline '%s'", self.name)
            return None, 0

        max_samples = self.dataset_config.get('max_samples', 10000)
        if len(episodes) > max_samples:
            episodes = episodes[:max_samples]

        # Build JSONL content — one JSON object per line.
        lines = []
        for ep in episodes:
            lines.append(json.dumps({
                'prompt': ep.input_text or '',
                'completion': ep.output_text or '',
                'episode_id': ep.id,
                'source': ep.source,
                'quality_score': ep.quality_score,
                'fairness_score': getattr(ep, 'fairness_score', 0.0),
            }, ensure_ascii=False))
        jsonl_bytes = '\n'.join(lines).encode('utf-8')

        # Create the JSONL attachment.
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        attachment = self.env['ir.attachment'].create({
            'name': f'pipeline_{self.id}_{timestamp}.jsonl',
            'datas': base64.b64encode(jsonl_bytes).decode('ascii'),
            'mimetype': 'application/x-jsonlines',
        })

        # Create the dataset, linking the attachment.
        dataset = self.env['llm.training.dataset'].create({
            'name': f"Pipeline {self.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'description': f"Auto-generated from pipeline {self.name}",
            'attachment_ids': [(6, 0, [attachment.id])],
        })

        episodes.write({
            'processed': True,
            'processed_date': fields.Datetime.now(),
        })

        count = len(episodes)
        _logger.info(
            "Created dataset %s with %s records for pipeline '%s'",
            dataset.id, count, self.name,
        )
        return dataset, count

    # =========================================================================
    # Training job submission
    # =========================================================================
    def submit_training_job(self, dataset_id):
        """
        Create an llm.training.job for the given dataset and submit it.

        Args:
            dataset_id (int): The llm.training.dataset to train on.

        Returns:
            llm.training.job record, or None if the pipeline is
            misconfigured (missing provider or base model).

        The job is created in 'draft' state, then `action_submit()` is
        called. That method dispatches to the provider's
        `start_training_job()` implementation, which talks to OpenAI,
        Anthropic, or whatever the provider is.
        """
        self.ensure_one()

        if not self.provider_id:
            _logger.warning(
                "Pipeline '%s' has no provider configured — cannot submit job",
                self.name,
            )
            return None

        if not self.base_model_id:
            _logger.warning(
                "Pipeline '%s' has no base model configured — cannot submit job",
                self.name,
            )
            return None

        dataset = self.env['llm.training.dataset'].browse(dataset_id)
        if not dataset.exists():
            _logger.warning("Dataset %s not found", dataset_id)
            return None

        # Create the job in draft state.
        job = self.env['llm.training.job'].create({
            'name': f"Pipeline {self.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'provider_id': self.provider_id.id,
            'base_model_id': self.base_model_id.id,
            'dataset_ids': [(6, 0, [dataset.id])],
            'hyperparameters': self.training_config.get('hyperparameters', {}),
            'state': 'draft',
        })

        # Submit to the provider. This transitions the job to 'validating'
        # (or raises UserError if the provider can't accept it).
        try:
            job.action_submit()
        except UserError:
            # Re-raise — a submit failure is a real problem, not something
            # to silently swallow.
            raise
        except Exception as e:
            _logger.exception("Job submission failed: %s", e)
            job.write({
                'state': 'failed',
                'training_logs': f"Submission error: {e}",
            })
            return job

        _logger.info("Submitted training job %s for pipeline '%s'", job.id, self.name)
        return job

    # =========================================================================
    # Helpers
    # =========================================================================
    def check_training_job_status(self, job):
        """
        Poll the provider for the job's current status.

        The llm.training.job.action_check_status() method dispatches to
        the provider's check_training_job_status() implementation. It
        updates job.state in place.
        """
        if not job or not job.exists():
            return
        try:
            job.action_check_status()
        except Exception as e:
            _logger.warning("Status check failed for job %s: %s", job.id, e)