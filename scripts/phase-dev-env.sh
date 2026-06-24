#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 1: Development Environment Setup (UPDATED)
# =============================================================================
# FILE: scripts/phase-dev-env.sh
#
# PURPOSE:
#   This script sets up the development environment for the NETTRADES platform.
#   It scaffolds the project, clones repositories, and installs dependencies.
#
# PHASE 1 STEPS:
#   1. Create project directory structure
#   2. Clone Odoo 19 CE and third-party dependencies
#   3. Clone custom NETTRADES modules
#   4. Install Python dependencies
#   5. Set up PostgreSQL database
#   6. Configure Odoo for development
#
# UPDATED:
#   - Added fairness module to the list of custom modules
#   - Added self-improving modules (data_collection, trigger, loop, config)
#   - Added bridge module for hub-and-spoke routing
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Phase 1: Development Environment${NC}"
echo -e "${GREEN}============================================================${NC}"

# =============================================================================
# 1. Create Project Directory Structure
# =============================================================================
echo -e "${YELLOW}Creating project directory structure...${NC}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Create directory structure
mkdir -p third-party
mkdir -p odoo-modules
mkdir -p src/core/agents
mkdir -p src/agent
mkdir -p deploy/docker/config
mkdir -p scripts

echo -e "${GREEN}✓ Directory structure created${NC}"

# =============================================================================
# 2. Clone Odoo 19 CE
# =============================================================================
echo -e "${YELLOW}Cloning Odoo 19 CE...${NC}"

if [ ! -d "third-party/odoo" ]; then
    git clone --branch 19.0 --depth 1 https://github.com/odoo/odoo.git third-party/odoo
    echo -e "${GREEN}✓ Odoo 19 CE cloned${NC}"
else
    echo -e "${GREEN}✓ Odoo 19 CE already exists${NC}"
fi

# =============================================================================
# 3. Clone Third-Party Dependencies
# =============================================================================
echo -e "${YELLOW}Cloning third-party dependencies...${NC}"

# Apexive LLM modules
if [ ! -d "third-party/odoo_llm" ]; then
    git clone --branch 19.0 --depth 1 https://github.com/apexive/odoo-llm.git third-party/odoo_llm
    echo -e "${GREEN}✓ Apexive LLM modules cloned${NC}"
else
    echo -e "${GREEN}✓ Apexive LLM modules already exist${NC}"
fi

# website_sale_marketplace
if [ ! -d "third-party/website_sale_marketplace" ]; then
    git clone --branch 19.0 --depth 1 https://github.com/erpgap/website_sale_marketplace.git third-party/website_sale_marketplace
    echo -e "${GREEN}✓ website_sale_marketplace cloned${NC}"
else
    echo -e "${GREEN}✓ website_sale_marketplace already exists${NC}"
fi

# queue_job
if [ ! -d "third-party/queue_job" ]; then
    git clone --branch 19.0 --depth 1 https://github.com/OCA/queue.git third-party/queue_job
    echo -e "${GREEN}✓ queue_job cloned${NC}"
else
    echo -e "${GREEN}✓ queue_job already exists${NC}"
fi

# MCP-Odoo bridge
if [ ! -d "third-party/mcp-odoo" ]; then
    git clone --branch main --depth 1 https://github.com/fgribreau/mcp-odoo.git third-party/mcp-odoo
    echo -e "${GREEN}✓ MCP-Odoo bridge cloned${NC}"
else
    echo -e "${GREEN}✓ MCP-Odoo bridge already exists${NC}"
fi

# =============================================================================
# 4. Create Custom NETTRADES Modules
# =============================================================================
echo -e "${YELLOW}Creating custom NETTRADES modules...${NC}"

# List of custom modules to create
CUSTOM_MODULES=(
    "nettrades_core"
    "nettrades_good_answer"
    "nettrades_ask_someone"
    "nettrades_gpu_admin"
    "nettrades_gpustack_adapter"
    "nettrades_queue"
    "nettrades_onboarding"
    "nettrades_job_matching"
    "nettrades_proposals"
    "nettrades_lead_scoring"
    "nettrades_research"
    "nettrades_chatbot"
    "nettrades_notifications"
    "nettrades_pwa"
    "nettrades_bridge"                      # NEW: Hub-and-spoke routing
    "nettrades_data_collection"             # NEW: Monitor phase
    "nettrades_trigger"                     # NEW: Analyze phase
    "nettrades_loop"                        # NEW: Plan + Execute phase
    "nettrades_self_improving_config"       # NEW: Admin interface
    "nettrades_fairness"                    # NEW: Fairness & bias detection
)

for module in "${CUSTOM_MODULES[@]}"; do
    if [ ! -d "odoo-modules/$module" ]; then
        mkdir -p "odoo-modules/$module"
        mkdir -p "odoo-modules/$module/models"
        mkdir -p "odoo-modules/$module/views"
        mkdir -p "odoo-modules/$module/security"
        mkdir -p "odoo-modules/$module/controllers"
        mkdir -p "odoo-modules/$module/data"
        mkdir -p "odoo-modules/$module/wizards"
        touch "odoo-modules/$module/__init__.py"
        echo -e "${GREEN}✓ Created module: $module${NC}"
    else
        echo -e "${GREEN}✓ Module already exists: $module${NC}"
    fi
