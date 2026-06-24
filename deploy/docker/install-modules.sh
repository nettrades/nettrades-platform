#!/bin/bash
# =============================================================================
# NETTRADES.AI – Module Installation Script
# =============================================================================
# FILE: deploy/docker/install-modules.sh
#
# PURPOSE:
#   This script installs all NETTRADES Odoo modules in the correct order.
#   It handles dependencies and ensures a clean installation.
#
# USAGE:
#   ./install-modules.sh [--force] [--upgrade]
#
# OPTIONS:
#   --force    Force installation even if modules are already installed
#   --upgrade  Upgrade existing modules
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Module Installation${NC}"
echo -e "${GREEN}============================================================${NC}"

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../.."  # Go to project root

# Check if Odoo is running
if ! docker ps | grep -q odoo; then
    echo -e "${RED}Error: Odoo container is not running.${NC}"
    echo "Please start the stack with: docker compose up -d"
    exit 1
fi

# Define module installation order
MODULES=(
    # Core NETTRADES modules
    "nettrades_core"
    "nettrades_good_answer"
    "nettrades_ask_someone"
    "nettrades_gpu_admin"
    "nettrades_gpustack_adapter"
    "nettrades_queue"

    # Bridge and self-improving modules
    "nettrades_bridge"
    "nettrades_data_collection"
    "nettrades_trigger"
    "nettrades_loop"
    "nettrades_self_improving_config"

    # End-user modules
    "nettrades_onboarding"
    "nettrades_job_matching"
    "nettrades_proposals"
    "nettrades_lead_scoring"
    "nettrades_research"
    "nettrades_chatbot"
    "nettrades_notifications"
    "nettrades_pwa"
)

# Parse arguments
FORCE=false
UPGRADE=false

for arg in "$@"; do
    case $arg in
        --force)
            FORCE=true
            shift
            ;;
        --upgrade)
            UPGRADE=true
            shift
            ;;
    esac
done

# Function to install a module
install_module() {
    local module=$1
    echo -e "${YELLOW}Installing module: $module${NC}"

    if [ "$UPGRADE" = true ]; then
        docker exec -it odoo python3 /usr/bin/odoo -c /etc/odoo/odoo.conf -u "$module" --stop-after-init
    else
        docker exec -it odoo python3 /usr/bin/odoo -c /etc/odoo/odoo.conf -i "$module" --stop-after-init
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Module $module installed successfully${NC}"
    else
        echo -e "${RED}✗ Module $module installation failed${NC}"
        exit 1
    fi
}

# Main installation loop
for module in "${MODULES[@]}"; do
    install_module "$module"
done

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}All modules installed successfully!${NC}"
echo -e "${GREEN}============================================================${NC}"