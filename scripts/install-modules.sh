#!/bin/bash
# =============================================================================
# FILE: scripts/install-modules.sh
# =============================================================================
# PURPOSE:
#   Installs all NETTRADES Odoo modules in the correct dependency order.
#   This script runs inside the Odoo container using docker exec.
#
# MODULES INSTALLED:
#   Core: nettrades_core, nettrades_good_answer, nettrades_ask_someone
#   GPU: nettrades_gpu_admin, nettrades_gpustack_adapter
#   Queue: nettrades_queue
#   Bridge: nettrades_bridge (hub-and-spoke routing)
#   Self-improving: nettrades_data_collection, nettrades_trigger,
#                   nettrades_loop, nettrades_self_improving_config
#   Fairness: nettrades_fairness
#   End-user: nettrades_onboarding, nettrades_job_matching, nettrades_proposals,
#             nettrades_lead_scoring, nettrades_research, nettrades_chatbot,
#             nettrades_notifications, nettrades_pwa
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
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Module Installation${NC}"
echo -e "${GREEN}============================================================${NC}"

# -----------------------------------------------------------------------------
# Get the directory of this script and change to project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." # Go to project root

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
    # Core NETTRADES modules – must be installed first
    "nettrades_core"
    "nettrades_good_answer"
    "nettrades_ask_someone"

    # GPU Admin module – token‑based registration for GPU nodes
    "nettrades_gpu_admin"

    # GPUStack adapter – integration with GPUStack for inference
    "nettrades_gpustack_adapter"

    # Queue module – background job processing
    "nettrades_queue"

    # Bridge module – hub‑and‑spoke routing between local and remote AI brains
    "nettrades_bridge"

    # Self‑improving modules – continuous learning loop (MAPE cycle)
    "nettrades_data_collection"      # Collects interaction episodes
    "nettrades_trigger"              # Triggers self‑improvement cycles
    "nettrades_loop"                 # Runs the self‑improvement loop
    "nettrades_self_improving_config" # Configuration for self‑improving

    # Fairness module – bias detection and evaluation
    "nettrades_fairness"

    # End‑user modules
    "nettrades_onboarding"           # User onboarding flows
    "nettrades_job_matching"         # AI‑powered job matching
    "nettrades_proposals"            # Proposal generation
    "nettrades_lead_scoring"         # Lead scoring and prioritisation
    "nettrades_research"             # Research assistant
    "nettrades_chatbot"              # AI chatbot for user queries
    "nettrades_notifications"        # Notification system
    "nettrades_pwa"                  # Progressive Web App support
)

# -----------------------------------------------------------------------------
# Parse command‑line arguments
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
# Function to install a single module
# -----------------------------------------------------------------------------
install_module() {
    local module=$1
    echo -e "${YELLOW}Installing module: $module${NC}"

    if [ "$UPGRADE" = true ]; then
        # Upgrade existing module
        docker exec -it odoo python3 /usr/bin/odoo \
            -c /etc/odoo/odoo.conf \
            -u "$module" \
            --stop-after-init
    else
        # Install new module
        docker exec -it odoo python3 /usr/bin/odoo \
            -c /etc/odoo/odoo.conf \
            -i "$module" \
            --stop-after-init
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Module $module installed successfully${NC}"
    else
        echo -e "${RED}✗ Module $module installation failed${NC}"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Main installation loop
# -----------------------------------------------------------------------------
for module in "${MODULES[@]}"; do
    install_module "$module"
done

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}All modules installed successfully!${NC}"
echo -e "${GREEN}============================================================${NC}"

echo ""
echo "Next steps:"
echo "  1. Configure fairness settings at: Settings → Technical → Fairness → Global Configuration"
echo "  2. Run an audit at: Settings → Technical → Fairness → Dashboard"
echo "  3. Monitor flags at: Settings → Technical → Fairness → Flags"
echo "  4. Configure GPU registration tokens at: GPU → Registration Tokens"
echo "  5. Set up bridge routing at: Bridge → Configuration"
echo "  6. Check the self‑improving loop at: Settings → Technical → Self‑Improving → Dashboard"