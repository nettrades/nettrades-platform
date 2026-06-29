#!/bin/bash
# =============================================================================
# FILE: scripts/create-nettrades-projects.sh
# =============================================================================
# PURPOSE:
#   Creates the full folder structure for nettrades-platform, clones external
#   repositories, writes small configuration files, and adapts LLM module
#   manifests for Odoo 19.
#
#   The directory structure follows the dual‑licensing layout:
#     src/          – AGPL‑3.0 (your original code)
#     odoo-modules/ – LGPL‑3.0 (your Odoo plugins)
#     third-party/  – UNMODIFIED third‑party code
#     deploy/       – AGPL‑3.0 (deployment configs)
#     docs/         – documentation and legal agreements
#     scripts/      – build and setup scripts
#
# MODULES CREATED:
#   - nettrades_core              (core platform logic)
#   - nettrades_good_answer       (quality voting system)
#   - nettrades_ask_someone       (expert marketplace)
#   - nettrades_gpu_admin         (GPU cluster management with token registration)
#   - nettrades_bridge            (hub‑and‑spoke routing)
#   - nettrades_data_collection   (self‑improving data collection)
#   - nettrades_trigger           (self‑improving triggers)
#   - nettrades_loop              (self‑improving loop)
#   - nettrades_self_improving_config (self‑improving configuration)
#   - nettrades_fairness          (fairness and bias evaluation)
#   - nettrades_gpustack_adapter  (GPUStack integration)
#   - nettrades_queue             (background job processing)
#   - nettrades_onboarding        (user onboarding)
#   - nettrades_job_matching      (AI‑powered job matching)
#   - nettrades_proposals         (proposal generation)
#   - nettrades_lead_scoring      (lead scoring)
#   - nettrades_research          (research assistant)
#   - nettrades_chatbot           (AI chatbot)
#   - nettrades_notifications     (notification system)
#   - nettrades_pwa               (Progressive Web App)
#
# USAGE:
#   ./create-nettrades-projects.sh
# =============================================================================

set -euo pipefail

BASE_DIR=$(pwd)

echo "============================================================="
echo "  NETTRADES.AI – Project Setup"
echo "============================================================="
echo ""

# -----------------------------------------------------------------------------
# 1. Create the main folder structure
# -----------------------------------------------------------------------------
echo "Creating nettrades-platform folder structure..."

# Top‑level directories
mkdir -p nettrades-platform/.vscode

# Your original code (AGPL‑3.0)
mkdir -p nettrades-platform/src/core/tools
mkdir -p nettrades-platform/src/core/agents
mkdir -p nettrades-platform/src/agent/modes
mkdir -p nettrades-platform/src/scripts

# Your Odoo plugins (LGPL‑3.0)
# Updated to include all new modules: bridge, fairness, self‑improving modules
for mod in \
    nettrades_core \
    nettrades_ask_someone \
    nettrades_good_answer \
    nettrades_gpu_admin \
    nettrades_gpustack_adapter \
    nettrades_queue \
    nettrades_bridge \
    nettrades_data_collection \
    nettrades_trigger \
    nettrades_loop \
    nettrades_self_improving_config \
    nettrades_fairness \
    nettrades_onboarding \
    nettrades_job_matching \
    nettrades_proposals \
    nettrades_lead_scoring \
    nettrades_research \
    nettrades_chatbot \
    nettrades_notifications \
    nettrades_pwa
do
    mkdir -p "nettrades-platform/odoo-modules/$mod/controllers"
    mkdir -p "nettrades-platform/odoo-modules/$mod/models"
    mkdir -p "nettrades-platform/odoo-modules/$mod/security"
    mkdir -p "nettrades-platform/odoo-modules/$mod/views"
done

# Extra folders for specific modules
mkdir -p nettrades-platform/odoo-modules/nettrades_core/data
mkdir -p nettrades-platform/odoo-modules/nettrades_good_answer/data
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/static/src/js
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/static/src/scss
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/data  # cron.xml
mkdir -p nettrades-platform/odoo-modules/nettrades_ask_someone/data  # expert agreement template
mkdir -p nettrades-platform/odoo-modules/nettrades_chatbot/static/src/js  # LLM message buttons
mkdir -p nettrades-platform/odoo-modules/nettrades_onboarding/templates
mkdir -p nettrades-platform/odoo-modules/nettrades_lead_scoring/data
mkdir -p nettrades-platform/odoo-modules/nettrades_pwa/static/src
mkdir -p nettrades-platform/odoo-modules/nettrades_pwa/templates
mkdir -p nettrades-platform/odoo-modules/nettrades_bridge/data
mkdir -p nettrades-platform/odoo-modules/nettrades_fairness/data
mkdir -p nettrades-platform/odoo-modules/nettrades_data_collection/data
mkdir -p nettrades-platform/odoo-modules/nettrades_trigger/data
mkdir -p nettrades-platform/odoo-modules/nettrades_loop/data
mkdir -p nettrades-platform/odoo-modules/nettrades_self_improving_config/data

# Third‑party code (unmodified)
mkdir -p nettrades-platform/third-party/odoo_llm_compat
mkdir -p nettrades-platform/third-party/payment_stripe_ce

# Deployment
mkdir -p nettrades-platform/deploy/docker/config
mkdir -p nettrades-platform/deploy/docker/backups
mkdir -p nettrades-platform/deploy/kubernetes/talos/talos-proxmox/patches
mkdir -p nettrades-platform/deploy/kubernetes/apps/frontend
mkdir -p nettrades-platform/deploy/kubernetes/apps/backend
mkdir -p nettrades-platform/deploy/kubernetes/apps/gpustack
mkdir -p nettrades-platform/deploy/kubernetes/apps/langgraph

