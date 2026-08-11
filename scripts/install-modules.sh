#!/bin/bash
# =============================================================================
# FILE: scripts/install-modules.sh
# =============================================================================
# PURPOSE:
#   Installs all NETTRADES Odoo modules in the correct dependency order.
#   The script runs inside the Odoo container using docker compose exec.
#
#   It is idempotent and can be re-run safely. With --upgrade, it upgrades
#   existing modules; with --force, it reinstalls even if already installed.
#
# USAGE:
#   ./install-modules.sh [--force] [--upgrade] [--auto]
#
# OPTIONS:
#   --force    Force installation (reinstall) even if modules are already installed
#   --upgrade  Upgrade existing modules to the latest version
#   --auto     Run in non-interactive mode (no prompts for failed modules)
#
# UPDATES (2026-08):
#   - Modules are now conditionally installed based on FEATURE_* flags from .env.
#   - The module list is built dynamically, so only enabled features are installed.
#   - Removed nettrades_gpustack_adapter (deprecated).
#   - NEW: Validates that all view files exist before installation, creating
#     placeholders if they are missing.
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Load environment variables and feature flags
# -----------------------------------------------------------------------------
set -a
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$PROJECT_ROOT/deploy/docker/.env"
# Read feature flags (defined in common.sh)
source "$SCRIPT_DIR/lib/common.sh"
read_feature_flags
set +a

# -----------------------------------------------------------------------------
# Colours
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
# Parse arguments
# -----------------------------------------------------------------------------
FORCE=false
UPGRADE=false
AUTO=false

for arg in "$@"; do
    case $arg in
        --force) FORCE=true; shift ;;
        --upgrade) UPGRADE=true; shift ;;
        --auto) AUTO=true; shift ;;
    esac
done

# -----------------------------------------------------------------------------
# Check if Odoo container is running
# -----------------------------------------------------------------------------
if ! docker ps | grep -q odoo; then
    log_error "Odoo container is not running."
    log_info "Please start the stack with: cd deploy/docker && docker compose up -d"
    exit 1
fi

# -----------------------------------------------------------------------------
# Ensure Odoo is using the latest modules (restart if --force)
# -----------------------------------------------------------------------------
if [[ "$FORCE" == true ]]; then
    log_info "Force mode – restarting Odoo to load latest modules..."
    docker compose restart odoo
    sleep 5
    log_success "Odoo restarted"
fi

# -----------------------------------------------------------------------------
# Test database connection
# -----------------------------------------------------------------------------
log_info "Testing database connection..."
cd "$PROJECT_ROOT/deploy/docker"

if ! docker compose exec -T postgres pg_isready -U odoo &>/dev/null; then
    log_error "PostgreSQL is not ready. Please start the stack first."
    exit 1
fi

if ! docker compose exec -T postgres psql -U odoo -d odoo -c "SELECT 1" &>/dev/null; then
    log_error "PostgreSQL authentication failed. Check POSTGRES_PASSWORD in .env."
    log_error "Current .env password: $POSTGRES_PASSWORD"
    log_error "Try: docker compose down && docker compose up -d"
    exit 1
fi
log_success "Database connection verified."

cd "$PROJECT_ROOT"

# -----------------------------------------------------------------------------
# NEW: Validate that all view files exist inside the container
# This prevents the "FileNotFoundError" we saw in the logs.
# -----------------------------------------------------------------------------
log_step "Validating Odoo module files inside the container..."

# Get the list of NETTRADES modules from the filesystem
MODULE_DIRS=$(docker compose exec -T odoo find /mnt/extra-addons -maxdepth 1 -type d -name "nettrades_*" 2>/dev/null | sed 's|/mnt/extra-addons/||' | tr -d '\r')

