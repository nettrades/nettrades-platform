# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.depends('line_ids.amount_residual')
    def _compute_payment_state(self):
        """Override to auto-confirm marketplace vendor POs when invoice is paid"""
        # Store previous payment states before compute
        previous_states = {move.id: move.payment_state for move in self if move.id}

        # Call parent to compute payment state
        result = super()._compute_payment_state()

        # Check for newly paid invoices
        for move in self:
            if (move.id and
                move.move_type == 'out_invoice' and
                move.state == 'posted' and
                previous_states.get(move.id) != 'paid' and
                move.payment_state == 'paid'):

                # Trigger auto-confirm in a separate transaction to avoid compute issues
                _logger.info(f'Invoice {move.name} paid - triggering marketplace PO auto-confirm')
                move.sudo()._auto_confirm_marketplace_purchase_orders()

        return result

    def _auto_confirm_marketplace_purchase_orders(self):
        """Auto-confirm purchase orders for marketplace vendor products"""
        self.ensure_one()

        # Get related sale order from invoice lines
        sale_orders = self.line_ids.sale_line_ids.order_id
        _logger.info(f'Checking sale orders for marketplace POs: {sale_orders.mapped("name")}')

        for sale_order in sale_orders:
            # Check if all invoices for this sale order are paid
            all_invoices = sale_order.invoice_ids.filtered(
                lambda inv: inv.move_type == 'out_invoice' and inv.state == 'posted'
            )

            if not all_invoices or not all(inv.payment_state == 'paid' for inv in all_invoices):
                continue

            # Get all purchase orders linked to this sale order
            purchase_orders = self.env['purchase.order'].search([
                ('origin', '=', sale_order.name),
                ('state', 'in', ['draft', 'sent', 'to approve'])
            ])
            _logger.info(f'Found {len(purchase_orders)} POs for SO {sale_order.name}: {purchase_orders.mapped("name")}')

            for po in purchase_orders:
                # Check if PO contains marketplace vendor products
                has_marketplace_products = any(
                    line.product_id.product_tmpl_id.marketplace_vendor_id
                    for line in po.order_line
                )
                _logger.info(f'PO {po.name} has marketplace products: {has_marketplace_products}')
                if has_marketplace_products:
                    try:
                        _logger.info(f'Confirming marketplace PO {po.name}')
                        po.button_confirm()
                        _logger.info(f'Successfully confirmed PO {po.name}')
                    except Exception as e:
                        # Log error but don't block payment
                        self.env['ir.logging'].sudo().create({
                            'name': 'Marketplace PO Auto-Confirm',
                            'type': 'server',
                            'level': 'error',
                            'message': f'Failed to auto-confirm PO {po.name}: {str(e)}',
                            'path': 'website_sale_marketplace',
                            'func': '_auto_confirm_marketplace_purchase_orders',
                            'line': '0',
                        })
