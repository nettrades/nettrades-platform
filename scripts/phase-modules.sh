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

set -a
source "$PROJECT_ROOT/deploy/docker/.env"
set +a

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Ensure VENV_DIR is available and activate the virtual environment
# VIRTUAL ENVIRONMENT IS NOW MANDATORY – fail if not found
# -----------------------------------------------------------------------------
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    log_info "Activated Python virtual environment: $VENV_DIR"
else
    log_error "Virtual environment not found at $VENV_DIR"
    log_info "Please run Phase 1 first: ./scripts/nettrades-setup.sh dev"
    exit 1
fi

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

log_step "Ensuring admin is in GPU administrator groups..."
ODOO_ADMIN_SCRIPT="$SCRIPT_DIR/configure-odoo-admin.sh"
if [[ -f "$ODOO_ADMIN_SCRIPT" ]] && [[ -n "${ODOO_ADMIN_PASSWORD:-}" ]]; then
    cd "$PROJECT_ROOT/deploy/docker"

    # Capture the script's full output so we can both forward its log
    # lines and parse its structured stdout. On this second pass the
    # service user already exists, so the script reuses the password
    # from .env and only regenerates the API key.
    CONFIGURE_OUTPUT=$(
        docker compose exec -T \
            -e ODOO_ADMIN_PASSWORD="$ODOO_ADMIN_PASSWORD" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e NETTRADES_SERVICE_PASSWORD="$NETTRADES_SERVICE_PASSWORD" \
            -e DYNAMO_API_KEY="${DYNAMO_API_KEY:-dummy}" \
            -e LLM_BASE_URL="${LLM_BASE_URL:-http://llama-cpp:8080/v1}" \
            odoo bash -c "$(cat "$ODOO_ADMIN_SCRIPT")" 2>&1
    )
    printf '%s\n' "$CONFIGURE_OUTPUT" | grep '^\[configure-odoo-admin\]' || true

    SERVICE_UID=$(printf '%s\n' "$CONFIGURE_OUTPUT" | grep '^NETTRADES_SERVICE_UID=' | tail -1 | cut -d= -f2- | tr -d '\r')
    SERVICE_PASSWORD=$(printf '%s\n' "$CONFIGURE_OUTPUT" | grep '^NETTRADES_SERVICE_PASSWORD=' | tail -1 | cut -d= -f2- | tr -d '\r')
    SERVICE_API_KEY=$(printf '%s\n' "$CONFIGURE_OUTPUT" | grep '^NETTRADES_SERVICE_API_KEY=' | tail -1 | cut -d= -f2- | tr -d '\r')

    ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
    if [[ -n "$SERVICE_UID" ]] && [[ -f "$ENV_FILE" ]]; then
        safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_UID" "$SERVICE_UID"
        export NETTRADES_SERVICE_UID="$SERVICE_UID"
        log_success "Service user UID recorded in .env: $SERVICE_UID"
    fi
    if [[ -n "$SERVICE_PASSWORD" ]] && [[ -f "$ENV_FILE" ]]; then
        safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_PASSWORD" "$SERVICE_PASSWORD"
        export NETTRADES_SERVICE_PASSWORD="$SERVICE_PASSWORD"
    fi
    if [[ -n "$SERVICE_API_KEY" ]] && [[ -f "$ENV_FILE" ]]; then
        safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_API_KEY" "$SERVICE_API_KEY"
        export NETTRADES_SERVICE_API_KEY="$SERVICE_API_KEY"
        log_success "Service user API key recorded in .env"
    fi

    # Recreate langgraph-server to apply the new API key.
    if [[ -n "$SERVICE_UID" ]] && [[ -n "$SERVICE_PASSWORD" ]]; then
        log_step "Recreating langgraph-server to apply service credentials..."
        docker compose up -d --force-recreate langgraph-server \
            || log_warning "Failed to recreate langgraph-server"
    fi

    cd "$PROJECT_ROOT"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 4
log_success "Phase 4 completed – modules installed"