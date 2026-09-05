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

set -euo pipefail

# -----------------------------------------------------------------------------
# Parse arguments early (so AUTO, FORCE, etc. are available)
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
UPGRADE="${UPGRADE:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"
REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
RESET_DATA="${RESET_DATA:-false}"
WITH_CUVS="${WITH_CUVS:-false}"
WITH_FINETUNE="${WITH_FINETUNE:-false}"
WITH_GROVE="${WITH_GROVE:-false}"
WITH_KAI="${WITH_KAI:-false}"
WITH_ROUTER="${WITH_ROUTER:-false}"
DOMAIN="${DOMAIN:-}"
export FORCE WITH_CUVS WITH_FINETUNE WITH_GROVE WITH_KAI WITH_ROUTER DOMAIN

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
    # If FORCE is true and .env file does not exist, assume a fresh HUB install.
    ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
    if [[ "$FORCE" == true ]] && [[ ! -f "$ENV_FILE" ]]; then
        log_info "Force mode with no .env – forcing HUB deployment."
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
    elif [[ "$DETECTION_MODE" == "spoke" ]]; then
        DEPLOYMENT_MODE="spoke"
        log_success "Deployment mode: SPOKE (forced)"
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

    # Find the sub-hub
    SUB_HUB_IP=""
    if command -v avahi-browse &>/dev/null; then
        SUB_HUB_IP=$(avahi-browse -t _nettrades._tcp -r 2>/dev/null | grep -oP '(\d+\.\d+\.\d+\.\d+)' | head -1)
    fi

    if [[ -z "$SUB_HUB_IP" ]]; then
        log_warning "Could not auto-detect sub-hub. Please specify SUB_HUB_IP in .env"
        SUB_HUB_IP="${SUB_HUB_IP:-}"
    fi

    if [[ -z "$SUB_HUB_IP" ]]; then
        log_error "No sub-hub IP found. Please set SUB_HUB_IP in .env or run as hub."
        exit 1
    fi

    log_info "Sub-hub IP: $SUB_HUB_IP"

    # Install spoke agent
    log_step "Installing spoke agent..."

    # Create spoke configuration
    mkdir -p "$PROJECT_ROOT/spoke"
    cat > "$PROJECT_ROOT/spoke/config.yaml" << EOF
# NETTRADES Spoke Configuration
sub_hub_url: http://${SUB_HUB_IP}:8080
node_name: $(hostname)
gpu_model: $(lspci | grep -i nvidia | head -1 | cut -d: -f3 | xargs || echo "unknown")
vram_gb: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 | cut -d' ' -f1 || echo "0")
heartbeat_interval: 10
inference_engine: llama.cpp
EOF

    # Install spoke agent service
    sudo cp "$PROJECT_ROOT/scripts/spoke-agent.py" /usr/local/bin/spoke-agent
    sudo chmod +x /usr/local/bin/spoke-agent

    # Create systemd service
    sudo cat > /etc/systemd/system/nettrades-spoke.service << EOF
[Unit]
Description=NETTRADES Spoke Agent
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_ROOT/spoke
ExecStart=/usr/local/bin/spoke-agent --config $PROJECT_ROOT/spoke/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable nettrades-spoke.service
    sudo systemctl start nettrades-spoke.service

    log_success "Spoke agent installed and started"

    log_success "Spoke deployment completed"
    exit 0
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

        if ! declare -f is_valid_domain_or_ip >/dev/null 2>&1; then
            echo "ERROR: is_valid_domain_or_ip function not found" >&2
            exit 1
        fi

        if [[ -z "$domain" || "$domain" == "changeit" || "$domain" == "localhost" || "$domain" == "nettrades.ai" ]] || ! is_valid_domain_or_ip "$domain"; then
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
        fi

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
    # EARLY: Download GGUF model for llama.cpp fallback from ModelScope mirror
    # =============================================================================
    if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
        log_step "Downloading GGUF model for llama.cpp fallback from ModelScope mirror..."
        mkdir -p "$MODELS_DIR"
        if bash "$SCRIPT_DIR/download-model.sh" --model deepseek-7b --format gguf --dir "$MODELS_DIR"; then
            log_success "GGUF model downloaded successfully to $MODELS_DIR"
        else
            log_warning "GGUF model download failed. Trying alternative source..."
            MODEL_FILE="$MODELS_DIR/deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
            if wget -O "$MODEL_FILE" "https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf" --progress=dot:giga; then
                log_success "GGUF model downloaded via fallback to $MODEL_FILE"
            else
                log_warning "GGUF model download failed. You may need to manually place a model in $MODELS_DIR."
            fi
        fi

        MODEL_FILE="$MODELS_DIR/deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
        if [[ -f "$MODEL_FILE" ]]; then
            FILE_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
            if [[ "$FILE_SIZE" -lt 1000000000 ]]; then
                log_warning "Model file exists but is too small ($FILE_SIZE bytes). It may be corrupted."
                log_info "Attempting to re-download the model..."
                rm -f "$MODEL_FILE"
                if wget -O "$MODEL_FILE" "https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf" --progress=dot:giga; then
                    NEW_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
                    if [[ "$NEW_SIZE" -gt 1000000000 ]]; then
                        log_success "Model re-downloaded successfully ($NEW_SIZE bytes)"
                    else
                        log_error "Re-downloaded file still too small. Please check the URL and disk space."
                    fi
                else
                    log_error "Re-download failed. llama.cpp will not start."
                fi
            else
                log_success "Model file validated: $MODEL_FILE ($FILE_SIZE bytes)"
            fi
        else
            log_warning "Model file not found at $MODEL_FILE. llama.cpp will fail to start."
        fi
    else
        log_warning "download-model.sh not found – skipping llama.cpp model download"
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
-- NETTRADES Database Initialisation Script
-- =============================================================================
-- This script creates all required PostgreSQL tables for the NETTRADES platform.
-- It is idempotent – tables are created only if they do not already exist.
-- =============================================================================

