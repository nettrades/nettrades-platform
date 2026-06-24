# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection – Data Episode Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_episode.py
#
# PURPOSE:
#   This model stores a complete interaction record (episode) between a user
#   and the AI system. Each episode captures the input, output, and any
#   subsequent feedback.
#
#   Episodes are the primary data source for the self-improving loop.
#   They are collected from:
#     - LangGraph agent interactions
#     - Ask Someone expert sessions
#     - Good Answer votes on AI answers
#     - Chatbot conversations
#     - ROS 2 / robotics interactions
#
# LIFECYCLE:
#   1. Created when an interaction occurs (e.g., user asks a question)
#   2. Updated with feedback when available (e.g., user clicks "Good Answer")
#   3. Qualified when quality_score meets threshold
#   4. Processed when exported to training dataset
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import json
import logging
from datetime import timedelta

_logger = logging.getLogger(__name__)


class DataEpisode(models.Model):
    """
    Data Episode – Complete interaction record.

    Each episode represents a single interaction between a user and the AI,
    including the input, output, and any feedback received.

    This is the foundational data unit for the self-improving system.
    """
    _name = 'data.episode'
    _description = 'AI Interaction Episode'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. SOURCE IDENTIFICATION
    # =========================================================================

    source = fields.Selection(
        [
            ('langgraph', 'LangGraph Agent'),
            ('ask_someone', 'Ask Someone Session'),
            ('good_answer', 'Good Answer Vote'),
            ('chatbot', 'Chatbot Interaction'),
            ('gpu', 'GPU Management'),
            ('ros2', 'ROS 2 / Robotics'),
            ('manual', 'Manual Entry'),
        ],
        string='Source',
        required=True,
        help="""The source system that generated this episode.
            This helps track which parts of the platform are producing
            the most valuable training data.
        """
    )

    source_id = fields.Char(
        string='Source ID',
        help="""The ID of the record in the source system.
            For example, if source='good_answer', this would be the
            good.answer.vote ID. This enables traceability.
        """
    )

    # =========================================================================
    # 2. INTERACTION DATA
    # =========================================================================

    input_text = fields.Text(
        string='User Input',
        required=True,
        help="The user's original query, request, or command."
    )

    output_text = fields.Text(
        string='AI Output',
        required=True,
        help="The AI agent's response or output."
    )

    context_data = fields.Json(
        string='Context Data',
        help="""JSON blob containing additional context:
            - agent_type: The LangGraph agent that handled the request
            - session_id: The conversation thread ID
            - metadata: Any other relevant context
            Example: {"agent_type": "recruitment", "session_id": "abc-123"}
        """
    )

    # =========================================================================
    # 3. QUALITY SIGNALS
    # =========================================================================

    quality_score = fields.Float(
        string='Quality Score',
        default=0.0,
        help="""A calculated quality score based on user feedback and
            expert review. Range: 0-10.
            Sources:
            - Good Answer votes: points (1-5, scaled to 2-10)
            - Expert ratings: 1-5 stars (scaled to 2-10)
            - AI confidence score: 0-1 (scaled to 0-10)
        """
    )

    confidence_score = fields.Float(
        string='Confidence Score',
        default=0.0,
        help="""The AI's confidence in its response (0-1).
            This is used for confidence-aware escalation.
            If confidence < threshold, the request may be escalated
            to a more capable model or a human expert.
        """
    )

    vote_count = fields.Integer(
        string='Vote Count',
        default=0,
        help="Number of 'Good Answer' votes received for this interaction."
    )

    is_qualified = fields.Boolean(
        string='Is Qualified',
        default=False,
        help="""Whether this episode has been marked as high-quality
            for training. Qualified episodes have:
            - quality_score >= min_quality_score (configurable)
            - At least min_votes votes (configurable)
            - Been reviewed by an expert (if required)
        """
    )

    # =========================================================================
    # 4. PROCESSING STATUS
    # =========================================================================

    processed = fields.Boolean(
        string='Processed for Training',
        default=False,
        help="Whether this episode has been exported to the training dataset."
    )

    processed_date = fields.Datetime(
        string='Processed Date',
        help="Timestamp when this episode was exported to the training dataset."
    )

    # =========================================================================
    # 5. RELATIONSHIPS
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='User',
        help="The user who initiated this interaction."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The professional field this interaction belongs to."
    )

    annotation_ids = fields.One2many(
        'data.annotation',
        'episode_id',
        string='Annotations',
        help="Human or expert annotations for this episode."
    )

    # =========================================================================
    # 6. COMPUTED FIELDS
    # =========================================================================

    has_annotation = fields.Boolean(
        compute='_compute_has_annotation',
        store=True,
        help="Whether this episode has at least one annotation."
    )

    @api.depends('annotation_ids')
    def _compute_has_annotation(self):
        for record in self:
            record.has_annotation = bool(record.annotation_ids)

    # =========================================================================
    # 7. CONSTRAINTS
    # =========================================================================

    @api.constrains('quality_score')
    def _check_quality_score(self):
        """Ensure quality score is between 0 and 10."""
        for record in self:
            if record.quality_score < 0 or record.quality_score > 10:
                raise ValidationError(_(
                    "Quality score must be between 0 and 10."
                ))

    # =========================================================================
    # 8. QUALIFICATION LOGIC
    # =========================================================================

    def action_qualify(self):
        """
        Manually qualify an episode for training.

        This method is called by administrators or triggered automatically
        when quality_score exceeds the threshold.
        """
        for record in self:
            record.is_qualified = True
            _logger.info("Qualified episode %s for training", record.id)

    def action_unqualify(self):
        """
        Manually unqualify an episode for training.
        """
        for record in self:
            record.is_qualified = False
            _logger.info("Unqualified episode %s for training", record.id)

    def action_qualify_by_score(self, min_score=5.0, min_votes=2):
        """
        Automatically qualify episodes that meet quality thresholds.

        Args:
            min_score (float): Minimum quality score required.
            min_votes (int): Minimum number of votes required.

        Returns:
            int: Number of episodes qualified.
        """
        episodes = self.search([
            ('is_qualified', '=', False),
            ('quality_score', '>=', min_score),
            ('vote_count', '>=', min_votes),
        ])

        count = len(episodes)
        episodes.write({'is_qualified': True})

        _logger.info("Qualified %s episodes by score threshold", count)
        return count

    # =========================================================================
    # 9. TRAINING DATA EXPORT
    # =========================================================================

    def action_export_to_training_dataset(self, field_id=None, min_score=5.0, min_votes=2):
        """
        Export qualified episodes to the Apexive llm.training.dataset.

        This method:
        1. Filters episodes by quality_score and is_qualified
        2. Converts them to the JSONL format required by llm.training
        3. Creates or updates a training dataset record
        4. Marks episodes as processed

        Args:
            field_id (int, optional): Filter by field ID.
            min_score (float): Minimum quality score.
            min_votes (int): Minimum vote count.

        Returns:
            llm.training.dataset: The created dataset, or None if no data.
        """
        # Build domain
        domain = [
            ('is_qualified', '=', True),
            ('processed', '=', False),
            ('quality_score', '>=', min_score),
            ('vote_count', '>=', min_votes),
        ]

        if field_id:
            domain.append(('field_id', '=', field_id))

        # Get episodes
        episodes = self.search(domain)

        if not episodes:
            _logger.info("No eligible episodes found for training export")
            return None

        # Prepare JSONL data
        jsonl_data = []
        for episode in episodes:
            jsonl_data.append({
                'prompt': episode.input_text,
                'completion': episode.output_text,
            })

        # Create llm.training.dataset
        dataset = self.env['llm.training.dataset'].create({
            'name': f"Episode Export {fields.Datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'description': f"Auto-exported from data.episode ({len(episodes)} records)",
            'record_count': len(jsonl_data),
            'data': json.dumps(jsonl_data),
            'status': 'draft',
            'field_id': field_id or episodes[0].field_id.id,
        })

        # Mark episodes as processed
        episodes.write({
            'processed': True,
            'processed_date': fields.Datetime.now(),
        })

        _logger.info("Exported %s episodes to training dataset %s", len(episodes), dataset.name)
        return dataset

    # =========================================================================
    # 10. STATISTICS
    # =========================================================================

    def get_quality_stats(self):
        """
        Calculate quality statistics for episodes.

        Returns:
            dict: Statistics including average quality, count by field, etc.
        """
        stats = {
            'total': len(self),
            'avg_quality': 0.0,
            'by_field': {},
            'by_source': {},
            'qualified': 0,
            'processed': 0,
        }

        if not self:
            return stats

        # Average quality
        total_quality = sum(e.quality_score for e in self)
        stats['avg_quality'] = total_quality / len(self)

        # Count by field
        for episode in self:
            field_name = episode.field_id.name or 'Unknown'
            stats['by_field'][field_name] = stats['by_field'].get(field_name, 0) + 1

        # Count by source
        for episode in self:
            stats['by_source'][episode.source] = stats['by_source'].get(episode.source, 0) + 1

        # Count qualified and processed
        stats['qualified'] = len(self.filtered(lambda e: e.is_qualified))
        stats['processed'] = len(self.filtered(lambda e: e.processed))

        return stats