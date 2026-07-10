#!/bin/bash
# =============================================================================
# FILE: scripts/phase-modules.sh
# =============================================================================
# PURPOSE:
#   Phase 4: Odoo Module Installation.
#   This phase installs or upgrades all NETTRADES custom Odoo modules.
#
#   IMPORTANT: This script does NOT re-run Phase 2 (unlike the previous version).
#   The main orchestrator (nettrades-setup.sh) ensures correct phase ordering.
#
# USAGE:
#   ./phase-modules.sh [--auto] [--force] [--upgrade]
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
UPGRADE="${UPGRADE:-false}"
SKIP_INSTALLED="${SKIP_INSTALLED:-true}"
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "4"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 4 && [[ "$FORCE" != true ]]; then
    log_warning "Phase 4 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# # Check if Phase 2 marker exists (ignoring FORCE)
# -----------------------------------------------------------------------------
# Check if Phase 2 marker exists (ignoring FORCE) – if missing, Phase 2 must be run.
if [[ ! -f "$PROJECT_ROOT/.phase-2-complete" ]]; then
    log_error "Phase 2 (Deployment) must be completed before installing modules."
    log_error "Please run: ./scripts/nettrades-setup.sh deploy --force"
    exit 1
fi

# -----------------------------------------------------------------------------
# Install modules
# -----------------------------------------------------------------------------
log_step "Installing Odoo modules..."

if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
    ARGS=""
    [[ "$FORCE" == true ]] && ARGS="$ARGS --force"
    [[ "$UPGRADE" == true ]] && ARGS="$ARGS --upgrade"
    [[ "$AUTO" == true ]] && ARGS="$ARGS --auto"
    bash "$SCRIPT_DIR/install-modules.sh" $ARGS
else
    log_error "install-modules.sh not found at $SCRIPT_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 4
log_success "Phase 4 completed – modules installed"