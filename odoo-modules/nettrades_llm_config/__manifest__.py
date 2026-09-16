# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LLM Configuration
# =============================================================================
# FILE: odoo-modules/nettrades_llm_config/__manifest__.py
#
# PURPOSE:
#   Configuration module for LLM providers and settings.
#   Manages connection settings, model selection, and API keys.
#
# DEPENDENCIES:
#   - 'llm'         : Apexive odoo-llm — provides the `llm.provider` model
#                     used as comodel in nettrades.llm.company.config.
#                     This is copied by prepare-odoo-addons.sh from third-party/.
#   - 'queue_job'   : OCA queue_job — for async jobs.
#
# REMOVED FROM MANIFEST (2026-09-16):
#   These files are referenced by the manifest but do not exist in the
#   repository. They were replaced by views/llm_company_config_views.xml
#   after the Dynamo refactor. Do not re-add them until they are created:
#     - views/llm_config_views.xml
#     - views/llm_provider_views.xml
#     - views/res_config_settings_views.xml
#     - data/llm_provider_data.xml
#     - demo/llm_provider_demo.xml
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
        'llm',   # Apexive odoo-llm — provides llm.provider comodel
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/llm_company_config_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'AGPL-3',
}