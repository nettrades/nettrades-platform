# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Models Package
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/__init__.py
#
# PURPOSE:
#   This file imports all model classes so they are registered with Odoo.
#
# IMPORTANT:
#   The order of imports does not matter as Odoo resolves dependencies
#   during the registry build, but it's good practice to import base models
#   before their extensions.
#
# =============================================================================

from . import res_partner
from . import hr_job
from . import project_project
from . import nettrades_user_match
from . import nettrades_skill
from . import nettrades_field
from . import nettrades_experience      # NEW: Work Experience model
from . import nettrades_review          # NEW: Review model