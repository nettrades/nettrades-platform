#!/bin/bash
# =============================================================================
# FILE: scripts/prepare-odoo-addons.sh
# PURPOSE:
#   Copies all Odoo addons from odoo-modules/ and third-party/
#   into deploy/docker/odoo-modules/, flattening nested directories.
#   It creates missing __init__.py files.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="$PROJECT_ROOT/deploy/docker/odoo-modules"

# Remove existing target
rm -rf "$TARGET"
mkdir -p "$TARGET"

echo "📦 Copying Odoo addons..."

# 1. Copy all top-level directories from odoo-modules/
if [[ -d "$PROJECT_ROOT/odoo-modules" ]]; then
    cp -r "$PROJECT_ROOT/odoo-modules"/* "$TARGET/" 2>/dev/null || true
    echo "  - Copied from odoo-modules/"
fi

# 2. Copy from third-party: find all modules and flatten them
if [[ -d "$PROJECT_ROOT/third-party" ]]; then
    echo "  - Scanning third-party/ (skipping the huge 'odoo' source)"
    find "$PROJECT_ROOT/third-party" -type f \( -name "__manifest__.py" -o -name "__openerp__.py" \) -printf "%h\n" | while read -r module_dir; do
        # Skip the full Odoo source
        if [[ "$module_dir" == "$PROJECT_ROOT/third-party/odoo"* ]]; then
            continue
        fi
        module_name=$(basename "$module_dir")
        # Only copy if not already copied (priority to odoo-modules)
        if [[ ! -d "$TARGET/$module_name" ]]; then
            cp -r "$module_dir" "$TARGET/"
            echo "    - Copied $module_name"
        else
            echo "    - Skipped $module_name (already from odoo-modules)"
        fi
    done
fi

# 3. Ensure every module has a top-level __init__.py
echo "  - Ensuring __init__.py for all modules"
for module_dir in "$TARGET"/*/; do
    if [[ -d "$module_dir" ]]; then
        if [[ ! -f "$module_dir/__init__.py" ]]; then
            echo "# -*- coding: utf-8 -*-\nfrom . import models" > "$module_dir/__init__.py"
        fi
    fi
done

# 4. Report result
MODULE_COUNT=$(ls -1 "$TARGET" | wc -l)
echo "✅ $MODULE_COUNT modules prepared in $TARGET"