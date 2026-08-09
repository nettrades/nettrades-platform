# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Trigger - Self-Improving System Analyze Phase
# =============================================================================
# FILE: odoo-modules/nettrades_trigger/__manifest__.py
#
# PURPOSE:
#   This module detects when the self-improving system should trigger a
#   training cycle. It is the "Analyze" phase of the MAPE loop.
#
#   Triggers evaluate conditions such as:
#     - Quality score dropping below threshold
#     - Task success rate declining
#     - Enough data accumulated for training
#     - New edge cases detected
#     - Manual trigger by administrator
#
#   When a trigger fires, it initiates a self-improvement cycle via the
#   nettrades_loop orchestrator.
#
# =============================================================================
{
    'name': 'NETTRADES Trigger Detection',
    'author': 'NETTRADES.AI',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Trigger detection for self-improving AI system',
    'description': """
        This module detects conditions that trigger a self-improvement
        cycle. It is the "Analyze" phase of the MAPE loop.

        Key Features:
        - Configurable trigger conditions
        - Quality score monitoring
        - Success rate analysis
        - Data volume thresholds
        - Edge case detection
        - Manual triggers

        When a trigger fires, it initiates a self-improvement cycle.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_data_collection',  # For episode data
        'base',                       # Core Odoo
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/trigger_config_views.xml',
        'views/trigger_event_views.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}