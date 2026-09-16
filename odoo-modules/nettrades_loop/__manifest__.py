# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop - Self-Improving AI Loop
# =============================================================================
# FILE: odoo-modules/nettrades_loop/__manifest__.py
#
# UPDATES (2026-09-17):
#   - Trimmed 'data' list to only reference files that exist. Several files
#     were referenced by the manifest but had not been created yet
#     (loop_config_views.xml, loop_workflow_views.xml, menu_views.xml,
#     loop_workflow_data.xml, loop_config_data.xml, loop_demo.xml). These
#     have been removed so Odoo does not try to load non-existent files.
#     Re-add each one when the corresponding file is created.
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
        'nettrades_core',
        'nettrades_data_collection',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/nettrades_loop_security.xml',
        'views/loop_cycle_views.xml',
        # 'views/loop_orchestrator_views.xml',  # disabled - see file 4
        # 'views/loop_config_views.xml',        # not yet created
        # 'views/loop_workflow_views.xml',      # not yet created
        # 'views/menu_views.xml',               # not yet created
        # 'data/loop_workflow_data.xml',        # not yet created
        # 'data/loop_config_data.xml',          # not yet created
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}