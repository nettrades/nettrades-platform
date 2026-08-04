# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer - Good Answer Vote Model
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/good_answer_vote.py
#
# PURPOSE:
#   This model stores user votes on AI-generated answers.
#   When a user clicks "Good Answer", a vote record is created.
#   These votes feed into the reputation system and the self-improving loop.
#
# KEY FEATURES:
#   - Tracks which answer was voted on (answer_id + answer_model)
#   - Stores the voter (user_id) and the answerer (answerer_id)
#   - Links to the professional field (field_id)
#   - Points awarded based on voter qualification
#   - Creates feedback records for the self-improving loop
#
# RELATIONSHIPS:
#   - user_id -> res.partner (the voter)
#   - answerer_id -> res.partner (the person who provided the answer)
#   - field_id -> nettrades.field (the professional field)
#
# INTEGRATION:
#   - Creates data.feedback records for the self-improving loop
#   - Updates user_field_reputation for the answerer
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class GoodAnswerVote(models.Model):
    _name = 'good.answer.vote'
    _description = 'Good Answer Vote'
    _order = 'created_at DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. BASIC FIELDS
    # =========================================================================

    user_id = fields.Many2one(
        'res.partner',
        required=True,
        help="The user who cast the vote."
    )

    answer_id = fields.Integer(
        required=True,
        help="The ID of the answer being voted on."
    )

    answer_model = fields.Char(
        required=True,
        help="The model of the answer being voted on (e.g., 'llm.message')."
    )

    answerer_id = fields.Many2one(
        'res.partner',
        required=True,
        help="The user who provided the answer."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        required=True,
        help="The professional field this vote belongs to."
    )

    points = fields.Integer(
        default=1,
        help="The number of reputation points awarded for this vote."
    )

    is_qualified_vote = fields.Boolean(
        default=False,
        help="True if the voter is a qualified professional for this field."
    )

    processed_for_ai = fields.Boolean(
        default=False,
        help="True if this vote has been processed for AI fine-tuning."
    )

    created_at = fields.Datetime(
        default=fields.Datetime.now,
        help="Timestamp when the vote was created."
    )

    # =========================================================================
    # 2. CONSTRAINTS
    # =========================================================================

    _sql_constraints = [
        ('unique_vote', 'unique(user_id, answer_id, answer_model)',
         'Already voted on this answer.')
    ]

    # =========================================================================
    # 3. BUSINESS METHODS
    # =========================================================================

    @api.model
    def create(self, vals):
        """
        Create a new vote and propagate it to the self-improving system.

        This method:
        1. Creates the vote record
        2. Creates a feedback record in data.feedback
        3. Updates the answerer's reputation
        """
        vote = super().create(vals)

        # Send to self-improving system
        try:
            # Check if data.feedback model exists
            if 'data.feedback' in self.env:
                self.env['data.feedback'].create({
                    'episode_id': vote.answer_id,
                    'user_id': vote.user_id.id,
                    'feedback_type': 'good_answer',
                    'value': vote.points or 1,
                    'source_id': str(vote.id),
                    'source_model': 'good.answer.vote',
                })
                _logger.debug("Feedback created for vote %s", vote.id)
            else:
                _logger.warning("data.feedback model not available")

            # Update answerer's reputation
            rep = self.env['user.field.reputation'].search([
                ('partner_id', '=', vote.answerer_id.id),
                ('field_id', '=', vote.field_id.id)
            ])
            if rep:
                rep.reputation_points += vote.points or 1
                _logger.debug("Reputation updated for answerer %s", vote.answerer_id.id)

        except Exception as e:
            _logger.warning("Failed to create feedback or update reputation: %s", e)

        return vote

    @api.model
    def get_vote_count(self, answer_id, answer_model):
        """
        Get the total vote count and points for an answer.

        Args:
            answer_id (int): The ID of the answer.
            answer_model (str): The model of the answer.

        Returns:
            dict: {
                'positive': int,
                'negative': int,
                'total_points': float
            }
        """
        votes = self.search([
            ('answer_id', '=', answer_id),
            ('answer_model', '=', answer_model),
        ])

        positive_count = 0
        negative_count = 0
        total_points = 0.0

        for vote in votes:
            if vote.points > 0:
                positive_count += 1
            else:
                negative_count += 1
            total_points += vote.points

        return {
            'positive': positive_count,
            'negative': negative_count,
            'total_points': total_points,
        }