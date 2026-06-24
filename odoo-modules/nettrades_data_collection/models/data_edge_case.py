# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection – Data Edge Case Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_edge_case.py
#
# PURPOSE:
#   This model stores novel or problematic interactions that may represent
#   edge cases. Edge cases are used to detect when the system needs improvement.
#
#   Edge cases are detected by:
#     - Low confidence scores (AI was unsure)
#     - Low rationality scores (response was illogical)
#     - High bias scores (response showed bias)
#     - User corrections (user corrected the AI)
#     - Novel patterns (low similarity to existing episodes)
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class DataEdgeCase(models.Model):
    """
    Data Edge Case – novel or problematic interactions.

    Each edge case record is linked to a specific episode.
    """
    _name = 'data.edge_case'
    _description = 'Data Edge Case'
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
        help="The episode that represents this edge case."
    )

    # =========================================================================
    # 2. Detection Data
    # =========================================================================
    detection_type = fields.Selection(
        [
            ('low_confidence', 'Low Confidence'),
            ('low_rationality', 'Low Rationality'),
            ('high_bias', 'High Bias'),
            ('user_correction', 'User Correction'),
            ('novel_pattern', 'Novel Pattern'),
            ('manual', 'Manual Review'),
        ],
        string='Detection Type',
        required=True,
        help="How this edge case was detected."
    )

    similarity_score = fields.Float(
        string='Similarity Score',
        help="Cosine similarity to nearest existing cluster (0-1). Lower indicates novelty."
    )

    is_confirmed = fields.Boolean(
        string='Is Confirmed',
        default=False,
        help="Whether this edge case has been confirmed by a human reviewer."
    )

    notes = fields.Text(
        string='Notes',
        help="Additional notes from the reviewer."
    )

    # =========================================================================
    # 3. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the edge case was recorded."
    )

    # =========================================================================
    # 4. Helper Methods
    # =========================================================================
    @api.model
    def create_from_episode(self, episode_id, detection_type, similarity_score=None):
        """
        Create an edge case from an episode.

        Args:
            episode_id (int): The episode ID.
            detection_type (str): The detection type.
            similarity_score (float, optional): The similarity score.

        Returns:
            DataEdgeCase: The created edge case record.
        """
        return self.create({
            'episode_id': episode_id,
            'detection_type': detection_type,
            'similarity_score': similarity_score,
        })