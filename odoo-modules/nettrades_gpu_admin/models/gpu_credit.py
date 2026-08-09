# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_credit.py
# =============================================================================
# PURPOSE:
#   GPU Credit model - tracks internal credits for users.
#   Used when payment_mode = 'internal' (no real money).
#
# KEY FEATURES:
#   - Tracks total, used, and remaining credits per user
#   - Supports reset intervals (monthly, quarterly, yearly)
#   - Department-based allocation
#   - Auto-reset based on interval
#
# UPDATES (2026-08-10):
#   - New model for internal credit accounting
# =============================================================================

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class GpuCredit(models.Model):
    _name = 'gpu.credit'
    _description = 'GPU Credit Allocation (Internal)'
    _rec_name = 'user_id'
    _order = 'remaining_credits DESC'

    # =========================================================================
    # FIELDS
    # =========================================================================

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        help="The user who owns these credits."
    )

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        help="The department that allocated these credits."
    )

    total_credits = fields.Float(
        string='Total Credits',
        default=100.0,
        help="Total credits allocated to this user."
    )

    used_credits = fields.Float(
        string='Used Credits',
        default=0.0,
        help="Credits already consumed."
    )

    remaining_credits = fields.Float(
        string='Remaining Credits',
        compute='_compute_remaining',
        store=True,
        help="Available credits (total - used)."
    )

    reset_interval = fields.Selection(
        [
            ('never', 'Never'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        string='Reset Interval',
        default='monthly',
        help="How often credits should be reset."
    )

    last_reset = fields.Datetime(
        string='Last Reset',
        default=fields.Datetime.now,
        help="When credits were last reset."
    )

    next_reset = fields.Datetime(
        string='Next Reset',
        compute='_compute_next_reset',
        store=True,
        help="When credits will be reset next."
    )

    notes = fields.Text(
        string='Notes',
        help="Additional notes about this credit allocation."
    )

    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================

    @api.depends('total_credits', 'used_credits')
    def _compute_remaining(self):
        """Calculate remaining credits."""
        for record in self:
            record.remaining_credits = record.total_credits - record.used_credits

    @api.depends('last_reset', 'reset_interval')
    def _compute_next_reset(self):
        """Calculate the next reset date."""
        for record in self:
            if record.reset_interval == 'never':
                record.next_reset = False
            elif record.reset_interval == 'monthly':
                record.next_reset = record.last_reset + timedelta(days=30)
            elif record.reset_interval == 'quarterly':
                record.next_reset = record.last_reset + timedelta(days=90)
            elif record.reset_interval == 'yearly':
                record.next_reset = record.last_reset + timedelta(days=365)

    # =========================================================================
    # CONSTRAINTS
    # =========================================================================

    _sql_constraints = [
        ('unique_user', 'unique(user_id)', 'Each user can have only one credit record.'),
        ('non_negative_credits', 'CHECK(remaining_credits >= 0)', 'Credits cannot be negative.'),
    ]

    # =========================================================================
    # METHODS
    # =========================================================================

    def deduct_credits(self, amount):
        """
        Deduct credits for a booking.

        Args:
            amount (float): Number of credits to deduct.

        Raises:
            ValidationError: If insufficient credits.
        """
        self.ensure_one()
        if self.remaining_credits < amount:
            raise ValidationError(_(
                "Insufficient credits. Available: %s, Required: %s"
            ) % (self.remaining_credits, amount))
        self.used_credits += amount
        _logger.info(f"Deducted {amount} credits from user {self.user_id.name}")

    def add_credits(self, amount):
        """
        Add credits to a user.

        Args:
            amount (float): Number of credits to add.
        """
        self.ensure_one()
        self.total_credits += amount
        _logger.info(f"Added {amount} credits to user {self.user_id.name}")

    def reset_credits(self):
        """Reset credits based on reset_interval."""
        self.ensure_one()
        if self.reset_interval == 'never':
            return

        # Reset total credits to default (or keep existing)
        self.total_credits = 100.0  # Could be read from system parameter
        self.used_credits = 0.0
        self.last_reset = fields.Datetime.now()
        _logger.info(f"Reset credits for user {self.user_id.name}")

    @api.model
    def check_and_reset_all(self):
        """Check all credit records and reset if next_reset is due."""
        now = fields.Datetime.now()
        to_reset = self.search([
            ('reset_interval', '!=', 'never'),
            ('next_reset', '<=', now),
        ])
        for record in to_reset:
            record.reset_credits()
        return len(to_reset)

    @api.model
    def get_or_create_for_user(self, user_id):
        """Get or create a credit record for a user."""
        record = self.search([('user_id', '=', user_id)], limit=1)
        if not record:
            record = self.create({
                'user_id': user_id,
                'total_credits': 100.0,
            })
        return record