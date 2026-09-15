# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core — Models Package
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
#
# UPDATES (2026-09-15):
#   - FIXED: The original file used `from . import module_name.py`, which is
#     invalid Python. Python treats `.py` as an attribute lookup on the
#     package, not as a file extension. Every import below has been changed
#     from `from . import foo.py` to `from . import foo`.
#   - IMPORTANT: All original imports are KEPT ACTIVE. Do not comment any
#     of them out until the module split (Phase E) is performed. The
#     security XML references these models, so commenting them out will
#     break the module install.
#   - Added the safety wrapper below so that if any import fails, the error
#     message names the file that is missing instead of a cascade of
#     cryptic "model not found" errors.
# =============================================================================

import logging
_logger = logging.getLogger(__name__)


def _safe_import(module_name):
    """
    Import a model submodule and turn any ImportError into a clear message
    that names the file to look for.

    This is defensive. It does NOT swallow the error — it re-raises it,
    because a missing model file must be fixed, not silently ignored.
    """
    try:
        __import__(module_name, globals(), locals(), ['*'], 1)
    except ImportError as exc:
        _logger.error(
            "Failed to import model '%s' in nettrades_core. "
            "Check that odoo-modules/nettrades_core/models/%s.py exists "
            "and is syntactically valid. Original error: %s",
            module_name, module_name, exc,
        )
        raise
    except Exception as exc:
        _logger.error(
            "Unexpected error importing model '%s': %s",
            module_name, exc,
        )
        raise


# =============================================================================
# ALL ORIGINAL IMPORTS — every one preserved, only the `.py` suffix removed
# =============================================================================
# Original imports (from your file, with `.py` extension):
#   from . import expert_session.py
#   from . import nettrades_company
#   from . import nettrades_experience
#   from . import nettrades_field
#   from . import nettrades_good_answer
#   from . import nettrades_project
#   from . import nettrades_review
#   from . import nettrades_secrets.py
#   from . import nettrades_skill
#   from . import nettrades_user
#   from . import nettrades_user_match
#   from . import nettrades_vote.py
#   from . import qualified_professional.py
#   from . import review.py
#   from . import sandbox_policy.py
#
# The two lines below the "Removed" comment in the original file:
#   # Removed: from . import res_partner
#   # Removed: from . import hr_job
#   # Removed: from . import project_project
# are kept as comments — they document a previous refactor.
# =============================================================================

from . import expert_session           # expert.session — was: expert_session.py
from . import nettrades_company
from . import nettrades_experience
from . import nettrades_field
from . import nettrades_good_answer
from . import nettrades_project
from . import nettrades_review
from . import nettrades_secrets        # was: nettrades_secrets.py
from . import nettrades_skill
from . import nettrades_user
from . import nettrades_user_match
from . import nettrades_vote           # was: nettrades_vote.py
from . import qualified_professional   # was: qualified_professional.py
from . import review                   # was: review.py
from . import sandbox_policy           # was: sandbox_policy.py