#!/bin/bash
# =============================================================================
# FILE: scripts/phase-modules.sh
# =============================================================================
# PURPOSE:
#   Phase 5: Odoo Module Installation.
#   This phase installs or upgrades all NETTRADES custom Odoo modules.
#   It calls the existing install-modules.sh script.
#
#   Modules installed:
#     - nettrades_core
#     - nettrades_good_answer
#     - nettrades_ask_someone
#     - nettrades_gpu_admin
#     - nettrades_gpustack_adapter
#     - nettrades_queue
#     - nettrades_bridge
#     - nettrades_data_collection
#     - nettrades_trigger
#     - nettrades_loop
#     - nettrades_self_improving_config
#     - nettrades_fairness
#     - nettrades_onboarding
#     - nettrades_job_matching
#     - nettrades_proposals
#     - nettrades_lead_scoring
#     - nettrades_research
#     - nettrades_chatbot
#     - nettrades_notifications
#     - nettrades_pwa
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

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 5 && [[ "$FORCE" != true ]]; then
    log_warning "Phase 5 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------
if ! phase_completed 2; then
    log_info "Phase 2 not completed. Running Phase 2 first..."
    bash "$SCRIPT_DIR/phase-deploy.sh"
fi

# -----------------------------------------------------------------------------
# Install modules
# -----------------------------------------------------------------------------
log_step "Installing Odoo modules..."

if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
    ARGS=""
    [[ "$FORCE" == true ]] && ARGS="$ARGS --force"
    [[ "$UPGRADE" == true ]] && ARGS="$ARGS --upgrade"

    bash "$SCRIPT_DIR/install-modules.sh" $ARGS
else
    log_error "install-modules.sh not found at $SCRIPT_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 5

log_success "Phase 5 completed – modules installed"