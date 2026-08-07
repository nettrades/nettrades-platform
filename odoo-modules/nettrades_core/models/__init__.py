# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - Models Package
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/__init__.py
#
# PURPOSE:
#   This file imports all models for the nettrades_core module.
#   We no longer extend core Odoo models; instead we use separate tables
#   linked via Many2one fields.
#
# UPDATES (2026-08):
#   - Removed res_partner, hr_job, project_project imports
#   - Added nettrades_user, nettrades_company, etc.
# =============================================================================

from . import nettrades_user
from . import nettrades_company
from . import nettrades_project
from . import nettrades_field
from . import nettrades_experience
from . import nettrades_review
from . import nettrades_skill
from . import nettrades_user_match
# Removed: from . import res_partner
# Removed: from . import hr_job
# Removed: from . import project_project