#!/bin/bash
# =============================================================================
# FILE: scripts/prepare-odoo-addons.sh
# =============================================================================
# PURPOSE:
#   Prepares Odoo addons for Docker build by copying all custom modules
#   from the odoo-modules/ and third-party/ directories to the Docker
#   build context (deploy/docker/odoo-modules).
#
#   It also ensures that every module has a top-level __init__.py,
#   and converts all text files to Unix (LF) line endings to avoid
#   Windows ↔ Linux corruption issues.
#
#   NEW: Automatically clones the Odoo repository if third-party/odoo is missing.
#   NEW: With --force, it always copies fresh modules (overwrites existing).
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours and logging functions
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
log_step() { echo -e "${BLUE}▶${NC} $1"; }

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ODOO_MODULES="$PROJECT_ROOT/odoo-modules"
THIRD_PARTY="$PROJECT_ROOT/third-party"
ODOO_REPO="$THIRD_PARTY/odoo"
TARGET="$PROJECT_ROOT/deploy/docker/odoo-modules"

# Parse arguments
FORCE=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
    esac
done

if [[ "$FORCE" == true ]]; then
    log_info "Force mode – removing existing target directory"
    rm -rf "$TARGET"
fi

# -----------------------------------------------------------------------------
# NEW: Clone Odoo repository if missing
# -----------------------------------------------------------------------------
if [[ ! -d "$ODOO_REPO" ]] || [[ -z "$(ls -A "$ODOO_REPO" 2>/dev/null)" ]]; then
    log_info "Odoo repository not found at $ODOO_REPO"
    log_info "Cloning Odoo (this may take a few minutes)..."

    # Create third-party directory if it doesn't exist
    mkdir -p "$THIRD_PARTY"
    
    # Clone Odoo (shallow clone to save time and bandwidth)
    if git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git "$ODOO_REPO"; then
        log_success "Odoo repository cloned successfully"
    else
        log_error "Failed to clone Odoo repository"
        log_info "Please clone it manually:"
        log_info "  git clone --depth 1 --branch 19.0 https://github.com/odoo/odoo.git third-party/odoo"
        exit 1
    fi
else
    log_success "Odoo repository already exists at $ODOO_REPO"
fi

# -----------------------------------------------------------------------------
# Create target directory
# -----------------------------------------------------------------------------
mkdir -p "$TARGET"
log_info "Preparing Odoo addons in $TARGET..."

# -----------------------------------------------------------------------------
# Copy from odoo-modules/
# -----------------------------------------------------------------------------
if [[ -d "$ODOO_MODULES" ]]; then
    log_info "Copying from odoo-modules/"
    cp -r "$ODOO_MODULES"/* "$TARGET/" 2>/dev/null || true
else
    log_warning "odoo-modules directory not found at $ODOO_MODULES"
fi

# -----------------------------------------------------------------------------
# Copy from third-party/ (excluding the huge 'odoo' source)
# -----------------------------------------------------------------------------
if [[ -d "$THIRD_PARTY" ]]; then
    log_info "Scanning third-party/ (skipping the huge 'odoo' source)"
    for module in "$THIRD_PARTY"/*; do
        if [[ -d "$module" ]] && [[ "$(basename "$module")" != "odoo" ]]; then
            module_name="$(basename "$module")"
            if [[ ! -d "$TARGET/$module_name" ]]; then
                cp -r "$module" "$TARGET/"
                log_info "  - Copied $module_name"
            else
                log_info "  - Skipped $module_name (already exists)"
            fi
        fi
    done
else
    log_warning "third-party/ directory not found"
fi

# -----------------------------------------------------------------------------
# Ensure __init__.py for all modules
# -----------------------------------------------------------------------------
log_step "Ensuring __init__.py for all modules..."
for module_dir in "$TARGET"/*/; do
    if [[ -d "$module_dir" ]]; then
        init_file="${module_dir}__init__.py"
        if [[ ! -f "$init_file" ]]; then
            touch "$init_file"
            log_info "  - Created __init__.py for $(basename "$module_dir")"
        fi
    fi
done

# -----------------------------------------------------------------------------
# NEW: Convert line endings to LF for all text files in Odoo modules
# -----------------------------------------------------------------------------
log_step "Converting line endings to LF in Odoo modules..."
if command -v dos2unix &>/dev/null; then
    find "$TARGET" -type f \( -name "*.py" -o -name "*.xml" -o -name "*.csv" -o -name "*.txt" -o -name "*.conf" -o -name "*.js" -o -name "*.css" -o -name "*.html" \) -exec dos2unix -q {} \;
    log_success "All text files in Odoo modules converted to LF"
else
    log_warning "dos2unix not found – skipping line ending conversion"
fi

# -----------------------------------------------------------------------------
# Count modules
# -----------------------------------------------------------------------------
MODULE_COUNT=$(find "$TARGET" -maxdepth 1 -type d | tail -n +2 | wc -l)
log_success "$MODULE_COUNT modules prepared in $TARGET"