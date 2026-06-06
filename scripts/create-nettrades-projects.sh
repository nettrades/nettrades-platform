#!/bin/bash
# =============================================================================
# NETTRADES.AI – Complete project scaffolding (final, multimodal edition)
# =============================================================================
# Creates the full folder structure for nettrades-platform, clones external
# repositories, writes small configuration files, and adapts LLM module
# manifests for Odoo 19.
#
# The directory structure follows the dual-licensing layout:
#   src/          – AGPL-3.0 (your original code)
#   odoo-modules/ – LGPL-3.0 (your Odoo plugins)
#   third-party/  – UNMODIFIED third-party code
#   deploy/       – AGPL-3.0 (deployment configs)
#   docs/         – documentation and legal agreements
#   scripts/      – build and setup scripts
# =============================================================================
set -euo pipefail

BASE_DIR=$(pwd)

echo "============================================================="
echo " NETTRADES.AI – Project Setup"
echo "============================================================="
echo ""

# ---------------------------------------------------------------------------
# 1. nettrades-platform – full folder tree
# ---------------------------------------------------------------------------
echo "Creating nettrades-platform folder structure..."

# Top-level
mkdir -p nettrades-platform/.vscode

# Your original code (AGPL-3.0)
mkdir -p nettrades-platform/src/core/tools
mkdir -p nettrades-platform/src/core/agents
mkdir -p nettrades-platform/src/agent/modes
mkdir -p nettrades-platform/src/scripts

# Your Odoo plugins (LGPL-3.0)
for mod in nettrades_core nettrades_ask_someone nettrades_good_answer \
           nettrades_gpu_admin nettrades_gpustack_adapter nettrades_queue \
           nettrades_onboarding nettrades_job_matching nettrades_proposals \
           nettrades_lead_scoring nettrades_research nettrades_chatbot \
           nettrades_notifications nettrades_pwa; do
    mkdir -p "nettrades-platform/odoo-modules/$mod/controllers"
    mkdir -p "nettrades-platform/odoo-modules/$mod/models"
    mkdir -p "nettrades-platform/odoo-modules/$mod/security"
    mkdir -p "nettrades-platform/odoo-modules/$mod/views"
done

# Extra folders for some modules
mkdir -p nettrades-platform/odoo-modules/nettrades_core/data
mkdir -p nettrades-platform/odoo-modules/nettrades_good_answer/data
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/static/src/js
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/static/src/scss
mkdir -p nettrades-platform/odoo-modules/nettrades_gpu_admin/data          # cron.xml
mkdir -p nettrades-platform/odoo-modules/nettrades_ask_someone/data        # expert agreement template
mkdir -p nettrades-platform/odoo-modules/nettrades_chatbot/static/src/js   # llm message buttons
mkdir -p nettrades-platform/odoo-modules/nettrades_onboarding/templates
mkdir -p nettrades-platform/odoo-modules/nettrades_lead_scoring/data
mkdir -p nettrades-platform/odoo-modules/nettrades_pwa/static/src
mkdir -p nettrades-platform/odoo-modules/nettrades_pwa/templates

# Third-party code (unmodified)
mkdir -p nettrades-platform/third-party/odoo_llm_compat
mkdir -p nettrades-platform/third-party/payment_stripe_ce

# Deployment
mkdir -p nettrades-platform/deploy/docker/config
mkdir -p nettrades-platform/deploy/docker/backups
mkdir -p nettrades-platform/deploy/kubernetes/talos/talos-proxmox/patches
mkdir -p nettrades-platform/deploy/kubernetes/apps/frontend
mkdir -p nettrades-platform/deploy/kubernetes/apps/backend
mkdir -p nettrades-platform/deploy/kubernetes/apps/ai
mkdir -p nettrades-platform/deploy/kubernetes/apps/forgejo
mkdir -p nettrades-platform/deploy/kubernetes/apps/gpustack
mkdir -p nettrades-platform/deploy/kubernetes/apps/monitoring
mkdir -p nettrades-platform/deploy/kubernetes/apps/registry
mkdir -p nettrades-platform/deploy/kubernetes/apps/runners
mkdir -p nettrades-platform/deploy/kubernetes/distributed-gpu/controller/wg-peer-manager
mkdir -p nettrades-platform/deploy/kubernetes/ingress
mkdir -p nettrades-platform/deploy/kubernetes/argocd

