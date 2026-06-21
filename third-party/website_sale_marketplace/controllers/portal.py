# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import http
from odoo.http import request
from odoo.addons.portal.controllers import portal


class CustomerPortal(portal.CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)

        if 'marketplace_product_count' in counters:
            values['marketplace_product_count'] = 1

        return values

    def _get_vendor_partner(self):
        """Get the vendor partner for current user"""
        partner = request.env.user.partner_id
        return partner.parent_id if partner.parent_id else partner

    def _prepare_marketplace_product_management_session_info(self, vendor_partner):
        """Prepare session info for marketplace product management web client"""
        session_info = request.env['ir.http'].session_info()
        user_context = dict(request.env.context) if request.session.uid else {}

        if request.env.lang:
            lang = request.env.lang
            session_info['user_context']['lang'] = lang
            user_context['lang'] = lang

        vendor_company = vendor_partner.company_id or request.env.user.company_id

        # Get the action ID to set as home action
        action = request.env.ref('website_sale_marketplace.marketplace_product_management_action')

        session_info.update(
            action_name="website_sale_marketplace.marketplace_product_management_action",
            vendor_partner_id=vendor_partner.id,
            vendor_partner_name=vendor_partner.name,
            user_companies={
                'current_company': vendor_company.id,
                'allowed_companies': {
                    vendor_company.id: {
                        'id': vendor_company.id,
                        'name': vendor_company.name,
                    },
                },
            },
            currencies=request.env['res.currency'].get_all_currencies(),
            home_action_id=action.id,  # Set as home action
        )

        # Add vendor_partner_id to user context for action domain filtering
        session_info['user_context']['vendor_partner_id'] = vendor_partner.id

        # Provide empty menu structure to avoid menu service errors
        session_info['menus'] = {
            'root': {'id': 'root', 'children': [], 'name': 'root', 'appID': False},
        }

        return session_info

    @http.route(['/my/products', '/my/products/<path:subpath>'], type='http', auth='user', methods=['GET'])
    def portal_my_products(self, subpath=None, **kwargs):
        """Display vendor's products in web client view"""
        vendor_partner = self._get_vendor_partner()

        # Check if user is a marketplace vendor
        if not vendor_partner.is_marketplace_vendor:
            return request.redirect('/my')

        # Render the web client view
        return request.render(
            'website_sale_marketplace.marketplace_product_management_portal',
            {'session_info': self._prepare_marketplace_product_management_session_info(vendor_partner)},
        )