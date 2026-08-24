#!/bin/bash
# =============================================================================
# FILE: scripts/per-user-setup.sh
# PURPOSE: Per-user installation (no root/sudo required)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Set per-user flags
export PER_USER=true
export INSTALL_DIR="${HOME}/.nettrades"
export VENV_DIR="${INSTALL_DIR}/.venv"
export DATA_DIR="${INSTALL_DIR}/data"

# Create per-user directories
mkdir -p "$INSTALL_DIR" "$DATA_DIR" "$INSTALL_DIR/logs"

# Run the setup in per-user mode
./scripts/nettrades-setup.sh all --force --auto --per-user