# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ProductCategory(models.Model):
    _inherit = 'product.category'

    marketplace_markup = fields.Float(
        string="Marketplace Markup",
        default=0.0,
        help="Markup percentage applied to vendor products in this category. "
             "Cost = Sale Price / (1 + Markup/100). "
             "Example: If markup is 5% and sale price is 100, cost will be 95.24. "
             "If set, this overrides the vendor's default markup."
    )