# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LLM Configuration - Provider Management for AI Agents
# =============================================================================
# FILE: odoo-modules/nettrades_llm_config/__manifest__.py
#
# PURPOSE:
#   This module extends the Apexive odoo-llm provider system to add company-
#   specific LLM configuration for LangGraph agents. It allows administrators
#   to configure which LLM provider each company should use for inference,
#   with support for:
#     - Multiple providers (OpenAI, Anthropic, DeepSeek, Ollama, NETTRADES.AI)
#     - GPU overflow routing to NETTRADES.AI
#     - Fallback providers
#     - Per-company API keys and endpoints
#
# KEY FEATURES:
#   - Company-specific LLM provider selection
#   - GPU overflow detection and routing
#   - Automatic provider switching based on configuration
#   - Integration with Apexive odoo-llm provider system
#   - Fallback provider support
#
# =============================================================================

{
    'name': 'NETTRADES LLM Configuration',
    'author': 'NETTRADES.AI',
    'version': '1.0.0',
    'category': 'Nettrades/LLM',
    'summary': 'Company-specific LLM provider configuration for LangGraph agents',
    'description': """
        This module extends the Apexive odoo-llm provider system to add company-
        specific LLM configuration for LangGraph agents.

        Administrators can configure:
        - Which LLM provider each company uses (OpenAI, Anthropic, DeepSeek,
          Ollama, NETTRADES.AI)
        - API keys and custom endpoints
        - GPU overflow routing to NETTRADES.AI
        - Fallback providers
        - Default models per provider

        The LangGraph supervisor reads this configuration at runtime and
        dynamically creates the appropriate LLM instance.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',          # For company and user models
        'nettrades_gpu_admin',     # For GPU utilisation monitoring
        'llm',                     # Apexive base LLM module
        'llm_provider',            # Apexive provider system
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/llm_company_config_views.xml',
        'data/llm_provider_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}