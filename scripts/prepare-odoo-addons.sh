#!/bin/bash
# =============================================================================
# FILE: scripts/prepare-odoo-addons.sh
# =============================================================================
# PURPOSE:
#   Prepares the Odoo build context by consolidating all addon modules
#   from the project root into deploy/docker/odoo-modules.
#
#   This script:
#     1. Scans odoo-modules/ and third-party/ (excluding the full 'odoo' source)
#     2. Finds all directories that contain __manifest__.py or __openerp__.py
#     3. Copies them directly into deploy/docker/odoo-modules/ (flattening)
#     4. Resolves conflicts: odoo-modules/ takes priority over third-party/
#     5. Ensures every module has a top-level __init__.py (imports models)
#
#   It is idempotent and safe to re-run.
#
# USAGE:
#   ./scripts/prepare-odoo-addons.sh [--force]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"

FORCE=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
    esac
done

TARGET="$PROJECT_ROOT/deploy/docker/odoo-modules"

if [[ -d "$TARGET" ]] && [[ "$FORCE" != true ]]; then
    log_warning "odoo-modules already exists. Use --force to rebuild."
    exit 0
fi

rm -rf "$TARGET"
mkdir -p "$TARGET"

# -----------------------------------------------------------------------------
# Helper: find all Odoo module directories under a given root
# -----------------------------------------------------------------------------
find_modules() {
    local root="$1"
    find "$root" -type f \( -name "__manifest__.py" -o -name "__openerp__.py" \) -printf "%h\n" 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Step 1: Collect modules from odoo-modules/ (highest priority)
# -----------------------------------------------------------------------------
declare -A MODULE_PATHS
if [[ -d "$PROJECT_ROOT/odoo-modules" ]]; then
    log_info "Scanning odoo-modules/"
    while IFS= read -r module_dir; do
        module_name=$(basename "$module_dir")
        MODULE_PATHS["$module_name"]="$module_dir"
    done < <(find_modules "$PROJECT_ROOT/odoo-modules")
fi

# -----------------------------------------------------------------------------
# Step 2: Collect modules from third-party/ (lower priority)
# -----------------------------------------------------------------------------
if [[ -d "$PROJECT_ROOT/third-party" ]]; then
    log_info "Scanning third-party/ (skipping 'odoo' folder)"
    while IFS= read -r module_dir; do
        # Skip the huge 'odoo' source
        if [[ "$module_dir" == "$PROJECT_ROOT/third-party/odoo"* ]]; then
            continue
        fi
        module_name=$(basename "$module_dir")
        # Only add if not already in the map (odoo-modules takes priority)
        if [[ -z "${MODULE_PATHS[$module_name]:-}" ]]; then
            MODULE_PATHS["$module_name"]="$module_dir"
        else
            log_info "Skipping $module_name (already from odoo-modules)"
        fi
    done < <(find_modules "$PROJECT_ROOT/third-party")
fi

# -----------------------------------------------------------------------------
# Step 3: Copy all modules to the target directory (flattened)
# -----------------------------------------------------------------------------
log_info "Copying modules to $TARGET"
copied=0
for module_name in "${!MODULE_PATHS[@]}"; do
    src="${MODULE_PATHS[$module_name]}"
    dst="$TARGET/$module_name"
    if [[ -d "$src" ]]; then
        cp -r "$src" "$dst"
        ((copied++))
        log_info "Copied $module_name"
    fi
done

# -----------------------------------------------------------------------------
# Step 4: Ensure each module has a top-level __init__.py
# -----------------------------------------------------------------------------
log_info "Ensuring all modules have a top-level __init__.py..."
for module_dir in "$TARGET"/*/; do
    if [[ -d "$module_dir" ]]; then
        init_file="$module_dir/__init__.py"
        if [[ ! -f "$init_file" ]]; then
            cat > "$init_file" << 'EOF'
# -*- coding: utf-8 -*-
from . import models
EOF
            log_info "Created $init_file"
        fi
    fi
done

log_success "Odoo addons prepared: $copied modules copied to $TARGET"