# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    is_marketplace_vendor = fields.Boolean(
        compute='_compute_is_marketplace_vendor', store=True, string="Marketplace Vendor")

    @api.depends('partner_id.is_marketplace_vendor', 'partner_id.parent_id.is_marketplace_vendor')
    def _compute_is_marketplace_vendor(self):
        for user in self:
            user.is_marketplace_vendor = user.partner_id.is_marketplace_vendor or \
                                         user.partner_id.parent_id.is_marketplace_vendor or False
