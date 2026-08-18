# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop - Self-Improving AI Loop
# =============================================================================
# FILE: odoo-modules/nettrades_loop/__manifest__.py
#
# PURPOSE:
#   The Loop module implements the self-improving AI loop architecture.
#   It manages the continuous improvement cycle of AI models through:
#     - Data collection and annotation
#     - Model training and fine-tuning
#     - Evaluation and feedback
#     - Deployment and monitoring
#
#   This module orchestrates the entire self-improving lifecycle.
#
# UPDATES (2026-08):
#   - Removed dependency on nettrades_gpustack_adapter (GPUStack replaced by Dynamo)
#   - Added dependency on nettrades_core for base functionality
# =============================================================================

{
    'name': 'NETTRADES Loop',
    'version': '1.0.0',
    'category': 'AI',
    'summary': 'Self-Improving AI Loop',
    'description': """
        Self-Improving AI Loop module.
        Orchestrates the continuous improvement cycle of AI models:
        - Data Collection & Annotation
        - Model Training & Fine-Tuning
        - Evaluation & Feedback
        - Deployment & Monitoring

        This is the core of the self-improving AI system.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'depends': [
        'base',
        'mail',
        'web',
        'queue_job',
        'nettrades_core',           # Core platform tables
        'nettrades_data_collection',  # Data collection module
        # 'nettrades_gpustack_adapter',  # REMOVED - GPUStack replaced by Dynamo
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/nettrades_loop_security.xml',
        'views/loop_cycle_views.xml',
        'views/loop_orchestrator_views.xml',
        'views/loop_config_views.xml',
        'views/loop_workflow_views.xml',
        'views/menu_views.xml',
        'data/loop_workflow_data.xml',
        'data/loop_config_data.xml',
    ],
    'demo': [
        'demo/loop_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}