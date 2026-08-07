# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - NetTrades Company Model
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_company.py
#
# PURPOSE:
#   This model stores NetTrades-specific company data.
#   It is linked to the Odoo res.partner via a Many2one field.
#
# UPDATES (2026-08):
#   - Created from former res_partner company extensions.
# =============================================================================

from odoo import fields, models, api


class NettradesCompany(models.Model):
    _name = 'nettrades.company'
    _description = 'NetTrades Company'
    _rec_name = 'partner_id'

    partner_id = fields.Many2one(
        'res.partner',
        string='Company',
        required=True,
        ondelete='cascade',
        help="Link to the Odoo partner record"
    )

    is_active = fields.Boolean(default=True)
    industry = fields.Char()
    website = fields.Char()
    description = fields.Text()

    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('partner_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.partner_id.name if rec.partner_id else ''