# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES LLM Configuration - Models
# =============================================================================
# FILE: odoo-modules/nettrades_llm_config/models/__init__.py
#
# PURPOSE:
#   This file imports all model files in the nettrades_llm_config module.
#   Each model must be imported here to be discovered by Odoo.
#
# UPDATES (2026-09-16):
#   - Removed `from . import llm_provider_mapping`. That file does not exist
#     in the repository. If it is added later, restore the import.
# =============================================================================

from . import llm_company_config