# Docs
mkdir -p nettrades-platform/docs/architecture

# ---------------------------------------------------------------------------
# 2. Clone external repositories (into third-party/)
# ---------------------------------------------------------------------------
echo "Cloning Odoo 19 Community Edition..."
if [ ! -d nettrades-platform/third-party/odoo/.git ]; then
    git clone https://github.com/odoo/odoo.git --branch 19.0 --depth 1 \
        nettrades-platform/third-party/odoo
else
    echo "  Odoo already exists – skipping."
fi

echo "Cloning website_sale_marketplace..."
if [ ! -d nettrades-platform/third-party/website_sale_marketplace/.git ]; then
    git clone https://github.com/erpgap/website_sale_marketplace.git \
        nettrades-platform/third-party/website_sale_marketplace
    mv nettrades-platform/third-party/website_sale_marketplace/website_sale_marketplace/* \
       nettrades-platform/third-party/website_sale_marketplace/
    rmdir nettrades-platform/third-party/website_sale_marketplace/website_sale_marketplace
else
    echo "  website_sale_marketplace already exists – skipping."
fi

echo "Setting up apexive/odoo-llm..."
if [ ! -d nettrades-platform/third-party/odoo_llm/.git ]; then
    git clone --branch 19.0 https://github.com/apexive/odoo-llm.git \
        nettrades-platform/third-party/odoo_llm
    git clone --branch 18.0 https://github.com/apexive/odoo-llm.git \
        nettrades-platform/third-party/odoo_llm_18

    find nettrades-platform/third-party/odoo_llm_18 -name '__manifest__.py' | while read manifest; do
        sed -i "s/'version': '18\.0\.[0-9.]*'/'version': '19.0.1.0.0'/" "$manifest"
    done

    moved=0
    for mod in nettrades-platform/third-party/odoo_llm_18/*/; do
        mod_name=$(basename "$mod")
        [[ "$mod_name" == ".claude" || "$mod_name" == ".git" ]] && continue
        if [ ! -d "nettrades-platform/third-party/odoo_llm/$mod_name" ]; then
            cp -r "$mod" "nettrades-platform/third-party/odoo_llm/"
            rm -rf "$mod"
            moved=$((moved + 1))
        fi
    done
    echo "  Added $moved new modules from 18.0."
    rm -rf nettrades-platform/third-party/odoo_llm_18
else
    echo "  odoo_llm already exists – skipping."
fi

echo "Cloning MCP-Odoo bridge..."
if [ -d nettrades-platform/third-party/mcp-odoo/.git ]; then
    cd nettrades-platform/third-party/mcp-odoo && git pull && cd "$BASE_DIR"
else
    git clone https://github.com/bmya/claude-odoo-api.git \
        nettrades-platform/third-party/mcp-odoo
fi

# ---------------------------------------------------------------------------
# 3. Write small files for nettrades-platform
# ---------------------------------------------------------------------------
echo "Writing configuration files..."

# .vscode/launch.json
cat > nettrades-platform/.vscode/launch.json << 'EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Odoo",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceRoot}/third-party/odoo/odoo-bin",
            "args": ["-c", "${workspaceFolder}/deploy/docker/config/odoo.conf"],
            "gevent": false,
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
EOF

# requirements-dev.txt
cat > nettrades-platform/requirements-dev.txt << 'EOF'
requests>=2.28
psutil
python-dotenv
pyyaml
fastapi
uvicorn
langgraph>=1.2.0
langgraph-checkpoint-postgres>=3.0.3
langchain-openai>=0.1.0
httpx
prometheus-client>=0.20.0
EOF

