# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – LLM Feedback Model
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/llm_feedback.py
#
# PURPOSE:
#   This model stores (question, answer) pairs that are extracted from
#   Good Answer votes on AI-generated responses. These pairs are used
#   as training data for the fine-tuning pipeline.
#
# KEY FEATURES:
#   - Stores input_text (question) and output_text (answer)
#   - Links to the original vote and professional field
#   - Weighted by vote points (higher for qualified professionals)
#   - Processed flag to avoid duplicate data
#   - Cron job to collect feedback and create datasets
#
# FIXES APPLIED:
#   - The `process_feedback` method now groups feedback by field_id
#     and creates a separate ft.dataset per field. Previously, it attempted
#     to create a single dataset without a field_id, causing a NOT NULL
#     constraint violation.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class LLMFeedback(models.Model):
    """
    LLM Feedback – stores (question, answer) pairs for training.

    Each record corresponds to a Good Answer vote on an AI-generated
    answer. The input_text is the user's question, output_text is the
    AI's response. The weight reflects the vote's point value (higher
    for qualified professionals).
    """
    _name = 'llm.feedback'
    _description = 'LLM Feedback for Fine-Tuning'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # -------------------------------------------------------------------------
    # 1. Fields
    # -------------------------------------------------------------------------

    vote_id = fields.Many2one(
        'good.answer.vote',
        string='Vote',
        help="The Good Answer vote that generated this feedback."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        required=True,
        help="The professional field this feedback belongs to."
    )

    input_text = fields.Text(
        string='Question',
        help="The user's original question."
    )

    output_text = fields.Text(
        string='Answer',
        help="The AI-generated answer that received the Good Answer vote."
    )

    weight = fields.Float(
        string='Weight',
        default=1.0,
        help="The weighted point value of the vote (higher for qualified professionals)."
    )

    processed = fields.Boolean(
        string='Processed',
        default=False,
        help="Whether this feedback has been exported to a fine-tuning dataset."
    )

    create_date = fields.Datetime(
        string='Created',
        readonly=True,
        default=fields.Datetime.now,
        help="Timestamp when this feedback record was created."
    )

    # -------------------------------------------------------------------------
    # 2. Helper Methods
    # -------------------------------------------------------------------------

    @api.model
    def _process_feedback_batch(self, field_id, feedback_ids):
        """
        Process a batch of feedback records for a specific field.

        This method creates a dataset for the field (if one doesn't exist)
        and marks the feedback as processed. It updates the dataset's
        record_count to reflect the number of processed feedbacks.

        Args:
            field_id (int): The ID of the professional field.
            feedback_ids (list): List of feedback record IDs to process.
        """
        # Get or create a dataset for this field
        dataset = self.env['ft.dataset'].search([
            ('field_id', '=', field_id),
            ('name', '=', 'good_answer_feedback')
        ], limit=1)

        if not dataset:
            dataset = self.env['ft.dataset'].create({
                'field_id': field_id,
                'name': 'good_answer_feedback',
                'description': 'User votes on AI answers from Good Answer system.',
            })
            _logger.info("Created new dataset for field %s", field_id)

        # Mark feedback as processed
        feedback_records = self.browse(feedback_ids)
        feedback_records.write({'processed': True})

        # Update dataset record count (increment by number of processed records)
        dataset.record_count += len(feedback_ids)

        _logger.info(
            "Processed %d feedback records for field %d. Dataset %s now has %d records.",
            len(feedback_ids),
            field_id,
            dataset.name,
            dataset.record_count
        )

    @api.model
    def process_feedback(self):
        """
        Process all unprocessed feedback records and group them by field.

        This method is called by a scheduled cron job. It:
        1. Fetches all unprocessed feedback records.
        2. Groups them by field_id.
        3. For each field, creates a dataset and marks the feedback as processed.
        4. Increments the dataset's record_count.

        Returns:
            dict: Summary of processed records per field.
        """
        # Fetch all unprocessed feedback records
        feedbacks = self.search([('processed', '=', False)])
        if not feedbacks:
            _logger.info("No unprocessed feedback records found.")
            return {}

        # Group by field_id
        field_groups = {}
        for fb in feedbacks:
            field_id = fb.field_id.id
            if not field_id:
                # Skip records without a field (should not happen)
                _logger.warning("Feedback record %s has no field_id; skipping.", fb.id)
                continue
            field_groups.setdefault(field_id, []).append(fb.id)

        # Process each group
        processed_counts = {}
        for field_id, fb_ids in field_groups.items():
            self._process_feedback_batch(field_id, fb_ids)
            processed_counts[field_id] = len(fb_ids)

        _logger.info("Processed feedback for %d fields: %s", len(processed_counts), processed_counts)
        return processed_counts