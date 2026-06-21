# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import models
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Override to auto-confirm marketplace vendor POs after SO confirmation"""
        result = super().action_confirm()

        for order in self:
            # Auto-confirm marketplace POs after procurement creates them
            order._auto_confirm_marketplace_pos()

        return result

    def _auto_confirm_marketplace_pos(self):
        """Auto-confirm purchase orders for marketplace products (dropship)"""
        self.ensure_one()

        # Get all purchase orders linked to this sale order
        purchase_orders = self.env['purchase.order'].search([
            ('origin', '=', self.name),
            ('state', 'in', ['draft', 'sent', 'to approve'])
        ])

        _logger.info(f'SO {self.name}: Found {len(purchase_orders)} POs to check: {purchase_orders.mapped("name")}')

        for po in purchase_orders:
            # Check if PO contains marketplace vendor products with dropship route
            has_marketplace_dropship = False
            dropship_route = self.env.ref('stock_dropshipping.route_drop_shipping', raise_if_not_found=False)

            for line in po.order_line:
                product_tmpl = line.product_id.product_tmpl_id
                is_marketplace = bool(product_tmpl.marketplace_vendor_id)
                is_dropship = dropship_route and dropship_route in product_tmpl.route_ids

                if is_marketplace and is_dropship:
                    has_marketplace_dropship = True
                    break

            if has_marketplace_dropship:
                try:
                    po.button_confirm()
                except Exception as e:
                    _logger.error(f'SO {self.name}: Failed to auto-confirm PO {po.name}: {str(e)}', exc_info=True)
