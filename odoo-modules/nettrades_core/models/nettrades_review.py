# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - Review Model
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_review.py
#
# PURPOSE:
#   This model stores user reviews (ratings and comments) left by one user
#   about another user's work on a project.
#
# RELATIONSHIPS:
#   - reviewer_id -> res.partner (the person who writes the review)
#   - reviewed_partner_id -> res.partner (the person being reviewed)
#   - project_id -> nettrades.project (optional link to a NETTRADES project)
#
# USAGE:
#   This model is referenced by res.partner via a One2many field:
#       review_ids = fields.One2many('nettrades.review', 'reviewed_partner_id')
#
#   It is used in the post-project completion flow.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class NettradesReview(models.Model):
    """
    User Review - ratings and comments left by one user about another.

    Each review is linked to a reviewer (the person giving the review),
    a reviewee (the person receiving the review), and optionally a project.
    Inherits mail.thread so the chatter widget (message_ids, activity_ids,
    message_follower_ids) works in the form view.
    """
    _name = 'nettrades.review'
    _description = 'User Review'
    _order = 'create_date DESC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # =========================================================================
    # 1. BASIC FIELDS
    # =========================================================================

    reviewer_id = fields.Many2one(
        'res.partner',
        string='Reviewer',
        required=True,
        help="The user who wrote this review (must be a valid partner)."
    )

    reviewed_partner_id = fields.Many2one(
        'res.partner',
        string='Reviewed Partner',
        required=True,
        help="The user who received this review."
    )

    project_id = fields.Many2one(
        'nettrades.project',
        string='Project',
        ondelete='set null',
        help="The project for which this review was given (optional)."
    )

    rating = fields.Integer(
        string='Rating',
        required=True,
        default=5,
        help="Rating from 1 (poor) to 5 (excellent)."
    )

    comment = fields.Text(
        string='Comment',
        help="A written comment or feedback about the reviewed user."
    )

    # Note: create_date is provided automatically by Odoo. Do not redeclare it.

    # =========================================================================
    # 2. CONSTRAINTS
    # =========================================================================

    @api.constrains('rating')
    def _check_rating(self):
        """Ensure that rating is between 1 and 5."""
        for record in self:
            if not (1 <= record.rating <= 5):
                raise ValidationError(_("Rating must be between 1 and 5."))

    @api.constrains('reviewer_id', 'reviewed_partner_id')
    def _check_not_self(self):
        """Prevent a user from reviewing themselves."""
        for record in self:
            if record.reviewer_id.id == record.reviewed_partner_id.id:
                raise ValidationError(_("You cannot review yourself."))

    # =========================================================================
    # 3. HELPERS
    # =========================================================================

    @api.model
    def create_review(self, reviewer_id, reviewed_id, rating, comment=None, project_id=None):
        """
        Helper method to create a new review with validation.

        Args:
            reviewer_id (int): ID of the partner giving the review.
            reviewed_id (int): ID of the partner receiving the review.
            rating (int): Rating (1-5).
            comment (str): Optional comment.
            project_id (int): Optional project ID (nettrades.project).

        Returns:
            NettradesReview: The created review record.
        """
        return self.create({
            'reviewer_id': reviewer_id,
            'reviewed_partner_id': reviewed_id,
            'rating': rating,
            'comment': comment,
            'project_id': project_id,
        })