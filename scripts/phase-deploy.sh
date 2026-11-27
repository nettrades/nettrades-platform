#!/bin/bash
# =============================================================================
# FILE: scripts/phase-deploy.sh
# =============================================================================
# PURPOSE:
#   Phase 2: Single-VM Docker deployment with Hub/Spoke/Addon detection.
#   This script detects the environment and deploys appropriately:
#     - HUB   : Full NETTRADES stack (Odoo, Dynamo, LangGraph, etc.)
#     - SPOKE : Lightweight agent only (no Odoo, no DB)
#     - ADDON : Add NETTRADES to an existing Odoo installation
#
#   When in HUB mode, it performs the full original deployment steps:
#   1. Create required directories.
#   2. Download models from ModelScope mirror.
#   3. Build custom Docker images (Odoo, LangGraph).
#   4. Generate `init-db.sql` with all NETTRADES tables.
#   5. Run security hardening (if Phase 0 not completed).
#   6. Start PostgreSQL and initialise the database.
#   7. Build and start the full Docker Compose stack.
#   8. Install all NETTRADES Odoo modules.
#   9. Set up cron for daily backups.
#   10. Verify service health.
#   11. Ensure Let's Encrypt certificate.
#   12. Display final status.
#
# UPDATES (2026-08):
#   - Added Hub/Spoke/Addon detection logic.
#   - Spoke nodes install only lightweight agent (no Odoo, no DB).
#   - Detection of existing Odoo installations.
#   - Detection of existing NETTRADES sub-hubs on the network.
#   - Support for adding NETTRADES to existing Odoo installations.
#   - All original deployment steps preserved for HUB mode.
#
#   UPDATES (2026-08):
#   - Improved Hub/Spoke/Addon detection:
#     * If --force and .env is missing, force HUB mode (fresh install).
#     * If Odoo is running in a Docker container, treat as HUB (not ADDON).
#   - All original deployment steps preserved for HUB mode.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

set -euo pipefail

# -----------------------------------------------------------------------------
# Parse arguments early (so AUTO, FORCE, etc. are available)
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
UPGRADE="${UPGRADE:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"

# -----------------------------------------------------------------------------
# Parse command-line flags
# -----------------------------------------------------------------------------
# The environment variables above are the source of truth for callers that
# set them explicitly (e.g. `FORCE=true ./phase-deploy.sh`). But the more
# natural form for an operator is `./phase-deploy.sh --force --auto`.
# Without this block, the flags were silently ignored: FORCE stayed false,
# and the phase_completed check short-circuited on a stale phase marker
# even though the operator asked for --force. Diagnosed 2026-11-16.
#
# Precedence: argv overrides env. If both set FORCE, FORCE=true.
# -----------------------------------------------------------------------------
for _arg in "$@"; do
    case "$_arg" in
        --force)   FORCE=true ;;
        --auto)    AUTO=true ;;
        --upgrade) UPGRADE=true ;;
    esac
done
unset _arg
export FORCE AUTO UPGRADE

REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
RESET_DATA="${RESET_DATA:-false}"
WITH_CUVS="${WITH_CUVS:-false}"
WITH_FINETUNE="${WITH_FINETUNE:-false}"
WITH_GROVE="${WITH_GROVE:-false}"
WITH_KAI="${WITH_KAI:-false}"
WITH_ROUTER="${WITH_ROUTER:-false}"
DOMAIN="${DOMAIN:-}"
export FORCE WITH_CUVS WITH_FINETUNE WITH_GROVE WITH_KAI WITH_ROUTER DOMAIN

WITH_WINDOWS_LAUNCHER="${WITH_WINDOWS_LAUNCHER:-false}"
export WITH_WINDOWS_LAUNCHER

# -----------------------------------------------------------------------------
# Network setup (needed for both hub and spoke)
# -----------------------------------------------------------------------------
if ! docker network ls --format '{{.Name}}' | grep -q "^web$"; then
    docker network create web
fi

# Set PROJECT_ROOT if not already set
if [ -z "${PROJECT_ROOT:-}" ]; then
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export PROJECT_ROOT
fi

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Detect WSL2 (needed later)
# -----------------------------------------------------------------------------
IS_WSL=false
if grep -q Microsoft /proc/version 2>/dev/null || grep -q WSL /proc/sys/fs/binfmt_misc/WSLInterop 2>/dev/null; then
    IS_WSL=true
    log_info "WSL2 detected – gVisor will be disabled for compatibility."
fi
export IS_WSL

# =============================================================================
# HUB / SPOKE / ADDON DETECTION (IMPROVED)
# =============================================================================
DETECTION_MODE="${DETECTION_MODE:-auto}"  # auto, hub, spoke, addon

detect_environment() {
    log_step "Detecting deployment environment..."

    local is_hub=false
    local has_odoo=false
    local has_nettrades=false
    local sub_hub_found=false
    local odoo_in_docker=false

    # ---- Check if we should force HUB mode ----
    # If FORCE is true, assume HUB deployment (fresh install)
    if [[ "$FORCE" == true ]]; then
        log_info "Force mode – forcing HUB deployment."
        DEPLOYMENT_MODE="hub"
        log_success "Deployment mode: HUB (forced)"
        export DEPLOYMENT_MODE
        return
    fi

    # ---- Check if Odoo is installed locally (on the host) ----
    if command -v odoo &>/dev/null || ps aux | grep -v grep | grep -q "odoo"; then
        has_odoo=true
        log_info "Odoo detected locally (process)"
    fi

    # ---- Check if Odoo port 8069 is open ----
    if nc -z localhost 8069 2>/dev/null || curl -s --connect-timeout 2 http://localhost:8069 >/dev/null 2>&1; then
        # Check if the process listening on 8069 is a Docker container
        if command -v docker &>/dev/null; then
            # Find the container that exposes port 8069
            CONTAINER_ID=$(docker ps --filter "publish=8069" --format "{{.ID}}" 2>/dev/null | head -1)
            if [[ -n "$CONTAINER_ID" ]]; then
                # Check if this container is part of the current compose project (by label)
                PROJECT_NAME=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]//g')
                COMPOSE_PROJECT=$(docker inspect "$CONTAINER_ID" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)
                if [[ "$COMPOSE_PROJECT" == "$PROJECT_NAME" ]]; then
                    odoo_in_docker=true
                    log_info "Odoo is running in a Docker container from the current compose project – not an external installation."
                else
                    # It's a Docker container but not from our project – treat as external.
                    has_odoo=true
                    log_info "Odoo detected on port 8069 (external Docker container)."
                fi
            else
                # Port open but not a Docker container – could be a native service.
                has_odoo=true
                log_info "Odoo detected on port 8069 (native process)."
            fi
        else
            # Docker not available – assume it's a native service.
            has_odoo=true
            log_info "Odoo detected on port 8069."
        fi
    fi

    # ---- Check if NETTRADES tables exist ----
    if [[ "$has_odoo" == true ]] && command -v psql &>/dev/null; then
        # Try to connect to the database (may need password)
        if PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -U odoo -d odoo -t -c "SELECT 1 FROM information_schema.tables WHERE table_name='nettrades_users'" 2>/dev/null | grep -q 1; then
            has_nettrades=true
            log_info "NETTRADES tables detected in Odoo database"
        fi
    fi

    # ---- Check for sub-hub on the network (mDNS) ----
    if command -v avahi-browse &>/dev/null; then
        if avahi-browse -t _nettrades._tcp -r 2>/dev/null | grep -q "NETTRADES"; then
            sub_hub_found=true
            log_info "NETTRADES sub-hub found on the network"
        fi
    fi

    # ---- Check for .nettrades_hub marker file ----
    if [[ -f "$PROJECT_ROOT/.nettrades_hub" ]]; then
        is_hub=true
        log_info "Hub marker file found"
    fi

    # ---- Determine deployment mode ----
    if [[ "$DETECTION_MODE" == "hub" ]] || [[ "$is_hub" == true ]]; then
        DEPLOYMENT_MODE="hub"
        log_success "Deployment mode: HUB"
    elif [[ "$DETECTION_MODE" == "sub-hub" ]] || [[ "${SUB_HUB_MODE:-false}" == "true" ]]; then
        DEPLOYMENT_MODE="sub-hub"
        log_success "Deployment mode: SUB-HUB"
    elif [[ "$DETECTION_MODE" == "spoke" ]] || [[ -n "${HUB_HOST:-}" ]]; then
        DEPLOYMENT_MODE="spoke"
        log_success "Deployment mode: SPOKE"
    elif [[ "$sub_hub_found" == true ]]; then
        DEPLOYMENT_MODE="spoke"
        log_success "Deployment mode: SPOKE (sub-hub found on network)"
    elif [[ "$has_odoo" == true ]] && [[ "$has_nettrades" == true ]]; then
        DEPLOYMENT_MODE="addon"
        log_success "Deployment mode: ADDON (Odoo + NETTRADES tables exist)"
    elif [[ "$has_odoo" == true ]] && [[ "$has_nettrades" == false ]] && [[ "$odoo_in_docker" == false ]]; then
        # Odoo exists but no NETTRADES tables, and it's NOT a container from our stack – likely an external Odoo.
        DEPLOYMENT_MODE="addon"
        log_success "Deployment mode: ADDON (external Odoo exists, NETTRADES tables missing)"
    elif [[ "$has_odoo" == true ]] && [[ "$odoo_in_docker" == true ]]; then
        # Odoo is in a container from our project, but no NETTRADES tables – treat as HUB (we are doing a fresh install).
        DEPLOYMENT_MODE="hub"
        log_success "Deployment mode: HUB (Odoo container from this project, fresh install)"
    else
        DEPLOYMENT_MODE="hub"
        log_success "Deployment mode: HUB (no Odoo or NETTRADES found)"
    fi

    export DEPLOYMENT_MODE
}

# Run detection
detect_environment

# -----------------------------------------------------------------------------
# SPOKE DEPLOYMENT (Lightweight)
# -----------------------------------------------------------------------------
if [[ "$DEPLOYMENT_MODE" == "spoke" ]]; then
    log_header "SPOKE Deployment - Lightweight Node"

    if [[ -z "${HUB_HOST:-}" ]] || [[ -z "${TOKEN:-}" ]]; then
        log_error "Spoke mode requires --hub-host and --token."
        log_info "Usage: ./scripts/nettrades-setup.sh spoke --hub-host=<IP> --token=<TOKEN>"
        exit 1
    fi

    log_info "Delegating to install-spoke.sh..."
    exec bash "$SCRIPT_DIR/install-spoke.sh" \
        --hub-host="$HUB_HOST" \
        --token="$TOKEN" \
        --inference-capability="${INFERENCE_CAPABILITY:-rpc_worker}" \
        --no-wireguard
fi

