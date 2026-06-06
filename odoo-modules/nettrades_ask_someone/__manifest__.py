# -*- coding: utf-8 -*-
# Section D – Ask Someone (Expert Help)
{
    'name': 'NETTRADES Ask Someone – Expert Help',
    'version': '1.0',
    'depends': ['nettrades_core', 'payment', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/ask_someone_config_views.xml',
        'views/expert_session_views.xml',
        'data/expert_agreement_template.xml',    # updated agreement with AI training transparency
    ],
    'controllers': ['controllers/main.py'],
    'installable': True,
}