# -*- coding: utf-8 -*-
# Section F.2 - Smart Onboarding
{
    'name': 'NETTRADES Smart Onboarding',
    'author': 'NETTRADES.AI',
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
        'views/res_partner_views.xml',
        'templates/onboarding_templates.xml',
    ],
    'controllers': ['controllers/onboarding.py'],
    'installable': True,
}