# -----------------------------------------------------------------------------
# ADDON DEPLOYMENT (Add to existing Odoo)
# -----------------------------------------------------------------------------
if [[ "$DEPLOYMENT_MODE" == "addon" ]]; then
    log_header "ADDON Deployment - Adding NETTRADES to Existing Odoo"

    # Detect Odoo installation path
    ODOO_PATH=""
    if command -v odoo &>/dev/null; then
        ODOO_PATH=$(which odoo)
    elif [[ -d "/usr/lib/python3/dist-packages/odoo" ]]; then
        ODOO_PATH="/usr/lib/python3/dist-packages/odoo"
    elif [[ -d "/usr/local/lib/python3.12/dist-packages/odoo" ]]; then
        ODOO_PATH="/usr/local/lib/python3.12/dist-packages/odoo"
    fi

    if [[ -z "$ODOO_PATH" ]]; then
        log_error "Could not detect Odoo installation path. ADDON mode requires Odoo installed on the host."
        log_info "If you want a full platform deployment, use HUB mode (remove existing containers or set FORCE_HUB=true)."
        exit 1
    fi

    log_info "Odoo installation found at: $ODOO_PATH"

    # Copy NETTRADES modules to Odoo addons path
    ADDONS_PATH="$ODOO_PATH/addons"
    if [[ -d "$ADDONS_PATH" ]]; then
        log_step "Copying NETTRADES modules to Odoo addons..."
        cp -r "$PROJECT_ROOT/odoo-modules/nettrades_"* "$ADDONS_PATH/"
        log_success "Modules copied"
    else
        log_error "Odoo addons path not found: $ADDONS_PATH"
        exit 1
    fi

    # Create or update the database schema
    log_step "Creating NETTRADES tables in existing Odoo database..."
    DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
    if [[ -f "$DEPLOY_DIR/init-db.sql" ]]; then
        # Try to run SQL directly (requires password from .env)
        if [[ -f "$DEPLOY_DIR/.env" ]]; then
            source "$DEPLOY_DIR/.env"
            PGPASSWORD="$POSTGRES_PASSWORD" psql -h localhost -U odoo -d odoo -f "$DEPLOY_DIR/init-db.sql" 2>/dev/null || {
                log_warning "Could not execute SQL directly. Trying via Odoo module installation..."
            }
        else
            log_warning ".env not found – skipping direct SQL"
        fi
    fi

    # Install NETTRADES modules via Odoo
    log_step "Installing NETTRADES Odoo modules..."
    if command -v odoo &>/dev/null; then
        sudo odoo -d odoo -i nettrades_core --stop-after-init --log-level=info || {
            log_warning "Odoo module installation failed. Please install manually."
        }
    fi

    log_success "Addon deployment completed"
    exit 0
fi

# =============================================================================
# HUB DEPLOYMENT – FULL ORIGINAL PHASE-DEPLOY LOGIC
# =============================================================================
# The following code is the original phase-deploy.sh, preserved in its entirety.
# It runs only when DEPLOYMENT_MODE is "hub".
# =============================================================================

if [[ "$DEPLOYMENT_MODE" == "hub" ]]; then
    log_header "HUB Deployment - Full NETTRADES Stack"

    # -------------------------------------------------------------------------
    # Phase marker and prerequisites
    # -------------------------------------------------------------------------
    if phase_completed 2 && [[ "$FORCE" != true ]]; then
        log_warning "Phase 2 already completed. Use --force to re-run."
        exit 0
    fi

    if ! phase_completed 1; then
        log_info "Phase 1 not completed. Running Phase 1 first..."
        bash "$SCRIPT_DIR/phase-env.sh"
    fi

    check_docker || exit 1

    # -------------------------------------------------------------------------
    # Set up paths
    # -------------------------------------------------------------------------
    DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
    ENV_FILE="$DEPLOY_DIR/.env"
    COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yaml"
    DATA_DIR="$PROJECT_ROOT/data"
    LOGS_DIR="$PROJECT_ROOT/logs"
    DYNAMO_DATA_DIR="$DEPLOY_DIR/dynamo-data"
    MODELS_DIR="$DYNAMO_DATA_DIR/models"
    ODOO_DATA_DIR="$DEPLOY_DIR/odoo-data"

    if [[ ! -f "$ENV_FILE" ]]; then
        log_error ".env not found. Please run Phase 1 first."
        exit 1
    fi

    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "docker-compose.yaml not found at $COMPOSE_FILE"
        exit 1
    fi

    # -------------------------------------------------------------------------
    # Source .env to get runtime configuration
    # -------------------------------------------------------------------------
    set -a
    source "$ENV_FILE"
    set +a

    # -------------------------------------------------------------------------
    # Ensure VENV_DIR is available and activate the virtual environment
    # -------------------------------------------------------------------------
    VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        log_info "Activated Python virtual environment: $VENV_DIR"
    else
        log_error "Virtual environment not found at $VENV_DIR"
        log_info "Please run Phase 1 first: ./scripts/nettrades-setup.sh dev"
        exit 1
    fi

    # -------------------------------------------------------------------------
    # SAFE PASSWORD GENERATOR – only alphanumeric characters
    # -------------------------------------------------------------------------
    generate_safe_password() {
        openssl rand -base64 24 | tr -d '+/=' | tr -d '\n' | cut -c1-24
    }

    # -------------------------------------------------------------------------
    # Helper: Wait for PostgreSQL
    # -------------------------------------------------------------------------
    wait_for_postgres() {
        local retries=60
        local delay=2
        log_step "Waiting for PostgreSQL to become ready..."
        for i in $(seq 1 $retries); do
            if docker compose exec -T postgres psql -U odoo -d odoo -c "SELECT 1" &>/dev/null; then
                log_success "PostgreSQL is ready"
                return 0
            fi
            if [ $((i % 10)) -eq 0 ]; then
                log_info "Still waiting for PostgreSQL... ($i/$retries attempts)"
            fi
            sleep $delay
        done
        log_error "PostgreSQL did not become ready within $((retries * delay)) seconds"
        log_info "Check PostgreSQL logs with: docker logs $(docker compose ps -q postgres) --tail 50"
        return 1
    }

    # -------------------------------------------------------------------------
    # Helper: Enable pgcrypto
    # -------------------------------------------------------------------------
    enable_pgcrypto() {
        log_step "Enabling pgcrypto extension in PostgreSQL..."
        if docker compose exec -T postgres psql -U odoo -d odoo -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null; then
            log_success "pgcrypto extension enabled"
            return 0
        else
            log_warning "Could not enable pgcrypto – emergency user creation may fail"
            return 1
        fi
    }

    # -------------------------------------------------------------------------
    # Helper: Install bcrypt
    # -------------------------------------------------------------------------
    ensure_bcrypt() {
        log_step "Ensuring bcrypt is available for Prometheus password hashing..."
        if python3 -c "import bcrypt" 2>/dev/null; then
            log_success "bcrypt already available"
            return 0
        else
            log_info "bcrypt not found – installing via pip in the virtual environment..."
            if "$VENV_DIR/bin/python" -m pip install bcrypt 2>/dev/null; then
                log_success "bcrypt installed successfully"
                return 0
            else
                log_warning "Could not install bcrypt. Fallback to plain-text passwords."
                return 1
            fi
        fi
    }

    # -----------------------------------------------------------------------------
    # DOMAIN CONFIGURATION & LET'S ENCRYPT SETUP
    # -----------------------------------------------------------------------------
    configure_domain() {
        local domain="${DOMAIN:-}"
        local acme_file="$DEPLOY_DIR/traefik-data/acme.json"

        # If DOMAIN is already set and valid, use it — do NOT auto-detect.
        if [[ -n "$domain" && "$domain" != "changeit" && "$domain" != "localhost" && "$domain" != "nettrades.ai" ]]; then
            if is_valid_domain_or_ip "$domain"; then
                log_info "Using existing DOMAIN from .env: $domain"
                if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$domain" == "localhost" ]]; then
                    log_warning "DOMAIN is an IP or localhost. Let's Encrypt cannot issue certificates."
                    USE_LETSENCRYPT=false
                else
                    USE_LETSENCRYPT=true
                fi
                export DOMAIN USE_LETSENCRYPT
                return
            fi
        fi

        # Only auto-detect if DOMAIN is empty or still a placeholder
        log_info "DOMAIN not configured or using default. Auto-detecting..."
        local public_ip=$(curl -s ifconfig.me 2>/dev/null || echo "")
        if [[ -n "$public_ip" ]]; then
            DOMAIN="$public_ip"
            log_info "Using detected public IP: $DOMAIN"
        else
            DOMAIN="localhost"
            log_info "Could not detect public IP. Using localhost."
        fi
        safe_sed_replace "$ENV_FILE" "DOMAIN" "$DOMAIN"
        log_success "DOMAIN set to: $DOMAIN"
        
        if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$DOMAIN" == "localhost" ]]; then
            log_warning "DOMAIN is an IP or localhost. Let's Encrypt cannot issue certificates."
            log_info "Using self-signed certificate. Your browser will show a warning."
            USE_LETSENCRYPT=false
        else
            if command -v dig &>/dev/null; then
                if dig +short "$DOMAIN" | grep -q .; then
                    log_success "Domain $DOMAIN resolves to an IP address."
                    USE_LETSENCRYPT=true
                else
                    log_warning "Domain $DOMAIN does not resolve. Using self-signed certificate."
                    USE_LETSENCRYPT=false
                fi
            else
                # No DNS tools – assume domain is valid
                USE_LETSENCRYPT=true
            fi
        fi
        export DOMAIN USE_LETSENCRYPT
    }

    # -------------------------------------------------------------------------
    # Production Safety Check (already done, but keep for consistency)
    # -------------------------------------------------------------------------
    confirm_force_production "2"

    # -------------------------------------------------------------------------
    # Download HF model for Dynamo (if not already present)
    # -------------------------------------------------------------------------
    if [[ "${INFERENCE_ENGINE:-auto}" == "auto" ]] || [[ "${INFERENCE_ENGINE:-auto}" == "dynamo" ]]; then
        log_step "Downloading HF model for Dynamo (vLLM) from ModelScope mirror..."
        mkdir -p "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}"
        if bash "$SCRIPT_DIR/download-model.sh" --model "${MODEL_NAME:-deepseek-7b}" --format hf --dir "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}"; then
            log_success "HF model downloaded to $MODELS_DIR/${MODEL_NAME:-deepseek-7b}"

            # 2026-10-23: Resolve Git LFS pointers to real weights.
            # HuggingFace and ModelScope often serve .safetensors files
            # as 135-byte LFS pointers on a plain git clone. Without
            # `git lfs pull`, vLLM fails at load time with a size
            # mismatch error that is very hard to diagnose.
            if [[ -d "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}/.git" ]]; then
                log_info "Resolving Git LFS objects for HF model..."
                ( cd "$MODELS_DIR/${MODEL_NAME:-deepseek-7b}" \
                  && git lfs install >/dev/null 2>&1 \
                  && git lfs pull ) \
                    && log_success "Git LFS pull complete" \
                    || log_warning "git lfs pull failed — model may be incomplete"
            fi
        else
            log_warning "HF model download failed. Dynamo worker will not start."
        fi
    fi

    # -------------------------------------------------------------------------
    # Ensure Dynamo model is in the correct location
    # -------------------------------------------------------------------------
    if [[ "${INFERENCE_ENGINE:-auto}" == "auto" ]] || [[ "${INFERENCE_ENGINE:-auto}" == "dynamo" ]]; then
        EXPECTED_MODEL_DIR="$MODELS_DIR/${MODEL_NAME:-deepseek-7b}"
        if [[ -d "$EXPECTED_MODEL_DIR" ]] && [[ -f "$EXPECTED_MODEL_DIR/config.json" ]]; then
            log_success "Dynamo model found at $EXPECTED_MODEL_DIR"
        else
            log_info "Searching for downloaded model..."
            CONFIG_FILE=$(find "$MODELS_DIR" -name "config.json" -type f 2>/dev/null | head -1)
            if [[ -n "$CONFIG_FILE" ]]; then
                ACTUAL_MODEL_DIR=$(dirname "$CONFIG_FILE")
                log_info "Found model at $ACTUAL_MODEL_DIR"
                if [[ ! -e "$EXPECTED_MODEL_DIR" ]]; then
                    ln -s "$ACTUAL_MODEL_DIR" "$EXPECTED_MODEL_DIR"
                    log_success "Created symlink from $ACTUAL_MODEL_DIR to $EXPECTED_MODEL_DIR"
                else
                    log_warning "Expected model directory exists but config.json not found. Please check manually."
                fi
            else
                log_warning "No config.json found in $MODELS_DIR. Dynamo worker may fail."
            fi
        fi
    fi

    # -------------------------------------------------------------------------
    # Determine tenant type for runtime selection
    # -------------------------------------------------------------------------
    TENANT_TYPE="${TENANT_TYPE:-enterprise}"
    log_info "Tenant type: $TENANT_TYPE"

    # -------------------------------------------------------------------------
    # Runtime Selection - Tenant-Aware
    # -------------------------------------------------------------------------
    RUNTIME_ODOO="${RUNTIME_ODOO:-}"
    RUNTIME_LANGGRAPH="${RUNTIME_LANGGRAPH:-}"
    RUNTIME_SELF_IMPROVING="${RUNTIME_SELF_IMPROVING:-}"
    RUNTIME_UI="${RUNTIME_UI:-}"
    RUNTIME_DYNAMO="${RUNTIME_DYNAMO:-}"
    RUNTIME_POSTGRES="${RUNTIME_POSTGRES:-}"
    RUNTIME_VALKEY="${RUNTIME_VALKEY:-}"

    if [ "$IS_WSL" = true ]; then
        log_info "WSL2 detected – forcing all services to use runc runtime."
        RUNTIME_ODOO=""
        RUNTIME_LANGGRAPH=""
        RUNTIME_SELF_IMPROVING=""
        RUNTIME_UI=""
        RUNTIME_DYNAMO=""
        RUNTIME_POSTGRES=""
        RUNTIME_VALKEY=""
    fi

    if [ "$TENANT_TYPE" = "freelancer" ] || [ "$TENANT_TYPE" = "home" ]; then
        log_info "Untrusted tenant type ($TENANT_TYPE) – enabling gVisor for AI agent services."
        if [ -z "$RUNTIME_LANGGRAPH" ]; then
            RUNTIME_LANGGRAPH="runsc"
        fi
        if [ -z "$RUNTIME_SELF_IMPROVING" ]; then
            RUNTIME_SELF_IMPROVING="runsc"
        fi
        if [ -z "$RUNTIME_UI" ]; then
            RUNTIME_UI="runsc"
        fi
        RUNTIME_DYNAMO=""
        RUNTIME_POSTGRES=""
        RUNTIME_VALKEY=""
    fi

    export RUNTIME_ODOO RUNTIME_LANGGRAPH RUNTIME_SELF_IMPROVING RUNTIME_UI \
           RUNTIME_DYNAMO RUNTIME_POSTGRES RUNTIME_VALKEY

    log_info "Runtime configuration:"
    log_info "  Odoo: ${RUNTIME_ODOO:-runc}"
    log_info "  LangGraph: ${RUNTIME_LANGGRAPH:-runc}"
    log_info "  Self-Improving: ${RUNTIME_SELF_IMPROVING:-runc}"
    log_info "  UI: ${RUNTIME_UI:-runc}"
    log_info "  Dynamo: ${RUNTIME_DYNAMO:-runc}"
    log_info "  PostgreSQL: ${RUNTIME_POSTGRES:-runc}"
    log_info "  Valkey: ${RUNTIME_VALKEY:-runc}"

    # -------------------------------------------------------------------------
    # 1. Create required directories (including redirector landing page)
    # -------------------------------------------------------------------------
    log_step "Creating required directories..."
    mkdir -p "$DATA_DIR/postgres" "$DATA_DIR/odoo" "$DATA_DIR/valkey" "$DATA_DIR/forgejo"
    mkdir -p "$DATA_DIR/prometheus" "$DATA_DIR/grafana" "$DATA_DIR/backups"
    mkdir -p "$DYNAMO_DATA_DIR" "$MODELS_DIR" "$LOGS_DIR" "$ODOO_DATA_DIR"
    mkdir -p "redirector/landing-page"

    # Ensure rpc.env exists BEFORE docker compose up. If this file is
    # missing, Docker creates it as a directory when binding the mount
    # into the master container, which breaks the RPC track and leaves a
    # stale directory behind after `docker compose down`. The file is
    # written with safe defaults: no backends, no split, master runs
    # single-node. The scheduler overwrites it the first time a cluster
    # is launched.
    RPC_ENV_FILE="$DEPLOY_DIR/rpc.env"
    if [[ ! -f "$RPC_ENV_FILE" ]]; then
        log_info "Creating default rpc.env (RPC_BACKENDS empty)"
        cat > "$RPC_ENV_FILE" << 'RPC_ENV_EOF'
