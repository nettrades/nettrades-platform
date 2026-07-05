# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Res Partner Extension
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/res_partner.py
#
# PURPOSE:
#   This file extends the res.partner model with nettrades-specific fields
#   for professional profiles, reputation, worker agents, and autonomous
#   administration.
#
# KEY FEATURES:
#   - Professional fields (skills, fields, experience)
#   - Karma and reputation system
#   - Worker agent configuration
#   - Autonomous administration flags
#   - GPU and token management
#   - Expert marketplace integration
#   - Social media / contact fields
#   - Resume and rating fields
#
# =============================================================================

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging
import json

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):

#    Extended res.partner model for nettrades platform.

    _inherit = 'res.partner'
    _description = 'Partner with Nettrades extensions'

    # -------------------------------------------------------------------------
    # 1. Professional Profile Fields
    # -------------------------------------------------------------------------

    field_ids = fields.Many2many(
        'nettrades.field',
        string='Professional Fields',
        help="The professional fields this partner specializes in."
    )

    skill_ids = fields.Many2many(
        'nettrades.skill',
        string='Skills',
        help="Technical and soft skills."
    )

    experience_ids = fields.One2many(
        'nettrades.experience',
        'partner_id',
        string='Experience',
        help="Work experience entries."
    )

    review_ids = fields.One2many(
        'nettrades.review',
        'reviewed_partner_id',
        string='Reviews',
        help="Reviews from other users."
    )

    # -------------------------------------------------------------------------
    # 2. Karma and Reputation
    # -------------------------------------------------------------------------

    karma = fields.Integer(
        string='Karma',
        default=100,
        help="Reputation points earned from contributions."
    )

    reputation_score = fields.Float(
        string='Reputation Score',
        compute='_compute_reputation',
        store=True,
        help="Calculated reputation score based on karma and reviews."
    )

    @api.depends('karma', 'review_ids.rating')
    def _compute_reputation(self):
# Calculate reputation score.
        for partner in self:
            avg_review = sum(
                review.rating for review in partner.review_ids
            ) / max(len(partner.review_ids), 1)
            partner.reputation_score = (partner.karma / 100.0) * 0.7 + (avg_review / 5.0) * 0.3

    # -------------------------------------------------------------------------
    # 3. Autonomous Administration
    # -------------------------------------------------------------------------

    is_qualified = fields.Boolean(
        string='Is Qualified',
        default=False,
        help="Whether this partner meets the qualification criteria."
    )

    qualification_reason = fields.Text(
        string='Qualification Reason',
        help="Reason for qualification or disqualification."
    )

    gpu_reputation = fields.Float(
        string='GPU Reputation',
        default=0.0,
        help="Reputation based on GPU contributions."
    )

    # -------------------------------------------------------------------------
    # 4. Worker Agent Configuration
    # -------------------------------------------------------------------------

    worker_agent = fields.Char(
        string='Worker Agent',
        help="The worker agent identifier for autonomous operations."
    )

    worker_context = fields.Json(
        string='Worker Context',
        help="JSON context for the worker agent."
    )

    worker_started = fields.Boolean(
        string='Worker Started',
        default=False,
        help="Whether the worker agent is currently running."
    )

    # -------------------------------------------------------------------------
    # 5. GPU and Token Management
    # -------------------------------------------------------------------------

    token_balance = fields.Float(
        string='Token Balance',
        default=0.0,
        help="Current token balance for GPU usage."
    )

    # -------------------------------------------------------------------------
    # 6. Expert Marketplace
    # -------------------------------------------------------------------------

    is_expert = fields.Boolean(
        string='Is Expert',
        default=False,
        help="Whether this partner is a verified expert."
    )

    expert_rate = fields.Float(
        string='Expert Rate (per hour)',
        help="Hourly rate for expert consultations."
    )

    expert_bio = fields.Text(
        string='Expert Bio',
        help="Detailed bio for expert profile."
    )

    # -------------------------------------------------------------------------
    # 7. Smart Matching and Agentic AI
    # -------------------------------------------------------------------------

    is_lead = fields.Boolean(
        string='Is Lead',
        default=False,
        help="Whether this partner is a lead generated by the AI."
    )

    # -------------------------------------------------------------------------
    # 8. Agent Control Methods
    # -------------------------------------------------------------------------

    def action_start_worker_agent(self):

