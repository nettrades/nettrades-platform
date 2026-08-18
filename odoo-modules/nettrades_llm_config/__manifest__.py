# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LLM Configuration
# =============================================================================
# FILE: odoo-modules/nettrades_llm_config/__manifest__.py
#
# PURPOSE:
#   Configuration module for LLM providers and settings.
#   This module manages the configuration of language model providers,
#   including connection settings, model selection, and API keys.
#
# UPDATES (2026-08):
#   - Removed dependency on llm_provider (replaced by Dynamo)
# =============================================================================

{
    'name': 'NETTRADES LLM Configuration',
    'version': '1.0.0',
    'category': 'Nettrades/LLM',
    'summary': 'LLM Provider Configuration',
    'description': """
        Configuration for Language Model providers.
        Manages connection settings, model selection, and API keys
        for various LLM providers including Dynamo, OpenAI, and others.
    """,
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'depends': [
        'base',
        'mail',
        'web',
        'queue_job',
        # 'llm_provider',  # REMOVED - replaced by Dynamo
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/llm_config_views.xml',
        'views/llm_provider_views.xml',
        'views/res_config_settings_views.xml',
        'data/llm_provider_data.xml',
    ],
    'demo': [
        'demo/llm_provider_demo.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}