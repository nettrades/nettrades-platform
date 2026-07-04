#!/bin/bash
# =============================================================================
# FILE: scripts/lib/common.sh
# =============================================================================
# PURPOSE:
#   Shared utility functions for all phase scripts.
#   Sourced by nettrades-setup.sh and all phase-*.sh scripts.
# =============================================================================

# Source logging if not already loaded
if [[ -z "${log_info:-}" ]]; then
    source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logging.sh"
fi

# -----------------------------------------------------------------------------
# OS Detection
# -----------------------------------------------------------------------------
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# -----------------------------------------------------------------------------
# GPU Detection
# -----------------------------------------------------------------------------
detect_gpu() {
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        return 0
    else
        return 1
    fi
}

get_gpu_name() {
    if detect_gpu; then
        nvidia-smi --query-gpu=name --format=csv,noheader | head -1
    else
        echo "none"
    fi
}

# -----------------------------------------------------------------------------
# Phase Marker Functions (idempotency)
# -----------------------------------------------------------------------------
get_phase_marker() {
    local phase="$1"
    echo "$PROJECT_ROOT/.phase-${phase}-complete"
}

phase_completed() {
    local phase="$1"
    local marker
    marker=$(get_phase_marker "$phase")
    # Phase is considered completed if the marker exists AND force is NOT true
    if [[ -f "$marker" ]] && [[ "${FORCE:-false}" != "true" ]]; then
        return 0
    else
        return 1
    fi
}

mark_phase_complete() {
    local phase="$1"
    local marker
    marker=$(get_phase_marker "$phase")
    echo "$(date -Iseconds)" > "$marker"
    log_success "Phase $phase completed"
}

# -----------------------------------------------------------------------------
# Production Safety Check for --force
# -----------------------------------------------------------------------------
confirm_force_production() {
    local phase_name="$1"
    local env="${ENVIRONMENT:-development}"

    if [[ "${FORCE:-false}" != "true" ]]; then
        return 0
    fi

    if [[ "$env" == "production" ]]; then
        echo ""
        echo "⚠️  ⚠️  ⚠️  WARNING  ⚠️  ⚠️  ⚠️"
        echo ""
        echo "You are running '--force' on Phase $phase_name in a PRODUCTION environment."
        echo "This will OVERWRITE existing configuration and may cause data loss."
        echo ""
        echo "This action CANNOT be undone."
        echo ""
        read -p "Type 'YES' to continue: " CONFIRM
        if [[ "$CONFIRM" != "YES" ]]; then
            echo "Aborted."
            exit 1
        fi
        echo ""
    fi
}

# -----------------------------------------------------------------------------
# Docker & Kubernetes Tool Checks
# -----------------------------------------------------------------------------
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker not found. Please install Docker."
        return 1
    fi
    if ! docker info &>/dev/null; then
        log_error "Docker daemon not running."
        return 1
    fi
    return 0
}

check_kubectl() {
    if ! command -v kubectl &>/dev/null; then
        log_error "kubectl not found. Please install kubectl."
        return 1
    fi
    return 0
}

check_helm() {
    if ! command -v helm &>/dev/null; then
        log_error "helm not found. Please install helm."
        return 1
    fi
    return 0
}

check_talosctl() {
    if ! command -v talosctl &>/dev/null; then
        log_error "talosctl not found. Please install talosctl."
        return 1
    fi
    return 0
}

# -----------------------------------------------------------------------------
# WireGuard Helper
# -----------------------------------------------------------------------------
generate_wireguard_key() {
    if command -v wg &>/dev/null; then
        wg genkey | tr -d '\n'
    else
        openssl rand -base64 32 | tr -d '\n'
    fi
}

# -----------------------------------------------------------------------------
# Secret Generation
# -----------------------------------------------------------------------------
generate_secret() {
    openssl rand -base64 32 | tr -d '\n'
}

generate_password() {
    openssl rand -base64 24 | tr -d '\n'
}