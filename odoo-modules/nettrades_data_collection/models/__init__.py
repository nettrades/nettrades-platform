# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection - Models Initialisation
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/__init__.py
#
# PURPOSE:
#   This file registers all models used by the data collection module.
#   Each model is imported here so Odoo can discover it.
#
# UPDATES (2026-09-17):
#   - Removed `from . import data_set` — that file does not exist in this
#     module. Importing it raised ImportError at load time, blocking the
#     whole module install. The correct filename is data_dataset.py, which
#     is imported below.
# =============================================================================

from . import data_episode
from . import data_annotation
from . import data_feedback
from . import data_metric
from . import data_edge_case
from . import data_collector   # Service class for collecting data
from . import data_dataset     # Dataset model (simulation.dataset)