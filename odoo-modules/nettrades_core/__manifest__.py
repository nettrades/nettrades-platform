# -*- coding: utf-8 -*-
# Section A-F - Core marketplace module
# Purpose: Manifest for the NETTRADES Core module.
# Depends on standard Odoo apps and the community LLM package.
{
    'name': 'NETTRADES Core',
    'version': '1.0',
    'category': 'Sales/Marketplace',
    'summary': 'Core marketplace features and AI matching foundation',
    'depends': [
        'base', #'hr_recruitment', 'crm', 'project',
     #   'website_sale_marketplace',  # multi-vendor marketplace addon
        # 'odoo_llm',                 # community LLM package � install separately
    ],
    'data': [
   #     'security/nettrades_security.xml',
   #     'security/ir.model.access.csv',
   #     'views/res_partner_views.xml',
   #     'views/hr_job_views.xml',
   #     'views/project_views.xml',
   #     'views/nettrades_review_views.xml',
   #     'views/nettrades_field_views.xml',        # new field configuration view
   #     'views/nettrades_core_menu.xml',
   #     'data/nettrades.skill.csv',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}