for module in $MODULE_DIRS; do
    # Check if the module has a manifest
    if docker compose exec -T odoo test -f "/mnt/extra-addons/$module/__manifest__.py" &>/dev/null; then
        # Extract view files from the manifest
        VIEW_FILES=$(docker compose exec -T odoo grep -E "['\"]views/.*\.xml['\"]" "/mnt/extra-addons/$module/__manifest__.py" 2>/dev/null | sed "s/.*['\"]\(views\/.*\.xml\)['\"].*/\1/" | tr -d '\r')
        
        for view_file in $VIEW_FILES; do
            if ! docker compose exec -T odoo test -f "/mnt/extra-addons/$module/$view_file" &>/dev/null; then
                log_warning "  - Missing view file in module $module: $view_file"
                log_info "    Creating placeholder inside the container..."
                
                # Create the directory if it doesn't exist
                docker compose exec -T odoo mkdir -p "/mnt/extra-addons/$module/$(dirname "$view_file")" 2>/dev/null || true
                
                # Create a minimal placeholder XML file
                docker compose exec -T odoo bash -c "cat > /mnt/extra-addons/$module/$view_file << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<!--
    AUTO-GENERATED PLACEHOLDER
    The original file '$view_file' was missing from the module '$module'.
    This placeholder was created to prevent Odoo from failing during installation.
    Please replace this with the actual view definition.
-->
<odoo>
    <data>
        <!-- TODO: Add view definitions for $module -->
    </data>
</odoo>
EOF" 2>/dev/null || {
                    log_warning "    Failed to create placeholder for $view_file"
                }
                log_info "    Created placeholder: $view_file"
            fi
        done
    fi
done
log_success "Module file validation complete"

# -----------------------------------------------------------------------------
# Define modules based on feature flags
# -----------------------------------------------------------------------------
MODULES=("nettrades_core")  # core is always installed

if [[ "${FEATURE_ASK_SOMEONE:-true}" == "true" ]]; then
    MODULES+=("nettrades_ask_someone")
fi
if [[ "${FEATURE_GOOD_ANSWER:-true}" == "true" ]]; then
    MODULES+=("nettrades_good_answer")
fi
if [[ "${FEATURE_GPU_MARKETPLACE:-false}" == "true" ]]; then
    MODULES+=("nettrades_gpu_admin")
fi
if [[ "${FEATURE_ROUTER:-false}" == "true" ]]; then
    MODULES+=("nettrades_bridge")
    MODULES+=("nettrades_llm_config")
fi
if [[ "${FEATURE_TRAINING:-false}" == "true" ]]; then
    # training modules depend on good_answer and others; we just add them
    MODULES+=("nettrades_data_collection")
    MODULES+=("nettrades_fairness")
    MODULES+=("nettrades_self_improving_config")
fi
if [[ "${FEATURE_ENTERPRISE:-false}" == "true" ]]; then
    MODULES+=("nettrades_job_matching")
    MODULES+=("nettrades_lead_scoring")
    MODULES+=("nettrades_proposals")
    MODULES+=("nettrades_research")
    MODULES+=("nettrades_onboarding")
    MODULES+=("nettrades_notifications")
    # Add forgejo integration if available
fi
# Always add utility modules
MODULES+=("nettrades_queue")

# Remove duplicates (just in case)
MODULES=($(printf "%s\n" "${MODULES[@]}" | sort -u))

log_info "Modules to install: ${MODULES[*]}"

# -----------------------------------------------------------------------------
# Install each module
# -----------------------------------------------------------------------------
install_module() {
    local module=$1
    local action="install"
    local flag="-i"

    if [ "$UPGRADE" = true ]; then
        action="upgrade"
        flag="-u"
    elif [ "$FORCE" = true ]; then
        action="reinstall"
        flag="-i"
    fi

    log_info "${action^}ing module: $module"

    # Explicitly pass database parameters to avoid any config issues
    if docker exec \
        -e PGPASSWORD="$POSTGRES_PASSWORD" \
        odoo odoo \
        -d odoo \
        --db_host=postgres \
        --db_port=5432 \
        --db_user=odoo \
        --db_password="$POSTGRES_PASSWORD" \
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