# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_round


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    marketplace_vendor_id = fields.Many2one('res.partner', string='Marketplace Vendor')
    marketplace_state = fields.Selection([
        ('draft', 'Draft'),
        ('approval', 'Pending Approval'),
        ('approved', 'Approved'),
    ], string='Marketplace State', default='draft', tracking=True,
       help='Marketplace products must be approved before they can be published on the website')
    description_ecommerce = fields.Html(
        string='eCommerce Description',
        translate=True,
        sanitize_attributes=False,
        sanitize_form=False
    )

    @api.model
    def _get_vendor_partner(self):
        """Get the vendor partner for the current user"""
        user = self.env.user

        # Portal users: return parent company if exists, otherwise themselves
        if user._is_portal():
            if user.partner_id.parent_id:
                return user.partner_id.parent_id
            else:
                return user.partner_id

        return None

    def _get_marketplace_markup(self, vendor_partner):
        """Get marketplace markup for product, checking category first then vendor"""
        # Check if category has marketplace_markup set
        if self.categ_id and self.categ_id.marketplace_markup:
            return self.categ_id.marketplace_markup
        # Fall back to vendor's marketplace_markup
        return vendor_partner.marketplace_markup or 0.0

    def write(self, vals):
        """Recalculate cost when sales price changes and reset marketplace state on vendor changes"""
        # Fields that should trigger state reset to 'draft' for marketplace products
        vendor_editable_fields = {
            'name', 'list_price', 'description', 'description_sale', 'description_ecommerce',
            'categ_id', 'uom_id', 'uom_po_id', 'image_1920', 'website_description'
        }

        # Check if vendor is editing their own product and changing significant fields
        should_reset_state = False
        if any(field in vals for field in vendor_editable_fields):
            vendor_partner = self._get_vendor_partner()
            if vendor_partner:
                for product in self:
                    # Reset state if vendor is editing their own marketplace product
                    # and it's currently in 'approved' state
                    if (product.marketplace_vendor_id == vendor_partner and
                        product.marketplace_state == 'approved' and
                        'marketplace_state' not in vals):  # Don't reset if state is being set explicitly
                        should_reset_state = True
                        break

        # If state should be reset, add it to vals and unpublish the product
        if should_reset_state and 'marketplace_state' not in vals:
            vals['marketplace_state'] = 'draft'
            # Unpublish the product since it needs re-approval
            vals['is_published'] = False

        # Check if user is a portal vendor
        vendor_partner = self._get_vendor_partner()
        is_portal_vendor = bool(vendor_partner)

        # Portal vendors need sudo to write products (same reason as create - stock module accesses routes)
        if is_portal_vendor:
            result = super(ProductTemplate, self.sudo()).write(vals)
        else:
            result = super().write(vals)

        # Only recalculate if list_price changed
        if 'list_price' in vals:
            for product in self:
                vendor_partner = product.marketplace_vendor_id
                if vendor_partner:
                    # Get marketplace markup (category first, then vendor)
                    markup_percent = product._get_marketplace_markup(vendor_partner)
                    sale_price = product.list_price or 0.0

                    # Calculate new cost
                    if markup_percent > 0:
                        cost_price = float_round(
                            sale_price / (1 + markup_percent),
                            precision_digits=2
                        )
                    else:
                        cost_price = sale_price

                    # Update product cost (use sudo for portal users)
                    if product.sudo().standard_price != cost_price:
                        product.sudo().write({'standard_price': cost_price})

                    # Update supplierinfo price
                    supplierinfo = self.env['product.supplierinfo'].sudo().search([
                        ('product_tmpl_id', '=', product.id),
                        ('partner_id', '=', vendor_partner.id)
                    ], limit=1)
                    if supplierinfo and supplierinfo.price != cost_price:
                        supplierinfo.sudo().write({'price': cost_price})

        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-assign marketplace_vendor_id and setup dropshipping on creation"""
        vendor_partner = self._get_vendor_partner()
        is_portal_vendor = bool(vendor_partner)

        for vals in vals_list:
            # Auto-assign vendor if not already set and user is portal/vendor
            if not vals.get('marketplace_vendor_id') and vendor_partner:
                vals['marketplace_vendor_id'] = vendor_partner.id

        # Portal vendors need sudo to create products (stock module accesses routes in defaults)
        if is_portal_vendor:
            products = super(ProductTemplate, self.sudo()).create(vals_list)
            # Setup dropshipping and supplierinfo
            self.sudo()._setup_vendor_dropshipping(products, vendor_partner)
        else:
            products = super().create(vals_list)

        return products

    def _setup_vendor_dropshipping(self, products, vendor_partner):
        """Setup dropshipping and supplier info for vendor products"""
        # Get dropship route
        dropship_route = self.env.ref('stock_dropshipping.route_drop_shipping', raise_if_not_found=False)

        for product in products:
            if product.marketplace_vendor_id == vendor_partner:
                # Get marketplace markup (category first, then vendor)
                markup_percent = product._get_marketplace_markup(vendor_partner)

                # Calculate cost based on markup: cost = sale_price / (1 + markup/100)
                sale_price = product.list_price or 0.0
                if markup_percent > 0:
                    cost_price = float_round(
                        sale_price / (1 + markup_percent),
                        precision_digits=2
                    )
                else:
                    cost_price = sale_price

                # Set dropship route and cost
                update_vals = {'standard_price': cost_price}
                if dropship_route:
                    update_vals['route_ids'] = [(4, dropship_route.id)]
                product.write(update_vals)

                # Create supplierinfo record with calculated cost
                self.env['product.supplierinfo'].create({
                    'partner_id': vendor_partner.id,
                    'product_tmpl_id': product.id,
                    'min_qty': 1.0,
                    'price': cost_price,
                })

    def action_send_for_approval(self):
        """Send marketplace product for approval"""
        for product in self:
            if product.marketplace_vendor_id and product.marketplace_state == 'draft':
                product.marketplace_state = 'approval'

    def action_approve(self):
        """Approve marketplace product (backend users only)"""
        for product in self:
            if product.marketplace_vendor_id and product.marketplace_state == 'approval':
                product.marketplace_state = 'approved'

    def action_set_draft(self):
        """Set marketplace product back to draft"""
        for product in self:
            if product.marketplace_vendor_id:
                product.marketplace_state = 'draft'

    @api.constrains('is_published', 'marketplace_vendor_id', 'marketplace_state')
    def _check_marketplace_publish(self):
        """Prevent publishing marketplace products that are not approved"""
        for product in self:
            if (product.marketplace_vendor_id and
                product.is_published and
                product.marketplace_state != 'approved'):
                raise ValidationError(
                    'Marketplace products must be approved before they can be published on the website. '
                    f'Current state: {dict(product._fields["marketplace_state"].selection).get(product.marketplace_state)}'
                )
