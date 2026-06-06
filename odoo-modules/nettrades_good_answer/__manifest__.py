# -*- coding: utf-8 -*-
# Section E – Good Answer Reputation & Fine-Tuning
{
    'name': 'NETTRADES Good Answer System',
    'version': '1.0',
    'depends': ['nettrades_core', 'odoo_llm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/qualified_professional_views.xml',
        'views/good_answer_config_views.xml',
        'views/ft_dataset_views.xml',
        'data/cron.xml',
    ],
    'controllers': ['controllers/main.py'],
    'installable': True,
}