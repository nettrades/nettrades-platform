# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness - Audit & Flag Models
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/models/fairness_audit.py
#
# PURPOSE:
#   This file defines the audit and flag models for the fairness system.
#   It tracks all fairness evaluations and provides a mechanism for
#   human review of flagged responses.
#
#   The audit log is used for:
#     - Compliance monitoring (NYC Local Law 144, EU AI Act)
#     - Performance analysis (tracking fairness metrics over time)
#     - Quality improvement (identifying patterns in low-quality responses)
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class FairnessAudit(models.Model):
    """
    Fairness Audit Log - tracks all fairness evaluations.

    Each record stores the evaluation of a single AI response.
    """
    _name = 'nettrades.fairness.audit'
    _description = 'Fairness Audit Log'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    response_id = fields.Many2one(
        'llm.assistant.message',
        string='AI Response',
        help="The AI response that was evaluated."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The professional field of the evaluation."
    )

    # =========================================================================
    # 2. Evaluation Data
    # =========================================================================
    question_text = fields.Text(
        string='Question',
        help="The user's question that prompted the response."
    )

    response_text = fields.Text(
        string='Response',
        help="The AI response that was evaluated."
    )

    rationality_score = fields.Float(
        string='Rationality Score',
        help="The rationality score (0-10) assigned by the LLM judge."
    )

    bias_score = fields.Float(
        string='Bias Score',
        help="The bias score (0-10) assigned by the LLM judge."
    )

    rationale = fields.Text(
        string='Rationale',
        help="The LLM judge's explanation for the scores."
    )

    # =========================================================================
    # 3. Metadata
    # =========================================================================
    evaluation_model = fields.Char(
        string='Evaluation Model',
        help="The model used for the evaluation (e.g., 'gpt-4o-mini')."
    )

    protected_attributes = fields.Char(
        string='Protected Attributes',
        help="The protected attributes that were checked for bias."
    )

    is_passed = fields.Boolean(
        string='Passed',
        compute='_compute_is_passed',
        store=True,
        help="Whether the response passed the rationality and bias thresholds."
    )

    # =========================================================================
    # 4. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the evaluation was created."
    )

    # =========================================================================
    # 5. Computed Fields
    # =========================================================================
    @api.depends('rationality_score', 'bias_score')
    def _compute_is_passed(self):
        """
        Determine if the response passed the fairness thresholds.
        """
        config = self.env['nettrades.fairness.config'].get_config()
        for record in self:
            rationality_threshold = config.rationality_threshold
            bias_threshold = config.bias_threshold

            rationality_passed = True
            bias_passed = True

            if record.rationality_score is not None:
                rationality_passed = record.rationality_score >= rationality_threshold

            if record.bias_score is not None:
                bias_passed = record.bias_score <= bias_threshold

            record.is_passed = rationality_passed and bias_passed

    # =========================================================================
    # 6. Statistics Methods
    # =========================================================================
    def get_stats(self):
        """
        Calculate statistics for a set of audit records.

        Returns:
            dict: Statistics including average scores, pass rate, etc.
        """
        if not self:
            return {}

        total = len(self)
        rationality_scores = [r.rationality_score for r in self if r.rationality_score is not None]
        bias_scores = [r.bias_score for r in self if r.bias_score is not None]
        passed = len(self.filtered(lambda r: r.is_passed))

        return {
            'total': total,
            'passed': passed,
            'pass_rate': (passed / total * 100) if total > 0 else 0,
            'avg_rationality': sum(rationality_scores) / len(rationality_scores) if rationality_scores else 0,
            'avg_bias': sum(bias_scores) / len(bias_scores) if bias_scores else 0,
            'min_rationality': min(rationality_scores) if rationality_scores else 0,
            'max_bias': max(bias_scores) if bias_scores else 0,
        }


class FairnessFlag(models.Model):
    """
    Fairness Flag - responses flagged for human review.

    When a response exceeds the rationality or bias thresholds, it is
    flagged for human review. An administrator can review the flag,
    accept or reject it, and take appropriate action.
    """
    _name = 'nettrades.fairness.flag'
    _description = 'Fairness Flag'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    response_id = fields.Many2one(
        'llm.assistant.message',
        string='AI Response',
        help="The AI response that was flagged."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The professional field of the flagged response."
    )

    # =========================================================================
    # 2. Flag Details
    # =========================================================================
    reason = fields.Text(
        string='Flag Reason',
        help="The reason the response was flagged."
    )

    rationality_score = fields.Float(
        string='Rationality Score',
        help="The rationality score that triggered the flag."
    )

    bias_score = fields.Float(
        string='Bias Score',
        help="The bias score that triggered the flag."
    )

    # =========================================================================
    # 3. Review Status
    # =========================================================================
    status = fields.Selection(
        [
            ('pending', 'Pending Review'),
            ('reviewed', 'Reviewed'),
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='pending',
        help="Current status of the flag."
    )

    reviewed_by = fields.Many2one(
        'res.users',
        string='Reviewed By',
        help="The user who reviewed the flag."
    )

    review_notes = fields.Text(
        string='Review Notes',
        help="Notes from the reviewer."
    )

    reviewed_date = fields.Datetime(
        string='Reviewed Date',
        help="Timestamp when the flag was reviewed."
    )

    # =========================================================================
    # 4. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the flag was created."
    )

    # =========================================================================
    # 5. Actions
    # =========================================================================
    def action_review(self, notes=None, status='reviewed'):
        """
        Review a flag.

        Args:
            notes (str, optional): Review notes.
            status (str): New status ('reviewed', 'accepted', 'rejected').
        """
        self.ensure_one()

        self.write({
            'status': status,
            'reviewed_by': self.env.user.id,
            'review_notes': notes,
            'reviewed_date': fields.Datetime.now(),
        })

        if status in ('accepted', 'rejected'):
            _logger.info("Flag %s %s by user %s", self.id, status, self.env.user.name)