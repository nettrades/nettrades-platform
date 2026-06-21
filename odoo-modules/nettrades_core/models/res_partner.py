# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Extended res.partner model
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/res_partner.py
#
# PURPOSE:
#   This file extends the standard Odoo res.partner with fields for user roles,
#   professional profiles, skills, experience, reviews, geolocation, and the
#   "Good Answer" reputation system.
#
# KEY FEATURES:
#   - user_type field (job_seeker / freelancer / company / partner)
#   - Professional profile fields (summary, skills, resume, hourly rate, etc.)
#   - Geolocation and online presence
#   - One2many relationships for experience and reviews
#   - action_good_answer() – records a Good Answer vote, updates reputation,
#     creates AI feedback records, and awards indirect reputation to
#     professionals whose expert answers contributed to fine-tuning.
#
# IMPORTANT FIX:
#   This file previously used '_' for translations but did NOT import it.
#   This caused a NameError when the file was loaded.
#
#   FIX: Added 'from odoo import _' to import the translation function.
#
# =============================================================================

import json
import logging
from odoo import fields, models, api, _  # <-- FIXED: Added '_' for translations
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    """
    Extended Partner Model – adds NETTRADES specific fields and methods.

    This model extends the standard Odoo res.partner with fields for:
    - User roles and professional profiles
    - Skills, experience, and reviews
    - Geolocation for expert matching
    - Reputation and "Good Answer" voting
    """
    _inherit = 'res.partner'

    # =========================================================================
    # 1. USER ROLE CLASSIFICATION
    # =========================================================================

    user_type = fields.Selection(
        [
            ('job_seeker', 'Job Seeker'),
            ('freelancer', 'Freelancer'),
            ('company', 'Company'),
            ('partner', 'Partner/Researcher'),
        ],
        string="User Type",
        help="Determines which features are available on the portal.",
        default='partner'
    )

    # =========================================================================
    # 2. PROFESSIONAL PROFILE
    # =========================================================================

    professional_summary = fields.Text(
        string="Professional Summary",
        help="A brief summary of your professional background and expertise."
    )

    skill_ids = fields.Many2many(
        'nettrades.skill',
        string="Skills",
        help="The skills you possess in this professional field."
    )

    resume_pdf = fields.Binary(
        string="CV / Resume",
        attachment=True,
        help="Upload your CV or resume as a PDF file."
    )

    hourly_rate = fields.Float(
        string="Hourly Rate",
        help="Rate charged for 'Ask Someone' sessions."
    )

    forgejo_username = fields.Char(
        string="Forgejo Username",
        help="Your username on Forgejo (self-hosted Git)."
    )

    github_username = fields.Char(
        string="GitHub Username",
        help="Your GitHub username for profile import."
    )

    blog_url = fields.Char(
        string="Personal Blog / Website",
        help="Your personal blog or website URL."
    )

    # =========================================================================
    # 3. GEOLOCATION & PRESENCE (for matching)
    # =========================================================================

    latitude = fields.Float(
        string="Latitude",
        help="Latitude coordinate for proximity matching in 'Ask Someone'."
    )

    longitude = fields.Float(
        string="Longitude",
        help="Longitude coordinate for proximity matching in 'Ask Someone'."
    )

    is_online = fields.Boolean(
        string="Online Status",
        default=False,
        help="Whether the user is currently online and available for sessions."
    )

    last_seen = fields.Datetime(
        string="Last Seen",
        help="The last time the user was active on the platform."
    )

    charge_rate = fields.Float(
        string="Charge Rate",
        help="Per-minute rate for expert sessions (Ask Someone)."
    )

    # =========================================================================
    # 4. RELATED RECORDS
    # =========================================================================

    experience_ids = fields.One2many(
        'nettrades.experience',
        'partner_id',
        string="Work Experience",
        help="Your work experience history."
    )

    review_ids = fields.One2many(
        'nettrades.review',
        'reviewed_partner_id',
        string="Reviews",
        help="Reviews received from other users."
    )

    average_rating = fields.Float(
        compute='_compute_average_rating',
        store=True,
        help="Average rating across all received reviews."
    )

    # =========================================================================
    # 5. REPUTATION
    # =========================================================================

    reputation_points = fields.Integer(
        string="Reputation Points",
        default=0,
        help="Total reputation points earned from Good Answer votes."
    )

    can_charge = fields.Boolean(
        string="Can Charge",
        default=False,
        help="Whether this user can charge for 'Ask Someone' sessions."
    )

    # =========================================================================
    # 6. COMPUTED FIELDS
    # =========================================================================

    @api.depends('review_ids.rating')
    def _compute_average_rating(self):
        """
        Compute the average star rating from received reviews.
        """
        for partner in self:
            ratings = partner.review_ids.mapped('rating')
            partner.average_rating = sum(ratings) / len(ratings) if ratings else 0.0

    # =========================================================================
    # 7. GOOD ANSWER VOTING
    # =========================================================================

    def action_good_answer(self, answer_id, answer_model, answerer_id, field_id):
        """
        Record a 'Good Answer' vote.

        This method:
        1. Prevents duplicate votes (one per user per answer)
        2. Awards points based on whether the voter is a qualified professional
        3. If the answer is AI-generated, creates an llm.feedback record
           for the fine-tuning pipeline
        4. If the field has expert_answers_trainable enabled and the answer
           comes from an expert session, captures the expert's answer for
           training (patient question omitted)
        5. Awards indirect reputation points to professionals whose expert
           answers contributed to the fine-tuned model that generated this
           answer

        Args:
            answer_id (int): The ID of the answer being voted on
            answer_model (str): The model of the answer (e.g., 'ai.assistant.message')
            answerer_id (int): The ID of the user who provided the answer
            field_id (int): The ID of the professional field

        Returns:
            dict: Result with status and message
        """
        # Get the current user
        current_user = self.env.user.partner_id

        # Check for duplicate vote
        existing = self.env['good.answer.vote'].search([
            ('user_id', '=', current_user.id),
            ('answer_id', '=', answer_id),
            ('answer_model', '=', answer_model),
        ], limit=1)

        if existing:
            raise UserError(_("You have already voted on this answer."))

        # Get the field
        field = self.env['nettrades.field'].browse(field_id)
        if not field.exists():
            raise UserError(_("Invalid professional field."))

        # Determine if the voter is a qualified professional in this field
        is_qualified = self.env['qualified.professional'].search([
            ('field_id', '=', field_id),
            ('partner_id', '=', current_user.id),
            ('is_active', '=', True),
        ], limit=1)

        # Calculate points
        points = field.qualified_points_per_vote if is_qualified else field.base_points_per_vote

        # Create the vote record
        vote = self.env['good.answer.vote'].create({
            'user_id': current_user.id,
            'answer_id': answer_id,
            'answer_model': answer_model,
            'answerer_id': answerer_id,
            'field_id': field_id,
            'points': points,
            'is_qualified_vote': bool(is_qualified),
            'processed_for_ai': False,
        })

        # Update the answerer's reputation
        answerer = self.browse(answerer_id)
        if answerer.exists():
            answerer.reputation_points += points

            # If the answerer reaches the threshold, enable charging
            if answerer.reputation_points >= field.reputation_threshold_for_charging:
                answerer.can_charge = True

        # If the answer is AI-generated, create feedback for fine-tuning
        if answer_model.startswith('ai.') or answer_model.startswith('llm.'):
            self._create_ai_feedback(vote.id, field_id)

        # If the field has expert_answers_trainable enabled, capture the expert's answer
        if field.expert_answers_trainable:
            self._capture_expert_answer(vote.id, field_id)

        # Award indirect reputation to contributors
        self._award_indirect_reputation(vote.id, field_id)

        return {
            'success': True,
            'message': _("Thank you for your vote!"),
            'points_awarded': points,
        }

    # =========================================================================
    # 8. HELPER METHODS FOR GOOD ANSWER
    # =========================================================================

    def _create_ai_feedback(self, vote_id, field_id):
        """
        Create an AI feedback record from a vote on an AI-generated answer.

        This method extracts the question and answer text from the vote
        and creates an llm.feedback record for the fine-tuning pipeline.

        Args:
            vote_id (int): The ID of the good.answer.vote record
            field_id (int): The ID of the professional field
        """
        vote = self.env['good.answer.vote'].browse(vote_id)

        # Get the answer content from the referenced model
        # This is a placeholder; the actual implementation depends on the
        # answer model (e.g., ai.assistant.message, llm.thread.message)
        input_text = "Question text would be retrieved here"
        output_text = "Answer text would be retrieved here"

        # Create the feedback record
        self.env['llm.feedback'].create({
            'vote_id': vote_id,
            'weight': vote.points,
            'field_id': field_id,
            'input_text': input_text,
            'output_text': output_text,
            'processed': False,
        })

        # Mark the vote as processed for AI
        vote.processed_for_ai = True

    def _capture_expert_answer(self, vote_id, field_id):
        """
        Capture an expert's answer for training (patient question omitted).

        This method is called when the field has expert_answers_trainable
        enabled. It captures the expert's answer from the Ask Someone session
        without storing the requester's question.

        Args:
            vote_id (int): The ID of the good.answer.vote record
            field_id (int): The ID of the professional field
        """
        vote = self.env['good.answer.vote'].browse(vote_id)

        # Check if the answer came from an expert session
        # This is a placeholder; the actual implementation depends on the
        # answer model and whether it's linked to an expert session
        if vote.answer_model == 'expert.session.message':
            # Extract the expert's answer from the session
            # The requester's question is omitted for privacy
            # Create a feedback record with only the expert's answer
            self.env['llm.feedback'].create({
                'vote_id': vote_id,
                'weight': vote.points,
                'field_id': field_id,
                'input_text': "",  # Omit the requester's question
                'output_text': "Expert answer text would be retrieved here",
                'processed': False,
            })

    def _award_indirect_reputation(self, vote_id, field_id):
        """
        Award indirect reputation to professionals whose answers contributed
        to the fine-tuned model that generated this answer.

        This method tracks the indirect reputation earned by professionals
        when AI answers trained on their data receive Good Answer votes.

        Args:
            vote_id (int): The ID of the good.answer.vote record
            field_id (int): The ID of the professional field
        """
        vote = self.env['good.answer.vote'].browse(vote_id)
        field = self.env['nettrades.field'].browse(field_id)

        # This is a placeholder; the actual implementation would:
        # 1. Determine which professionals contributed to the fine-tuned model
        # 2. Award indirect reputation points to each contributor
        # 3. This is handled by the ft_dataset_contribution model

        # For now, we log the indirect reputation
        if field.indirect_reputation_points > 0:
            _logger.info(
                f"Awarding indirect reputation of {field.indirect_reputation_points} "
                f"points for vote {vote_id} in field {field_id}"
            )