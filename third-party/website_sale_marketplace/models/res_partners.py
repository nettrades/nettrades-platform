# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_marketplace_vendor = fields.Boolean(string="Marketplace Vendor")
    is_marketplace_vendor_parent = fields.Boolean("Marketplace Vendor", related='parent_id.is_marketplace_vendor', store=True)
    marketplace_markup = fields.Float(
        string="Marketplace Markup",
        default=0.0,
        help="Markup percentage applied to vendor products. "
             "Cost = Sale Price / (1 + Markup/100). "
             "Example: If markup is 5% and sale price is 100, cost will be 95.24"
    )
