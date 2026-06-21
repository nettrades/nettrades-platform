# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Module Manifest
# =============================================================================
# FILE: odoo-modules/nettrades_core/__manifest__.py
#
# PURPOSE:
#   This file defines the module's metadata, dependencies, and data files.
#
# DEPENDENCIES:
#   - base: Core Odoo
#   - hr_recruitment: For job and applicant models
#   - crm: For lead management
#   - project: For project and milestone models
#   - website_sale_marketplace: For marketplace features
#
# =============================================================================

{
    'name': 'NETTRADES Core',
    'version': '1.0',
    'category': 'Nettrades',
    'summary': 'Core marketplace and AI integration',
    'description': """
        This module provides the core functionality for the NETTRADES.AI platform:
        - Professional field configuration
        - User roles and profiles
        - Work experience and reviews
        - AI matching and lead generation
        - Integration with Forgejo Git
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'depends': [
        'base',
        'hr_recruitment',
        'crm',
        'project',                     # Added for project_project and reviews
        'website_sale_marketplace',
    ],
    'data': [
        'security/nettrades_security.xml',
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/hr_job_views.xml',
        'views/project_views.xml',
        'views/nettrades_review_views.xml',   # New view for reviews
        'views/nettrades_field_views.xml',
        'data/nettrades.skill.csv',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}