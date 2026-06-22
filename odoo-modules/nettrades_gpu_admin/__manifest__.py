# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES GPU Admin – GPU Cluster Management
# =============================================================================
# FILE:    odoo-modules/nettrades_gpu_admin/__manifest__.py
#
# PURPOSE:
#   This module provides a complete GPU cluster management interface for
#   system administrators. It manages GPU nodes, WireGuard configuration,
#   pool assignment, token economics, and GPUStack integration.
#
# KEY FEATURES:
#   - GPU cluster and node registration
#   - WireGuard VPN configuration (mesh and hub‑and‑spoke)
#   - Pool assignment (internal vs public)
#   - Container runtime selection (Docker vs gVisor)
#   - GPUStack worker integration
#   - Token economics and payout scheduling
#   - Multimodal and edge device configuration
#
# DEPENDENCIES:
#   - nettrades_core : for company and user models
#   - web            : for UI assets
#   - bus            : for real‑time updates
#
# =============================================================================
{
    'name': 'NETTRADES GPU Admin',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'GPU cluster administration and GPUStack integration',
    'description': """
        This module provides a comprehensive administration dashboard for
        managing GPU clusters and nodes. It integrates with GPUStack to
        orchestrate inference and fine‑tuning workloads.

        Features:
          - Real‑time cluster dashboard
          - Node registration and health monitoring
          - WireGuard network management
          - Pool assignment (internal/public)
          - Token economics and payout scheduling
          - Multimodal and edge device configuration
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'LGPL-3',
    'depends': [
        'nettrades_core',
        'web',
        'bus',
    ],
    'data': [
        'security/gpu_admin_security.xml',
        'security/ir.model.access.csv',
        'views/gpu_cluster_views.xml',
        'views/gpu_node_views.xml',
        'views/gpu_schedule_views.xml',
        'views/gpu_token_economics_views.xml',
        'views/gpu_dashboard_templates.xml',
        'views/menu_items.xml',
        'views/multimodal_config_views.xml',
        'data/cron.xml',
    ],
    'controllers': ['controllers/main.py'],
    'assets': {
        'web.assets_backend': [
            'nettrades_gpu_admin/static/src/scss/dashboard.scss',
            'nettrades_gpu_admin/static/src/js/dashboard.js',
            'nettrades_gpu_admin/static/src/js/node_manager.js',
            'nettrades_gpu_admin/static/src/js/network_scan.js',
            'nettrades_gpu_admin/static/src/js/wireguard_manager.js',
        ],
    },
    'installable': True,
    'application': False,
}