#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/__manifest__.py
# =============================================================================
# UPDATES (2026-10):
#   - Added `views/inference_model_policy_views.xml` for per-model failover
#     policy overrides. The inline list on the cluster form is fine for
#     quick edits; the dedicated screen is useful when a customer has many
#     models with different failover requirements.
#   - The `views/menu_items.xml` file has been DELETED. It used the
#     `<act_window>` element, which was removed in Odoo 17. All actions
#     are now defined inline in their respective view files.
# =============================================================================
{
    'name': 'NETTRADES GPU Admin',
    'version': '19.0.1.2.0',
    'category': 'Technical',
    'summary': 'GPU Cluster Management with Secure Token Registration',
    'description': """
        GPU Cluster Management for the NETTRADES Platform.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',

    'depends': [
        'base',
        'mail',
        'nettrades_core',
    ],

    'data': [
        # Security (Groups, Access Control, Record Rules)
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/gpu_admin_security.xml',
        'security/gpu_registration_token_security.xml',

        # Service user `nettrades-service` is created by configure-odoo-admin.sh. which is loaded AFTER security/groups.xml so the
        # group XML IDs (group_gpu_administrator, group_gpu_operator)
        # are already defined.

        # Views (UI Screens)
        'views/gpu_cluster_views.xml',
        # 'views/inference_model_policy_views.xml',
         
        # THESE VIEWS ARE BROKEN AND NEED FIXING
        # 'views/gpu_node_views.xml',
        # 'views/gpu_schedule_views.xml',
        # 'views/gpu_token_economics_views.xml',
        # 'views/multimodal_config_views.xml',
        # 'views/menu_items.xml',
        # 'views/gpu_dashboard_templates.xml',
        # 'views/gpu_registration_token_views.xml',

        # Data (Cron jobs, default records, etc.)
        'data/cron.xml',
    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',

    'external_dependencies': {
        'python': [
            'cryptography',
        ],
        'bin': [
            'wg',
            'wg-quick',
            'ssh',
            'ping',
        ],
    },
}