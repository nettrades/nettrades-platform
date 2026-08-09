# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - Hub-and-Spoke Routing Module
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/__manifest__.py
#
# PURPOSE:
#   This module acts as the central "switchboard" for the NETTRADES platform.
#   It allows client companies to route AI requests either to their local
#   LangGraph instance (for internal operations) or to the remote NETTRADES.ai
#   brain (for global services like external recruitment and GPU overflow).
#
#   This is the core commercial engine of Nettrades.com, enabling the
#   hub-and-spoke business model.
#
# KEY FEATURES:
#   - Global and per-company configuration of routing rules
#   - Intent-based routing (recruitment, freelance, GPU, etc.)
#   - GPU overflow detection and routing to the global marketplace
#   - Graceful fallback between local and remote brains
#   - Usage tracking and billing integration
#
# =============================================================================
{
    'name': 'NETTRADES Bridge',
    'author': 'NETTRADES.AI',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Hub-and-spoke routing layer for AI requests',
    'description': """
        This module provides a configurable routing service that decides
        whether AI requests should be processed locally (via the client's
        own LangGraph agents) or forwarded to the remote NETTRADES.ai brain.

        It is the core commercial engine for the hub-and-spoke business model,
        enabling client companies to use local AI for internal operations
        while seamlessly accessing global services when needed.

        ============================================================
        CONFIGURATION
        ============================================================
        1. Global Settings: Settings -> Technical -> Bridge -> Global Config
        2. Company Settings: Settings -> Technical -> Bridge -> Company Config
        3. Usage Logs: Settings -> Technical -> Bridge -> Usage Logs
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',          # For company and user models
        'nettrades_gpu_admin',     # For GPU capacity monitoring
        'base',                    # Core Odoo
    ],
    'data': [
        'security/bridge_security.xml',
        'security/ir.model.access.csv',
        'views/bridge_config_views.xml',
        'views/bridge_company_config_views.xml',
        'views/bridge_usage_log_views.xml',
        'data/bridge_cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}