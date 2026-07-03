# -*- coding: utf-8 -*-
# =============================================================================
# SECTION F - CHATBOT CONTROLLERS
# =============================================================================
# FILE: odoo-modules/nettrades_chatbot/controllers/__init__.py
#
# PURPOSE:
#   This file imports all HTTP controllers for the Chatbot module.
#   Controllers handle API endpoints for the AI chatbot widget and
#   Ask Someone integration.
#
# IMPORTANT:
#   This file was previously EMPTY, which meant that the chatbot
#   controllers were never imported and the chatbot widget endpoints
#   were completely non-functional.
#
#   FIX: We now import the chatbot controller to register all endpoints.
#
# =============================================================================

# Import the chatbot controller which handles:
#   - /chatbot/message (send and receive chat messages)
#   - /chatbot/session (session management)
#   - /chatbot/ask_someone (integration with Ask Someone)
from . import chatbot