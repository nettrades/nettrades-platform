# -*- coding: utf-8 -*-
# =============================================================================
# SECTION E - PROFESSIONAL FIELD MODEL
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_field.py
#
# PURPOSE:
#   This model represents a professional field (e.g., "Cardiology",
#   "Python Development", "Legal Advisory"). It stores all configuration
#   for qualification, voting, fine-tuning, and quality control.
#
# RELATIONSHIPS:
#   - One-to-many with user_field_reputation (reputation per user per field)
#   - One-to-many with good_answer_vote (votes in this field)
#   - One-to-many with ft_dataset (fine-tuning datasets for this field)
#
# KEY FEATURES:
#   - Qualification rules (only_qualified, auto_karma_qualify)
#   - Voting weights (base_points_per_vote, qualified_points_per_vote)
#   - Expert answer usage (expert_answers_trainable, indirect_reputation_points)
#   - Fine-tuning configuration (finetune_provider, base_model, hyperparameters)
#   - Data-Juicer quality pipeline (enable_data_juicer, etc.)
#   - DEITA LLM-as-Judge scoring (enable_deita_scoring, etc.)
#   - Advanced training (A/B testing, GRPO, benchmark evaluation)
#
# USAGE:
#   - Created by the system administrator via the Odoo admin panel
#   - Used by the LangGraph agent to route questions to the correct model
#   - Used by the voting system to weight votes appropriately
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class NettradesField(models.Model):
    """
    Professional Field Model - represents a domain of expertise.

    This model stores all configuration for a professional field, including
    qualification rules, voting weights, and fine-tuning settings.
    """
    _name = 'nettrades.field'
    _description = 'Professional Field'
    _rec_name = 'name'

    # =========================================================================
    # 1. BASIC IDENTIFICATION
    # =========================================================================

    name = fields.Char(
        string='Name',
        required=True,
        translate=True,
        help="The name of the professional field (e.g., 'Cardiology', 'Python Development')."
    )

    description = fields.Text(
        string='Description',
        help="A detailed description of this professional field."
    )

    # =========================================================================
    # 2. QUALIFICATION RULES
    # =========================================================================

    only_qualified = fields.Boolean(
        string='Require Manual Verification',
        default=False,
        help="If enabled, only professionals who are manually verified by an administrator can answer questions in this field. This is typically enabled for restricted fields like medical or legal domains."
    )

    auto_karma_qualify = fields.Boolean(
        string='Auto-Qualify by Karma',
        default=False,
        help="If enabled, users who reach the reputation threshold are automatically added to the Qualified Professionals list. This allows high-reputation users to gain expert status without manual intervention."
    )

    reputation_threshold_for_charging = fields.Integer(
        string='Minimum Reputation to Charge',
        default=100,
        help="The minimum reputation points a professional must have to be able to charge for 'Ask Someone' sessions in this field."
    )

    # =========================================================================
    # 3. VOTING WEIGHTS
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

    qualified_professional_count = fields.Integer(
        string='Qualified Professionals',
        compute='_compute_qualified_stats',
        store=False,
        help="The total number of active qualified professionals in this field."
    )

    total_voter_count = fields.Integer(
        string='Total Voters',
        compute='_compute_qualified_stats',
        store=False,
        help="The total number of distinct users who have voted in this field."
    )

    suggested_qualified_weight = fields.Integer(
        string='Suggested Qualified Weight',
        compute='_compute_qualified_stats',
        store=False,
        help="Automatically calculated suggestion for qualified_points_per_vote. Higher when many qualified professionals exist, lower when the field relies on community voting."
    )

    auto_adjust_weights = fields.Boolean(
        string='Auto-Adjust Weights',
        default=False,
        help="If enabled, the system automatically adjusts voting weights based on the ratio of qualified professionals to total voters."
    )

    # =========================================================================
    # 4. EXPERT ANSWER USAGE
    # =========================================================================

    expert_answers_trainable = fields.Boolean(
        string='Use Expert Answers for Training',
        default=False,
        help="If enabled, expert answers from 'Ask Someone' sessions are included in the fine-tuning dataset. Only the expert's answer is stored - the requester's question is omitted. This is off by default for medical fields for privacy reasons."
    )

    indirect_reputation_points = fields.Float(
        string='Indirect Reputation Points',
        default=1.0,
        help="When an AI answer trained on a professional's expert answer receives a 'Good Answer' vote, the original professional receives this many reputation points."
    )

    # =========================================================================
    # 5. FINE-TUNING CONFIGURATION
    # =========================================================================

    finetune_provider = fields.Selection(
        [
            ('unsloth', 'Unsloth (single-GPU)'),
            ('axolotl', 'Axolotl (multi-GPU)'),
        ],
        string='Fine-tuning Backend',
        default='unsloth',
        help="The backend to use for fine-tuning models in this field: Unsloth: Single-GPU fine-tuning (2x faster, 70% less VRAM). Axolotl: Multi-GPU fine-tuning with FSDP2 (for larger models)."
    )

    base_model = fields.Char(
        string='Base Model',
        default='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
        help="The base model to use for fine-tuning in this field."
    )

    hyperparameters = fields.Json(
        string='Hyperparameters',
        help='JSON object containing fine-tuning hyperparameters. Example: {"lora_r": 16, "epochs": 3, "lr": 2e-4, "batch_size": 4}.'
    )

    # =========================================================================
    # 6. DATA-JUICER QUALITY PIPELINE
    # =========================================================================

    enable_data_juicer = fields.Boolean(
        string='Enable Data-Juicer Quality Pipeline',
        default=False,
        help="If enabled, the fine-tuning pipeline runs Data-Juicer on the exported dataset for quality filtering, deduplication, and PII removal. This requires the 'py-data-juicer[generic,nlp]' package to be installed."
    )

    data_juicer_status = fields.Selection(
        [
            ('idle', 'Idle'),
            ('running', 'Running'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        string='Data-Juicer Status',
        default='idle',
        help="Current status of the Data-Juicer quality pipeline for this field."
    )

    data_juicer_endpoint_type = fields.Selection(
        [
            ('local', 'Local'),
            ('cloud', 'Cloud (AWS)'),
            ('hybrid', 'Hybrid'),
        ],
        string="Data-Juicer Endpoint",
        default="local",
        help="Type of endpoint used for Data-Juicer processing."
    )

    data_juicer_max_rejection_rate = fields.Float(
        string="Max Rejection Rate",
        default=0.3,
        help="Maximum percentage of examples that can be rejected during quality filtering."
    )

    data_juicer_min_quality_score = fields.Float(
        string='Minimum Quality Score',
        default=0.6,
        help="The minimum quality score for an example to be included in training."
    )

    # RENAMED: was data_juicer_dedup ? data_juicer_enable_dedup
    data_juicer_enable_dedup = fields.Boolean(
        string='Enable Deduplication',
        default=True,
        help="If enabled, Data-Juicer removes exact and near-duplicate entries."
    )

    # RENAMED: was data_juicer_pii_removal ? data_juicer_enable_pii
    data_juicer_enable_pii = fields.Boolean(
        string='Enable PII Removal',
        default=True,
        help="If enabled, Data-Juicer attempts to remove personally identifiable information."
    )
    
    # =========================================================================
    # 7. DEITA LLM-AS-JUDGE SCORING
    # =========================================================================

    enable_deita_scoring = fields.Boolean(
        string='Enable DEITA LLM-as-Judge Scoring',
        default=False,
        help="If enabled, the fine-tuning pipeline runs DEITA scoring on the dataset via distilabel. This scores examples on complexity, quality, and diversity. Requires 'distilabel[vllm]' to be installed."
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
    # 8. ADVANCED TRAINING
    # =========================================================================

    enable_ab_testing = fields.Boolean(
        string='Enable A/B Testing',
        default=False,
        help="If enabled, new models are deployed in shadow mode for A/B testing. A percentage of traffic is routed to the new model to compare performance."
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
        help="If enabled, GRPO reinforcement learning is used to train models from Good Answer preferences. Requires Unsloth support."
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
        help="If enabled, fine-tuned models are evaluated against field-specific benchmarks before deployment. Requires NeMo Evaluator."
    )

    # =========================================================================
    # 9. COMPUTED FIELDS
    # =========================================================================

    @api.depends('name')
    def _compute_qualified_stats(self):
        """
        Compute statistics about qualified professionals and voters.

        This method calculates:
        - The number of active qualified professionals in this field
        - The total number of voters in this field
        - A suggested qualified weight based on the ratio
        """
        for field in self:
            # Count active qualified professionals
            qualified = self.env['qualified.professional'].search([
                ('field_id', '=', field.id),
                ('is_active', '=', True),
            ])
            field.qualified_professional_count = len(qualified)

            # Count unique voters in this field
            votes = self.env['good.answer.vote'].search([
                ('field_id', '=', field.id),
            ])
            field.total_voter_count = len(votes.mapped('user_id'))

            # Calculate suggested weight based on ratio
            ratio = field.qualified_professional_count / max(field.total_voter_count, 1)
            if ratio > 0.1:
                field.suggested_qualified_weight = 5
            elif ratio > 0.01:
                field.suggested_qualified_weight = 3
            else:
                field.suggested_qualified_weight = 1

    # =========================================================================
    # 10. HELPER METHODS
    # =========================================================================

    def get_qualified_experts(self):
        """
        Get all qualified experts for this field.

        Returns:
            recordset: The res.partner records of all qualified experts.
        """
        self.ensure_one()

        qualified = self.env['qualified.professional'].search([
            ('field_id', '=', self.id),
            ('is_active', '=', True),
        ])

        return qualified.mapped('partner_id')

    def get_voting_weight(self, user):
        """
        Get the voting weight for a specific user in this field.

        Args:
            user (res.partner): The user casting the vote.

        Returns:
            float: The voting weight (base or qualified points).
        """
        self.ensure_one()

        # Check if the user is a qualified professional in this field
        is_qualified = self.env['qualified.professional'].search([
            ('field_id', '=', self.id),
            ('partner_id', '=', user.id),
            ('is_active', '=', True),
        ], limit=1)

        if is_qualified:
            return self.qualified_points_per_vote
        else:
            return self.base_points_per_vote

    def action_auto_adjust_weights(self):
        """
        Automatically adjust voting weights based on community composition.

        This method is called by the cron job when auto_adjust_weights is enabled.
        """
        fields_to_adjust = self.search([('auto_adjust_weights', '=', True)])

        for field in fields_to_adjust:
            field._compute_qualified_stats()
            if field.suggested_qualified_weight != field.qualified_points_per_vote:
                field.qualified_points_per_vote = field.suggested_qualified_weight
                _logger.info(
                    f"Auto-adjusted qualified_points_per_vote for field {field.name} "
                    f"to {field.suggested_qualified_weight}"
                )

    # =========================================================================
    # 11. CONSTRAINTS AND VALIDATION
    # =========================================================================

    @api.constrains('reputation_threshold_for_charging')
    def _check_reputation_threshold(self):
        """
        Validate the reputation threshold.

        Ensures the threshold is a positive number.
        """
        for field in self:
            if field.reputation_threshold_for_charging < 0:
                raise ValidationError(_(
                    "The reputation threshold must be a positive number."
                ))

    @api.constrains('base_points_per_vote', 'qualified_points_per_vote')
    def _check_voting_weights(self):
        """
        Validate voting weights.

        Ensures the weights are positive numbers.
        """
        for field in self:
            if field.base_points_per_vote < 0:
                raise ValidationError(_("Base points per vote must be a positive number."))
            if field.qualified_points_per_vote < 0:
                raise ValidationError(_("Qualified points per vote must be a positive number."))

    @api.constrains('data_juicer_min_quality_score')
    def _check_quality_score(self):
        """
        Validate the quality score range.
        """
        for field in self:
            if field.enable_data_juicer and not (0 <= field.data_juicer_min_quality_score <= 1):
                raise ValidationError(_(
                    "The minimum quality score must be between 0 and 1."
                ))

    @api.constrains('deita_min_complexity')
    def _check_complexity_score(self):
        """
        Validate the complexity score range.
        """
        for field in self:
            if field.enable_deita_scoring and not (0 <= field.deita_min_complexity <= 1):
                raise ValidationError(_(
                    "The minimum complexity score must be between 0 and 1."
                ))

    @api.constrains('ab_testing_traffic_split')
    def _check_traffic_split(self):
        """
        Validate the traffic split range.
        """
        for field in self:
            if field.enable_ab_testing and not (0 < field.ab_testing_traffic_split < 100):
                raise ValidationError(_(
                    "The traffic split must be between 0 and 100."
                ))

    # =========================================================================
    # 12. DEFAULT VALUES
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
            'data_juicer_max_rejection_rate': 0.3,
            'deita_min_complexity': 0.3,
            'indirect_reputation_points': 1.0,
            'min_votes_for_training': 1,
            'min_unique_voters': 1,
            'ab_testing_traffic_split': 10.0,
            'auto_promote_threshold': 0.05,
        })
        return defaults
