# -*- coding: utf-8 -*-
# Copyright 2024 ERPGAP/PROMPTEQUATION LDA
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
{
    'name': 'Marketplace',
    'version': '19.0.0.0.2',
    'category': 'Sales',
    'license': 'AGPL-3',
    'summary': 'Post, Sell, its your marketplace',
    'website': 'https://www.erpgap.com',
    'description': """ """,
    'depends': [
        'website_sale',
        'portal',
        'contacts',
        'product',
        'uom',
        'html_editor',
        'sale_management',
        'stock_dropshipping'
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/res_users_views.xml',
        'views/res_partner_views.xml',
        'views/product_category_views.xml',
        'views/product_views.xml',
        'views/portal_templates.xml',
    ],
        # Assets temporarily disabled due to Odoo 19 asset path changes
    # 'assets': { ... },
    'installable': True,
    'application': True,
}
