# -*- coding: utf-8 -*-
# =============================================================================
# SECTION H – Token economic configuration per company.
# =============================================================================

# -----------------------------------------------------------------------------
# IMPORTS – Each import MUST be on its own line for valid Python syntax.
# -----------------------------------------------------------------------------
from odoo import fields, models


class GPUTokenEconomics(models.Model):
    _name = 'gpu.token.economics'
    _description = 'GPU Token Economics Configuration'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    earn_rate_per_1k_tokens = fields.Float(
        string='Earn Rate per 1K Tokens (USD)',
        default=0.015
    )

    minimum_payout_amount = fields.Float(
        string='Minimum Payout (USD)',
        default=10.00
    )

    payout_schedule = fields.Selection(
        [
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
        ],
        string='Payout Schedule',
        default='monthly'
    )

    platform_markup_pct = fields.Float(
        string='Platform Markup (%)',
        default=5.0
    )

    free_tokens_per_user = fields.Integer(
        string='Free Monthly Tokens',
        default=100000
    )

    token_cost_per_1k_chars = fields.Float(
        string='Token Cost per 1K Characters',
        default=1.0
    )