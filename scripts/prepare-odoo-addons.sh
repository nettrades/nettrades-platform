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
#   Automatically clones the Odoo repository if third-party/odoo is missing.
#   With --force, always copies fresh modules (overwrites existing).
#
#   VALIDATES that all files referenced in each module's manifest exist
#   before copying. Fails loudly if any are missing.
#
# UPDATES (2026-09-17):
#   - REPLACED placeholder creation with fail-loud validation. Previously,
#     missing view files were silently replaced with empty XML stubs, which
#     produced modules that loaded without any UI. That hid real bugs and
#     caused phantom errors when the placeholders were later loaded by Odoo.
#     Now the script exits with code 1 and lists every missing file.
#   - EXTENDED validation to check ALL file types referenced in manifests
#     (xml, csv, yml, yaml, js, css, scss), not just views/*.xml. This
#     catches missing data files, security files, and assets too.
#   - ADDED --skip-validation flag as an escape hatch. Do not use in normal
#     workflow — it exists only for rare debugging scenarios.
#
# PREVIOUS UPDATES:
#   - FIXED: Validates PROJECT_ROOT to prevent duplicate path issues.
#   - FIXED: Uses realpath to ensure PROJECT_ROOT is always an absolute path,
#            preventing path duplication when called from subdirectories.
#   - FIXED (2026-08): Removed an uncommented separator line that caused a
#            shell error. All comment lines now start with '#'.
#   - FIXED (2026-09): Corrected HTML entity corruption (&amp;&gt; → >,
#            &amp;&amp; → &&) that was causing syntax errors in the script.
#   - FIXED (2026-09): Respects PROJECT_ROOT environment variable if already
#            set, allowing the caller to override the detected root.
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
# CRITICAL FIX: Respect PROJECT_ROOT if already set in environment.
# This allows the caller (e.g., phase-deploy.sh) to specify the correct root,
# preventing path duplication issues when the script is called from subdirectories.
# =============================================================================
if [[ -n "${PROJECT_ROOT:-}" ]]; then
    # Use the provided PROJECT_ROOT
    PROJECT_ROOT="$(realpath "$PROJECT_ROOT" 2>/dev/null || echo "$PROJECT_ROOT")"
    log_info "Using PROJECT_ROOT from environment: $PROJECT_ROOT"
else
    # Compute PROJECT_ROOT from SCRIPT_DIR
    if command -v realpath >/dev/null 2>&1; then
        PROJECT_ROOT="$(realpath "$SCRIPT_DIR/..")"
    else
        # Fallback for systems without realpath
        PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
    fi
    log_info "Computed PROJECT_ROOT: $PROJECT_ROOT"
fi

# =============================================================================
# Validate PROJECT_ROOT to prevent duplicate path issues
# =============================================================================
if [[ ! -d "$PROJECT_ROOT/scripts" ]]; then
    log_error "PROJECT_ROOT is incorrect: $PROJECT_ROOT"
    log_error "Expected to find scripts/ directory at $PROJECT_ROOT/scripts"
    log_error "This usually happens when the script is run from the wrong directory."
    log_error "Please run this script from the project root or set PROJECT_ROOT correctly."
    exit 1
fi
log_success "PROJECT_ROOT validated: $PROJECT_ROOT"

ODOO_MODULES="$PROJECT_ROOT/odoo-modules"
THIRD_PARTY="$PROJECT_ROOT/third-party"
ODOO_REPO="$THIRD_PARTY/odoo"
TARGET="$PROJECT_ROOT/deploy/docker/odoo-modules"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
FORCE=false
SKIP_VALIDATION=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
        --skip-validation) SKIP_VALIDATION=true ;;
    esac
done

if [[ "$FORCE" == true ]]; then
    log_info "Force mode – removing existing target directory"
    rm -rf "$TARGET"
fi

# -----------------------------------------------------------------------------
# Clone Odoo repository if missing
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

# =============================================================================
# MANIFEST VALIDATION
# =============================================================================
# Validate that every file referenced in a module's __manifest__.py exists
# on disk before we copy anything. This catches manifest-vs-reality drift
# early, instead of letting Odoo fail later with a confusing error.
#
# The previous version of this script created empty placeholder files for
# any missing view. That hid the problem: the module would install, but
# there would be no UI. Even worse, the placeholders could themselves
# trigger errors when Odoo tried to load them. Failing loudly is better.
# =============================================================================

