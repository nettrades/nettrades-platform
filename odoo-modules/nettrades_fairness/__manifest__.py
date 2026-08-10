# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness & Rationality - Module Manifest
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/__manifest__.py
#
# PURPOSE:
#   This file defines the module's metadata, dependencies, and data files.
#   It also lists the security, views, and data files to load.
#
#   This module implements a comprehensive fairness and rationality system
#   that evaluates AI responses for logical coherence and bias, filters
#   training data to improve model quality, and provides admin configurable
#   thresholds and automated actions.
#
# KEY FEATURES:
#   - LLM-as-Judge rationality and bias scoring
#   - Configurable thresholds (global and per-field)
#   - Automated filtering of training data
#   - Fairness metrics and audit logging
#   - A/B testing for model improvements
#   - Admin configuration screens
#
# DEPENDENCIES:
#   - nettrades_core (for fields and partner models)
#   - nettrades_good_answer (for feedback and training data)
#   - base (core Odoo)
#
# =============================================================================

{
    'name': 'NETTRADES Fairness & Rationality',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'AI Fairness, Rationality, and Bias Detection',
    'description': """
        This module provides a comprehensive fairness and rationality
        system for the NETTRADES platform.

        Key Features:
        - LLM-as-Judge rationality and bias scoring
        - Configurable thresholds (global and per-field)
        - Automated filtering of training data
        - Fairness metrics and audit logging
        - A/B testing for model improvements
        - Admin configuration screens

        This is the core of the self-improving, bias-resistant AI system.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',          # For fields and partner models
        'nettrades_good_answer',   # For feedback and training data
        'base',                    # Core Odoo
    ],
    'data': [
        'security/fairness_security.xml',
        'security/ir.model.access.csv',
        'views/fairness_config_views.xml',
        'views/fairness_audit_views.xml',
        'views/fairness_dashboard_views.xml',
        'data/cron_data.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}