# README.md
cat > nettrades-platform/README.md << 'EOF'
# NETTRADES.AI Platform

The open-source autonomous enterprise platform — matching talent, running AI on your
own hardware, and continuously improving.

## Quick Start
1. Run `./scripts/create-nettrades-projects.sh` to scaffold the project.
2. Run `./scripts/nettrades-setup.sh` and select Phase 1 for a dev environment.
3. Start Odoo 19 CE and install the modules.
EOF

# Root LICENSE.txt
cat > nettrades-platform/LICENSE.txt << 'EOF'
This project contains multiple components, each with its own license:

  src/             – AGPL-3.0 (GNU Affero General Public License v3)
  odoo-modules/    – LGPL-3.0 (GNU Lesser General Public License v3)
  third-party/     – see OPEN-SOURCE-NOTICES.txt for individual licenses
  deploy/          – AGPL-3.0
  docs/            – Creative Commons Attribution 4.0
  scripts/         – MIT

A commercial license for AGPL-free use of src/ is available from
NETTRADES AI (PVT) LIMITED.  Contact licensing@nettrades.ai.
EOF

# .gitignore
cat > nettrades-platform/.gitignore << 'EOF'
__pycache__/
*.py[cod]
*.egg-info/
odoo/session/
odoo/filestore/
.vscode/
.idea/
.env
*.key
*.pem
postgres-data/
odoo-data/
forgejo-data/
llama-cpp-data/
gpustack-data/
valkey-data/
traefik-data/
prometheus-data/
grafana-data/
backups/
*.log
EOF

# --- Create empty __init__.py files for all Odoo modules ---
for dir in nettrades-platform/odoo-modules/*/; do
    touch "${dir}__init__.py"
    for sub in controllers models; do
        [ -d "${dir}$sub" ] && touch "${dir}${sub}/__init__.py"
    done
done

# --- Write placeholder stubs for large files that need the full code later ---
for stub_file in \
    nettrades-platform/src/core/app.py \
    nettrades-platform/src/core/supervisor.py \
    nettrades-platform/src/core/tools/odoo_tools.py \
    nettrades-platform/src/core/tools/inference_tools.py \
    nettrades-platform/src/core/agents/recruitment_agent.py \
    nettrades-platform/src/core/agents/freelance_agent.py \
    nettrades-platform/src/core/agents/lead_gen_agent.py \
    nettrades-platform/src/core/agents/gpu_management_agent.py \
    nettrades-platform/src/core/agents/vision_agent.py \
    nettrades-platform/src/core/agents/action_agent.py \
    nettrades-platform/src/core/tools/ros2_tools.py \
    nettrades-platform/src/core/tools/iot_tools.py \
    nettrades-platform/src/agent/agent.py \
    nettrades-platform/src/agent/wg_dns_watchdog.py \
    nettrades-platform/src/agent/tee_detect.py \
    nettrades-platform/src/agent/edge_detect.py \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/controllers/main.py \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/models/gpu_node.py \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/views/gpu_cluster_views.xml \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/views/gpu_dashboard_templates.xml \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/static/src/js/dashboard.js \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/models/multimodal_config.py \
    nettrades-platform/odoo-modules/nettrades_gpu_admin/views/multimodal_config_views.xml; do
    echo "// PLACEHOLDER – Replace with full code from the conversation." > "$stub_file"
done

# License stubs
for lic in nettrades-platform/src/LICENSE.txt \
           nettrades-platform/odoo-modules/LICENSE.txt \
           nettrades-platform/deploy/LICENSE.txt; do
    [ ! -f "$lic" ] && echo "// License text placeholder." > "$lic"
done

echo ""
echo "============================================================="
echo " Scaffold complete."
echo "============================================================="
echo " Run the orchestrator to set up your environment:"
echo "   ./scripts/nettrades-setup.sh"