# =============================================================================
# llama.cpp RPC pipeline configuration
# =============================================================================
# This file is written by src/core/rpc_scheduler.py whenever the RPC
# cluster topology changes. Do not edit it manually — the scheduler
# will overwrite your changes on the next launch_cluster() or
# restart_without_node() call.
#
# The master container reads this file at startup. When RPC_BACKENDS
# is empty, the master runs single-node (no distributed offload).
# =============================================================================
RPC_BACKENDS=
RPC_SPLIT=
RPC_MASTER_MODEL=/models/deepseek-r1-distill-qwen-7b-q4_k_m.gguf
RPC_N_GPU_LAYERS=0
RPC_ENV_EOF
        log_success "rpc.env created with safe defaults"
    else
        log_info "rpc.env already exists — preserving operator configuration"
    fi

    if [[ ! -f "redirector/landing-page/index.html" ]]; then
        cat > "redirector/landing-page/index.html" << 'EOF'
<!DOCTYPE html>
<html>
<head><title>NETTRADES Platform</title></head>
<body>
<h1>NETTRADES Platform</h1>
<p>Welcome to the NETTRADES AI Marketplace.</p>
<p><a href="/odoo">Odoo</a> | <a href="http://localhost:3002">AI Chat UI</a></p>
</body>
</html>
EOF
        log_success "Default landing page created"
    fi
    log_success "Directories created"

    # -----------------------------------------------------------------------------
    # Create redirector nginx.conf.template if missing
    # -----------------------------------------------------------------------------
    log_step "Ensuring redirector nginx.conf.template exists..."
    NGINX_TEMPLATE="$DEPLOY_DIR/redirector/nginx.conf.template"
    if [[ ! -f "$NGINX_TEMPLATE" ]]; then
        log_info "nginx.conf.template not found. Creating default template..."
        mkdir -p "$DEPLOY_DIR/redirector"
        cat > "$NGINX_TEMPLATE" << 'EOF'
events {
    worker_connections 1024;
}
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    server {
        listen 80;
        server_name _;

        set $landing_page "${DEFAULT_LANDING_PAGE:-odoo}";

        if ($landing_page = "odoo") {
            return 302 https://${DOMAIN}/odoo;
        }

        if ($landing_page = "ui") {
            return 302 http://${DOMAIN}:3002;
        }

        location / {
            root   /usr/share/nginx/html;
            index  index.html;
            try_files $uri $uri/ /index.html;
        }
    }
}
EOF
        log_success "Created default nginx.conf.template"
    else
        log_success "nginx.conf.template already exists"
    fi

    # =============================================================================
    # EARLY: Download GGUF model for llama.cpp fallback
    # =============================================================================
    if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
        log_step "Downloading GGUF model for llama.cpp..."
        mkdir -p "$MODELS_DIR"
        
        # 1. Use dynamic MODEL_NAME
        if bash "$SCRIPT_DIR/download-model.sh" --model "${MODEL_NAME:-deepseek-7b}" --format gguf --dir "$MODELS_DIR"; then
            log_success "GGUF model downloaded successfully to $MODELS_DIR"
        else
            log_warning "GGUF model download failed. Please check your network or download manually."
        fi

        # 2. Use dynamic MODEL_FILE
        MODEL_FILE="$MODELS_DIR/${MODEL_FILE:-Fanar-1-9B-Instruct.Q4_K_M.gguf}"
        
        if [[ -f "$MODEL_FILE" ]]; then
            FILE_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
            if [[ "$FILE_SIZE" -lt 1000000000 ]]; then
                log_warning "Model file exists but is too small ($FILE_SIZE bytes). It may be corrupted."
                log_info "Please delete $MODEL_FILE and re-run the deployment."
            else
                log_success "Model file validated: $MODEL_FILE ($FILE_SIZE bytes)"
            fi
        else
            log_warning "Model file not found at $MODEL_FILE. llama.cpp will not start."
        fi
    else
        log_warning "download-model.sh not found – skipping llama.cpp model download"
    fi

    # =============================================================================
    # EARLY: Download Audar-ASR-V1-Flash for the llama-asr service.
    # =============================================================================
    # Two files are needed: the decoder GGUF and the audio projector (mmproj).
    # Both land in $MODELS_DIR/audar-asr/. The llama-asr service mounts the
    # same dynamo-data/models volume as llama-cpp, so it reads them in place.
    if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
        log_step "Downloading Audar-ASR-V1-Flash (ASR model + projector)..."
        if bash "$SCRIPT_DIR/download-model.sh" \
             --model audar-asr \
             --format gguf \
             --dir "$MODELS_DIR"; then
            log_success "Audar-ASR-V1-Flash downloaded to $MODELS_DIR/audar-asr"
        else
            log_warning "Audar-ASR-V1-Flash download failed — ASR will be disabled."
            log_warning "Fallback: set ASR_MODEL=qwen3-asr-0.6b in .env and re-run."
        fi
    fi

    # -----------------------------------------------------------------------------
    # Prepare Odoo addons
    # -----------------------------------------------------------------------------
    log_step "Preparing Odoo addons for build..."
    if [[ -f "$SCRIPT_DIR/prepare-odoo-addons.sh" ]]; then
        # Export PROJECT_ROOT so the child script uses the correct root
        export PROJECT_ROOT
        if [[ "$FORCE" == true ]]; then
            bash "$SCRIPT_DIR/prepare-odoo-addons.sh" --force
        else
            bash "$SCRIPT_DIR/prepare-odoo-addons.sh"
        fi
    else
        log_warning "prepare-odoo-addons.sh not found – skipping addon preparation"
    fi

    # -----------------------------------------------------------------------------
    # Build custom Docker images
    # -----------------------------------------------------------------------------
    log_step "Building custom Docker images..."

    ODOO_DOCKERFILE="$DEPLOY_DIR/Dockerfile.odoo"
    if [[ -f "$ODOO_DOCKERFILE" ]]; then
        if [[ "$FORCE" == true ]] || ! docker image inspect nettrades-odoo:latest &>/dev/null; then
            log_info "Building Odoo image (force=$FORCE)..."
            docker build -f "$ODOO_DOCKERFILE" -t nettrades-odoo:latest "$DEPLOY_DIR"
            log_success "Odoo image built"
        else
            log_success "Odoo image already exists (use --force to rebuild)"
        fi
    else
        log_warning "Dockerfile.odoo not found – skipping Odoo image build"
    fi

    LANGGRAPH_DOCKERFILE="$PROJECT_ROOT/src/core/Dockerfile"
    if [[ -f "$LANGGRAPH_DOCKERFILE" ]]; then
        if [[ "$FORCE" == true ]] || ! docker image inspect nettrades-langgraph:latest &>/dev/null; then
            log_info "Building LangGraph image (force=$FORCE)..."
            docker build -f "$LANGGRAPH_DOCKERFILE" -t nettrades-langgraph:latest "$PROJECT_ROOT/src/core"
            log_success "LangGraph image built"
        else
            log_success "LangGraph image already exists (use --force to rebuild)"
        fi
    else
        log_warning "Dockerfile for LangGraph not found – skipping build"
    fi

    # -----------------------------------------------------------------------------
    # Query the Odoo user UID from the built image
    # -----------------------------------------------------------------------------
    ODOO_UID=""
    if docker image inspect nettrades-odoo:latest &>/dev/null; then
        ODOO_UID=$(docker run --rm nettrades-odoo:latest id -u odoo 2>/dev/null || echo "")
    fi
    if [[ -z "$ODOO_UID" ]]; then
        log_warning "Could not determine Odoo UID from image. Falling back to UID 100."
        ODOO_UID="100"
    fi
    log_info "Odoo user UID: $ODOO_UID"

    mkdir -p "$ODOO_DATA_DIR"
    chown -R "$ODOO_UID:$ODOO_UID" "$ODOO_DATA_DIR" 2>/dev/null || true
    log_success "Odoo data directory permissions set to UID $ODOO_UID"

    # -----------------------------------------------------------------------------
    # Generate init-db.sql with all NETTRADES tables
    # -----------------------------------------------------------------------------
    log_step "Generating init-db.sql with all NETTRADES tables..."
    INIT_SQL="$DEPLOY_DIR/init-db.sql"
    if [[ ! -f "$INIT_SQL" ]] || [[ "$FORCE" == true ]]; then
        cat > "$INIT_SQL" << 'EOF'
