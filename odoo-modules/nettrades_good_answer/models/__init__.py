# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer - Models Package
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/__init__.py
#
# PURPOSE:
#   This file imports all models for the nettrades_good_answer module.
#
# NOTE:
#   - 'nettrades_field' is NOT imported here because it is already defined
#     in nettrades_core. Importing it here would cause a circular dependency.
#   - Instead, we rely on the field_id Many2one relationship to resolve
#     the model reference at runtime.
# =============================================================================

from . import good_answer_vote
from . import llm_feedback
from . import user_field_reputation
from . import qualified_professional
from . import ft_dataset
from . import ft_training_job
from . import ft_dataset_contribution
# from . import nettrades_field  # REMOVED - already defined in nettrades_core