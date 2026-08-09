# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - Qualified Professional (Expert) Model
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/qualified_professional.py
#
# PURPOSE:
#   This model stores verified experts who can answer questions in the
#   "Ask Someone" system. It supports both regulated (medical, legal,
#   financial) and community (non-regulated) tracks.
#
# KEY FEATURES:
#   - Verification status with licence/registration tracking
#   - Audit trail for compliance (GDPR, HIPAA)
#   - Community ranking for non-regulated experts
#   - Consent and data processing agreement tracking
#   - Expertise areas and availability management
#
# UPDATES (2026-08):
#   - Added verification_status, licence_number, registration_body
#   - Added audit_log for compliance
#   - Added community_rank and good_answer_count for gamification
#   - Added consent and data processing agreement fields
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import date, datetime
import logging

_logger = logging.getLogger(__name__)


class QualifiedProfessional(models.Model):
    _name = 'qualified_professional'
    _description = 'Qualified Professional (Expert)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'partner_id'
    _order = 'community_rank DESC, reputation_score DESC'

    # =========================================================================
    # 1. Core Fields
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        help="The Odoo partner record for this expert"
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        required=True,
        help="The primary professional field of expertise"
    )

    expertise_areas = fields.Many2many(
        'nettrades.field',
        string='Expertise Areas',
        help="Additional areas of expertise"
    )

    # =========================================================================
    # 2. Verification & Licensing (Critical for Regulated Use)
    # =========================================================================

    verification_status = fields.Selection([
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('expired', 'Verification Expired'),
        ('revoked', 'Revoked'),
    ], string='Verification Status', default='pending', tracking=True, required=True)

    licence_number = fields.Char(
        string='Licence/Registration Number',
        tracking=True,
        help="Professional licence or registration number (e.g., GMC number)"
    )

    registration_body = fields.Char(
        string='Registration Body',
        tracking=True,
        help="The body that issued the licence (e.g., GMC, Law Society)"
    )

    licence_expiry = fields.Date(
        string='Licence Expiry Date',
        tracking=True,
        help="Date when the licence expires. Experts with expired licences cannot answer regulated questions."
    )

    verified_by = fields.Many2one(
        'res.users',
        string='Verified By',
        tracking=True,
        help="The user who verified this expert"
    )

    verified_at = fields.Datetime(
        string='Verified At',
        tracking=True,
        help="When this expert was verified"
    )

    verification_notes = fields.Text(
        string='Verification Notes',
        help="Notes about the verification process"
    )

    credentials_url = fields.Char(
        string='Credentials URL',
        help="URL to credentials or CV"
    )

    cv_attachment = fields.Binary(
        string='CV/Resume Attachment',
        help="CV or resume file"
    )

    cv_filename = fields.Char(
        string='CV Filename',
        help="Filename of the CV attachment"
    )

    # =========================================================================
    # 3. Insurance & Compliance
    # =========================================================================

    insurance_provider = fields.Char(
        string='Insurance Provider',
        help="Professional indemnity insurance provider"
    )

    insurance_expiry = fields.Date(
        string='Insurance Expiry',
        help="Date when insurance expires"
    )

    data_processing_agreement = fields.Binary(
        string='DPA Attachment',
        help="Data Processing Agreement attachment"
    )

    dpa_filename = fields.Char(
        string='DPA Filename',
        help="Filename of the DPA attachment"
    )

    # =========================================================================
    # 4. Community (Non-Regulated) Track
    # =========================================================================

    community_rank = fields.Integer(
        string='Community Rank',
        default=0,
        help="Rank in the community based on Good Answer votes and contributions"
    )

    good_answer_count = fields.Integer(
        string='Good Answer Count',
        default=0,
        help="Number of Good Answer votes received"
    )

    total_answers_given = fields.Integer(
        string='Total Answers Given',
        default=0,
        help="Total number of answers provided"
    )

    answer_acceptance_rate = fields.Float(
        string='Answer Acceptance Rate',
        compute='_compute_acceptance_rate',
        store=True,
        help="Percentage of answers that were marked as Good Answer"
    )

    reputation_score = fields.Float(
        string='Reputation Score',
        default=0.0,
        help="Overall reputation score combining community rank and verification status"
    )

    is_available = fields.Boolean(
        string='Available',
        default=True,
        help="Whether the expert is currently available to answer questions"
    )

    # =========================================================================
    # 5. Consent & GDPR
    # =========================================================================

    consent_given = fields.Boolean(
        string='Consent Given',
        default=False,
        help="Whether the expert has given consent for data processing"
    )

    consent_given_at = fields.Datetime(
        string='Consent Given At',
        help="When consent was given"
    )

    consent_version = fields.Char(
        string='Consent Version',
        help="Version of the consent form"
    )

    # =========================================================================
    # 6. Audit Trail
    # =========================================================================

    last_reviewed_at = fields.Datetime(
        string='Last Reviewed',
        help="When this expert was last reviewed"
    )

    review_notes = fields.Text(
        string='Review Notes',
        help="Notes from the last review"
    )

    audit_log = fields.Json(
        string='Audit Log',
        readonly=True,
        help="Full audit trail of all changes to this record"
    )

    # =========================================================================
    # 7. Computed Fields
    # =========================================================================

    @api.depends('good_answer_count', 'total_answers_given')
    def _compute_acceptance_rate(self):
        for expert in self:
            if expert.total_answers_given > 0:
                expert.answer_acceptance_rate = (
                    expert.good_answer_count / expert.total_answers_given
                ) * 100
            else:
                expert.answer_acceptance_rate = 0.0

    # =========================================================================
    # 8. Constraints
    # =========================================================================

    _sql_constraints = [
        ('unique_licence', 'unique(licence_number, registration_body)',
         'Licence number must be unique per registration body'),
    ]

    # =========================================================================
    # 9. Helper Methods
    # =========================================================================

    def is_verified_for_regulated(self) -> bool:
        """Check if the expert is verified for regulated questions."""
        if self.verification_status != 'verified':
            return False
        if self.licence_expiry and self.licence_expiry < date.today():
            return False
        if not self.consent_given:
            return False
        return True

    def can_answer_category(self, category: str) -> bool:
        """Check if the expert can answer questions in a given category."""
        if category in ['medical', 'legal', 'financial']:
            return self.is_verified_for_regulated()
        return self.is_available

    def add_good_answer(self):
        """Increment the Good Answer count."""
        self.good_answer_count += 1
        self.total_answers_given += 1
        self.community_rank += 10  # +10 rank per Good Answer
        self._update_reputation()

    def add_answer_attempt(self):
        """Increment the total answers given count."""
        self.total_answers_given += 1
        self._update_reputation()

    def _update_reputation(self):
        """Update the reputation score based on community rank and verification."""
        base_score = self.community_rank / 10.0  # 1 point per 10 rank
        if self.verification_status == 'verified':
            base_score += 50.0  # Bonus for verified experts
        self.reputation_score = base_score

    def log_audit(self, action: str, user_id: int, details: dict):
        """Log an audit entry for this expert."""
        if not self.audit_log:
            self.audit_log = []
        self.audit_log.append({
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user_id': user_id,
            'details': details,
        })