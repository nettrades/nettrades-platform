# -*- coding: utf-8 -*-
# =============================================================================
# SECTION F – JOB MATCHING CONTROLLERS
# =============================================================================
# FILE: odoo-modules/nettrades_job_matching/controllers/__init__.py
#
# PURPOSE:
#   This file imports all HTTP controllers for the Job Matching module.
#   Controllers handle API endpoints for conversational job search and
#   one-click apply functionality.
#
# IMPORTANT:
#   This file previously had a SYNTAX ERROR: 'from . import job_search.py'
#   The '.py' extension is NOT allowed in import statements and causes
#   a SyntaxError that prevents the entire module from loading.
#
#   FIX: Removed the '.py' extension to use the correct import syntax.
#
# =============================================================================

# Import the job search controller which handles:
#   - /api/jobs/search (natural language job search)
#   - /api/jobs/apply (one-click application)
#   - /api/jobs/recommendations (AI-powered job recommendations)
from . import job_search