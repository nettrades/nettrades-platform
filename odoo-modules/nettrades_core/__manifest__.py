# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Module Manifest
# =============================================================================
# FILE:    odoo-modules/nettrades_core/__manifest__.py
# VERSION: 1.0 (fully commented)
#
# PURPOSE:
#   This module provides the core functionality for the NETTRADES.AI platform.
#   It extends the standard Odoo models with fields for user roles, skills,
#   professional fields, experience, reviews, and AI matching. It also defines
#   the security groups and views that are used across other NETTRADES modules.
#
# DEPENDENCIES:
#   - base          : Odoo core
#   - hr_recruitment: Job postings and applicants
#   - crm           : Lead management
#   - project       : Project management and milestones
#   - website_sale_marketplace : Multi‑vendor marketplace (for e-commerce)
#
# MODELS PROVIDED:
#   - res.partner (extended)
#   - nettrades.field
#   - nettrades.experience
#   - nettrades.review
#   - nettrades.skill
#   - nettrades.user_match
#   - hr_job (extended)
#   - project.project (extended)
#
# =============================================================================
{
    'name': 'NETTRADES Core',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Core marketplace and AI integration',
    'description': """
        This module provides the essential building blocks for the
        NETTRADES.AI autonomous enterprise platform.

        It extends Odoo's standard models to support:
          - User roles (Job Seeker, Freelancer, Company, Partner)
          - Professional fields and qualifications
          - Work experience and reviews
          - AI‑powered job matching
          - Lead generation and scoring

        This module is a dependency for all other NETTRADES modules.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'maintainer': 'Nettrades',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'hr_recruitment',
        'crm',
        'project',
        'website_sale_marketplace',
    ],
    'data': [
        'security/nettrades_security.xml',
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/hr_job_views.xml',
        'views/project_views.xml',
        'views/nettrades_review_views.xml',
        'views/nettrades_field_views.xml',
        'data/nettrades.skill.csv',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}