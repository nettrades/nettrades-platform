# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving Config - Administration Module
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving_config/__manifest__.py
#
# PURPOSE:
#   This module provides the administration interface for the self-improving
#   system. It allows administrators to configure and monitor the
#   self-improving loop.
#
#   Configuration includes:
#     - Loop settings: enable/disable, frequency, auto-deploy
#     - Data quality: minimum quality score, votes required
#     - A/B testing: enable, traffic split, promotion threshold
#     - Triggers: create, edit, delete trigger configurations
#     - Cycles: view and monitor self-improvement cycles
#
# =============================================================================
{
    'name': 'NETTRADES Self-Improving Configuration',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Administration interface for self-improving AI system',
    'description': """
        This module provides the administration interface for the
        self-improving AI system.

        Key Features:
        - Loop configuration (enable/disable, frequency)
        - Data quality settings
        - A/B testing configuration
        - Trigger management
        - Cycle monitoring and reporting
        - Manual cycle triggering
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_loop',           # For cycle management
        'nettrades_trigger',        # For trigger management
        'nettrades_data_collection', # For episode management
        'base',                     # Core Odoo
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/config_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}