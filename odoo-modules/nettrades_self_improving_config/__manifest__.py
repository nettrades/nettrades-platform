# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving Configuration
# =============================================================================
# FILE: odoo-modules/nettrades_self_improving_config/__manifest__.py
#
# PURPOSE:
#   Configuration module for self-improving AI features.
#   Provides configuration options for:
#     - Training triggers and thresholds
#     - Model selection for fine-tuning
#     - Data quality requirements
#     - Episode management
#
# UPDATES (2026-08):
#   - Removed dependency on nettrades_gpustack_adapter (GPUStack replaced by Dynamo)
#   - Added dependency on nettrades_core for base functionality
# =============================================================================

{
    'name': 'NETTRADES Self-Improving Configuration',
    'version': '1.0.0',
    'category': 'AI',
    'summary': 'Self-Improving AI Configuration',
    'description': """
        Configuration for self-improving AI features.
        Provides configuration options for:
        - Training triggers and thresholds (episodes, quality scores)
        - Model selection for fine-tuning (DeepSeek, Qwen, Llama)
        - Data quality requirements
        - Episode management and classification
        - Auto-trigger settings
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'depends': [
        'base',
        'mail',
        'web',
        'queue_job',
        'nettrades_core',           # Core platform tables
        'nettrades_data_collection',  # Data collection
        'nettrades_loop',             # Loop orchestration
        # 'nettrades_gpustack_adapter',  # REMOVED - GPUStack replaced by Dynamo
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/nettrades_self_improving_config_security.xml',
        # 'views/self_improving_config_views.xml',   # Deferred - views not yet written
        'views/dashboard_views.xml',
        'views/menu_views.xml',
        # 'views/trigger_config_views.xml',           # Deferred - views not yet written
        # 'data/self_improving_config_data.xml',     # Deferred - no default data yet
    ],
    'demo': [
        # 'demo/self_improving_config_demo.xml',     # Deferred - no demo data
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}