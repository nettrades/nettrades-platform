# -*- coding: utf-8 -*-
# Section F.5 - Company Lead Scoring
{
    'name': 'NETTRADES Company Lead Scoring',
    'version': '1.0',
    'category': 'Nettrades',
    'summary': 'NETTRADES Company Lead Scoring',
    'description': """
        NETTRADES Company Lead Scoring.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': ['nettrades_core', 'crm'],
    'data': [],
    'controllers': ['controllers/lead_score.py'],
    'installable': True,
}