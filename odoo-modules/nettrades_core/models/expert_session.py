# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - Expert Session (Ask Someone Request)
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/expert_session.py
#
# PURPOSE:
#   This model tracks each "Ask Someone" request, from initial question
#   through expert assignment, answer, review, and closure.
#
# KEY FEATURES:
#   - Two-track system: regulated (medical/legal) vs community
#   - Review workflow for regulated answers
#   - Idempotency protection for duplicate requests
#   - Full audit trail for compliance
#   - Data classification for GDPR/HIPAA
#
# UPDATES (2026-08):
#   - Added track field (regulated/community)
#   - Added review workflow fields
#   - Added idempotency_key for duplicate protection
#   - Added audit_log for compliance
#   - Added data_classification for GDPR/HIPAA
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class ExpertSession(models.Model):
    _name = 'expert.session'
    _description = 'Expert Session (Ask Someone Request)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'task_summary'
    _order = 'created_at DESC'

    # =========================================================================
    # 1. Core Fields
    # =========================================================================

    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        help="The user who asked the question"
    )

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        required=True,
        help="The professional field of the question"
    )

    task_summary = fields.Text(
        string='Question/Task Summary',
        required=True,
        help="The user's question or task description"
    )

    urgency = fields.Selection([
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ], string='Urgency', default='normal', required=True)

    # =========================================================================
    # 2. Track System (Regulated vs Community)
    # =========================================================================

    track = fields.Selection([
        ('regulated', 'Regulated Professional'),
        ('community', 'Community'),
    ], string='Track', default='community', required=True, tracking=True)

    # =========================================================================
    # 3. Expert Assignment
    # =========================================================================

    expert_id = fields.Many2one(
        'qualified_professional',
        string='Assigned Expert',
        tracking=True,
        help="The expert assigned to answer this question"
    )

    assigned_at = fields.Datetime(
        string='Assigned At',
        tracking=True,
        help="When the expert was assigned"
    )

    assigned_by = fields.Many2one(
        'res.users',
        string='Assigned By',
        help="Who assigned the expert"
    )

    # =========================================================================
    # 4. Status Workflow
    # =========================================================================

    status = fields.Selection([
        ('pending', 'Pending'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('answered', 'Answered'),
        ('reviewed', 'Reviewed'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True, tracking=True)

    # =========================================================================
    # 5. Answer & Review (Critical for Regulated)
    # =========================================================================

    answer = fields.Html(
        string='Expert Answer',
        help="The expert's answer"
    )

    answered_at = fields.Datetime(
        string='Answered At',
        help="When the expert provided the answer"
    )

    reviewed_by = fields.Many2one(
        'res.users',
        string='Reviewed By',
        help="Who reviewed the answer"
    )

    reviewed_at = fields.Datetime(
        string='Reviewed At',
        help="When the answer was reviewed"
    )

    review_notes = fields.Text(
        string='Review Notes',
        help="Notes from the review"
    )

    is_approved = fields.Boolean(
        string='Approved',
        default=False,
        help="Whether the answer has been approved"
    )

    # =========================================================================
    # 6. Feedback & Rating
    # =========================================================================

    rating = fields.Integer(
        string='Rating',
        help="User rating (1-5)"
    )

    feedback = fields.Text(
        string='Feedback',
        help="User feedback on the answer"
    )

    is_good_answer = fields.Boolean(
        string='Good Answer',
        default=False,
        help="Whether the user marked this as a Good Answer"
    )

    # =========================================================================
    # 7. Compliance & Data Classification
    # =========================================================================

    data_classification = fields.Selection([
        ('public', 'Public'),
        ('internal', 'Internal'),
        ('confidential', 'Confidential'),
        ('restricted', 'Restricted'),
    ], string='Data Classification', default='confidential', required=True)

    idempotency_key = fields.Char(
        string='Idempotency Key',
        index=True,
        help="Unique key to prevent duplicate requests"
    )

    audit_log = fields.Json(
        string='Audit Log',
        readonly=True,
        help="Full audit trail of all changes to this session"
    )

    # =========================================================================
    # 8. Consent
    # =========================================================================

    consent_given = fields.Boolean(
        string='Consent Given',
        default=False,
        help="Whether the requester has given consent"
    )

    consent_given_at = fields.Datetime(
        string='Consent Given At',
        help="When consent was given"
    )

    # =========================================================================
    # 9. Timestamps
    # =========================================================================

    created_at = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True
    )

    updated_at = fields.Datetime(
        string='Updated At',
        default=fields.Datetime.now,
        readonly=True
    )

    closed_at = fields.Datetime(
        string='Closed At',
        help="When the session was closed"
    )

    # =========================================================================
    # 10. Constraints
    # =========================================================================

    _sql_constraints = [
        ('unique_idempotency_key', 'unique(idempotency_key)',
         'Idempotency key must be unique'),
    ]

    # =========================================================================
    # 11. Helper Methods
    # =========================================================================

    def can_be_answered(self) -> bool:
        """Check if the session can be answered."""
        return self.status in ['assigned', 'in_progress']

    def can_be_reviewed(self) -> bool:
        """Check if the session can be reviewed."""
        return self.status == 'answered' and self.track == 'regulated'

    def assign_expert(self, expert_id: int, assigned_by: int):
        """Assign an expert to this session."""
        self.expert_id = expert_id
        self.assigned_at = datetime.now()
        self.assigned_by = assigned_by
        self.status = 'assigned'
        self.log_audit('assign_expert', assigned_by, {'expert_id': expert_id})

    def mark_answered(self, answer: str):
        """Mark the session as answered."""
        self.answer = answer
        self.answered_at = datetime.now()
        self.status = 'answered'
        self.log_audit('mark_answered', self.assigned_by.id if self.assigned_by else None,
                       {'answer_length': len(answer)})

    def review_answer(self, reviewed_by: int, is_approved: bool, notes: str = ''):
        """Review the answer (required for regulated track)."""
        self.reviewed_by = reviewed_by
        self.reviewed_at = datetime.now()
        self.is_approved = is_approved
        self.review_notes = notes
        self.status = 'reviewed' if is_approved else 'answered'  # Allow re-answer
        self.log_audit('review_answer', reviewed_by, {
            'is_approved': is_approved,
            'notes': notes[:100] if notes else '',
        })

    def close(self):
        """Close the session."""
        self.status = 'closed'
        self.closed_at = datetime.now()

    def log_audit(self, action: str, user_id: int, details: dict):
        """Log an audit entry for this session."""
        if not self.audit_log:
            self.audit_log = []
        self.audit_log.append({
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user_id': user_id,
            'details': details,
        })

    def get_audit_trail(self) -> list:
        """Get the full audit trail."""
        return self.audit_log or []