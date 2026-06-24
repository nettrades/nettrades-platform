# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness & Rationality Module
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/__init__.py
#
# PURPOSE:
#   This file initialises the nettrades_fairness module. It imports all
#   sub-packages so they are registered with Odoo.
#
#   The module provides:
#     - Configurable rationality and bias evaluation
#     - LLM-as-Judge scoring for AI responses
#     - Fairness metrics and audit logging
#     - Automated filtering of training data
#     - Admin configuration screens
#
# =============================================================================

from . import models
from . import wizards