-- =============================================================================
-- NETTRADES Database Initialisation (odoo database)
-- =============================================================================
-- Extensions only, per ADR-001. Business entities are created by the
-- Odoo ORM; operational state lives in nettrades_infra; LangGraph
-- checkpoints live in `checkpoints`.
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
EOF
        log_success "init-db.sql generated (extensions only, per ADR-001)"
    else
        log_success "init-db.sql already exists"
    fi


    # -----------------------------------------------------------------------------
    # Run security hardening (if Phase 0 not completed)
    # -----------------------------------------------------------------------------
    if [[ -f "$PROJECT_ROOT/.phase-0-complete" ]]; then
        log_success "Phase 0 already completed – skipping hardening."
    else
        log_step "Phase 0 not completed – running security hardening..."
        if [[ -f "$SCRIPT_DIR/phase-system.sh" ]]; then
            bash "$SCRIPT_DIR/phase-system.sh"
        else
            log_warning "phase-system.sh not found – skipping hardening"
        fi
    fi

    # -----------------------------------------------------------------------------
    # Start PostgreSQL and initialise the database (if empty)
    # -----------------------------------------------------------------------------
    cd "$DEPLOY_DIR"
    log_step "Starting PostgreSQL container and initialising database..."

    if command -v dos2unix &>/dev/null && grep -q $'\r' "$ENV_FILE" 2>/dev/null; then
        dos2unix "$ENV_FILE" 2>/dev/null || true
        log_info "Converted .env to LF line endings"
    elif command -v dos2unix &>/dev/null; then
        log_info ".env already has LF line endings – skipping dos2unix"
    fi

    set -a
    source "$ENV_FILE"
    set +a

    configure_domain

    check_postgres_password() {
        local pg_container
        pg_container=$(docker compose ps -q postgres 2>/dev/null)
        if [[ -n "$pg_container" ]] && docker inspect -f '{{.State.Running}}' "$pg_container" 2>/dev/null | grep -q true; then
            local actual_pass
            actual_pass=$(docker exec "$pg_container" env | grep POSTGRES_PASSWORD | cut -d= -f2)
            # TRIM whitespace and newlines
            actual_pass=$(echo -n "$actual_pass" | tr -d '\n\r')
            # Force alphanumeric only to prevent corruption
            actual_pass=$(echo -n "$actual_pass" | tr -cd 'a-zA-Z0-9')
            if [[ -n "$actual_pass" && "$actual_pass" != "$POSTGRES_PASSWORD" ]]; then
                log_warning "PostgreSQL password mismatch."
                log_warning "  .env password: $POSTGRES_PASSWORD"
                log_warning "  Container password: $actual_pass"
                if [[ "$FORCE" == true ]] || [[ "$AUTO" == true ]]; then
                    log_info "Updating .env to match the container's password (trimmed)."
                    safe_sed_replace "$ENV_FILE" "POSTGRES_PASSWORD" "$actual_pass"
                    export POSTGRES_PASSWORD="$actual_pass"
                else
                    log_error "Please either set the correct password in .env or use --force to update .env."
                    exit 1
                fi
            fi
        fi
    }
    check_postgres_password

    POSTGRES_PRESERVED=false
    PG_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null)
    if [[ -n "$PG_CONTAINER" ]]; then
        if docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true; then
            CURRENT_PG_PASS=$(docker exec "$PG_CONTAINER" env | grep POSTGRES_PASSWORD | cut -d= -f2)
            # TRIM whitespace and newlines
            CURRENT_PG_PASS=$(echo -n "$CURRENT_PG_PASS" | tr -d '\n\r')
            # Force alphanumeric only to prevent corruption
            CURRENT_PG_PASS=$(echo -n "$CURRENT_PG_PASS" | tr -cd 'a-zA-Z0-9')
            if [[ -n "$CURRENT_PG_PASS" ]]; then
                log_info "PostgreSQL container is running. Using its password: $CURRENT_PG_PASS"
                safe_sed_replace "$ENV_FILE" "POSTGRES_PASSWORD" "$CURRENT_PG_PASS"
                export POSTGRES_PASSWORD="$CURRENT_PG_PASS"
                POSTGRES_PRESERVED=true
            fi
        else
            log_info "PostgreSQL container exists but is not running. Skipping password preservation."
        fi
    else
        log_info "PostgreSQL container does not exist. Will generate password if weak."
    fi

    generate_secret() {
        generate_safe_password
    }

    SECRET_VARS=(
        POSTGRES_PASSWORD
        DB_MANAGER_UI_PASSWORD
        ODOO_ADMIN_PASSWORD
        FORGEJO_DB_PASSWORD
        FORGEJO_SECRET_KEY
        GRAFANA_PASSWORD
        PROMETHEUS_PASSWORD
        LANGGRAPH_API_KEY
        ODOO_API_KEY
        PROXY_API_KEY
        NETTRADES_SERVICE_PASSWORD
        SESSION_SECRET
    )

    # If .env exists as a directory (Docker Compose creates this when a
    # bind-mount source file is missing), remove it so we can create the
    # real file. This is the fix for the "cp: cannot create regular file
    # '.../.env/.env.example': Permission denied" error.

    if [[ -d "$ENV_FILE" ]]; then
        log_error ".env is a directory. Run phase-env.sh first or remove it manually:"
        log_info "  rm -rf $ENV_FILE"
        exit 1
    fi

    if [[ ! -f "$ENV_FILE" ]] || [[ "$REGENERATE_SECRETS" == true ]]; then
        if [[ "$REGENERATE_SECRETS" == true ]]; then
            log_warning "Regenerating secrets in .env (this will break running services!)."
            BACKUP_ENV="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
            cp "$ENV_FILE" "$BACKUP_ENV"
            log_info "Backed up .env to $BACKUP_ENV"
        fi

        for VAR in "${SECRET_VARS[@]}"; do
            if [[ "$VAR" == "POSTGRES_PASSWORD" ]] && [[ "$POSTGRES_PRESERVED" == true ]]; then
                log_info "POSTGRES_PASSWORD preserved from container – skipping regeneration."
                continue
            fi

            if grep -q "^${VAR}=" "$ENV_FILE"; then
                CURRENT_VALUE=$(grep "^${VAR}=" "$ENV_FILE" | cut -d'=' -f2-)
                if [[ -z "$CURRENT_VALUE" || "$CURRENT_VALUE" == "changeit" ]]; then
                    NEW_VALUE=$(generate_secret)
                    safe_sed_replace "$ENV_FILE" "$VAR" "$NEW_VALUE"
                    log_info "Regenerated ${VAR} (was weak)"
                    export "${VAR}=${NEW_VALUE}"
                else
                    export "${VAR}=${CURRENT_VALUE}"
                fi
            else
                NEW_VALUE=$(generate_secret)
                safe_sed_replace "$ENV_FILE" "$VAR" "$NEW_VALUE"
                log_info "Generated ${VAR}"
                export "${VAR}=${NEW_VALUE}"
            fi
        done

        ODOO_API_KEY=$(grep "^ODOO_API_KEY=" "$ENV_FILE" | cut -d'=' -f2-)
        PROXY_API_KEY=$(grep "^PROXY_API_KEY=" "$ENV_FILE" | cut -d'=' -f2-)
        if [[ "$ODOO_API_KEY" != "$PROXY_API_KEY" ]]; then
            NEW_KEY=$(generate_secret)
            safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$NEW_KEY"
            safe_sed_replace "$ENV_FILE" "PROXY_API_KEY" "$NEW_KEY"
            export ODOO_API_KEY="${NEW_KEY}"
            export PROXY_API_KEY="${NEW_KEY}"
            log_info "Synchronised ODOO_API_KEY and PROXY_API_KEY"
        fi
    fi

    # =============================================================================
    # Set Self-Improving Environment Variables
    # =============================================================================
    log_step "Setting self-improving environment variables..."

    if ! grep -q "^THRESHOLD_EPISODES=" "$ENV_FILE"; then
        safe_sed_replace "$ENV_FILE" "THRESHOLD_EPISODES" "50"
        log_info "Set THRESHOLD_EPISODES=50"
    fi

    if ! grep -q "^THRESHOLD_QUALITY=" "$ENV_FILE"; then
        safe_sed_replace "$ENV_FILE" "THRESHOLD_QUALITY" "7.0"
        log_info "Set THRESHOLD_QUALITY=7.0"
    fi

    if ! grep -q "^FINE_TUNE_MODEL=" "$ENV_FILE"; then
        safe_sed_replace "$ENV_FILE" "FINE_TUNE_MODEL" "deepseek-7b"
        log_info "Set FINE_TUNE_MODEL=deepseek-7b"
    fi

    if ! grep -q "^FINE_TUNE_METHOD=" "$ENV_FILE"; then
        safe_sed_replace "$ENV_FILE" "FINE_TUNE_METHOD" "unsloth"
        log_info "Set FINE_TUNE_METHOD=unsloth"
    fi

    # -----------------------------------------------------------------------------
    # Generate Grafana datasource provisioning
    # -----------------------------------------------------------------------------
    log_step "Generating Grafana datasource provisioning..."
    GRAFANA_DATASOURCES_DIR="$DEPLOY_DIR/grafana-datasources"
    GRAFANA_DATASOURCES_FILE="$GRAFANA_DATASOURCES_DIR/datasources.yaml"
    PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"
    mkdir -p "$GRAFANA_DATASOURCES_DIR"

    if [[ -f "$GRAFANA_DATASOURCES_FILE" ]]; then
        BACKUP_DS="${GRAFANA_DATASOURCES_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
        cp "$GRAFANA_DATASOURCES_FILE" "$BACKUP_DS"
        log_info "Backed up existing datasources.yaml to $BACKUP_DS"
    fi

    cat > "$GRAFANA_DATASOURCES_FILE" << EOF
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    basicAuth: true
    basicAuthUser: admin
    secureJsonData:
      basicAuthPassword: ${PROMETHEUS_PASSWORD}
    isDefault: true
    editable: false
