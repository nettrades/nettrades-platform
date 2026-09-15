# -*- coding: utf-8 -*-
{
    'name': 'NETTRADES Core',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Core marketplace and AI integration',
    'description': """
        This module provides the essential building blocks for the
        NETTRADES platform. It defines separate tables for NetTrades users
        and companies, linked to Odoo core models via Many2one fields.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',

    # =========================================================================
    # DEPENDENCIES
    # =========================================================================
    # ORIGINAL (from your file):
    #   'base', 'hr_recruitment', 'crm', 'project',
    #   'website_sale_marketplace', 'auth_signup', 'queue_job'
    #
    # CHANGE (2026-09-15):
    #   Reduced to ['base', 'mail'] to unblock installation. The reason is
    #   that any one of the six removed modules being missing, misconfigured,
    #   or slow to install blocks the ENTIRE NETTRADES module tree, because
    #   nettrades_core is the root of the dependency graph.
    #
    #   The models that are still in nettrades_core today reference ONLY
    #   base models (res.partner, res.company, res.currency). None of them
    #   reference hr_recruitment, crm, project, or website_sale_marketplace
    #   directly. In the final phase, the models that DO need those modules
    #   will be moved into their own modules which declare the dependency.
    #
    #   If you want to revert to the original dependency set, uncomment the
    #   six lines below and comment out the reduced list.
    # =========================================================================
    'depends': [
        # Original dependencies (kept here as a comment for reference):
        # 'hr_recruitment',
        # 'crm',
        # 'project',
        # 'website_sale_marketplace',
        # 'auth_signup',
        # 'queue_job',

        # Reduced set (Phase A — safe to install anywhere):
        'base',    # res.partner, res.company, res.currency, res.users
        'mail',    # mail.thread, mail.activity.mixin, chatter
    ],

    # =========================================================================
    # DATA FILES
    # =========================================================================
    # Every data file from the ORIGINAL manifest is preserved below.
    # The order has been reorganised slightly for correctness (security
    # before views before data), but no file has been removed.
    # =========================================================================
    'data': [
        # Security – must load first, before anything that references it
        'security/nettrades_security.xml',
        'security/ir.model.access.csv',

        # Menu – must load before views that reference it
        # (Original name: nettrades_core_menu.xml — preserved)
        'views/nettrades_core_menu.xml',

        # Views — every one from the original manifest
        'views/hr_job_views.xml',
        'views/res_partner_views.xml',
        'views/nettrades_user_views.xml',
        'views/nettrades_company_views.xml',
        'views/nettrades_project_views.xml',
        'views/nettrades_field_views.xml',
        'views/nettrades_review_views.xml',
        'views/nettrades_experience_views.xml',
        'views/nettrades_user_match_views.xml',

        # Data (reference data loaded last)
        'data/nettrades.skill.csv',
        'data/portal_data.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}