done

# =============================================================================
# 5. Install Python Dependencies
# =============================================================================
echo -e "${YELLOW}Installing Python dependencies...${NC}"

if [ -f "requirements-dev.txt" ]; then
    pip install -r requirements-dev.txt
    echo -e "${GREEN}✓ Development dependencies installed${NC}"
fi

if [ -f "src/core/requirements.txt" ]; then
    pip install -r src/core/requirements.txt
    echo -e "${GREEN}✓ Core dependencies installed${NC}"
fi

# Install fairness evaluation dependencies
echo -e "${YELLOW}Installing fairness evaluation dependencies...${NC}"
pip install pandas numpy scikit-learn 2>/dev/null || echo "Some fairness dependencies failed to install"
echo -e "${GREEN}✓ Fairness dependencies installed${NC}"

# =============================================================================
# 6. Set Up PostgreSQL Database
# =============================================================================
echo -e "${YELLOW}Setting up PostgreSQL database...${NC}"

# Check if PostgreSQL is running
if command -v psql &> /dev/null; then
    # Create odoo user and database
    sudo -u postgres psql -c "CREATE USER odoo WITH PASSWORD 'Password123';" 2>/dev/null || echo "User odoo already exists"
    sudo -u postgres psql -c "CREATE DATABASE nettrades OWNER odoo;" 2>/dev/null || echo "Database nettrades already exists"
    echo -e "${GREEN}✓ PostgreSQL database configured${NC}"
else
    echo -e "${YELLOW}⚠ PostgreSQL not found. Please install PostgreSQL 18+ manually.${NC}"
fi

# =============================================================================
# 7. Configure Odoo for Development
# =============================================================================
echo -e "${YELLOW}Configuring Odoo for development...${NC}"

# Create odoo.conf
cat > deploy/docker/config/odoo.conf << 'EOF'
[options]
admin_passwd = admin
db_host = localhost
db_port = 5432
db_user = odoo
db_password = Password123
db_name = nettrades

# Addons path – includes all custom NETTRADES modules
addons_path = ./odoo-modules/nettrades_core,./odoo-modules/nettrades_good_answer,./odoo-modules/nettrades_ask_someone,./odoo-modules/nettrades_gpu_admin,./odoo-modules/nettrades_gpustack_adapter,./odoo-modules/nettrades_queue,./odoo-modules/nettrades_onboarding,./odoo-modules/nettrades_job_matching,./odoo-modules/nettrades_proposals,./odoo-modules/nettrades_lead_scoring,./odoo-modules/nettrades_research,./odoo-modules/nettrades_chatbot,./odoo-modules/nettrades_notifications,./odoo-modules/nettrades_pwa,./odoo-modules/nettrades_bridge,./odoo-modules/nettrades_data_collection,./odoo-modules/nettrades_trigger,./odoo-modules/nettrades_loop,./odoo-modules/nettrades_self_improving_config,./odoo-modules/nettrades_fairness,./third-party/odoo/addons,./third-party/odoo_llm,./third-party/odoo_llm_compat,./third-party/website_sale_marketplace,./third-party/queue_job

# Development settings
workers = 0
log_level = info
EOF

echo -e "${GREEN}✓ Odoo configuration created${NC}"

# =============================================================================
# 8. Create VS Code Launch Configuration
# =============================================================================
echo -e "${YELLOW}Creating VS Code launch configuration...${NC}"

mkdir -p .vscode
cat > .vscode/launch.json << 'EOF'
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Odoo",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/third-party/odoo/odoo-bin",
            "args": [
                "-c",
                "${workspaceFolder}/deploy/docker/config/odoo.conf"
            ],
            "console": "integratedTerminal",
            "justMyCode": false
        }
    ]
}
EOF

echo -e "${GREEN}✓ VS Code launch configuration created${NC}"

# =============================================================================
# 9. Complete
# =============================================================================
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}Phase 1 complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Next steps:"
echo "1. Start Odoo: python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf"
echo "2. Open http://localhost:8069"
echo "3. Install the NETTRADES modules in the correct order"
echo ""
echo "Module installation order:"
echo "  1. nettrades_core"
echo "  2. nettrades_good_answer"
echo "  3. nettrades_ask_someone"
echo "  4. nettrades_gpu_admin"
echo "  5. nettrades_gpustack_adapter"
echo "  6. nettrades_queue"
echo "  7. nettrades_bridge"
echo "  8. nettrades_data_collection"
echo "  9. nettrades_trigger"
echo " 10. nettrades_loop"
echo " 11. nettrades_self_improving_config"
echo " 12. nettrades_fairness"
echo " 13. nettrades_onboarding"
echo " 14. nettrades_job_matching"
echo " 15. nettrades_proposals"
echo " 16. nettrades_lead_scoring"
echo " 17. nettrades_research"
echo " 18. nettrades_chatbot"
echo " 19. nettrades_notifications"
echo " 20. nettrades_pwa"