EOF
    log_success "Grafana datasource provisioning created"

    ensure_bcrypt || log_warning "bcrypt installation failed – Prometheus will use plain-text passwords"

    # =============================================================================
    # Generate Prometheus web.yml with basic auth
    # =============================================================================
    log_step "Generating Prometheus web.yml with basic auth..."
    WEB_CONFIG_DIR="$DEPLOY_DIR/prometheus"
    WEB_CONFIG_FILE="$WEB_CONFIG_DIR/web.yml"
    PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"

    if [[ -d "$WEB_CONFIG_FILE" ]]; then
        rm -rf "$WEB_CONFIG_FILE"
    fi

    mkdir -p "$WEB_CONFIG_DIR"

    HASH=""
    if python3 -c "import bcrypt" 2>/dev/null; then
        HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw('$PROMETHEUS_PASSWORD'.encode(), bcrypt.gensalt()).decode())")
    else
        log_warning "bcrypt not available – using plain-text password (INSECURE)."
        HASH="$PROMETHEUS_PASSWORD"
    fi

    cat > "$WEB_CONFIG_FILE" << EOF
basic_auth_users:
    admin: '$HASH'
EOF

    if [[ "$HASH" == "$PROMETHEUS_PASSWORD" ]]; then
        log_warning "bcrypt not available in Python – using plain-text password (INSECURE)."
        cat > "$WEB_CONFIG_FILE" << EOF
# WARNING: No bcrypt – basic auth uses plain text!
basic_auth_users:
    admin: '$PROMETHEUS_PASSWORD'