#        Start the worker agent for this partner.

#        This method initializes a LangGraph agent with the partner's
#        context and starts the autonomous worker loop.

        self.ensure_one()

        if self.worker_started:
            raise ValidationError(_("Worker agent already started."))

        # Create worker context if not exists
        if not self.worker_context:
            self.worker_context = {
                'partner_id': self.id,
                'karma': self.karma,
                'reputation': self.reputation_score,
                'fields': [f.id for f in self.field_ids],
                'skills': [s.id for s in self.skill_ids],
                'token_balance': self.token_balance
            }

        # Call the LangGraph supervisor to start the worker
        try:
            # In production: call the LangGraph supervisor
            # result = self._call_langgraph_supervisor('start_worker', {
            #     'partner_id': self.id,
            #     'context': self.worker_context
            # })

            self.worker_started = True
            _logger.info(f"Worker agent started for partner {self.id}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Worker Agent Started'),
                    'message': _('The worker agent is now running for this partner.'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(f"Failed to start worker agent: {e}")
            raise ValidationError(_("Failed to start worker agent: {}").format(str(e)))

    def action_stop_worker_agent(self):

#        Stop the worker agent for this partner.

        self.ensure_one()

        if not self.worker_started:
            raise ValidationError(_("Worker agent is not running."))

        # Call the LangGraph supervisor to stop the worker
        try:
            # In production: call the LangGraph supervisor
            # result = self._call_langgraph_supervisor('stop_worker', {
            #     'partner_id': self.id
            # })

            self.worker_started = False
            _logger.info(f"Worker agent stopped for partner {self.id}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Worker Agent Stopped'),
                    'message': _('The worker agent has been stopped.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error(f"Failed to stop worker agent: {e}")
            raise ValidationError(_("Failed to stop worker agent: {}").format(str(e)))

    def action_update_worker_context(self, context_updates):
        """
        Update the worker context with new data.
        """
        self.ensure_one()

        if not self.worker_context:
            self.worker_context = {}

        # Update context
        if isinstance(context_updates, dict):
            self.worker_context.update(context_updates)
        elif isinstance(context_updates, str):
            try:
                updates = json.loads(context_updates)
                self.worker_context.update(updates)
            except json.JSONDecodeError:
                raise ValidationError(_("Invalid JSON format for context updates."))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Worker Context Updated'),
                'message': _('The worker context has been updated.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # -------------------------------------------------------------------------
    # 9. Qualification Methods
    # -------------------------------------------------------------------------

    def action_check_qualification(self):

#        Check if the partner meets the qualification criteria.

#        Qualification criteria:
#        - Minimum karma: 50
#        - Minimum reputation score: 2.0
#        - At least one skill
#        - At least one field

        self.ensure_one()

        criteria = []

        if self.karma < 50:
            criteria.append("Karma score must be at least 50 (currently {})".format(self.karma))
        if self.reputation_score < 2.0:
            criteria.append("Reputation score must be at least 2.0 (currently {:.2f})".format(
                self.reputation_score
            ))
        if not self.skill_ids:
            criteria.append("At least one skill is required")
        if not self.field_ids:
            criteria.append("At least one professional field is required")

        if criteria:
            self.is_qualified = False
            self.qualification_reason = "; ".join(criteria)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Not Qualified'),
                    'message': _('The partner does not meet the qualification criteria:\n{}').format(
                        '\n'.join(criteria)
                    ),
                    'type': 'danger',
                    'sticky': True,
                }
            }

        self.is_qualified = True
        self.qualification_reason = "All qualification criteria met."

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Qualified'),
                'message': _('The partner meets all qualification criteria.'),
                'type': 'success',
                'sticky': False,
            }
        }

    # -------------------------------------------------------------------------
    # 10. Karma Methods
    # -------------------------------------------------------------------------

    def add_karma(self, amount, reason):

#        Add karma points to the partner.

#        Args:
#            amount (int): The amount of karma to add (can be negative).
#            reason (str): The reason for the karma change.

        self.ensure_one()

        if not isinstance(amount, int):
            raise ValidationError(_("Karma amount must be an integer."))

        old_karma = self.karma
        self.karma += amount

        # Prevent negative karma
        if self.karma < 0:
            self.karma = 0

        _logger.info(f"Partner {self.id} karma changed from {old_karma} to {self.karma} ({reason})")

        return self.karma

    # =========================================================================
    # 11. USER TYPE CLASSIFICATION
    # =========================================================================

    user_type = fields.Selection(
        [
            ('company', 'Company'),
            ('freelancer', 'Freelancer'),
            ('employee', 'Employee'),
            ('student', 'Student'),
            ('other', 'Other'),
        ],
        string="User Type",
        default='company',
        help="Classifies the partner type for platform features"
    )

    # =========================================================================
    # 12. FREELANCER-SPECIFIC FIELDS
    # =========================================================================

    professional_summary = fields.Text(
        string="Professional Summary",
        help="A brief summary of the freelancer's professional background and expertise"
    )

    hourly_rate = fields.Float(
        string="Hourly Rate",
        digits=(16, 2),
        help="The freelancer's standard hourly rate in the default currency"
    )

    resume_pdf = fields.Binary(
        string="Resume PDF",
        help="Upload the resume as a PDF file."
    )

    # =========================================================================
    # 13. COMPANY REGISTRY AND DUPLICATE DETECTION
    # =========================================================================

    company_registry = fields.Char(
        string="Company Registry Number",
        help="Official company registration number for verification"
    )

    # Computed fields for duplicate detection (used in the view)
    same_vat_partner_id = fields.Many2one(
        'res.partner',
        string="Same VAT Partner",
        compute='_compute_same_vat_partner',
        help="Partner with the same VAT number (computed)"
    )

    same_company_registry_partner_id = fields.Many2one(
        'res.partner',
        string="Same Registry Partner",
        compute='_compute_same_registry_partner',
        help="Partner with the same company registry number (computed)"
    )

    vat_label = fields.Char(
        string="VAT Label",
        compute='_compute_vat_label',
        help="Display label for VAT field"
    )

    company_registry_label = fields.Char(
        string="Company Registry Label",
        compute='_compute_company_registry_label',
        help="Display label for company registry field."
    )

    # =========================================================================
    # 14. SOCIAL / CONTACT FIELDS
    # =========================================================================

    forgejo_username = fields.Char(
        string="Forgejo Username",
        help="Username on the Forgejo Git platform."
    )

    github_username = fields.Char(
        string="GitHub Username",
        help="Username on GitHub."
    )

    linkedin_username = fields.Char(
        string="LinkedIn Username",
        help="Username on LinkedIn."
    )

    twitter_username = fields.Char(
        string="Twitter/X Username",
        help="Username on Twitter/X."
    )

    blog_url = fields.Char(
        string="Blog URL",
        help="URL of the user's blog or personal website."
    )

    # =========================================================================
    # 15. AVERAGE RATING (Computed)
    # =========================================================================

    average_rating = fields.Float(
        string="Average Rating",
        compute='_compute_average_rating',
        help="Average rating from reviews."
    )

    # =========================================================================
    # 16. COMPUTATION METHODS
    # =========================================================================

    @api.depends('vat')
    def _compute_same_vat_partner(self):
# Find partners with the same VAT number.
        for partner in self:
            if not partner.vat:
                partner.same_vat_partner_id = False
                continue
            same = self.search([
                ('vat', '=', partner.vat),
                ('id', '!=', partner.id),
                ('vat', '!=', False)
            ], limit=1)
            partner.same_vat_partner_id = same.id if same else False

    @api.depends('company_registry')
    def _compute_same_registry_partner(self):
# Find partners with the same company registry number.
        for partner in self:
            if not partner.company_registry:
                partner.same_company_registry_partner_id = False
                continue
            same = self.search([
                ('company_registry', '=', partner.company_registry),
                ('id', '!=', partner.id),
                ('company_registry', '!=', False)
            ], limit=1)
            partner.same_company_registry_partner_id = same.id if same else False

    def _compute_vat_label(self):
# Get the display label for VAT field.
        for partner in self:
            partner.vat_label = "VAT"

    def _compute_company_registry_label(self):
# Get the display label for company registry field.
        for partner in self:
            partner.company_registry_label = partner.company_registry or ''

    def _compute_average_rating(self):
# Compute average rating from reviews.
        for partner in self:
            ratings = partner.review_ids.mapped('rating')
            partner.average_rating = sum(ratings) / len(ratings) if ratings else 0.0