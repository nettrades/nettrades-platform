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
TARGET="$PROJECT_ROOT/deploy/docker/odoo-modules"

# Parse arguments
FORCE="${1:-}"
if [[ "$FORCE" == "--force" ]]; then
    log_info "Force mode – removing existing target directory"
    rm -rf "$TARGET"
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
    log_warning "odoo-modules directory not found"
fi

# -----------------------------------------------------------------------------
# Copy from third-party/ (skip the huge 'odoo' source)
# -----------------------------------------------------------------------------
if [[ -d "$THIRD_PARTY" ]]; then
    log_info "Scanning third-party/ (skipping the huge 'odoo' source)"
    find "$THIRD_PARTY" -maxdepth 2 -type f \( -name "__manifest__.py" -o -name "__openerp__.py" \) -print0 | while IFS= read -r -d '' manifest; do
        module_dir="$(dirname "$manifest")"
        module_name="$(basename "$module_dir")"
        if [[ "$module_name" == "odoo" ]]; then
            continue
        fi
        log_info "  - Copied $module_name"
        cp -r "$module_dir" "$TARGET/"
    done
else
    log_warning "third-party directory not found"
fi

# -----------------------------------------------------------------------------
# Ensure every module has a top-level __init__.py
# -----------------------------------------------------------------------------
log_info "Ensuring __init__.py for all modules..."
for module_dir in "$TARGET"/*/; do
    if [[ -d "$module_dir" ]] && [[ ! -f "$module_dir/__init__.py" ]]; then
        echo "# -*- coding: utf-8 -*-" > "$module_dir/__init__.py"
        echo "from . import models" >> "$module_dir/__init__.py"
        log_info "  - Created __init__.py for $(basename "$module_dir")"
    fi
done

# -----------------------------------------------------------------------------
# Convert all text files to Unix (LF) line endings
# -----------------------------------------------------------------------------
if command -v dos2unix &>/dev/null; then
    log_info "Converting line endings to LF in Odoo modules..."
    find "$TARGET" -type f \( \
        -name "*.py" -o \
        -name "*.xml" -o \
        -name "*.sh" -o \
        -name "*.conf" -o \
        -name "*.txt" -o \
        -name "*.md" -o \
        -name "*.yml" -o \
        -name "*.yaml" -o \
        -name "*.json" -o \
        -name "*.csv" -o \
        -name "*.sql" \
    \) -exec dos2unix {} \; >/dev/null 2>&1
    log_success "All text files in Odoo modules converted to LF"
else
    log_warning "dos2unix not found – skipping line ending conversion"
    log_info "Install dos2unix with: sudo apt install dos2unix"
fi

# -----------------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------------
log_success "$(find "$TARGET" -maxdepth 1 -type d | wc -l) modules prepared in $TARGET"