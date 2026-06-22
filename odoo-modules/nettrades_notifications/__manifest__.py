# -*- coding: utf-8 -*-
# Section F.8 – Notifications, Reviews & Disputes
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
    'license': 'AGPL-3.0',
    'depends': ['nettrades_core', 'mail'],
    'data': [],
    'controllers': ['controllers/notification.py'],
    'installable': True,
}