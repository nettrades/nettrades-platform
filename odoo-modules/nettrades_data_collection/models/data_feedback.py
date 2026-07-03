# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection - Data Feedback Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_feedback.py
#
# PURPOSE:
#   This model stores user feedback for data episodes.
#   Feedback includes Good Answer votes, ratings, and corrections.
#
#   Feedback is collected from:
#     - "Good Answer" votes
#     - User ratings (star ratings)
#     - User corrections to AI responses
#     - Expert session ratings
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class DataFeedback(models.Model):
    """
    Data Feedback - user ratings and votes for episodes.

    Each feedback record is linked to a specific episode and user.
    """
    _name = 'data.feedback'
    _description = 'Data Feedback'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    episode_id = fields.Many2one(
        'data.episode',
        string='Episode',
        required=True,
        ondelete='cascade',
        help="The episode being rated."
    )

    user_id = fields.Many2one(
        'res.partner',
        string='User',
        required=True,
        help="The user who provided the feedback."
    )

    # =========================================================================
    # 2. Feedback Data
    # =========================================================================
    feedback_type = fields.Selection(
        [
            ('good_answer', 'Good Answer Vote'),
            ('rating', 'Star Rating'),
            ('correction', 'Manual Correction'),
            ('expert_rating', 'Expert Session Rating'),
        ],
        string='Feedback Type',
        required=True,
        help="The type of feedback being provided."
    )

    value = fields.Float(
        string='Value',
        required=True,
        help="The numeric value of the feedback (e.g., vote points, star rating)."
    )

    comment = fields.Text(
        string='Comment',
        help="Optional comment from the user."
    )

    # =========================================================================
    # 3. Source Reference
    # =========================================================================
    source_id = fields.Char(
        string='Source ID',
        help="The ID of the source record (e.g., good.answer.vote ID)."
    )

    source_model = fields.Char(
        string='Source Model',
        help="The model of the source record."
    )

    # =========================================================================
    # 4. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the feedback was created."
    )

    # =========================================================================
    # 5. Helper Methods
    # =========================================================================
    @api.model
    def create_good_answer(self, episode_id, user_id, points, source_id=None):
        """
        Create a Good Answer feedback record.

        Args:
            episode_id (int): The episode ID.
            user_id (int): The user partner ID.
            points (float): The vote points.
            source_id (str, optional): The source vote ID.

        Returns:
            DataFeedback: The created feedback record.
        """
        return self.create({
            'episode_id': episode_id,
            'user_id': user_id,
            'feedback_type': 'good_answer',
            'value': points,
            'source_id': source_id,
            'source_model': 'good.answer.vote',
        })