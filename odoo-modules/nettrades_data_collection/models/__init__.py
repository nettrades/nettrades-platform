# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection – Models Initialisation
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/__init__.py
#
# PURPOSE:
#   This file registers all models used by the data collection module.
#   Each model is imported here so Odoo can discover it.
#
# =============================================================================

from . import data_episode
from . import data_annotation
from . import data_feedback
from . import data_metric
from . import data_edge_case
from . import data_collector  # Service class for collecting data
from . import data_set