# -*- coding: utf-8 -*-
# =============================================================================
# SECTION E - PROFESSIONAL FIELD EXTENSION (Good Answer)
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/nettrades_field.py
#
# PURPOSE:
#   This file extends the nettrades.field model with fields specific to
#   the Good Answer voting and fine-tuning systems.
#
# RELATIONSHIPS:
#   - Inherits all fields from nettrades.field
#   - Adds Good Answer specific fields
#
# KEY FEATURES:
#   - Fine-tuning configuration (finetune_provider, base_model, hyperparameters)
#   - Expert answer training settings
#   - Data-Juicer and DEITA configuration
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class NettradesField(models.Model):
    """
    Extended Professional Field Model - adds Good Answer specific fields.

    This extension adds all the fields needed for the Good Answer voting
    system and the fine-tuning pipeline.
    """
    _inherit = 'nettrades.field'

    # =========================================================================
    # 1. FINE-TUNING CONFIGURATION
    # =========================================================================

    finetune_provider = fields.Selection(
        [
            ('unsloth', 'Unsloth (single-GPU)'),
            ('axolotl', 'Axolotl (multi-GPU)'),
        ],
        string='Fine-tuning Backend',
        default='unsloth',
        help="""The backend to use for fine-tuning models in this field:
            - Unsloth: Single-GPU fine-tuning (2x faster, 70% less VRAM)
            - Axolotl: Multi-GPU fine-tuning with FSDP2 (for larger models)
        """
    )

    base_model = fields.Char(
        string='Base Model',
        default='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
        help="The base model to use for fine-tuning in this field."
    )

    hyperparameters = fields.Json(
        string='Hyperparameters',
        default=lambda self: {
            'lora_r': 16,
            'epochs': 3,
            'lr': 2e-4,
            'batch_size': 4,
            'gradient_accumulation_steps': 4,
            'warmup_ratio': 0.03,
        },
        help="""JSON object containing fine-tuning hyperparameters.
            Example: {"lora_r": 16, "epochs": 3, "lr": 2e-4, "batch_size": 4}
        """
    )

    # =========================================================================
    # 2. EXPERT ANSWER USAGE
    # =========================================================================

    expert_answers_trainable = fields.Boolean(
        string='Use Expert Answers for Training',
        default=False,
        help="""If enabled, expert answers from 'Ask Someone' sessions are
            included in the fine-tuning dataset. Only the expert's answer is
            stored - the requester's question is omitted.
            This is off by default for medical fields for privacy reasons.
        """
    )

    indirect_reputation_points = fields.Float(
        string='Indirect Reputation Points',
        default=1.0,
        help="""When an AI answer trained on a professional's expert answer
            receives a 'Good Answer' vote, the original professional receives
            this many reputation points.
        """
    )

    # =========================================================================
    # 3. QUALIFICATION RULES (extended)
    # =========================================================================

    auto_karma_qualify = fields.Boolean(
        string='Auto-Qualify by Karma',
        default=False,
        help="""If enabled, users who reach the reputation threshold
            are automatically added to the Qualified Professionals list.
            This allows high-reputation users to gain expert status
            without manual intervention.
        """
    )

    reputation_threshold_for_charging = fields.Integer(
        string='Minimum Reputation to Charge',
        default=100,
        help="""The minimum reputation points a professional must have
            to be able to charge for 'Ask Someone' sessions in this field.
        """
    )

    # =========================================================================
    # 4. VOTING WEIGHTS (extended)
    # =========================================================================

    base_points_per_vote = fields.Float(
        string='Points per Vote (Regular)',
        default=1.0,
        help="The number of reputation points awarded for a vote from a regular user."
    )

    qualified_points_per_vote = fields.Float(
        string='Points per Vote (Qualified)',
        default=5.0,
        help="The number of reputation points awarded for a vote from a qualified professional."
    )

    auto_adjust_weights = fields.Boolean(
        string='Auto-Adjust Weights',
        default=False,
        help="""If enabled, the system automatically adjusts voting weights
            based on the ratio of qualified professionals to total voters.
        """
    )

    # =========================================================================
    # 5. DATA-JUICER QUALITY PIPELINE
    # =========================================================================

    enable_data_juicer = fields.Boolean(
        string='Enable Data-Juicer Quality Pipeline',
        default=False,
        help="""If enabled, the fine-tuning pipeline runs Data-Juicer on the
            exported dataset for quality filtering, deduplication, and PII removal.
            This requires the 'py-data-juicer[generic,nlp]' package to be installed.
        """
    )

    data_juicer_min_quality_score = fields.Float(
        string='Minimum Quality Score',
        default=0.6,
        help="The minimum quality score for an example to be included in training."
    )

    data_juicer_dedup = fields.Boolean(
        string='Enable Deduplication',
        default=True,
        help="If enabled, Data-Juicer removes exact and near-duplicate entries."
    )

    data_juicer_pii_removal = fields.Boolean(
        string='Enable PII Removal',
        default=True,
        help="If enabled, Data-Juicer attempts to remove personally identifiable information."
    )

    # =========================================================================
    # 6. DEITA LLM-AS-JUDGE SCORING
    # =========================================================================

    enable_deita_scoring = fields.Boolean(
        string='Enable DEITA LLM-as-Judge Scoring',
        default=False,
        help="""If enabled, the fine-tuning pipeline runs DEITA scoring
            on the dataset via distilabel. This scores examples on complexity,
            quality, and diversity. Requires 'distilabel[vllm]' to be installed.
        """
    )

    deita_min_complexity = fields.Float(
        string='Minimum Complexity Score',
        default=0.3,
        help="The minimum complexity score for an example to be included in training."
    )

    deita_judge_model = fields.Char(
        string='Judge Model',
        default='gpt-4o-mini',
        help="The LLM to use as the judge for DEITA scoring."
    )

    # =========================================================================
    # 7. ADVANCED TRAINING (extended)
    # =========================================================================

    enable_ab_testing = fields.Boolean(
        string='Enable A/B Testing',
        default=False,
        help="""If enabled, new models are deployed in shadow mode for A/B testing.
            A percentage of traffic is routed to the new model to compare performance.
        """
    )

    ab_testing_traffic_split = fields.Float(
        string='A/B Testing Traffic Split (%)',
        default=10.0,
        help="The percentage of traffic to route to the test model during A/B testing."
    )

    auto_promote_threshold = fields.Float(
        string='Auto-Promote Threshold',
        default=0.05,
        help="The performance improvement threshold for auto-promotion of a new model."
    )

    enable_grpo_training = fields.Boolean(
        string='Enable GRPO Training',
        default=False,
        help="""If enabled, GRPO reinforcement learning is used to train
            models from Good Answer preferences. Requires Unsloth support.
        """
    )

    min_votes_for_training = fields.Integer(
        string='Minimum Votes for Training',
        default=1,
        help="The minimum number of votes a record must have to be included in training."
    )

    min_unique_voters = fields.Integer(
        string='Minimum Unique Voters',
        default=1,
        help="The minimum number of unique voters for a record to be included in training."
    )

    enable_benchmark_evaluation = fields.Boolean(
        string='Enable Benchmark Evaluation',
        default=False,
        help="""If enabled, fine-tuned models are evaluated against field-specific
            benchmarks before deployment. Requires NeMo Evaluator.
        """
    )

    # =========================================================================
    # 8. DEFAULT VALUES
    # =========================================================================

    @api.model
    def default_get(self, fields_list):
        """
        Set default values for new fields.
        """
        defaults = super().default_get(fields_list)
        defaults.update({
            'finetune_provider': 'unsloth',
            'base_model': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
            'reputation_threshold_for_charging': 100,
            'base_points_per_vote': 1.0,
            'qualified_points_per_vote': 5.0,
            'data_juicer_min_quality_score': 0.6,
            'deita_min_complexity': 0.3,
            'indirect_reputation_points': 1.0,
            'min_votes_for_training': 1,
            'min_unique_voters': 1,
            'ab_testing_traffic_split': 10.0,
            'auto_promote_threshold': 0.05,
        })
        return defaults