# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection – Data Annotation Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_annotation.py
#
# PURPOSE:
#   This model stores human or expert annotations for data episodes.
#   Annotations are used to enrich training data and provide quality signals.
#
#   Annotations can be:
#     - Expert validation: An expert confirms the quality of an episode
#     - Manual correction: An expert corrects an AI-generated response
#     - Quality rating: An expert rates the quality of an episode
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class DataAnnotation(models.Model):
    """
    Data Annotation – human or expert evaluation of an episode.

    Each annotation is linked to a specific episode and annotator.
    """
    _name = 'data.annotation'
    _description = 'Data Annotation'
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
        help="The episode being annotated."
    )

    annotator_id = fields.Many2one(
        'res.partner',
        string='Annotator',
        required=True,
        help="The user who created this annotation."
    )

    # =========================================================================
    # 2. Annotation Data
    # =========================================================================
    annotation_type = fields.Selection(
        [
            ('expert_validation', 'Expert Validation'),
            ('manual_correction', 'Manual Correction'),
            ('quality_rating', 'Quality Rating'),
            ('bias_flag', 'Bias Flag'),
            ('rationality_flag', 'Rationality Flag'),
            ('general', 'General Annotation'),
        ],
        string='Annotation Type',
        required=True,
        help="The type of annotation being made."
    )

    annotation_data = fields.Json(
        string='Annotation Data',
        help="JSON blob containing the annotation data. Structure varies by type."
    )

    # =========================================================================
    # 3. Quality Signals
    # =========================================================================
    quality_score = fields.Float(
        string='Quality Score',
        help="Quality score assigned by the annotator (0-10)."
    )

    is_approved = fields.Boolean(
        string='Is Approved',
        default=False,
        help="Whether this annotation has been approved by a supervisor."
    )

    # =========================================================================
    # 4. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the annotation was created."
    )

    # =========================================================================
    # 5. Helper Methods
    # =========================================================================
    @api.model
    def create_expert_validation(self, episode_id, annotator_id, quality_score, notes=None):
        """
        Create an expert validation annotation.

        Args:
            episode_id (int): The episode ID.
            annotator_id (int): The annotator partner ID.
            quality_score (float): Quality score (0-10).
            notes (str, optional): Additional notes.

        Returns:
            DataAnnotation: The created annotation record.
        """
        return self.create({
            'episode_id': episode_id,
            'annotator_id': annotator_id,
            'annotation_type': 'expert_validation',
            'quality_score': quality_score,
            'annotation_data': {'notes': notes} if notes else {},
        })