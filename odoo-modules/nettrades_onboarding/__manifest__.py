# -*- coding: utf-8 -*-
# FILE: odoo-modules/nettrades_onboarding/__manifest__.py
# Section F.2 - Smart Onboarding
#
# NOTE: This file must contain only ASCII characters. A previous version
# contained an em-dash (--) encoded as Windows-1252 byte 0x97, which
# caused Odoo's manifest parser to fail with "manifest not found" because
# Python 3 decodes files as UTF-8. Keep the comments plain ASCII.
{
    'name': 'NETTRADES Smart Onboarding',
    'version': '1.0',
    'category': 'Website',
    'summary': 'AI-powered user onboarding with CV parsing and profile completeness wizard',
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': ['nettrades_core', 'website', 'auth_oauth'],
    'data': [
        'security/ir.model.access.csv',
        'views/onboarding_wizard.xml',
        # 'views/res_partner_views.xml',   # Removed -- was inheriting a
        #                                     non-existent view in
        #                                     nettrades_core. The wizard
        #                                     handles profile completion.
        'templates/onboarding_templates.xml',
    ],
    'installable': True,
}