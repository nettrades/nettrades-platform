#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/__manifest__.py
# =============================================================================
{
    'name': 'NETTRADES GPU Admin',
    'author': 'NETTRADES.AI',
    'version': '19.0.1.1.0',
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

        # Views (UI Screens)
        'views/gpu_cluster_views.xml',
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
            'ipaddress',
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