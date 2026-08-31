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
#   NEW: Validates that all view files referenced in module manifests exist,
#        and creates placeholder files if they are missing (with a warning).
#   FIXED: Validates PROJECT_ROOT to prevent duplicate path issues.
#   FIXED: Uses realpath to ensure PROJECT_ROOT is always an absolute path,
#          preventing path duplication when called from subdirectories.
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

# =============================================================================
# CRITICAL FIX: Use realpath to get absolute path of PROJECT_ROOT
# This prevents path duplication when the script is called from subdirectories
# (e.g., deploy/docker/), which was causing modules to be copied to
# deploy/docker/deploy/docker/odoo-modules instead of deploy/docker/odoo-modules.
# =============================================================================
if command -v realpath &>/dev/null; then
    PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"
else
    # Fallback for systems without realpath (e.g., some macOS versions)
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
fi

# =============================================================================
# Validate PROJECT_ROOT to prevent duplicate path issues
# =============================================================================
if [[ ! -d "$PROJECT_ROOT/scripts" ]]; then
    log_error "PROJECT_ROOT is incorrect: $PROJECT_ROOT"
    log_error "Expected to find scripts/ directory at $PROJECT_ROOT/scripts"
    log_error "This usually happens when the script is run from the wrong directory."
    log_error "Please run this script from the project root or use absolute paths."
    exit 1
fi
log_success "PROJECT_ROOT validated: $PROJECT_ROOT"

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
# NEW: Validate that all view files referenced in manifests exist
# If a file is missing, create a placeholder to prevent Odoo from failing.
# -----------------------------------------------------------------------------
log_step "Validating Odoo module view files..."
for manifest in "$TARGET"/*/__manifest__.py; do
    if [[ -f "$manifest" ]]; then
        module_dir="$(dirname "$manifest")"
        module_name="$(basename "$module_dir")"

        # Extract data files from manifest (simple grep for 'views/*.xml')
        # This is a best-effort approach – Odoo's manifest can be more complex,
        # but this catches the common case.
        while IFS= read -r view_file; do
            # Remove quotes and whitespace
            view_file=$(echo "$view_file" | sed "s/['\"]//g" | xargs)
            if [[ -n "$view_file" ]]; then
                full_path="$module_dir/$view_file"
                if [[ ! -f "$full_path" ]]; then
                    log_warning "  - Missing view file: $view_file in module $module_name"
                    log_info "    Creating placeholder file to prevent Odoo failure..."

                    # Create the directory if it doesn't exist
                    mkdir -p "$(dirname "$full_path")"

                    # Create a minimal placeholder XML file
                    cat > "$full_path" << EOF
<?xml version="1.0" encoding="utf-8"?>
<!--
    AUTO-GENERATED PLACEHOLDER
    The original file '$view_file' was missing from the module '$module_name'.
    This placeholder was created to prevent Odoo from failing during installation.
    Please replace this with the actual view definition.
-->
<odoo>
    <data>
        <!-- TODO: Add view definitions for $module_name -->
    </data>
</odoo>
EOF
                    log_info "    Created placeholder: $full_path"
                fi
            fi
        done < <(grep -E "['\"]views/.*\.xml['\"]" "$manifest" | sed "s/.*['\"]\(views\/.*\.xml\)['\"].*/\1/")
    fi
done
log_success "View file validation complete"

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



 =============================================================================
 NEW: Strip UI from NETTRADES modules (headless mode)
 =============================================================================

strip_odoo_ui() {
    log_step "Stripping UI from NETTRADES modules (headless mode)..."
    
    for module_dir in "$TARGET"/nettrades_*/; do
        if [[ -d "$module_dir" ]]; then
            module_name="$(basename "$module_dir")"
            
            # Remove views directory
            if [[ -d "$module_dir/views" ]]; then
                rm -rf "$module_dir/views"
                log_info "  - Removed views/ from $module_name"
            fi
            
            # Clean manifest data section
            manifest="$module_dir/__manifest__.py"
            if [[ -f "$manifest" ]]; then
                # Remove all view references from the 'data' list
                sed -i "/'data':/,/]/d" "$manifest"
                # Add empty data section
                sed -i "/'depends'/a\    'data': [],  # STRIPPED - UI moved to Electron Launcher" "$manifest"
                log_info "  - Cleaned manifest for $module_name"
            fi
        fi
    done
    
    log_success "UI stripped from all NETTRADES modules"
}

# Call the function after copying modules
strip_odoo_ui