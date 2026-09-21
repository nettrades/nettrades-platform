# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class TrainingPipeline(models.Model):
    _name = 'training.pipeline'
    _description = 'Training Pipeline'
    _rec_name = 'name'

    SUPPORTED_BACKENDS = ('unsloth', 'axolotl', 'dynamo')

    name = fields.Char(required=True)
    field_id = fields.Many2one('nettrades.field')
    active = fields.Boolean(default=True)

    # -------------------------------------------------------------------------
    # Declarative dataset filters
    # -------------------------------------------------------------------------
    # Each filter is {'field': str, 'op': str, 'value': any}.
    # The pipeline reads `data.episode._fields` to skip filters for
    # fields that don't exist (graceful degradation).
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
            'backend': 'unsloth',
            'base_model': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
            'hyperparameters': {
                'lora_r': 16,
                'epochs': 3,
                'lr': 2e-4,
                'batch_size': 4,
                'gradient_accumulation_steps': 4,
                'warmup_ratio': 0.03,
            },
            'backend_options': {},
        },
    )

    ab_testing_enabled = fields.Boolean(default=False)
    ab_traffic_split = fields.Float(default=10.0)
    ab_promotion_threshold = fields.Float(default=5.0)

    gpu_requirements = fields.Json(
        default={'min_vram_gb': 16, 'min_gpus': 1, 'max_gpus': 8},
    )

    # -------------------------------------------------------------------------
    # Dataset creation
    # -------------------------------------------------------------------------
    def create_dataset(self):
        self.ensure_one()
        Episode = self.env['data.episode']
        available = set(Episode._fields.keys())

        domain = [('is_qualified', '=', True), ('processed', '=', False)]
        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        # Apply declarative filters, skipping fields that don't exist.
        for flt in self.dataset_config.get('filters', []):
            fname = flt.get('field')
            op = flt.get('op')
            value = flt.get('value')
            if not fname or not op:
                continue
            if fname not in available:
                _logger.info("Filter field '%s' not present on data.episode — skipping", fname)
                continue
            domain.append((fname, op, value))

        episodes = Episode.search(domain)
        if not episodes:
            _logger.info("No episodes matched filter for pipeline '%s'", self.name)
            return None

        max_samples = self.dataset_config.get('max_samples', 10000)
        if len(episodes) > max_samples:
            episodes = episodes[:max_samples]

        jsonl = [
            {'prompt': ep.input_text, 'completion': ep.output_text}
            for ep in episodes
        ]

        dataset = self.env['llm.training.dataset'].create({
            'name': f"Pipeline {self.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'description': f"Auto-generated from pipeline {self.name}",
            'record_count': len(jsonl),
            'data': json.dumps(jsonl),
            'status': 'draft',
            'field_id': self.field_id.id if self.field_id else None,
        })

        episodes.write({
            'processed': True,
            'processed_date': fields.Datetime.now(),
        })

        _logger.info("Created dataset with %s records", len(episodes))
        return dataset

    # -------------------------------------------------------------------------
    # Backend dispatch
    # -------------------------------------------------------------------------
    def submit_training_job(self, dataset_id):
        self.ensure_one()
        backend = self.training_config.get('backend', 'unsloth')
        if backend not in self.SUPPORTED_BACKENDS:
            raise UserError(_(
                "Unsupported training backend: '%s'. Supported: %s"
            ) % (backend, ', '.join(self.SUPPORTED_BACKENDS)))
        handler = getattr(self, f'_submit_{backend}')
        return handler(dataset_id)

    def _make_job(self, dataset_id, provider_label):
        """Common job creation for all backends."""
        job = self.env['llm.training.job'].create({
            'dataset_id': dataset_id,
            'field_id': self.field_id.id if self.field_id else None,
            'provider': provider_label,
            'base_model': self.training_config.get('base_model'),
            'hyperparameters': self.training_config.get('hyperparameters', {}),
            'status': 'pending',
            'started_at': fields.Datetime.now(),
        })
        job.status = 'running'
        return job

    def _submit_unsloth(self, dataset_id):
        _logger.info("Submitting to Unsloth backend")
        return self._make_job(dataset_id, 'unsloth')

    def _submit_axolotl(self, dataset_id):
        _logger.info("Submitting to Axolotl backend")
        return self._make_job(dataset_id, 'axolotl')

    def _submit_dynamo(self, dataset_id):
        _logger.info("Submitting to Dynamo backend")
        return self._make_job(dataset_id, 'dynamo')

    # -------------------------------------------------------------------------
    # Deployment
    # -------------------------------------------------------------------------
    def deploy_model(self, job_id):
        self.ensure_one()
        job = self.env['llm.training.job'].browse(job_id)
        if not job.exists():
            return None
        provider = self.env['llm.provider'].create({
            'name': f"Fine-tuned {self.name} - {datetime.now().strftime('%Y-%m-%d')}",
            'provider_type': 'openai_compatible',
            'api_base': 'http://dynamo:8000/v1',
            'model_name': f"finetuned_{job.id}",
            'is_enabled': True,
        })
        return provider

    def deploy_as_shadow(self, job_id):
        self.ensure_one()
        _logger.info("Deploying job %s as shadow (%.1f%% traffic)",
                     job_id, self.ab_traffic_split)
        return self.deploy_model(job_id)