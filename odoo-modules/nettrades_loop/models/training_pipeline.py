# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop – Training Pipeline Model
# =============================================================================
# FILE: odoo-modules/nettrades_loop/models/training_pipeline.py
#
# PURPOSE:
#   This model configures and manages the training pipeline for the
#   self-improving system. It defines how training data is prepared,
#   how fine-tuning jobs are submitted, and how models are deployed.
#
#   Each pipeline is associated with a professional field and can be
#   customised with dataset filters, training hyperparameters, and
#   A/B testing settings.
#
# =============================================================================

from odoo import fields, models, api, _
import logging
import json
from datetime import datetime

_logger = logging.getLogger(__name__)


class TrainingPipeline(models.Model):
    """
    Training Pipeline – configuration for fine-tuning.

    Each pipeline defines how training data is prepared and how models
    are trained and deployed.
    """
    _name = 'training.pipeline'
    _description = 'Training Pipeline'
    _rec_name = 'name'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    name = fields.Char(
        string='Name',
        required=True,
        help="A human-readable name for this pipeline."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The professional field this pipeline is for."
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help="Whether this pipeline is active."
    )

    # =========================================================================
    # 2. Dataset Configuration
    # =========================================================================
    dataset_config = fields.Json(
        string='Dataset Configuration',
        default={
            'min_quality_score': 5.0,
            'min_votes': 2,
            'max_samples': 10000,
            'include_expert_answers': True,
            'include_good_answers': True,
            'exclude_low_rationality': True,
            'exclude_high_bias': True,
        },
        help="Configuration for dataset preparation. Controls filtering and sampling."
    )

    # =========================================================================
    # 3. Training Configuration
    # =========================================================================
    training_config = fields.Json(
        string='Training Configuration',
        default={
            'provider': 'unsloth',
            'base_model': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
            'hyperparameters': {
                'lora_r': 16,
                'epochs': 3,
                'lr': 2e-4,
                'batch_size': 4,
                'gradient_accumulation_steps': 4,
                'warmup_ratio': 0.03,
            },
        },
        help="Configuration for fine-tuning. Controls training hyperparameters."
    )

    # =========================================================================
    # 4. A/B Testing Configuration
    # =========================================================================
    ab_testing_enabled = fields.Boolean(
        string='Enable A/B Testing',
        default=False,
        help="Whether A/B testing is enabled for this pipeline."
    )

    ab_traffic_split = fields.Float(
        string='A/B Traffic Split (%)',
        default=10.0,
        help="Percentage of traffic to route to test model (0-100)."
    )

    ab_promotion_threshold = fields.Float(
        string='Promotion Threshold (%)',
        default=5.0,
        help="Minimum improvement required to promote test model."
    )

    # =========================================================================
    # 5. GPU Configuration
    # =========================================================================
    gpu_requirements = fields.Json(
        string='GPU Requirements',
        default={
            'min_vram_gb': 16,
            'min_gpus': 1,
            'max_gpus': 8,
        },
        help="GPU requirements for training jobs."
    )

    # =========================================================================
    # 6. Helper Methods
    # =========================================================================
    def create_dataset(self):
        """
        Create a training dataset from collected episodes.

        Returns:
            llm.training.dataset: The created dataset, or None if no data.
        """
        self.ensure_one()

        # Query episodes
        domain = [
            ('is_qualified', '=', True),
            ('processed', '=', False),
        ]

        if self.field_id:
            domain.append(('field_id', '=', self.field_id.id))

        # Apply dataset filters
        min_score = self.dataset_config.get('min_quality_score', 5.0)
        min_votes = self.dataset_config.get('min_votes', 2)

        if min_score:
            domain.append(('quality_score', '>=', min_score))

        if min_votes:
            domain.append(('vote_count', '>=', min_votes))

        # If exclude low rationality, filter by fairness
        if self.dataset_config.get('exclude_low_rationality', True):
            # This relies on the fairness audit table
            # We'll filter manually
            pass

        episodes = self.env['data.episode'].search(domain)

        if not episodes:
            _logger.info("No eligible episodes found for training")
            return None

        # Limit samples
        max_samples = self.dataset_config.get('max_samples', 10000)
        if len(episodes) > max_samples:
            episodes = episodes[:max_samples]

        # Prepare JSONL data
        jsonl_data = []
        for episode in episodes:
            jsonl_data.append({
                'prompt': episode.input_text,
                'completion': episode.output_text,
            })

        # Create llm.training.dataset
        dataset = self.env['llm.training.dataset'].create({
            'name': f"Pipeline {self.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'description': f"Auto-generated from pipeline {self.name}",
            'record_count': len(jsonl_data),
            'data': json.dumps(jsonl_data),
            'status': 'draft',
            'field_id': self.field_id.id if self.field_id else None,
        })

        # Mark episodes as processed
        episodes.write({
            'processed': True,
            'processed_date': fields.Datetime.now(),
        })

        _logger.info("Created dataset with %s records from pipeline %s", len(episodes), self.name)
        return dataset

    def submit_training_job(self, dataset_id):
        """
        Submit a training job to GPUStack.

        Args:
            dataset_id (int): The dataset ID.

        Returns:
            llm.training.job: The created training job.
        """
        self.ensure_one()

        dataset = self.env['llm.training.dataset'].browse(dataset_id)

        if not dataset:
            _logger.warning("Dataset %s not found", dataset_id)
            return None

        # Create training job
        job = self.env['llm.training.job'].create({
            'dataset_id': dataset.id,
            'field_id': self.field_id.id if self.field_id else None,
            'provider': self.training_config.get('provider', 'unsloth'),
            'base_model': self.training_config.get('base_model', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B'),
            'hyperparameters': self.training_config.get('hyperparameters', {}),
            'status': 'pending',
            'started_at': fields.Datetime.now(),
        })

        # Here we would submit to GPUStack
        # For now, we simulate submission
        job.status = 'running'

        _logger.info("Submitted training job %s", job.id)
        return job

    def deploy_model(self, job_id):
        """
        Deploy a trained model to GPUStack.

        Args:
            job_id (int): The training job ID.

        Returns:
            llm.provider: The created provider record.
        """
        self.ensure_one()

        job = self.env['llm.training.job'].browse(job_id)

        if not job:
            _logger.warning("Job %s not found", job_id)
            return None

        # Here we would deploy to GPUStack
        # For now, we simulate deployment

        provider = self.env['llm.provider'].create({
            'name': f"Fine-tuned {self.name} - {datetime.now().strftime('%Y-%m-%d')}",
            'provider_type': 'openai_compatible',
            'api_base': 'http://gpustack:80/v1-openai',
            'model_name': f"finetuned_{job.id}",
            'is_enabled': True,
        })

        _logger.info("Deployed model as provider %s", provider.id)
        return provider