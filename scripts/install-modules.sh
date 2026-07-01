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
#   ./install-modules.sh [--force] [--upgrade] [--auto]
#
# OPTIONS:
#   --force    Force installation even if modules are already installed
#   --upgrade  Upgrade existing modules to the latest version
#   --auto     Run in non-interactive mode (no prompts)
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Colours for output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Module Installation${NC}"
echo -e "${GREEN}=============================================================${NC}"

# -----------------------------------------------------------------------------
# Get the directory of this script and change to project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# -----------------------------------------------------------------------------
# Parse command-line arguments
# -----------------------------------------------------------------------------
FORCE=false
UPGRADE=false
AUTO=false

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
        --auto)
            AUTO=true
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Load POSTGRES_PASSWORD from .env
# -----------------------------------------------------------------------------
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    POSTGRES_PASSWORD=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
    if [ -z "$POSTGRES_PASSWORD" ]; then
        log_error "POSTGRES_PASSWORD not found in $ENV_FILE"
        exit 1
    fi
else
    log_error ".env file not found at $ENV_FILE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Check if Odoo container is running
# -----------------------------------------------------------------------------
if ! docker ps | grep -q odoo; then
    log_error "Odoo container is not running."
    log_info "Please start the stack with: docker compose up -d"
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

    # LLM Configuration (depends on gpu_admin)
    "nettrades_llm_config"

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
    local flag="-i"

    if [ "$UPGRADE" = true ]; then
        action="upgrade"
        flag="-u"
    else
        action="install"
        flag="-i"
    fi
# --upgrade → uses -u (upgrade existing modules).
# --force (without --upgrade) → uses -i (install, even if already installed, but reinstall).
# No flags → uses -i (install).

    log_info "${action^}ing module: $module"

    # Correct flags: underscore, not hyphen
    if docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" \
        odoo python3 /usr/bin/odoo \
        -c /etc/odoo/odoo.conf \
        --db_host=postgres \
        --db_port=5432 \
        --db_user=odoo \
        --db_password="$POSTGRES_PASSWORD" \
        -d odoo \
        "$flag" "$module" \
        --stop-after-init 2>&1; then
        log_success "✓ Module $module ${action}ed successfully"
        return 0
    else
        log_error "✗ Module $module ${action} failed"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main installation loop
# -----------------------------------------------------------------------------
FAILED_MODULES=()
TOTAL_MODULES=${#MODULES[@]}
CURRENT=0

log_info "Starting installation of $TOTAL_MODULES modules..."

for module in "${MODULES[@]}"; do
    CURRENT=$((CURRENT + 1))
    log_info "[$CURRENT/$TOTAL_MODULES] Processing module: $module"
    if ! install_module "$module"; then
        FAILED_MODULES+=("$module")
        if [ "$AUTO" != true ]; then
            log_warning "Module $module failed. Continue? (y/N): "
            read -r continue_anyway
            if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                log_error "Aborting installation."
                exit 1
            fi
        fi
    fi
done

echo -e "${GREEN}=============================================================${NC}"

if [ ${#FAILED_MODULES[@]} -eq 0 ]; then
    log_success "All modules installed successfully!"
else
    log_error "The following modules failed: ${FAILED_MODULES[*]}"
    log_info "Check the logs and try again with: ./scripts/install-modules.sh --force"
    exit 1
fi

echo -e "${GREEN}=============================================================${NC}"
echo ""
log_info "Next steps:"
echo "  1. Configure fairness settings: Settings → Technical → Fairness → Global Configuration"
echo "  2. Run an audit at: Settings → Technical → Fairness → Dashboard"
echo "  3. Configure GPU registration tokens: GPU → Registration Tokens"
echo "  4. Set up bridge routing: Settings → Technical → Bridge → Global Configuration"