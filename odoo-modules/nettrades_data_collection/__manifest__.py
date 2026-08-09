# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection - Self-Improving System Monitor Phase
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/__manifest__.py
#
# PURPOSE:
#   This module collects and structures data from all platform interactions.
#   It is the "Monitor" phase of the self-improving MAPE loop.
#
#   The module stores:
#     - Episodes: Complete interaction records (input -> output -> feedback)
#     - Annotations: Human or expert evaluations
#     - Feedback: User ratings, "Good Answer" votes
#     - Metrics: Performance data (latency, quality, success rate)
#     - Edge Cases: Novel or problematic interactions
#
# INTEGRATION POINTS:
#   - Good Answer votes -> Creates feedback records
#   - Ask Someone sessions -> Creates episodes from expert answers
#   - LangGraph agents -> Creates episodes from user interactions
#   - GPUStack -> Collects performance metrics
#   - ROS 2 / robotics -> Collects sensor and action data
#
# =============================================================================
{
    'name': 'NETTRADES Data Collection',
    'author': 'NETTRADES.AI',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Data collection for self-improving AI system',
    'description': """
        This module collects and structures data from all platform
        interactions for the self-improving AI system.

        Key Features:
        - Episodes: Complete interaction records
        - Annotations: Human or expert evaluations
        - Feedback: User ratings and votes
        - Metrics: Performance data
        - Edge Cases: Novel interactions

        This is the Monitor phase of the MAPE loop.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',          # For fields and partner models
        'nettrades_good_answer',   # For Good Answer votes
        'nettrades_ask_someone',   # For expert sessions
        'base',                    # Core Odoo
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/data_episode_views.xml',
        'views/data_annotation_views.xml',
        'views/data_feedback_views.xml',
        'views/data_metric_views.xml',
        'views/data_edge_case_views.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}