validate_one_module() {
    local module_dir="$1"
    local issues_file="$2"
    local manifest="$module_dir/__manifest__.py"
    local module_name
    module_name="$(basename "$module_dir")"

    [[ -f "$manifest" ]] || return 0

    # -------------------------------------------------------------------------
    # BUG A FIX: Strip Python comments before extracting paths.
    # 'sed s/#.*$//' removes everything from the first '#' to end-of-line.
    # This stops commented-out manifest entries (e.g. '# views/foo.xml')
    # from being treated as active references.
    # -------------------------------------------------------------------------
    local cleaned
    cleaned="$(sed 's/#.*$//' "$manifest")"

    local paths
    paths="$(echo "$cleaned" \
        | grep -oE "['\"][a-zA-Z0-9_][a-zA-Z0-9_./-]*\.(xml|csv|yml|yaml|js|css|scss)['\"]" \
        | tr -d "\"'" \
        | sort -u)"

    [[ -z "$paths" ]] && return 0

    while IFS= read -r rel_path; do
        [[ -z "$rel_path" ]] && continue

        # Skip absolute paths and URLs
        [[ "$rel_path" == /* ]] && continue
        [[ "$rel_path" == *"://"* ]] && continue
        [[ "$rel_path" =~ ^[a-z]+: ]] && continue

        # ---------------------------------------------------------------------
        # BUG B FIX: Skip asset paths belonging to OTHER modules.
        # Odoo asset paths have the form <module_name>/static/...
        # If the first segment is not this module's name, the file belongs
        # to that other module — not our responsibility to validate.
        # ---------------------------------------------------------------------
        if [[ "$rel_path" == */static/* ]]; then
            local first_seg="${rel_path%%/*}"
            if [[ "$first_seg" != "$module_name" ]]; then
                continue
            fi
        fi

        # Strip the current module's own prefix for asset paths,
        # so '<module_name>/static/...' resolves to './static/...' locally.
        local effective_path="$rel_path"
        if [[ "$rel_path" == "$module_name/"* ]]; then
            effective_path="${rel_path#"$module_name/"}"
        fi

        local full_path="$module_dir/$effective_path"
        if [[ ! -f "$full_path" ]]; then
            echo "MISSING: $module_name/$effective_path" >> "$issues_file"
        fi
    done <<< "$paths"

    return 0
}

validate_manifests() {
    log_step "Validating module manifests..."

    local modules_checked=0
    local issues_file
    issues_file="$(mktemp)"

    # --- Validate modules in odoo-modules/ -----------------------------------
    if [[ -d "$ODOO_MODULES" ]]; then
        for module_dir in "$ODOO_MODULES"/*/; do
            [[ -d "$module_dir" ]] || continue
            validate_one_module "$module_dir" "$issues_file" || true
            modules_checked=$((modules_checked + 1))
        done
    fi

    # --- Validate modules in third-party/ (excluding 'odoo' source) ----------
    if [[ -d "$THIRD_PARTY" ]]; then
        for module_dir in "$THIRD_PARTY"/*/; do
            [[ -d "$module_dir" ]] || continue
            local name
            name="$(basename "$module_dir")"
            [[ "$name" == "odoo" ]] && continue
            validate_one_module "$module_dir" "$issues_file" || true
            modules_checked=$((modules_checked + 1))
        done
    fi

    # --- Report results ------------------------------------------------------
    if [[ -s "$issues_file" ]]; then
        local total_missing
        total_missing="$(wc -l < "$issues_file" | tr -d ' ')"

        echo ""
        log_error "════════════════════════════════════════════════════════════════"
        log_error "  MANIFEST VALIDATION FAILED"
        log_error "════════════════════════════════════════════════════════════════"
        log_error "  $total_missing missing file(s):"
        echo ""
        sed 's/^/    /' "$issues_file"
        echo ""
        log_error "════════════════════════════════════════════════════════════════"
        log_error "Fix each missing file by either:"
        log_error "  1. Creating the file at the expected path, OR"
        log_error "  2. Removing the reference from __manifest__.py"
        log_error ""
        log_error "Do NOT create placeholder files — they hide real bugs and"
        log_error "produce modules that install but have no UI."
        log_error "════════════════════════════════════════════════════════════════"
        rm -f "$issues_file"
        return 1
    fi

    rm -f "$issues_file"
    log_success "Validated $modules_checked modules — all manifest references resolve"
    return 0
}

if [[ "$SKIP_VALIDATION" == true ]]; then
    log_warning "Manifest validation skipped (--skip-validation passed)"
else
    if ! validate_manifests; then
        log_error "Aborting before copy — fix the missing files first."
        exit 1
    fi
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
# Parsing all XML files to catch syntax errors before Docker build
# -----------------------------------------------------------------------------

log_step "Parsing all XML files to catch syntax errors before Docker build..."
PARSE_ERRORS=0
while IFS= read -r -d '' f; do
    if ! python3 -c "import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])" "$f" 2>/dev/null; then
        log_error "  ✗ Invalid XML: ${f#$TARGET/}"
        PARSE_ERRORS=$((PARSE_ERRORS + 1))
    fi
done < <(find "$TARGET" -type f -name "*.xml" -print0)
if [ "$PARSE_ERRORS" -gt 0 ]; then
    log_error "$PARSE_ERRORS XML file(s) failed to parse. Aborting."
    exit 1
fi
log_success "All XML files parse cleanly"

# -----------------------------------------------------------------------------
# Find unterminated strings
# -----------------------------------------------------------------------------
find odoo-modules third-party -name '*.py' -print0 | while IFS= read -r -d '' f; do
    if ! python3 -m py_compile "$f" 2>/dev/null; then
        echo "SYNTAX ERROR: $f"
        python3 -m py_compile "$f" 2>&1 | tail -3
    fi
done

# -----------------------------------------------------------------------------
# Runs a compile check on the whole tree before a build - Shows any Python file that has a syntax error
# -----------------------------------------------------------------------------
find odoo-modules third-party -name '*.py' -not -path '*/node_modules/*' -print0 | \
while IFS= read -r -d '' f; do
    python3 -m py_compile "$f" 2>/dev/null || {
        echo "SYNTAX ERROR: $f"
        python3 -m py_compile "$f" 2>&1 | tail -3
    }
done

# -----------------------------------------------------------------------------
# Convert line endings to LF for all text files in Odoo modules
# -----------------------------------------------------------------------------
log_step "Converting line endings to LF in Odoo modules..."
if command -v dos2unix >/dev/null 2>&1; then
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

# =============================================================================
# End of script
# =============================================================================