#!/bin/bash
# =============================================================================
# FILE: scripts/prepare-odoo-addons.sh
# =============================================================================
# PURPOSE:
#   Prepares the Odoo build context by consolidating all addon modules
#   from the project root into deploy/docker/odoo-modules.
#
#   This script automatically discovers and copies:
#     1. All directories from ./odoo-modules/
#     2. All directories from ./third-party/ (including subdirectories)
#     3. Any additional addon directories from ./addons/ (if present)
#
#   It is designed to be called by nettrades-setup.sh during Phase 2
#   and is idempotent – it can be re-run safely.
#
# USAGE:
#   ./scripts/prepare-odoo-addons.sh [--force]
#
#   --force  Remove existing odoo-modules and rebuild from scratch.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_DIR/lib/colors.sh" ]]; then
    source "$SCRIPT_DIR/lib/colors.sh"
else
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
fi

if [[ -f "$SCRIPT_DIR/lib/logging.sh" ]]; then
    source "$SCRIPT_DIR/lib/logging.sh"
else
    log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
    log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
    log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
    log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
fi

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
FORCE=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
    esac
done

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
DEPLOY_DOCKER_DIR="$PROJECT_ROOT/deploy/docker"
ODOO_MODULES_TARGET="$DEPLOY_DOCKER_DIR/odoo-modules"

# Source directories (add your module locations here as they are added)
SOURCE_DIRS=(
    "$PROJECT_ROOT/odoo-modules"
    "$PROJECT_ROOT/third-party"
    "$PROJECT_ROOT/addons"
)

# -----------------------------------------------------------------------------
# Main execution
# -----------------------------------------------------------------------------
log_info "Preparing Odoo addons for Docker build..."

# Remove existing target if --force
if [[ -d "$ODOO_MODULES_TARGET" ]]; then
    if [[ "$FORCE" == true ]]; then
        log_info "Removing existing odoo-modules (--force)..."
        rm -rf "$ODOO_MODULES_TARGET"
    else
        log_warning "odoo-modules already exists. Use --force to rebuild."
        exit 0
    fi
fi

# Create target directory
mkdir -p "$ODOO_MODULES_TARGET"

# Copy addons from each source directory
copied_count=0
for src_dir in "${SOURCE_DIRS[@]}"; do
    if [[ -d "$src_dir" ]]; then
        log_info "Copying from: $src_dir"
        
        # Copy all subdirectories (each is an Odoo module)
        for item in "$src_dir"/*/; do
            if [[ -d "$item" ]]; then
                module_name=$(basename "$item")
                # Skip empty directories and common exclusions
                if [[ "$module_name" != ".*" ]] && [[ "$module_name" != "__pycache__" ]]; then
                    cp -r "$item" "$ODOO_MODULES_TARGET/"
                    ((copied_count++))
                fi
            fi
        done
    else
        log_warning "Source directory not found: $src_dir"
    fi
done

# Also copy any loose directories that might be addons (e.g., mcp-odoo, odoo_llm)
# Some third-party repos may have their own structure – copy any top-level directories
for src_dir in "$PROJECT_ROOT/third-party"/*/; do
    if [[ -d "$src_dir" ]]; then
        # Check if this looks like an Odoo addon (has __manifest__.py or __openerp__.py)
        if [[ -f "$src_dir/__manifest__.py" ]] || [[ -f "$src_dir/__openerp__.py" ]] || \
           [[ -f "$src_dir/models/__init__.py" ]] || [[ -f "$src_dir/views/__init__.py" ]]; then
            module_name=$(basename "$src_dir")
            # Skip if already copied (avoid duplicates)
            if [[ ! -d "$ODOO_MODULES_TARGET/$module_name" ]]; then
                log_info "Copying third-party module: $module_name"
                cp -r "$src_dir" "$ODOO_MODULES_TARGET/"
                ((copied_count++))
            fi
        fi
    fi
done

# -----------------------------------------------------------------------------
# Verify and display results
# -----------------------------------------------------------------------------
module_count=$(ls -1 "$ODOO_MODULES_TARGET" 2>/dev/null | wc -l)
log_success "Odoo addons prepared: $module_count modules copied"

if [[ $module_count -eq 0 ]]; then
    log_warning "No modules were copied. Please check your source directories."
    log_info "Expected locations:"
    for src_dir in "${SOURCE_DIRS[@]}"; do
        log_info "  - $src_dir"
    done
fi

# -----------------------------------------------------------------------------
# Create a marker file for idempotency
# -----------------------------------------------------------------------------
echo "$(date -Iseconds)" > "$ODOO_MODULES_TARGET/.prepared"
log_success "Build context prepared at: $ODOO_MODULES_TARGET"