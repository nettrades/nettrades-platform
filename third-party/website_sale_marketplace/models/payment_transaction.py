# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    # Payment transaction model kept for future marketplace-related customizations
    # Note: Marketplace PO auto-confirmation is handled in sale.order.action_confirm()