# Documentation
mkdir -p nettrades-platform/docs/developer
mkdir -p nettrades-platform/docs/operations
mkdir -p nettrades-platform/docs/legal

# Scripts
mkdir -p nettrades-platform/scripts

echo "✅ Folder structure created."

# -----------------------------------------------------------------------------
# 2. Create a minimal __manifest__.py for each module (if missing)
# -----------------------------------------------------------------------------
echo "Creating minimal module manifests..."

for mod in \
    nettrades_core \
    nettrades_ask_someone \
    nettrades_good_answer \
    nettrades_gpu_admin \
    nettrades_gpustack_adapter \
    nettrades_queue \
    nettrades_bridge \
    nettrades_data_collection \
    nettrades_trigger \
    nettrades_loop \
    nettrades_self_improving_config \
    nettrades_fairness \
    nettrades_onboarding \
    nettrades_job_matching \
    nettrades_proposals \
    nettrades_lead_scoring \
    nettrades_research \
    nettrades_chatbot \
    nettrades_notifications \
    nettrades_pwa
do
    manifest_file="nettrades-platform/odoo-modules/$mod/__manifest__.py"
    if [ ! -f "$manifest_file" ]; then
        cat > "$manifest_file" << EOF
{
    'name': 'NETTRADES $mod',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'NETTRADES $mod module',
    'description': \"\"\"NETTRADES $mod module.\"\"\",
    'author': 'NETTRADES',
    'website': 'https://nettrades.ai',
    'depends': ['base'],
    'data': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
EOF
        echo "  Created $manifest_file"
    fi
done

echo "✅ Module manifests created."

# -----------------------------------------------------------------------------
# 3. Create a minimal __init__.py for each module
# -----------------------------------------------------------------------------
echo "Creating module __init__.py files..."

for mod in \
    nettrades_core \
    nettrades_ask_someone \
    nettrades_good_answer \
    nettrades_gpu_admin \
    nettrades_gpustack_adapter \
    nettrades_queue \
    nettrades_bridge \
    nettrades_data_collection \
    nettrades_trigger \
    nettrades_loop \
    nettrades_self_improving_config \
    nettrades_fairness \
    nettrades_onboarding \
    nettrades_job_matching \
    nettrades_proposals \
    nettrades_lead_scoring \
    nettrades_research \
    nettrades_chatbot \
    nettrades_notifications \
    nettrades_pwa
do
    init_file="nettrades-platform/odoo-modules/$mod/__init__.py"
    if [ ! -f "$init_file" ]; then
        cat > "$init_file" << EOF
# -*- coding: utf-8 -*-
from . import controllers
from . import models
EOF
        echo "  Created $init_file"
    fi
done

echo "✅ __init__.py files created."

# -----------------------------------------------------------------------------
# 4. Create placeholder files for subdirectories
# -----------------------------------------------------------------------------
echo "Creating placeholder files..."

for mod in \
    nettrades_core \
    nettrades_ask_someone \
    nettrades_good_answer \
    nettrades_gpu_admin \
    nettrades_gpustack_adapter \
    nettrades_queue \
    nettrades_bridge \
    nettrades_data_collection \
    nettrades_trigger \
    nettrades_loop \
    nettrades_self_improving_config \
    nettrades_fairness \
    nettrades_onboarding \
    nettrades_job_matching \
    nettrades_proposals \
    nettrades_lead_scoring \
    nettrades_research \
    nettrades_chatbot \
    nettrades_notifications \
    nettrades_pwa
do
    # controllers/__init__.py
    if [ ! -f "nettrades-platform/odoo-modules/$mod/controllers/__init__.py" ]; then
        echo "from . import main" > "nettrades-platform/odoo-modules/$mod/controllers/__init__.py"
    fi

    # models/__init__.py
    if [ ! -f "nettrades-platform/odoo-modules/$mod/models/__init__.py" ]; then
        echo "# Models for $mod" > "nettrades-platform/odoo-modules/$mod/models/__init__.py"
    fi

    # security/ir.model.access.csv
    if [ ! -f "nettrades-platform/odoo-modules/$mod/security/ir.model.access.csv" ]; then
        echo "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink" > "nettrades-platform/odoo-modules/$mod/security/ir.model.access.csv"
    fi
done

echo "✅ Placeholder files created."

# -----------------------------------------------------------------------------
# 5. Summary
# -----------------------------------------------------------------------------
echo ""
echo "============================================================="
echo "  Project setup complete!"
echo "============================================================="
echo ""
echo "Directory structure created at: nettrades-platform/"
echo ""
echo "Next steps:"
echo "  1. cd nettrades-platform"
echo "  2. Copy your Odoo modules into odoo-modules/"
echo "  3. Run the installation script: ./scripts/install-modules.sh"
echo "  4. Start the stack: cd deploy/docker && docker compose up -d"
echo ""
echo "Module list (20 modules):"
echo "  - nettrades_core"
echo "  - nettrades_ask_someone"
echo "  - nettrades_good_answer"
echo "  - nettrades_gpu_admin"
echo "  - nettrades_gpustack_adapter"
echo "  - nettrades_queue"
echo "  - nettrades_bridge"
echo "  - nettrades_data_collection"
echo "  - nettrades_trigger"
echo "  - nettrades_loop"
echo "  - nettrades_self_improving_config"
echo "  - nettrades_fairness"
echo "  - nettrades_onboarding"
echo "  - nettrades_job_matching"
echo "  - nettrades_proposals"
echo "  - nettrades_lead_scoring"
echo "  - nettrades_research"
echo "  - nettrades_chatbot"
echo "  - nettrades_notifications"
echo "  - nettrades_pwa"