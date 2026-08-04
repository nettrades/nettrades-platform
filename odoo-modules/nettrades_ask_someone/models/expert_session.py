# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Ask Someone - Expert Session Model
# =============================================================================
# FILE: odoo-modules/nettrades_ask_someone/models/expert_session.py
#
# PURPOSE:
#   This model represents an expert session between a requester and an expert.
#   It tracks the entire lifecycle of an Ask Someone interaction, from request
#   to completion, including rating and reputation updates.
#
# KEY FEATURES:
#   - Tracks session status (pending, accepted, active, completed, disputed)
#   - Manages escrow via Stripe
#   - Updates expert reputation based on ratings
#   - Records episodes for the self-improving loop
#   - Integrates with Forgejo for repository creation
#
# RELATIONSHIPS:
#   - requester_id -> res.partner (the user asking the question)
#   - expert_id -> res.partner (the professional answering)
#   - field_id -> nettrades.field (the professional field)
#
# USAGE:
#   - Created when a user clicks the "Ask Someone" button
#   - Updated through the session lifecycle
#   - Completed when the expert provides an answer
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import secrets
import logging

_logger = logging.getLogger(__name__)


class ExpertSession(models.Model):
    _name = 'expert.session'
    _description = 'Expert Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date DESC'

    # =========================================================================
    # 1. BASIC IDENTIFICATION
    # =========================================================================

    session_id = fields.Char(
        default=lambda self: secrets.token_urlsafe(16),
        required=True,
        readonly=True,
        help="Unique session identifier for external reference."
    )

    # =========================================================================
    # 2. PARTIES
    # =========================================================================

    requester_id = fields.Many2one(
        'res.partner',
        required=True,
        help="The user who is asking the question."
    )

    expert_id = fields.Many2one(
        'res.partner',
        required=True,
        help="The professional who is answering the question."
    )

    field_id = fields.Many2one(
        'nettrades.field',
        required=True,
        help="The professional field this session belongs to."
    )

    # =========================================================================
    # 3. SESSION DATA
    # =========================================================================

    task_summary = fields.Text(
        help="The user's question or task description."
    )

    ai_context_bundle = fields.Json(
        help="JSON blob containing the AI context from the original conversation."
    )

    duration_minutes = fields.Integer(
        default=30,
        help="Estimated duration of the session in minutes."
    )

    rate_per_minute = fields.Float(
        default=1.0,
        help="The rate charged per minute for this session."
    )

    total_charged = fields.Float(
        compute='_compute_total',
        store=True,
        help="Total amount charged for the session."
    )

    escrow_id = fields.Char(
        help="Stripe escrow payment ID."
    )

    # =========================================================================
    # 4. STATUS AND TIMING
    # =========================================================================

    status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('accepted', 'Accepted'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('disputed', 'Disputed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending',
        tracking=True,
        help="Current status of the session."
    )

    started_at = fields.Datetime(
        help="Timestamp when the session became active."
    )

    ended_at = fields.Datetime(
        help="Timestamp when the session was completed."
    )

    # =========================================================================
    # 5. RATINGS
    # =========================================================================

    rating_by_requester = fields.Integer(
        help="Rating given by the requester (1-5 stars)."
    )

    rating_by_expert = fields.Integer(
        help="Rating given by the expert (1-5 stars)."
    )

    # =========================================================================
    # 6. INTEGRATION
    # =========================================================================

    forgejo_repo_url = fields.Char(
        help="URL to the Forgejo repository created for this session."
    )

    # =========================================================================
    # 7. COMPUTED FIELDS
    # =========================================================================

    @api.depends('duration_minutes', 'rate_per_minute')
    def _compute_total(self):
        for rec in self:
            rec.total_charged = rec.duration_minutes * rec.rate_per_minute

    # =========================================================================
    # 8. BUSINESS METHODS
    # =========================================================================

    def action_accept(self):
        """Accept the session and move to active state."""
        self.ensure_one()
        if not self.expert_id.is_online:
            raise UserError(_("Expert is not online."))
        self._create_escrow()
        self.status = 'active'
        self.started_at = fields.Datetime.now()

    def _create_escrow(self):
        """Create a Stripe escrow hold for the session."""
        acquirer = self.env['payment.acquirer'].search(
            [('provider', '=', 'stripe')],
            limit=1
        )
        if not acquirer:
            raise UserError(_("Stripe acquirer not configured."))
        # In full implementation, this would create a payment.transaction
        self.escrow_id = 'escrow_dummy_' + secrets.token_urlsafe(8)

    def action_complete(self):
        """Complete the session and update reputation."""
        self.ensure_one()
        self.status = 'completed'
        self.ended_at = fields.Datetime.now()

        # Update expert reputation based on requester rating
        if self.rating_by_requester:
            rep = self.env['user.field.reputation'].search([
                ('partner_id', '=', self.expert_id.id),
                ('field_id', '=', self.field_id.id)
            ])
            if not rep:
                rep = self.env['user.field.reputation'].create({
                    'partner_id': self.expert_id.id,
                    'field_id': self.field_id.id,
                })
            rep.reputation_points += self.rating_by_requester * 2

    def action_complete_session(self):
        """
        Complete an expert session and collect data for the self-improving loop.

        This method:
        1. Completes the session (same as action_complete)
        2. Records an episode in data.episode for the self-improving loop
        3. Creates a feedback record for the session
        """
        self.ensure_one()

        # First, complete the session using the existing method
        self.action_complete()

        # Retrieve the expert's answer from the mail thread
        # The answer is typically stored as the last message in the thread
        expert_answer = self._get_expert_answer()

        # Record the episode for the self-improving loop
        try:
            self.env['data.episode'].create({
                'source': 'ask_someone',
                'source_id': str(self.id),
                'input_text': self.task_summary or '',
                'output_text': expert_answer or '',
                'quality_score': (self.rating_by_requester or 0) * 2,  # Scale to 1-10
                'field_id': self.field_id.id,
                'partner_id': self.expert_id.id,
                'context_data': {
                    'session_id': self.session_id,
                    'source': 'ask_someone',
                    'expert_id': self.expert_id.id,
                    'requester_id': self.requester_id.id,
                }
            })
            _logger.info("Episode recorded for session %s", self.session_id)
        except Exception as e:
            _logger.warning("Failed to record episode for session %s: %s", self.session_id, e)

        # Create a feedback record
        if self.rating_by_requester:
            try:
                self.env['data.feedback'].create({
                    'episode_id': self.id,
                    'user_id': self.requester_id.id,
                    'feedback_type': 'expert_rating',
                    'value': self.rating_by_requester,
                    'source_id': str(self.id),
                    'source_model': 'expert.session',
                })
                _logger.info("Feedback created for session %s", self.session_id)
            except Exception as e:
                _logger.warning("Failed to create feedback for session %s: %s", self.session_id, e)

    def _get_expert_answer(self):
        """
        Retrieve the expert's answer from the mail thread.

        Returns:
            str: The expert's answer, or an empty string if not found.
        """
        # Search for messages in the thread
        messages = self.env['mail.message'].search([
            ('res_id', '=', self.id),
            ('res_model', '=', 'expert.session'),
            ('message_type', '=', 'comment'),
        ], order='create_date DESC', limit=1)

        if messages:
            return messages[0].body or ''

        # Fallback: use the task_summary if no answer found
        return self.task_summary or ''

    # =========================================================================
    # 9. CONSTRAINTS
    # =========================================================================

    @api.constrains('rating_by_requester', 'rating_by_expert')
    def _check_ratings(self):
        """Ensure ratings are between 1 and 5."""
        for rec in self:
            if rec.rating_by_requester and not (1 <= rec.rating_by_requester <= 5):
                raise ValidationError(_("Requester rating must be between 1 and 5."))
            if rec.rating_by_expert and not (1 <= rec.rating_by_expert <= 5):
                raise ValidationError(_("Expert rating must be between 1 and 5."))