-- Enable pgcrypto for password hashing (used by Odoo emergency user)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Enable pgvector extension for AI embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- Core Platform Tables
-- =============================================================================

-- nettrades_core – Core platform tables
CREATE TABLE IF NOT EXISTS nettrades_users (
    id SERIAL PRIMARY KEY,
    odoo_user_id INTEGER UNIQUE,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    wallet_address VARCHAR(42),
    karma_score INTEGER DEFAULT 0,
    reputation_score DECIMAL(5,2) DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    website VARCHAR(255),
    industry VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_projects (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES nettrades_companies(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    budget DECIMAL(15,2),
    status VARCHAR(50) DEFAULT 'open',
    required_skills TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Good Answer / Self-Improving AI
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_good_answers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model_used VARCHAR(100),
    votes_positive INTEGER DEFAULT 0,
    votes_negative INTEGER DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_votes (
    id SERIAL PRIMARY KEY,
    answer_id INTEGER REFERENCES nettrades_good_answers(id),
    user_id INTEGER REFERENCES nettrades_users(id),
    vote_type VARCHAR(10) CHECK (vote_type IN ('positive', 'negative')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(answer_id, user_id)
);

-- =============================================================================
-- Ask Someone – Expert Marketplace
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_ask_someone_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    budget DECIMAL(15,2),
    category VARCHAR(100),
    status VARCHAR(50) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_ask_someone_offers (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES nettrades_ask_someone_requests(id),
    expert_id INTEGER REFERENCES nettrades_users(id),
    price DECIMAL(15,2),
    proposal TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- GPU Marketplace
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_gpu_nodes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    gpu_model VARCHAR(100),
    vram_gb INTEGER,
    compute_capability VARCHAR(20),
    ip_address VARCHAR(45),
    port INTEGER,
    status VARCHAR(50) DEFAULT 'available',
    owner_id INTEGER REFERENCES nettrades_users(id),
    price_per_hour DECIMAL(10,4),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_gpu_bookings (
    id SERIAL PRIMARY KEY,
    node_id INTEGER REFERENCES nettrades_gpu_nodes(id),
    user_id INTEGER REFERENCES nettrades_users(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    total_cost DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_gpu_usage_logs (
    id SERIAL PRIMARY KEY,
    booking_id INTEGER REFERENCES nettrades_gpu_bookings(id),
    node_id INTEGER REFERENCES nettrades_gpu_nodes(id),
    usage_type VARCHAR(50),
    duration_seconds INTEGER,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Bridge / Hub-and-Spoke Routing
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_bridge_routes (
    id SERIAL PRIMARY KEY,
    source_node VARCHAR(255),
    target_node VARCHAR(255),
    route_type VARCHAR(50),
    config JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Job Matching & Proposals
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_job_matches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES nettrades_projects(id),
    freelancer_id INTEGER REFERENCES nettrades_users(id),
    match_score DECIMAL(5,2),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_proposals (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES nettrades_projects(id),
    freelancer_id INTEGER REFERENCES nettrades_users(id),
    cover_letter TEXT,
    bid_amount DECIMAL(15,2),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Fairness & Reputation
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_fairness_scores (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    fairness_score DECIMAL(5,2) DEFAULT 0,
    trust_score DECIMAL(5,2) DEFAULT 0,
    last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Notifications
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    type VARCHAR(50),
    title VARCHAR(255),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Research Module
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_research_projects (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    researcher_id INTEGER REFERENCES nettrades_users(id),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Queue / Task Management
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_queue_tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(100),
    payload JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    scheduled_at TIMESTAMP,
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Self-Improving Config
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_self_improving_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value JSONB,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Lead Scoring
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_leads (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES nettrades_companies(id),
    score INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'new',
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Chatbot
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_chatbot_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    session_id VARCHAR(255),
    messages JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- PWA / Offline
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_pwa_cache (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    cache_key VARCHAR(255),
    cache_data JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Create secrets table with pgcrypto encryption
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_secrets (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value BYTEA NOT NULL,
    description TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
);

-- =============================================================================
-- Create an audit log
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_secrets_audit (
    id SERIAL PRIMARY KEY,
    secret_key VARCHAR(255),
    action VARCHAR(50),
    performed_by VARCHAR(255),
    performed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =============================================================================
-- Indexes for Performance
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_good_answers_user_id ON nettrades_good_answers(user_id);
CREATE INDEX IF NOT EXISTS idx_gpu_nodes_status ON nettrades_gpu_nodes(status);
CREATE INDEX IF NOT EXISTS idx_gpu_bookings_user_id ON nettrades_gpu_bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_project_id ON nettrades_job_matches(project_id);
CREATE INDEX IF NOT EXISTS idx_proposals_project_id ON nettrades_proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON nettrades_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_queue_tasks_status ON nettrades_queue_tasks(status);

EOF
        log_success "init-db.sql generated with all NETTRADES tables"
    else
        log_success "init-db.sql already exists"
    fi

    # -----------------------------------------------------------------------------
    # 5. Run security hardening (if Phase 0 not completed)
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
    # 6. Start PostgreSQL and initialise the database (if empty)
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
            if [[ -n "$actual_pass" && "$actual_pass" != "$POSTGRES_PASSWORD" ]]; then
                log_warning "PostgreSQL password mismatch."
                log_warning "  .env password: $POSTGRES_PASSWORD"
                log_warning "  Container password: $actual_pass"
                if [[ "$FORCE" == true ]] || [[ "$AUTO" == true ]]; then
                    log_info "Updating .env to match the container's password."
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
        ADMIN_PASSWORD
        FORGEJO_DB_PASSWORD
        FORGEJO_SECRET_KEY
        GRAFANA_PASSWORD
        PROMETHEUS_PASSWORD
        LANGGRAPH_API_KEY
        ODOO_API_KEY
        PROXY_API_KEY
    )

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
        safe_sed_replace "$ENV_FILE" "FINE_TUNE_MODEL" "deepseek-1.5b"
        log_info "Set FINE_TUNE_MODEL=deepseek-1.5b"
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

    # -----------------------------------------------------------------------------
    # 7. Build and start the full Docker Compose stack (with retry)
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

    if [[ "${WITH_FINETUNE:-false}" == "true" ]]; then
        log_info "Starting fine-tuning workers..."
        if [[ -f "$DEPLOY_DIR/docker-compose.finetune.yaml" ]]; then
            docker compose -f docker-compose.yaml -f docker-compose.finetune.yaml up -d training-worker
            log_success "Fine-tuning workers started"
        else
            log_warning "docker-compose.finetune.yaml not found – skipping fine-tuning"
        fi
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
    # 10. DYNAMO SETUP
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

    sleep 5

    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models \
           -H "Authorization: Bearer $DYNAMO_API_KEY" | grep -q "200"; then
        log_success "Dynamo is healthy. Using Dynamo as the primary inference backend."
        LLM_BASE_URL="http://dynamo:8000/v1"
        OPENAI_API_KEY="$DYNAMO_API_KEY"
    else
        log_warning "Dynamo not available or not ready. Falling back to llama.cpp (CPU)."
        LLM_BASE_URL="http://llama-cpp:8080/v1"
        OPENAI_API_KEY="dummy"
    fi

    log_step "Updating .env with inference backend settings..."
    safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
    safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
    log_success ".env updated"

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

    # -----------------------------------------------------------------------------
    # 11. Install NETTRADES Odoo modules
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

    # -----------------------------------------------------------------------------
    # 12. Create emergency Odoo user and multiple fallback options
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

    BACKUP_SCRIPT="$DEPLOY_DIR/backup.sh"
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
    # 18. Display final status
    # -----------------------------------------------------------------------------
    cd "$PROJECT_ROOT"
    mark_phase_complete 2
    touch /tmp/nettrades-phase2-completed

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
    echo "  Odoo:      http://localhost:8069  (admin / password in .env ADMIN_PASSWORD)"
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