EOF
    else
        log_success "Prometheus web.yml generated with bcrypt hash"
    fi

    REMOVE_VOLUME=false
    if [[ "$RESET_DATA" == true ]]; then
        if [[ "$AUTO" == true ]]; then
            REMOVE_VOLUME=true
            log_info "Auto mode: will remove dynamo_data volume without prompt."
        else
            echo ""
            echo -e "${YELLOW}WARNING: You are about to DELETE ALL Dynamo data (models, configurations).${NC}"
            echo "This action is irreversible."
            read -rp "Are you sure you want to remove the dynamo_data volume? (y/N): " confirm
            if [[ "$confirm" =~ ^[Yy]$ ]]; then
                REMOVE_VOLUME=true
            else
                log_info "Skipping volume removal."
            fi
        fi
    fi

    if [[ "$FORCE" == true ]]; then
        log_info "Force mode – recreating containers..."

        REMOVE_ORPHANS=""
        if [[ "$AUTO" == true ]]; then
            REMOVE_ORPHANS="--remove-orphans"
            log_info "Auto mode: removing orphans without prompt."
        else
            echo ""
            echo -e "${YELLOW}Do you want to remove orphan containers (containers that were part of this NETTRADES stack but are no longer defined in the compose file)?${NC}"
            echo "This will NOT affect other containers running on this server from different projects."
            read -rp "Remove orphans? (y/N): " confirm_orphans
            if [[ "$confirm_orphans" =~ ^[Yy]$ ]]; then
                REMOVE_ORPHANS="--remove-orphans"
            else
                REMOVE_ORPHANS=""
            fi
        fi

        if [[ "$RESET_DATA" == true ]]; then
            docker compose down $REMOVE_ORPHANS -v
            log_info "Removed all containers and volumes (--reset-data)"
        else
            docker compose down $REMOVE_ORPHANS
            log_info "Removed containers (data preserved)"
        fi

        if [[ "$REMOVE_VOLUME" == true ]] && [[ "$RESET_DATA" != true ]]; then
            if docker volume ls -q | grep -q "dynamo_data"; then
                docker volume rm dynamo_data 2>/dev/null || true
                log_info "Removed dynamo_data volume"
            else
                log_info "dynamo_data volume not found"
            fi
        fi
    fi

    # --- Start PostgreSQL and initialise ---
    log_info "Starting PostgreSQL..."
    docker compose up -d postgres

    wait_for_postgres || {
        log_error "PostgreSQL failed to become ready. Cannot initialise database."
        exit 1
    }

    DB_INITIALISED=false
    if docker compose exec -T postgres psql -U odoo -d odoo -c "\dt" 2>/dev/null | grep -q "ir_module_module"; then
        DB_INITIALISED=true
    fi

    TABLE_COUNT=$(docker compose exec -T postgres psql -U odoo -d odoo -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')

    if [ "$DB_INITIALISED" = false ] || [ "$TABLE_COUNT" -lt 10 ] || [[ "$FORCE" == true ]]; then
        log_info "Database not properly initialised or --force used. Running full initialisation..."

        if [[ "$FORCE" == true ]]; then
            log_info "Force mode: dropping and recreating database..."
            docker compose exec -T postgres dropdb -U odoo odoo 2>/dev/null || true
            docker compose exec -T postgres createdb -U odoo odoo
        fi

        if [[ -f "$INIT_SQL" ]]; then
            docker compose exec -T postgres psql -U odoo odoo < "$INIT_SQL" || {
                log_warning "Database initialisation may have already been done."
            }
        else
            log_error "init-db.sql not found!"
            exit 1
        fi

        log_info "Installing base modules..."
        docker compose run --rm \
            -e PGHOST=postgres \
            -e PGPORT=5432 \
            -e PGUSER=odoo \
            -e PGPASSWORD="$POSTGRES_PASSWORD" \
            -e PGDATABASE=odoo \
            odoo odoo -d odoo \
            --db_host=postgres \
            --db_port=5432 \
            --db_user=odoo \
            --db_password="$POSTGRES_PASSWORD" \
            -i base --stop-after-init --log-level=info
        log_success "Base modules installed"
    else
        log_success "Database already initialised – skipping init."
    fi

    enable_pgcrypto || true

    # Phase 1a — apply the operational-state schema (ADR-002, ADR-003).
    # Creates `nettrades_infra` and `checkpoints` if missing, applies
    # init-infra.sql to the former. Idempotent — safe on every deploy.
    log_step "Applying Phase 1a database schema..."
    if [[ -f "$SCRIPT_DIR/migrate-phase1-databases.sh" ]]; then
        bash "$SCRIPT_DIR/migrate-phase1-databases.sh" || \
            log_warning "Phase 1a migration failed — the stack will run, " \
                        "but operational state stays in the Odoo database."
    else
        log_warning "migrate-phase1-databases.sh not found — skipping Phase 1a."
    fi

    # -----------------------------------------------------------------------------
    # Build and start the full Docker Compose stack (with retry)
    # -----------------------------------------------------------------------------
    log_step "Building and starting Docker Compose stack (with retries)..."

    RUNTIME_ODOO="${RUNTIME_ODOO:-}" \
    RUNTIME_LANGGRAPH="${RUNTIME_LANGGRAPH:-}" \
    RUNTIME_SELF_IMPROVING="${RUNTIME_SELF_IMPROVING:-}" \
    RUNTIME_UI="${RUNTIME_UI:-}" \
    RUNTIME_DYNAMO="${RUNTIME_DYNAMO:-}" \
    RUNTIME_POSTGRES="${RUNTIME_POSTGRES:-}" \
    RUNTIME_VALKEY="${RUNTIME_VALKEY:-}" \
    docker compose up -d --build

    if [[ "${WITH_GROVE:-false}" == "true" ]]; then
        log_info "Starting Grove observability stack..."
        if [[ -f "$DEPLOY_DIR/docker-compose.grove.yaml" ]]; then
            docker compose -f docker-compose.yaml -f docker-compose.grove.yaml up -d grove loki tempo
            log_success "Grove stack started"
        else
            log_warning "docker-compose.grove.yaml not found – skipping Grove"
        fi
    fi

    if [[ "${WITH_KAI:-false}" == "true" ]]; then
        log_info "Starting KAI Scheduler..."
        if [[ -f "$DEPLOY_DIR/docker-compose.kai.yaml" ]]; then
            docker compose -f docker-compose.yaml -f docker-compose.kai.yaml up -d kai-scheduler
            log_success "KAI Scheduler started"
        else
            log_warning "docker-compose.kai.yaml not found – skipping KAI Scheduler"
        fi
    fi

    # The main "docker compose up -d --build" command it will not start self-improving because it now uses profile
    # Self-improving can be started with "docker compose --profile finetune up -d self-improving"

    if [[ "${WITH_FINETUNE:-false}" == "true" ]]; then
        log_info "Starting fine-tuning service (--with-finetune enabled)..."
        docker compose --profile finetune up -d self-improving
        log_success "Fine-tuning service started"
    else
        log_info "Fine-tuning disabled. Use --with-finetune to enable."
    fi

    if [[ "${WITH_CUVS:-false}" == "true" ]]; then
        log_info "RAPIDS cuVS is installed in the virtual environment and will be available for vector search."
    fi

    log_success "Docker Compose stack started"

    # -----------------------------------------------------------------------------
    # 8. Validate deployment
    # -----------------------------------------------------------------------------
    validate_deployment() {
        local max_retries=120
        local attempt=1
        local odoo_ready=false
        local langgraph_ready=false

        log_step "Validating deployment health..."

        log_info "Waiting for Odoo to become ready (this may take 2-3 minutes on first install)..."
        for i in {1..90}; do
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:8069 2>/dev/null)
            if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "302" || "$HTTP_CODE" == "303" ]]; then
                odoo_ready=true
                log_success "Odoo is ready (HTTP $HTTP_CODE)"
                break
            fi
            if [ $((i % 10)) -eq 0 ]; then
                log_info "Still waiting for Odoo... ($i/90 attempts) - HTTP $HTTP_CODE"
            fi
            sleep 2
        done

        if [ "$odoo_ready" != true ]; then
            log_error "Odoo failed to become ready within 3 minutes."
            log_info "Check Odoo logs with: docker logs odoo --tail 50"
            return 1
        fi

        log_info "Waiting for LangGraph to become ready..."
        while [[ $attempt -le $max_retries ]]; do
            if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q "200"; then
                langgraph_ready=true
                log_success "LangGraph is healthy"
                break
            else
                if [ $((attempt % 10)) -eq 0 ]; then
                    log_info "Still waiting for LangGraph... ($attempt/$max_retries attempts)"
                fi
            fi
            log_info "Waiting for services to be ready... ($attempt/$max_retries)"
            sleep 2
            attempt=$((attempt + 1))
        done

        if [ "$langgraph_ready" != true ]; then
            log_error "LangGraph failed to become ready within $((max_retries * 2)) seconds."
            log_info "Check LangGraph logs with: docker logs langgraph-server --tail 50"
            return 1
        fi

        log_info "Waiting for NETTRADES UI to become ready..."
        local ui_ready=false
        for i in {1..60}; do
            if curl -s -o /dev/null -w "%{http_code}" http://localhost:3002/ 2>/dev/null | grep -q "200"; then
                ui_ready=true
                log_success "NETTRADES UI is ready"
                break
            fi
            sleep 2
        done
        if [ "$ui_ready" != true ]; then
            log_warning "NETTRADES UI did not become ready within 2 minutes. Check logs."
        else
            log_success "NETTRADES UI is healthy"
        fi

        if [[ "${WITH_GROVE:-false}" == "true" ]]; then
            log_info "Checking Grove health..."
            for i in {1..30}; do
                if curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/health 2>/dev/null | grep -q "200"; then
                    log_success "Grove is healthy"
                    break
                fi
                sleep 2
            done
        fi

        if [[ "${WITH_KAI:-false}" == "true" ]]; then
            log_info "Checking KAI Scheduler health..."
            for i in {1..30}; do
                if curl -s -o /dev/null -w "%{http_code}" http://localhost:9091/health 2>/dev/null | grep -q "200"; then
                    log_success "KAI Scheduler is healthy"
                    break
                fi
                sleep 2
            done
        fi

        log_success "All services are healthy"
        return 0
    }

    if validate_deployment; then
        log_success "Deployment validation passed"
    else
        log_error "Deployment validation failed. Check logs."
        exit 1
    fi

    # -----------------------------------------------------------------------------
    # Wait for Dynamo to be ready
    # -----------------------------------------------------------------------------
    log_step "Waiting for Dynamo to be ready..."
    for i in {1..60}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models | grep -q "200"; then
            log_success "Dynamo is ready"
            break
        fi
        sleep 2
    done

    # =============================================================================
    # DYNAMO SETUP
    # =============================================================================
    log_step "Configuring NVIDIA Dynamo..."

    if [[ -z "${DYNAMO_API_KEY:-}" ]]; then
        DYNAMO_API_KEY=$(generate_safe_password)
        safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"
        export DYNAMO_API_KEY
        log_info "Generated DYNAMO_API_KEY and updated .env"
    fi

    log_step "Waiting for Dynamo to be ready..."
    DYNAMO_HEALTHY=false
    for i in {1..30}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models \
            -H "Authorization: Bearer $DYNAMO_API_KEY" | grep -q "200"; then
            DYNAMO_HEALTHY=true
            log_success "Dynamo is ready"
            break
        fi
        sleep 2
    done

    if [[ "$DYNAMO_HEALTHY" == false ]]; then
        log_warning "Dynamo is not responding. Will use llama.cpp fallback."
    else
        MODEL_LIST=$(curl -s -H "Authorization: Bearer $DYNAMO_API_KEY" http://localhost:8001/v1/models)
        if echo "$MODEL_LIST" | grep -q '"data":\[\]'; then
            log_warning "Dynamo has no models registered."
            log_info "Restarting Dynamo to pick up model files..."
            docker compose restart dynamo
            sleep 10
            MODEL_LIST=$(curl -s -H "Authorization: Bearer $DYNAMO_API_KEY" http://localhost:8001/v1/models)
            if echo "$MODEL_LIST" | grep -q '"data":\[\]'; then
                log_warning "Dynamo still has no models. Falling back to llama.cpp."
                DYNAMO_HEALTHY=false
            else
                log_success "Dynamo now has models loaded after restart."
            fi
        else
            log_success "Dynamo has models loaded."
        fi
    fi

    # -----------------------------------------------------------------------------
    # Determine inference backend
    # -----------------------------------------------------------------------------
    log_step "Determining inference backend..."

    if [[ "$DYNAMO_HEALTHY" == true ]]; then
        log_success "Dynamo is healthy. Using Dynamo as the primary inference backend."
        LLM_BASE_URL="http://dynamo:8000/v1"
        OPENAI_API_KEY="$DYNAMO_API_KEY"
    else
        log_warning "Dynamo not available or not ready. Falling back to llama.cpp (CPU)."
        LLM_BASE_URL="http://llama-cpp:8080/v1"
        OPENAI_API_KEY="dummy"
    fi

    safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
    safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
    safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"
    log_success ".env updated with inference backend settings"

    log_step "Restarting LangGraph to apply new inference settings..."

    if ! timeout 120s docker compose restart langgraph-server; then
        log_warning "Timeout or failure restarting langgraph-server. Attempting to recreate..."
        docker compose stop langgraph-server
        docker compose rm -f langgraph-server
        docker compose up -d langgraph-server
        log_info "LangGraph container recreated."
    else
        log_success "LangGraph restarted successfully."
    fi

    sleep 7

    # After restarting LangGraph, re-check Dynamo and update .env if needed
    log_step "Re-verifying inference backend after LangGraph restart..."
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models \
           -H "Authorization: Bearer $DYNAMO_API_KEY" | grep -q "200"; then
        MODEL_LIST=$(curl -s -H "Authorization: Bearer $DYNAMO_API_KEY" http://localhost:8001/v1/models)
        if echo "$MODEL_LIST" | grep -q '"data":\[\]'; then
            log_warning "Dynamo has no models after restart – forcing llama.cpp fallback"
            DYNAMO_HEALTHY=false
            LLM_BASE_URL="http://llama-cpp:8080/v1"
            OPENAI_API_KEY="dummy"
            safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
            safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
            docker compose restart langgraph-server
        fi
    fi

    # -----------------------------------------------------------------------------
    # Update .env with inference backend settings — PRESERVING operator overrides.
    # -----------------------------------------------------------------------------
    # 2026-10-22: The previous version unconditionally overwrote LLM_BASE_URL
    # with either 'http://dynamo:8000/v1' or 'http://llama-cpp:8080/v1'.
    # That is fine for a fresh install, but for an operator who has set
    # 'http://192.168.1.212:8001/v1' to point at their real vLLM, the
    # overwrite silently kills the setup on the next re-run.
    #
    # We now distinguish between installer-owned values (safe to overwrite)
    # and operator-owned values (leave alone). The installer-owned values
    # are exactly the two strings this script itself would produce.
    # -----------------------------------------------------------------------------
    log_step "Updating .env with inference backend settings..."
    _CURRENT_LLM_BASE_URL="$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" 2>/dev/null \
        | tail -1 | cut -d= -f2- | tr -d '\r' | tr -d "'" || true)"

    case "$_CURRENT_LLM_BASE_URL" in
        ""|http://dynamo:8000/v1|http://llama-cpp:8080/v1|changeit)
            # Installer-owned (or missing). Safe to overwrite.
            if [[ "$DYNAMO_HEALTHY" == true ]]; then
                LLM_BASE_URL="http://dynamo:8000/v1"
                OPENAI_API_KEY="$DYNAMO_API_KEY"
            else
                LLM_BASE_URL="http://llama-cpp:8080/v1"
                OPENAI_API_KEY="dummy"
            fi
            safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
            safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
            log_success ".env updated with installer-chosen inference backend: $LLM_BASE_URL"
            ;;
        *)
            # Operator-owned. Do NOT overwrite.
            LLM_BASE_URL="$_CURRENT_LLM_BASE_URL"
            log_info "Preserving operator-set LLM_BASE_URL=$LLM_BASE_URL"
            log_info "To reset to the installer default, remove LLM_BASE_URL from $ENV_FILE"
            ;;
    esac

    log_step "Restarting LangGraph..."
    if ! timeout 120s docker compose restart langgraph-server; then
        log_warning "Timeout or failure restarting langgraph-server. Attempting to recreate..."
        docker compose stop langgraph-server
        docker compose rm -f langgraph-server
        docker compose up -d langgraph-server
        log_info "LangGraph container recreated."
    else
        log_success "LangGraph restarted successfully."
    fi

    # -------------------------------------------------------------------------
    # Configure the Odoo admin user (idempotent)
    # -------------------------------------------------------------------------
    log_step "Configuring Odoo admin user for external services..."
    ODOO_ADMIN_SCRIPT="$SCRIPT_DIR/configure-odoo-admin.sh"
    if [[ -f "$ODOO_ADMIN_SCRIPT" ]]; then
        # Capture BOTH stdout and stderr so we can parse the structured
        # output (ADMIN_UID=, NETTRADES_SERVICE_UID=, ...) while still
        # letting the script's [configure-odoo-admin] log lines pass
        # through.
        # Stream output live AND capture it for parsing.
        # The temporary file lets us grep after the command finishes without
        # hiding progress from the operator (the previous CONFIGURE_OUTPUT=$(...)
        # form was silent for 60-90 seconds while odoo shell booted, and looked
        # like a hang).
        CONFIGURE_LOG=$(mktemp)
        docker compose exec -T \
            -e ODOO_ADMIN_PASSWORD="$ODOO_ADMIN_PASSWORD" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e NETTRADES_SERVICE_PASSWORD="$NETTRADES_SERVICE_PASSWORD" \
            -e DYNAMO_API_KEY="${DYNAMO_API_KEY:-dummy}" \
            -e LLM_BASE_URL="${LLM_BASE_URL:-http://llama-cpp:8080/v1}" \
            odoo bash -c "$(cat "$ODOO_ADMIN_SCRIPT")" 2>&1 | tee "$CONFIGURE_LOG"

        ADMIN_UID=$(grep '^ADMIN_UID=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_UID=$(grep '^NETTRADES_SERVICE_UID=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_PASSWORD=$(grep '^NETTRADES_SERVICE_PASSWORD=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_API_KEY=$(grep '^NETTRADES_SERVICE_API_KEY=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        rm -f "$CONFIGURE_LOG"

        if [[ -n "$ADMIN_UID" ]]; then
            log_success "Admin user configured (uid=$ADMIN_UID)"
            safe_sed_replace "$ENV_FILE" "ODOO_USER" "$ADMIN_UID"
            export ODOO_USER="$ADMIN_UID"
        else
            log_warning "Could not determine admin uid; defaulting to 2."
            safe_sed_replace "$ENV_FILE" "ODOO_USER" "2"
        fi

        # Keep ODOO_PASSWORD in sync with ODOO_ADMIN_PASSWORD.
        #
        # configure-odoo-admin.sh has just set the admin user's password
        # to $ODOO_ADMIN_PASSWORD (a random 24-char string). But every
        # consumer inside the LangGraph container — app.py,
        # rpc_scheduler.py, odoo_proxy/main.py, routes/wireguard.py —
        # reads ODOO_PASSWORD with a fallback to "admin". The fallback
        # was valid only on very old deployments. On a fresh install,
        # admin's real password is $ODOO_ADMIN_PASSWORD, so the fallback
        # always fails authentication.
        #
        # Without this write:
        #   - _load_node_inventory_into_monitor() silently returns early
        #   - dynamo_worker is never registered with the health monitor
        #   - Tier 2 failover never fires
        #
        # Writing ODOO_PASSWORD here makes every consumer authenticate
        # as the same identity configure-odoo-admin.sh just set up.
        if [[ -n "${ODOO_ADMIN_PASSWORD:-}" ]]; then
            safe_sed_replace "$ENV_FILE" "ODOO_PASSWORD" "$ODOO_ADMIN_PASSWORD"
            export ODOO_PASSWORD="$ODOO_ADMIN_PASSWORD"
        fi

        # Persist the service user's credentials to .env. The password
        # came from the script itself (generated because .env had none);
        # the UID and API key come from the same run. All three are
        # written here so that subsequent runs of configure-odoo-admin.sh
        # reuse the same password instead of generating a new one.
        if [[ -n "$SERVICE_UID" ]]; then
            log_success "Service user configured (uid=$SERVICE_UID)"
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_UID" "$SERVICE_UID"
            export NETTRADES_SERVICE_UID="$SERVICE_UID"
        fi
        if [[ -n "$SERVICE_PASSWORD" ]]; then
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_PASSWORD" "$SERVICE_PASSWORD"
            export NETTRADES_SERVICE_PASSWORD="$SERVICE_PASSWORD"
        fi
        if [[ -n "$SERVICE_API_KEY" ]]; then
            log_success "Service user API key generated and recorded in .env"
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_API_KEY" "$SERVICE_API_KEY"
            export NETTRADES_SERVICE_API_KEY="$SERVICE_API_KEY"
        fi

        # Recreate langgraph-server so it picks up the credentials we
        # just wrote. `docker compose restart` is not sufficient: compose
        # only re-reads the .env file when the container is created.
        # `--force-recreate` guarantees a fresh container with the
        # updated environment.
        if [[ -n "$SERVICE_UID" ]] && [[ -n "$SERVICE_PASSWORD" ]]; then
            log_step "Recreating langgraph-server to apply service user credentials..."
            docker compose up -d --force-recreate langgraph-server \
                || log_warning "Failed to recreate langgraph-server; it will pick up the credentials on the next restart."
        fi
    else
        log_warning "configure-odoo-admin.sh not found – skipping."
    fi

    # -----------------------------------------------------------------------------
    # Install NETTRADES Odoo modules
    # -----------------------------------------------------------------------------
    log_step "Installing NETTRADES Odoo modules..."

    log_info "Waiting for Odoo to be ready..."
    for i in {1..30}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
            log_success "Odoo is ready"
            break
        fi
        sleep 2
    done

    log_info "Testing database connection..."
    if ! docker compose exec -T odoo odoo -d odoo --db_host=postgres --db_port=5432 --db_user=odoo --db_password="$POSTGRES_PASSWORD" --stop-after-init --log-level=error 2>/dev/null; then
        log_error "Odoo cannot connect to PostgreSQL. Please check the password."
        log_error "Current .env password: $POSTGRES_PASSWORD"
        log_error "Try: docker compose exec odoo odoo -d odoo --db_host=postgres --db_user=odoo --db_password=... --stop-after-init"
        exit 1
    fi

    if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
        log_step "Installing NETTRADES Odoo modules..."
        ARGS=""
        [[ "$FORCE" == true ]] && ARGS="$ARGS --force"
        [[ "$UPGRADE" == true ]] && ARGS="$ARGS --upgrade"
        [[ "$AUTO" == true ]] && ARGS="$ARGS --auto"
        bash "$SCRIPT_DIR/install-modules.sh" $ARGS
    else
        log_warning "install-modules.sh not found – skipping module installation"
    fi


    # -------------------------------------------------------------------------
    # Re-run configure-odoo-admin.sh AFTER install-modules.sh.
    #
    # The first run (above, before install-modules.sh) cannot create the
    # llm.provider record, because the `service` Selection on llm.provider
    # is populated by the Apexive llm_* service modules, which are not yet
    # installed at that point. This second run happens after
    # install-modules.sh has installed llm_openai, so `service='openai'`
    # is a valid value and the provider create succeeds.
    #
    # This is the same pattern phase-modules.sh uses. It makes the deploy
    # profile self-contained: `./scripts/nettrades-setup.sh deploy --force`
    # now produces a fully working LLM provider, without requiring a later
    # `modules` phase.
    # -------------------------------------------------------------------------
    if [[ -f "$ODOO_ADMIN_SCRIPT" ]]; then
        log_step "Re-configuring Odoo admin after module install..."


        # Stream output live AND capture it for parsing.
        # The temporary file lets us grep after the command finishes without
        # hiding progress from the operator (the previous CONFIGURE_OUTPUT=$(...)
        # form was silent for 60-90 seconds while odoo shell booted, and looked
        # like a hang).
        CONFIGURE_LOG=$(mktemp)
        docker compose exec -T \
            -e ODOO_ADMIN_PASSWORD="$ODOO_ADMIN_PASSWORD" \
            -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
            -e NETTRADES_SERVICE_PASSWORD="$NETTRADES_SERVICE_PASSWORD" \
            -e DYNAMO_API_KEY="${DYNAMO_API_KEY:-dummy}" \
            -e LLM_BASE_URL="${LLM_BASE_URL:-http://llama-cpp:8080/v1}" \
            odoo bash -c "$(cat "$ODOO_ADMIN_SCRIPT")" 2>&1 | tee "$CONFIGURE_LOG"

        # Parse the same structured output from the second pass.
        # The values are the same ones written by the first pass, but
        # reading them again here keeps the block symmetric and makes
        # the second pass idempotent if the first was interrupted.
        ADMIN_UID_2=$(grep '^ADMIN_UID=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_UID_2=$(grep '^NETTRADES_SERVICE_UID=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_PASSWORD_2=$(grep '^NETTRADES_SERVICE_PASSWORD=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        SERVICE_API_KEY_2=$(grep '^NETTRADES_SERVICE_API_KEY=' "$CONFIGURE_LOG" | tail -1 | cut -d= -f2- | tr -d '\r')
        rm -f "$CONFIGURE_LOG"

        if [[ -n "$SERVICE_UID_2" ]]; then
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_UID" "$SERVICE_UID_2"
        fi
        if [[ -n "$SERVICE_PASSWORD_2" ]]; then
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_PASSWORD" "$SERVICE_PASSWORD_2"
        fi
        if [[ -n "$SERVICE_API_KEY_2" ]]; then
            safe_sed_replace "$ENV_FILE" "NETTRADES_SERVICE_API_KEY" "$SERVICE_API_KEY_2"
        fi

        # Recreate langgraph-server so it picks up any credentials the
        # second pass rewrote.
        docker compose up -d --force-recreate langgraph-server \
            || log_warning "Failed to recreate langgraph-server after second configure pass"
    fi

    # -----------------------------------------------------------------------------
    # Create emergency Odoo user and multiple fallback options
    # -----------------------------------------------------------------------------
    log_step "Creating emergency access options..."

    if [ "$EUID" -eq 0 ]; then
        EMERGENCY_DIR="/root/emergency_access"
    else
        EMERGENCY_DIR="$HOME/.nettrades/emergency"
    fi

    mkdir -p "$EMERGENCY_DIR"
    EMERGENCY_PASSWORD=$(openssl rand -base64 24 | tr -d '+/=' | cut -c1-24)
    VALID_UNTIL=$(date -d "+${EMERGENCY_ACCESS_DURATION} hours" '+%Y-%m-%d %H:%M:%S')

    docker compose exec -T postgres psql -U odoo -d odoo <<EOF
CREATE TABLE IF NOT EXISTS nettrades_emergency_users (
    id SERIAL PRIMARY KEY,
    login VARCHAR(64) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP NOT NULL,
    last_used TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_emergency_audit (
    id SERIAL PRIMARY KEY,
    login VARCHAR(64) NOT NULL,
    action TEXT NOT NULL,
    ip_address INET,
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO nettrades_emergency_users (login, password_hash, valid_until)
VALUES ('emergency', crypt('$EMERGENCY_PASSWORD', gen_salt('bf')), '$VALID_UNTIL')
ON CONFLICT (login) DO NOTHING;
EOF

    echo "ODOO_EMERGENCY_PASSWORD=$EMERGENCY_PASSWORD" > "$EMERGENCY_DIR/credentials.txt"
    chmod 600 "$EMERGENCY_DIR/credentials.txt"

    log_success "Emergency credentials stored in: $EMERGENCY_DIR/credentials.txt"
    log_info "Emergency user 'emergency' is valid for ${EMERGENCY_ACCESS_DURATION} hours (until: $VALID_UNTIL)"

    cat > "$EMERGENCY_DIR/reset_admin_password.sh" << 'EOF'
#!/bin/bash
read -sp "Enter new admin password: " new_password
docker compose exec -T postgres psql -U odoo -d odoo <<SQL
UPDATE res_users SET password = crypt('$new_password', gen_salt('bf'))
WHERE login = 'admin';
SQL
echo "Admin password updated successfully"
EOF
    chmod +x "$EMERGENCY_DIR/reset_admin_password.sh"
    chmod 600 "$EMERGENCY_DIR/reset_admin_password.sh"

    log_success "Emergency access configured:"
    echo ""
    echo "============================================================"
    echo " EMERGENCY ACCESS OPTIONS"
    echo "============================================================"
    echo "1. Odoo Emergency User:      login='emergency'"
    echo "   Password: $EMERGENCY_DIR/credentials.txt"
    echo "   Valid until: $VALID_UNTIL"
    echo "2. Rescue SSH:               ssh -p 2222 localhost (password auth)"
    echo "3. Admin Password Reset:     $EMERGENCY_DIR/reset_admin_password.sh"
    echo "============================================================"

    # -----------------------------------------------------------------------------
    # 13. Set up cron for daily backups
    # -----------------------------------------------------------------------------
    log_step "Setting up cron for daily backups..."

    BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
    if [[ -f "$BACKUP_SCRIPT" ]]; then
        if command -v crontab &>/dev/null; then
            (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" || echo "") > /tmp/cron.tmp
            echo "0 2 * * * $BACKUP_SCRIPT >> $LOGS_DIR/backup.log 2>&1" >> /tmp/cron.tmp
            crontab /tmp/cron.tmp
            rm /tmp/cron.tmp
            log_success "Cron backup scheduled at 2 AM daily"
        else
            log_warning "crontab not found – skipping cron setup"
        fi
    else
        log_warning "backup.sh not found – skipping cron setup"
    fi

    # -----------------------------------------------------------------------------
    # 14. Final health checks
    # -----------------------------------------------------------------------------
    log_step "Verifying service health..."
    sleep 10

    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
        log_success "Odoo is healthy"
    else
        log_warning "Odoo health check failed – please check logs"
    fi

    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
        log_success "LangGraph is healthy"
    else
        log_warning "LangGraph health check failed – please check logs"
    fi

    if docker compose exec -T postgres pg_isready -U odoo &>/dev/null; then
        log_success "PostgreSQL is healthy"
    else
        log_warning "PostgreSQL health check failed – please check logs"
    fi

    log_step "Waiting for LangGraph Server to be ready..."
    for i in {1..30}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
            log_success "LangGraph Server is ready"
            break
        fi
        sleep 2
    done

    # =============================================================================
    # 15. Ensure Let's Encrypt certificate
    # =============================================================================
    ensure_letsencrypt_certificate() {
        local domain="${DOMAIN:-nettrades.ai}"
        local acme_file="$DEPLOY_DIR/traefik-data/acme.json"
        local max_attempts=6
        local attempt=1

        log_step "Ensuring Let's Encrypt certificate for domain: $domain"

        if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$domain" == "localhost" ]]; then
            log_warning "DOMAIN is an IP or localhost – Let's Encrypt cannot issue certificates."
            log_info "Using self-signed certificate. Your browser will show a warning."
            log_info "To use Let's Encrypt, set DOMAIN to a valid domain name with DNS resolution."
            return 0
        fi

        if [[ "${USE_LETSENCRYPT:-true}" == "false" ]]; then
            log_info "Let's Encrypt disabled. Using self-signed certificate."
            return 0
        fi

        if [[ -f "$acme_file" ]] && grep -q '"Certificate"' "$acme_file"; then
            log_success "Certificate already exists in $acme_file"
            expire_date=$(grep -o '"notAfter":"[^"]*"' "$acme_file" | head -1 | cut -d'"' -f4 | cut -d'T' -f1)
            if [[ -n "$expire_date" ]]; then
                log_info "Certificate expires on: $expire_date"
            fi
            return 0
        fi

        log_info "Certificate not found or invalid. Triggering certificate request..."
        mkdir -p "$DEPLOY_DIR/traefik-data"
        chmod 755 "$DEPLOY_DIR/traefik-data"

        if [[ -f "$acme_file" ]]; then
            sudo rm -f "$acme_file"
            log_info "Removed old acme.json"
        fi

        docker compose restart traefik

        while [[ $attempt -le $max_attempts ]]; do
            log_info "Checking for certificate (attempt $attempt/$max_attempts)..."
            sleep 15

            if [[ -f "$acme_file" ]] && grep -q '"Certificate"' "$acme_file"; then
                log_success "Certificate successfully obtained!"
                docker compose restart traefik
                return 0
            fi

            if docker compose logs traefik 2>/dev/null | grep -q "acme: error"; then
                log_error "ACME error detected. Check Traefik logs for details."
                log_info "Common issues: domain not resolving, port 80 blocked, rate limiting."
                log_info "You may need to accept the self-signed certificate in your browser for now."
                break
            fi

            attempt=$((attempt + 1))
        done

        log_warning "Certificate could not be obtained after $max_attempts attempts."
        log_warning "The site will still work with the self-signed certificate, but your browser will show a warning."
        log_info "You can manually force a renewal by running:"
        echo "  cd $DEPLOY_DIR && sudo rm -f traefik-data/acme.json && docker compose restart traefik"
    }

    ensure_letsencrypt_certificate

    # -----------------------------------------------------------------------------
    # 16. Reset Grafana admin password
    # -----------------------------------------------------------------------------
    log_step "Resetting Grafana admin password..."
    if [[ -n "${GRAFANA_PASSWORD:-}" ]]; then
        for i in {1..30}; do
            if curl -s -f -o /dev/null http://localhost:3001/api/health; then
                break
            fi
            sleep 2
        done
        for i in {1..5}; do
            if docker exec grafana grafana cli admin reset-admin-password "$GRAFANA_PASSWORD" &>/dev/null; then
                log_success "Grafana password reset successfully"
                break
            fi
            sleep 3
        done
    else
        log_warning "GRAFANA_PASSWORD not set – skipping password reset"
    fi

    # -----------------------------------------------------------------------------
    # 17. Start Self-Improving Service
    # -----------------------------------------------------------------------------
    log_step "Starting self-improving service..."
    if docker compose ps -q self-improving &>/dev/null; then
        docker compose up -d self-improving
        log_success "Self-improving service started"
    else
        log_warning "Self-improving service not defined in docker-compose.yaml – skipping"
    fi

    # -----------------------------------------------------------------------------
    # Install Wine for Windows launcher builds (with 32‑bit support)
    # -----------------------------------------------------------------------------
    install_wine() {
        log_step "Installing Wine for Windows launcher builds..."
    
        # Check if Wine is already installed and functional
        if command -v wine &>/dev/null && wine --version &>/dev/null; then
            log_success "Wine already installed: $(wine --version)"
            return 0
        fi
    
        if [[ "$OS" != "linux" ]]; then
            log_warning "Wine installation only supported on Linux. Skipping."
            return 1
        fi
    
        log_info "Enabling multi-architecture (i386) support..."
        sudo dpkg --add-architecture i386 || {
            log_error "Failed to add i386 architecture. Please check your system."
            return 1
        }
    
        log_info "Updating package lists..."
        sudo apt update -qq || {
            log_error "Failed to update package lists."
            return 1
        }
    
        log_info "Installing Wine and 32‑bit libraries..."
        sudo apt install -y \
            wine \
            wine64 \
            wine32:i386 \
            libasound2t64 \
            libasound2t64:i386 \
            libnspr4 \
            libnss3 \
            libxss1 \
            libatk-bridge2.0-0t64 \
            libgtk-3-0t64 \
            libgbm1 \
            libnspr4:i386 \
            libnss3:i386 \
            libgtk-3-0t64:i386 \
            || {
                log_warning "Some Wine dependencies failed to install. Continuing anyway."
            }
    
        # Verify installation
        if ! command -v wine &>/dev/null; then
            log_error "Wine installation failed. Skipping Windows build."
            return 1
        fi
    
        log_info "Configuring a fresh 32‑bit Wine prefix..."
        # Remove any existing prefix to avoid conflicts
        if [[ -d "$HOME/.wine" ]]; then
            log_info "Removing old Wine prefix..."
            rm -rf "$HOME/.wine"
        fi
    
        export WINEARCH=win32
        export WINEPREFIX="$HOME/.wine"
    
        # Initialise Wine – this downloads and configures 32‑bit components
        log_info "Initialising Wine (this may take a moment)..."
        wine winecfg 2>/dev/null || {
            log_warning "Wine initialisation failed but may still work."
        }
    
        log_success "Wine installation completed."
        return 0
    }

    # Wine and the Windows launcher build are only needed if the operator
    # is building the Windows installer on this host. On a headless
    # server (the V100), this adds 300–500 MB of GUI packages for no
    # benefit. Gate it behind WITH_WINDOWS_LAUNCHER.
    if [[ "${WITH_WINDOWS_LAUNCHER}" == "true" ]]; then
        install_wine || log_warning "Wine setup failed; Windows build will be skipped."
    else
        log_info "Skipping Wine installation (set WITH_WINDOWS_LAUNCHER=true to enable)."
    fi

    # Write the hub's own hardware manifest so langgraph-server can
    # correct the gpu.node record for this machine. The detection code
    # (scripts/lib/detect.py) is the same one install-spoke.sh uses,
    # so the hub and its spokes describe hardware in the same shape.
    log_step "Detecting hub hardware (scripts/lib/detect.py)..."
    if [[ -f "$SCRIPT_DIR/lib/detect.py" ]]; then
        if python3 "$SCRIPT_DIR/lib/detect.py" --json > "$DEPLOY_DIR/hub-manifest.json" 2>/dev/null; then
            chmod 644 "$DEPLOY_DIR/hub-manifest.json"
            log_success "Hub manifest written to $DEPLOY_DIR/hub-manifest.json"
        else
            rm -f "$DEPLOY_DIR/hub-manifest.json"
            log_warning "detect.py failed — hub hardware will not be auto-refreshed"
        fi
    else
        log_warning "scripts/lib/detect.py not found — hub hardware will not be auto-refreshed"
    fi

    # =============================================================================
    # BUILD NETTRADES LAUNCHER
    # =============================================================================
    build_launcher() {
        log_step "Building NETTRADES Launcher..."
        local installer_dir="$PROJECT_ROOT/installer"

        if [[ ! -d "$installer_dir" ]]; then
            log_warning "Installer directory not found: $installer_dir"
            return 1
        fi

        cd "$installer_dir"

        # Install dependencies if node_modules is missing
        if [[ ! -d "node_modules" ]]; then
            log_info "Installing npm dependencies..."
            npm install || {
                log_warning "npm install failed. The launcher may not build correctly."
            }
        fi

        # Build for Linux
        log_info "Building Linux launcher..."
        npm run build:linux || {
            log_warning "Linux build failed. Skipping."
        }

        # Build for Windows — gated behind WITH_WINDOWS_LAUNCHER because the
        # Windows build depends on Wine, which is a heavy install with GUI
        # packages that are useless on a headless server. The installer
        # only needs the Linux AppImage for the demo.
        if [[ "${WITH_WINDOWS_LAUNCHER}" == "true" ]] && command -v wine &>/dev/null; then
            log_info "Building Windows launcher (requires Wine)..."
            npm run build:win || {
                log_warning "Windows build failed. Wine may not be properly configured."
            }
        else
            log_info "Skipping Windows launcher build (set WITH_WINDOWS_LAUNCHER=true to enable)."
        fi
        log_success "Launcher build completed"
        cd "$PROJECT_ROOT"
    }

    # -----------------------------------------------------------------------------
    # 18. Display final status
    # -----------------------------------------------------------------------------
    cd "$PROJECT_ROOT"
    mark_phase_complete 2
    touch /tmp/nettrades-phase2-completed

    # Build the launcher after all services are running
    build_launcher

    log_success "Phase 2 completed – Docker stack deployed with all modules"
    echo ""
    echo "============================================================"
    echo " NETTRADES Platform is now running!"
    echo "============================================================"
    echo ""
    docker compose -f "$DEPLOY_DIR/docker-compose.yaml" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
    echo ""
    echo "Access the services:"
    echo "  Frontend (UI): http://localhost:3002 (or http://nettrades.ai:3002)"
    echo "  Odoo:      http://localhost:8069  (admin / password in .env ODOO_ADMIN_PASSWORD)"
    if [[ "${WITH_GROVE:-false}" == "true" ]]; then
        echo "  Grove:     http://localhost:8081  (observability dashboard)"
        echo "  Loki:      http://localhost:3100  (logs)"
        echo "  Tempo:     http://localhost:3200  (traces)"
    fi
    if [[ "${WITH_KAI:-false}" == "true" ]]; then
        echo "  KAI Scheduler: http://localhost:9091  (GPU scheduling)"
    fi
    echo "  Grafana:   http://localhost:3001  (admin / password in .env GRAFANA_PASSWORD)"
    echo "  Prometheus: http://localhost:9090 (admin / password in .env PROMETHEUS_PASSWORD)"
    echo "  Dynamo:    http://localhost:8001  (primary inference, API key in .env DYNAMO_API_KEY)"
    echo "  llama.cpp: http://localhost:8080  (fallback inference, includes built-in UI)"
    if [[ "${WITH_FINETUNE:-false}" == "true" ]]; then
        echo "  Training Worker: http://localhost:8002  (fine-tuning API)"
    fi
    echo ""
    echo "Emergency Odoo user: emergency (password in /root/emergency_password.txt)"
    echo "Use this if you get locked out of admin."
    if [[ "$ENVIRONMENT" == "production" ]]; then
        echo ""
        echo "Production mode: SSH is key-only on port 22. Use port 2222 for password auth."
        echo "SSH keys are stored in: $PROJECT_ROOT/ssh-keys/"
    fi

fi # end of HUB mode

# End of script
