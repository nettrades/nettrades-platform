# -*- coding: utf-8 -*-
# Section F.4 – Freelancer Proposals & Milestones
{
    'name': 'NETTRADES Freelancer Proposals',
    'version': '1.0',
    'category': 'Nettrades',
    'summary': 'NETTRADES Freelancer Proposals',
    'description': """
       NETTRADES Freelancer Proposals.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3.0',
    'depends': ['nettrades_core', 'project'],
    'data': [
        'views/project_milestone_views.xml',
    ],
    'controllers': ['controllers/proposal.py'],
    'installable': True,
}