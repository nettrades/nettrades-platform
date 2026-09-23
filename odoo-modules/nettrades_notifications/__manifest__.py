# -*- coding: utf-8 -*-
# FILE: # FILE: odoo-modules/nettrades_notifications/__manifest__.py
# Section F.8 - Notifications, Reviews & Disputes
{
    'name': 'NETTRADES Notifications & Reviews',
    'version': '1.0',
    'category': 'Nettrades',
    'summary': 'NETTRADES Notifications & Reviews',
    'description': """
        NETTRADES Notifications & Reviews.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': ['nettrades_core', 'mail'],
    'data': [],
    'controllers': ['controllers/notification.py'],
    'installable': True,
}