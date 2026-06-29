#!/bin/bash
# =============================================================================
# FILE: scripts/install-modules.sh
# =============================================================================
# PURPOSE:
#   Installs all NETTRADES Odoo modules in the correct dependency order.
#   This script runs inside the Odoo container using docker exec.
#
#   It is idempotent and can be re-run safely. With --upgrade, it upgrades
#   existing modules; with --force, it reinstalls even if already installed.
#
# USAGE:
#   ./install-modules.sh [--force] [--upgrade]
#
# OPTIONS:
#   --force    Force installation even if modules are already installed
#   --upgrade  Upgrade existing modules to the latest version
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Colours for output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Module Installation${NC}"
echo -e "${GREEN}============================================================${NC}"

# -----------------------------------------------------------------------------
# Get the directory of this script and change to project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 1

# -----------------------------------------------------------------------------
# Parse command-line arguments
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Check if Odoo container is running
# -----------------------------------------------------------------------------
if ! docker ps | grep -q odoo; then
    echo -e "${RED}Error: Odoo container is not running.${NC}"
    echo "Please start the stack with: docker compose up -d"
    exit 1
fi

# -----------------------------------------------------------------------------
# Define module installation order (dependencies first)
# -----------------------------------------------------------------------------
MODULES=(
    # Core NETTRADES modules
    "nettrades_core"
    "nettrades_good_answer"
    "nettrades_ask_someone"

    # GPU Admin module
    "nettrades_gpu_admin"

    # GPUStack adapter
    "nettrades_gpustack_adapter"

    # Queue module
    "nettrades_queue"

    # Bridge module – hub-and-spoke routing
    "nettrades_bridge"

    # Self-improving modules – continuous learning loop (MAPE cycle)
    "nettrades_data_collection"
    "nettrades_trigger"
    "nettrades_loop"
    "nettrades_self_improving_config"

    # Fairness module
    "nettrades_fairness"

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

# -----------------------------------------------------------------------------
# Function to install or upgrade a single module
# -----------------------------------------------------------------------------
install_module() {
    local module=$1
    local action="install"

    if [ "$UPGRADE" = true ] || [ "$FORCE" = true ]; then
        action="upgrade"
        local flag="-u"
    else
        local flag="-i"
    fi

    echo -e "${YELLOW}${action^}ing module: $module${NC}"

    # Run the Odoo command
    if docker exec -it odoo python3 /usr/bin/odoo \
        -c /etc/odoo/odoo.conf \
        "$flag" "$module" \
        --stop-after-init; then
        echo -e "${GREEN}✓ Module $module ${action}ed successfully${NC}"
        return 0
    else
        echo -e "${RED}✗ Module $module ${action} failed${NC}"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main installation loop
# -----------------------------------------------------------------------------
FAILED_MODULES=()

for module in "${MODULES[@]}"; do
    if ! install_module "$module"; then
        FAILED_MODULES+=("$module")
    fi
done

echo -e "${GREEN}============================================================${NC}"

if [ ${#FAILED_MODULES[@]} -eq 0 ]; then
    echo -e "${GREEN}All modules installed successfully!${NC}"
else
    echo -e "${RED}The following modules failed: ${FAILED_MODULES[*]}${NC}"
    echo "Please check the logs and try again."
    exit 1
fi

echo -e "${GREEN}============================================================${NC}"

echo ""
echo "Next steps:"
echo "  1. Configure fairness settings: Settings → Technical → Fairness → Global Configuration"
echo "  2. Run an audit at: Settings → Technical → Fairness → Dashboard"
echo "  3. Configure GPU registration tokens: GPU → Registration Tokens"
echo "  4. Set up bridge routing: Settings → Technical → Bridge → Global Configuration"