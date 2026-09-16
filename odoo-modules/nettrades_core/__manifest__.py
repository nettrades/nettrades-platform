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
    # Reduced to ['base', 'mail'] to unblock installation. Any one of the
    # six original dependencies being missing blocks the ENTIRE NETTRADES
    # module tree, because nettrades_core is the root of the graph.
    #
    # Models still in nettrades_core reference ONLY base models
    # (res.partner, res.company, res.currency). The models that DO need
    # hr_recruitment, crm, project, or website_sale_marketplace will be
    # moved into their own modules in Phase E.
    # =========================================================================
    'depends': [
        # Original dependencies (kept here as a comment for reference):
        # 'hr_recruitment',            # For job matching
        # 'crm',                       # For lead management
        # 'project',                   # For project management
        # 'website_sale_marketplace',  # For marketplace features
        # 'auth_signup',               # For self-service onboarding
        # 'queue_job',                 # For async jobs

        # Reduced set (Phase A — safe to install anywhere):
        'base',    # res.partner, res.company, res.currency, res.users
        'mail',    # mail.thread, mail.activity.mixin, chatter
    ],

    # =========================================================================
    # DATA FILES
    # =========================================================================
    # Load order is critical. Odoo resolves XML ID references at load time,
    # so anything a file references must already be loaded.
    #
    # Correct order:
    #   1. Security               — groups, then rules, then model access
    #   2. Menu ROOT              — the root menu item, referenced by every view
    #   3. Views                  — define the actions that the sub-menus use
    #   4. Menu SUB-MENUS         — reference both the root menu and the actions
    #   5. Reference data         — CSV/XML content loaded last
    #
    # FIXED (2026-09-16):
    #   The menu file was a single file that both:
    #     (a) defined the root menu that the views reference, and
    #     (b) referenced actions that the views define.
    #   That is a circular dependency. It has been split:
    #     - nettrades_core_menu_root.xml : root menu only  → loads first
    #     - nettrades_core_menu.xml      : sub-menus + actions → loads last
    # =========================================================================
    'data': [
        # --- Security: must load first ---
        'security/nettrades_security.xml',
        'security/ir.model.access.csv',

        # --- Menu root: referenced by every view below ---
        'views/nettrades_core_menu_root.xml',

        # --- Views: define the actions the sub-menus reference ---
        'views/nettrades_user_views.xml',
        'views/nettrades_company_views.xml',
        'views/nettrades_project_views.xml',
        'views/nettrades_field_views.xml',
        'views/nettrades_review_views.xml',
        'views/nettrades_experience_views.xml',

        # --- Menu sub-menus: reference the root menu AND the actions above ---
        'views/nettrades_core_menu.xml',

        # --- Reference data: loaded last ---
        'data/nettrades.skill.csv',
        'data/portal_data.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}