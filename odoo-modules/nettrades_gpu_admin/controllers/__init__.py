# -*- coding: utf-8 -*-
# =============================================================================
# SECTION H – GPU ADMIN CONTROLLERS
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/controllers/__init__.py
#
# PURPOSE:
#   This file imports all HTTP controllers for the GPU Admin module.
#   Controllers handle API endpoints for GPU node registration, WireGuard
#   peer management, and administrator actions.
#
# IMPORTANT:
#   This file was previously EMPTY, which meant that none of the GPU
#   admin controllers were being imported. This caused the
#   /api/v1/gpu/register endpoint to be completely non-functional.
#
#   FIX: We now import the main controller to register all endpoints.
#
# =============================================================================

# Import the main controller which contains all GPU admin endpoints
# This registers routes like:
#   - /api/v1/gpu/register (GPU node registration)
#   - /api/v1/gpu/peers (WireGuard peer list)
#   - /api/v1/admin/scan_network (network discovery)
#   - /api/v1/admin/install_node (remote node installation)
#   - /api/v1/admin/remove_node (node removal)
#   - /api/v1/admin/finetune/start (fine-tuning job submission)
#   - /api/v1/admin/finetune/status (fine-tuning job status)
#   - /api/v1/admin/finetune/deploy (model deployment)
from . import main

# Note: client_registration.py is dead/legacy code that references
# non-existent ai.gpu.* models. It is NOT imported here.
# It should be deleted from the repository.
#
# The main.py controller is the correct one for all GPU admin endpoints.