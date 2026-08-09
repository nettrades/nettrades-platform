# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Loop - Self-Improving System Orchestrator
# =============================================================================
# FILE: odoo-modules/nettrades_loop/__manifest__.py
#
# PURPOSE:
#   This module orchestrates the complete self-improving loop. It is the
#   "Orchestrator" that connects the Monitor, Analyze, Plan, and Execute
#   phases of the MAPE loop.
#
#   The orchestrator:
#     1. Checks triggers (Analyze phase)
#     2. Creates datasets (Plan phase)
#     3. Submits training jobs (Plan phase)
#     4. Deploys trained models (Execute phase)
#
#   This module integrates with:
#     - nettrades_data_collection -> Monitor phase
#     - nettrades_trigger -> Analyze phase
#     - llm_training (Apexive) -> Plan phase (dataset and job management)
#     - GPUStack -> Execute phase (model deployment)
#
# =============================================================================
{
    'name': 'NETTRADES Self-Improving Loop',
    'author': 'NETTRADES.AI',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Orchestrator for self-improving AI system',
    'description': """
        This module orchestrates the complete self-improving loop,
        connecting the Monitor, Analyze, Plan, and Execute phases.

        Key Features:
        - Trigger evaluation and firing
        - Dataset creation and management
        - Training job submission and monitoring
        - Model deployment and A/B testing
        - Cycle tracking and reporting
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_data_collection',  # Monitor phase
        'nettrades_trigger',          # Analyze phase
        'llm_training',               # Plan phase (Apexive)
        'nettrades_gpustack_adapter',       # Execute phase
        'base',                       # Core Odoo
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/loop_cycle_views.xml',
        'views/loop_orchestrator_views.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}