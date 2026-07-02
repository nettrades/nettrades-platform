# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Ask Someone - Expert Help Marketplace
# =============================================================================
# FILE:    odoo-modules/nettrades_ask_someone/__manifest__.py
#
# PURPOSE:
#   This module provides a real-time expert help marketplace where users can
#   request paid consultations from verified professionals. It handles expert
#   matching, Stripe escrow, live sessions, and ratings.
#
# KEY FEATURES:
#   - Intelligent expert matching (reputation, proximity, online status)
#   - Stripe escrow payments (manual capture)
#   - Live chat sessions via WebSocket (Odoo bus)
#   - Rating and review system
#   - Expert agreement and legal consent
#
# DEPENDENCIES:
#   - nettrades_core : for fields and partner models
#   - payment        : for payment framework
#   - mail           : for messaging
#
# =============================================================================
{
    'name': 'NETTRADES Ask Someone',
    'version': '1.0.0',
    'category': 'Nettrades',
    'summary': 'Expert help marketplace with Stripe escrow',
    'description': """
        Users can request help from verified professionals in real-time.
        Payments are held in escrow until the session is completed.
        Matching is based on reputation, location, and online status.
    """,
    'author': 'Nettrades',
    'website': 'https://nettrades.ai',
    'license': 'AGPL-3',
    'depends': [
        'nettrades_core',
        'payment',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/ask_someone_config_views.xml',
        'views/expert_session_views.xml',
        'data/expert_agreement_template.xml',    # updated agreement with AI training transparency
    ],
    'controllers': ['controllers/main.py'],
    'installable': True,
    'application': False,
}