# -*- coding: utf-8 -*-
# =============================================================================
# Section A-F NETTRADES Core – Professional Field model (nettrades.field)
# Used by the Ask Someone and Good Answer systems to categorise expertise.
# =============================================================================
# This model represents a professional field or domain of expertise
# (e.g. "Cardiology", "Python Development").  It controls reputation
# thresholds, voting point values, qualification rules, fine-tuning
# configuration, and the optional data-quality pipelines.
#
# Every field is documented with a help string so that administrators
# can understand each setting directly in the Odoo UI.
#
# KEY COMPUTED FIELDS
#   qualified_professional_count   – number of active verified experts
#   total_voter_count              – number of distinct Good Answer voters
#   suggested_qualified_weight     – recommended qualified_points_per_vote
#
# FUTURE ENHANCEMENTS
#   - Per-field model selection for fine-tuning (currently uses a single
#     base_model across the whole field).
#   - Integration with external certification APIs to auto-verify
#     professional credentials.
#   - Historical tracking of voting-weight changes for audit purposes.
# =============================================================================
from odoo import fields, models, api


class NettradesField(models.Model):
    _name = 'nettrades.field'
    _description = 'Professional Field'

    # ------------------------------------------------------------------
    # Basic identification
    # ------------------------------------------------------------------
    name = fields.Char(
        'Name', required=True,
        help="Name of the field, e.g. 'Cardiology', 'Python Development'."
    )
    description = fields.Text(
        help="Optional longer description of the field, visible to users."
    )

    # ------------------------------------------------------------------
    # Qualification rules
    # ------------------------------------------------------------------
    only_qualified = fields.Boolean(
        string="Require Manual Verification",
        default=False,
        help="When enabled, only professionals who have been manually verified "
             "(uploaded credentials) can answer questions in this field. "
             "Leave unchecked for fields where community voting is sufficient."
    )
    auto_karma_qualify = fields.Boolean(
        string="Auto-Qualify by Karma",
        default=False,
        help="If 'Require Manual Verification' is enabled, this setting allows "
             "the system to automatically grant Qualified Professional status "
             "once a user reaches the Karma threshold below. "
             "DO NOT enable for regulated fields (medical, legal, etc.) where "
             "credentials must be checked by a human."
    )
    expert_answers_trainable = fields.Boolean(
        string="Use Expert Answers for Training",
        default=False,
        help=(
            "When enabled, answers from verified professionals in Ask Someone "
            "sessions for this field may be used to improve the AI through "
            "fine-tuning.  The expert's answer is stored without the patient's "
            "original question — only the general medical knowledge is captured.\n\n"
            "WARNING: Do NOT enable this for fields where patient questions "
            "contain Protected Health Information (PHI) unless a de-identification "
            "process is in place."
        )
    )

    # ------------------------------------------------------------------
    # Voting weights (admin-configurable, optionally auto-adjusted)
    # ------------------------------------------------------------------
    reputation_threshold_for_charging = fields.Integer(
        default=100,
        help="Number of reputation points a user must accumulate in this field "
             "before they can charge for their answers (Ask Someone)."
    )
    base_points_per_vote = fields.Integer(
        default=1,
        help="Points awarded when an unqualified user clicks 'Good Answer'."
    )
    qualified_points_per_vote = fields.Integer(
        default=5,
        help="Points awarded when a qualified professional clicks 'Good Answer'."
    )

    # ------------------------------------------------------------------
    # Computed voting insights
    # ------------------------------------------------------------------
    # qualified_professional_count = fields.Integer(
    #     string='Qualified Professionals',
    #     compute='_compute_qualified_stats',
    #     help="Total number of active qualified professionals in this field.  "
    #          "This count is used to suggest optimal voting weights."
    # )
    # total_voter_count = fields.Integer(
    #     string='Total Voters',
    #     compute='_compute_qualified_stats',
    #     help="Total number of distinct users who have cast a Good Answer vote "
    #          "in this field."
    # )
    # suggested_qualified_weight = fields.Integer(
    #     string='Suggested Qualified Weight',
    #     compute='_compute_qualified_stats',
    #     help="Automatically calculated suggestion: higher when many qualified "
    #          "professionals exist, lower when the field relies on community voting."
    # )
    auto_adjust_weights = fields.Boolean(
        string='Auto-Adjust Weights',
        default=False,
        help="When enabled, the system automatically adjusts voting weights based "
             "on the ratio of qualified professionals to total voters."
    )

    # ------------------------------------------------------------------
    # Indirect reputation
    # ------------------------------------------------------------------
    indirect_reputation_points = fields.Integer(
        string="Indirect Reputation Points",
        default=1,
        help="When a future AI answer that was improved by fine-tuning on expert "
             "answers from this field receives a 'Good Answer' vote, each "
             "contributing professional receives this many reputation points.\n\n"
             "This rewards professionals whose expertise helped train the AI, "
             "even though they did not directly answer the current question."
    )

    # ------------------------------------------------------------------
    # Fine-tuning
    # ------------------------------------------------------------------
    finetune_provider = fields.Selection([
        ('unsloth', 'Unsloth (single-GPU)'),
        ('axolotl', 'Axolotl (multi-GPU)'),
    ], string='Fine-tuning Backend', default='unsloth')
    base_model = fields.Char(
        'Base Model',
        default='deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B'
    )
    hyperparameters = fields.Json('Hyperparameters')

    # ------------------------------------------------------------------
    # Data-Juicer quality pipeline (Apache-2.0, Alibaba)
    # ------------------------------------------------------------------
    enable_data_juicer = fields.Boolean(
        string='Enable Data-Juicer Quality Filter',
        default=False,
        help="When enabled, every fine-tuning dataset exported for this field "
             "is automatically filtered through Data-Juicer's quality pipeline: "
             "LLM-based quality scoring, deduplication, and optional PII redaction."
    )
    data_juicer_endpoint_type = fields.Selection([
        ('gpustack', 'GPUStack (central server)'),
        ('local_vllm', 'Local vLLM'),
        ('field_llm', 'Field Default LLM Provider'),
    ], string='Inference Endpoint', default='field_llm',
       help="Which LLM to use for Data-Juicer's quality scoring. "
            "GPUStack uses the NETTRADES central GPU cluster. "
            "Local vLLM uses a dedicated inference endpoint. "
            "Field Default uses the LLM provider configured for this field.")
    data_juicer_min_quality_score = fields.Float(
        string='Minimum Quality Score', default=0.6,
        help="Samples scoring below this threshold are rejected from the training dataset. "
             "Range: 0.0 (keep everything) to 1.0 (keep only perfect examples)."
    )
    data_juicer_max_rejection_rate = fields.Float(
        string='Maximum Rejection Rate', default=0.5,
        help="If more than this fraction of samples are rejected by Data-Juicer, "
             "the quality filter is automatically disabled to prevent starving the "
             "training pipeline.  Set to 0.0 to disable auto-disable."
    )
    data_juicer_enable_dedup = fields.Boolean(
        string='Enable Deduplication', default=True,
        help="Remove duplicate (question, answer) pairs.  Fuzzy matching is also applied."
    )
    data_juicer_enable_pii = fields.Boolean(
        string='Enable PII Redaction', default=False,
        help="Automatically detect and redact personally identifiable information "
             "(names, emails, phone numbers, addresses) from training data."
    )
    data_juicer_auto_disable = fields.Boolean(
        string='Auto-Disable on Poor Results', default=True,
        help="If Data-Juicer rejects too many samples, automatically disable it "
             "and notify the administrator."
    )
    data_juicer_status = fields.Selection([
        ('disabled', 'Disabled'),
        ('enabled', 'Enabled'),
        ('auto_disabled', 'Auto-Disabled (High Rejection)'),
    ], string='Data-Juicer Status', compute='_compute_quality_status', store=True)
    data_juicer_last_run = fields.Datetime(string='Last Run')
    data_juicer_last_stats = fields.Json(string='Last Run Statistics')

    # ------------------------------------------------------------------
    # DEITA / LLM-as-Judge (Apache-2.0, Argilla)
    # ------------------------------------------------------------------
    enable_deita_scoring = fields.Boolean(
        string='Enable DEITA Quality Scoring (LLM-as-Judge)',
        default=False,
        help="When enabled, every training example is scored by an LLM judge "
             "on complexity, quality, and diversity.  Low-scoring examples are "
             "excluded from the fine-tuning dataset.  This is a second validation "
             "layer that runs AFTER Data-Juicer (if enabled)."
    )
    deita_endpoint_type = fields.Selection([
        ('gpustack', 'GPUStack (central server)'),
        ('local_vllm', 'Local vLLM'),
        ('field_llm', 'Field Default LLM Provider'),
    ], string='DEITA Endpoint', default='field_llm')
    deita_min_complexity = fields.Float(
        string='Minimum Complexity', default=0.0,
        help="Samples with complexity below this threshold are rejected. "
             "Higher complexity means the question required more reasoning. "
             "Range: 0.0 (keep all) to 1.0 (keep only the hardest questions)."
    )
    deita_min_quality = fields.Float(
        string='Minimum Quality', default=0.0,
        help="Samples with quality below this threshold are rejected. "
             "Quality measures helpfulness, relevance, accuracy, depth, "
             "creativity, and level of detail.  Range: 0.0 to 1.0."
    )
    deita_auto_disable = fields.Boolean(
        string='Auto-Disable DEITA on Poor Results', default=True
    )
    deita_status = fields.Selection([
        ('disabled', 'Disabled'),
        ('enabled', 'Enabled'),
        ('auto_disabled', 'Auto-Disabled'),
    ], string='DEITA Status', compute='_compute_quality_status', store=True)
    deita_last_run = fields.Datetime(string='Last DEITA Run')
    deita_last_stats = fields.Json(string='Last DEITA Statistics')

    # ------------------------------------------------------------------
    # Advanced training options
    # ------------------------------------------------------------------
    enable_ab_testing = fields.Boolean(
        string='Enable A/B Testing for Fine-Tuned Models',
        default=False,
        help="After fine-tuning, deploy the new model as a shadow endpoint. "
             "A configurable percentage of inference requests are routed to the "
             "new model, and Good Answer rates are compared against the production "
             "model.  If the new model outperforms, it is automatically promoted."
    )
    ab_testing_traffic_split = fields.Float(
        string='A/B Traffic Split', default=0.1,
        help="Fraction of inference requests routed to the new model during A/B testing. "
             "Range: 0.05 (5%) to 0.5 (50%)."
    )
    ab_testing_min_samples = fields.Integer(
        string='A/B Minimum Samples', default=100,
        help="Minimum number of inference requests before the A/B test is considered "
             "complete."
    )
    auto_promote_threshold = fields.Float(
        string='Auto-Promote Threshold', default=0.05,
        help="Statistical significance threshold for automatic model promotion. "
             "If the new model's Good Answer rate exceeds the old model's by this "
             "margin (e.g., 0.05 = 5 percentage points), it is promoted automatically."
    )
    enable_grpo_training = fields.Boolean(
        string='Enable GRPO Reinforcement Learning',
        default=False,
        help="When enough preference pairs exist, trigger Group Relative Policy "
             "Optimisation (GRPO) training via Unsloth.  GRPO uses Good Answer "
             "votes as positive rewards and Ask Someone expert answers as negative "
             "preferences to optimise the model directly."
    )
    min_votes_for_training = fields.Integer(
        string='Minimum Votes for Training', default=1,
        help="A (question, answer) pair must receive at least this many Good Answer "
             "votes before it is included in the fine-tuning dataset.  Set higher "
             "to improve data quality at the cost of dataset size."
    )
    min_unique_voters = fields.Integer(
        string='Minimum Unique Voters', default=1,
        help="A (question, answer) pair must be voted on by at least this many "
             "different users before inclusion.  Prevents single-user bias and "
             "Sybil attacks."
    )
    enable_benchmark_evaluation = fields.Boolean(
        string='Enable Benchmark Evaluation',
        default=False,
        help="After fine-tuning, run the new model against a held-out benchmark "
             "dataset for this field.  If benchmark scores drop, the model is "
             "rejected and the administrator is notified."
    )

    # ------------------------------------------------------------------
    # Computed methods
    # ------------------------------------------------------------------
    @api.depends('enable_data_juicer', 'data_juicer_auto_disable',
                 'enable_deita_scoring', 'deita_auto_disable')
    def _compute_quality_status(self):
        """Update the status badges for Data-Juicer and DEITA based on current settings."""
        for field in self:
            if field.enable_data_juicer:
                field.data_juicer_status = 'enabled'
            else:
                field.data_juicer_status = 'disabled'
            if field.enable_deita_scoring:
                field.deita_status = 'enabled'
            else:
                field.deita_status = 'disabled'

    @api.depends('qualified_professional_ids.is_active')
   # def _compute_qualified_stats(self):
   #      """
   #      Compute:
   #        - qualified_professional_count (active verified experts)
   #        - total_voter_count (distinct Good Answer voters)
   #        - suggested_qualified_weight (based on expert-to-voter ratio)
   #      """
   #      for field in self:
   #          field.qualified_professional_count = len(
   #              field.qualified_professional_ids.filtered(lambda q: q.is_active)
   #          )
   #          votes = self.env['good.answer.vote'].search([
   #              ('field_id', '=', field.id)
   #          ])
   #          field.total_voter_count = len(votes.mapped('user_id'))
   #          ratio = field.qualified_professional_count / max(field.total_voter_count, 1)
   #          if ratio > 0.1:
   #              field.suggested_qualified_weight = 5
   #          elif ratio > 0.01:
   #              field.suggested_qualified_weight = 3
   #          else:
   #              field.suggested_qualified_weight = 1