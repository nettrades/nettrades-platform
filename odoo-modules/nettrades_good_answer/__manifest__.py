# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – Voting, Reputation, and Fine-Tuning
# =============================================================================
# FILE:    odoo-modules/nettrades_good_answer/__manifest__.py
#
# PURPOSE:
#   This module implements the "Good Answer" voting system, user reputation
#   management, and the fine-tuning pipeline for self-improving AI.
#
# KEY FEATURES:
#   - Good Answer voting (weighted by professional qualification)
#   - Field-specific reputation with decay and auto-qualification
#   - Export of feedback data for fine-tuning (JSONL)
#   - Quality filtering via Data-Juicer and DEITA scoring
#   - Triggering fine-tuning jobs on GPUStack
#
# DEPENDENCIES:
#   - nettrades_core : for fields and partner extensions
#   - llm            : for AI provider configuration
#   - mail           : for notifications
#
# =============================================================================
{
    'name': 'NETTRADES Good Answer System',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Voting, reputation, and fine-tuning pipeline',
    'description': """
        This module enables users to vote on answers (both AI-generated and
        human) and builds a reputation system that is field-specific.

        It also collects feedback data and triggers automated fine-tuning
        using Unsloth (single-GPU) or Axolotl (multi-GPU) via GPUStack.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',
        'llm',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/qualified_professional_views.xml',
        'views/good_answer_config_views.xml',
        'views/ft_dataset_views.xml',
        'data/cron.xml',
    ],
    'controllers': ['controllers/main.py'],
    'installable': True,
    'application': False,
}