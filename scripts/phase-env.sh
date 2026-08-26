#!/bin/bash
# =============================================================================
# FILE: scripts/phase-env.sh
# =============================================================================
# PURPOSE:
#   Phase 1: Environment & Secrets Generation.
#   This phase generates all required secrets and creates the .env file.
#   VIRTUAL ENVIRONMENT IS NOW MANDATORY – this script creates it if missing.
#
#   SAFETY FEATURES:
#   - If .env already exists, the script will NOT modify it unless --force is used.
#   - With --force and --regenerate-secrets, it will regenerate (with backup).
#   - With --auto and --force, it regenerates silently (for CI/CD).
#   - In production, additional confirmation is required.
#   - NEW: Automatically detects the server IP and prompts for domain/email.
#   - FIXED: DATABASE_URL is no longer modified – uses the template's placeholder.
#   - FIXED: POSTGRES_PASSWORD is validated to be alphanumeric only.
#
#   SECRETS GENERATED:
#   - POSTGRES_PASSWORD (prompted)
#   - ADMIN_PASSWORD, JWT_SECRET, PROXY_API_KEY
#   - GRAFANA_PASSWORD, PROMETHEUS_PASSWORD
#   - DYNAMO_API_KEY (NEW – replaces GPUStack)
#   - LANGGRAPH_API_KEY
#   - WireGuard keys
#
#   DOMAIN CONFIG:
#   - Detects IP and prompts for domain (warns if IP used for Let's Encrypt)
#
# USAGE:
#   ./phase-env.sh [--auto] [--force] [--regenerate-secrets]
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# FIX: Set default for PER_USER to prevent "unbound variable" error
# -----------------------------------------------------------------------------
PER_USER="${PER_USER:-false}"
export PER_USER

# Set PROJECT_ROOT if not already set (for standalone execution)
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

read_feature_flags

# -----------------------------------------------------------------------------
# Determine .env location based on PER_USER
# -----------------------------------------------------------------------------
if [[ "$PER_USER" == true ]]; then
    ENV_FILE="$HOME/.nettrades/deploy/docker/.env"
    mkdir -p "$(dirname "$ENV_FILE")"
else
    ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
fi

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
WITH_CUVS="${WITH_CUVS:-false}"
export FORCE WITH_CUVS

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "1"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 1; then
    log_warning "Phase 1 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Set up paths
# -----------------------------------------------------------------------------
ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
ENV_EXAMPLE="$PROJECT_ROOT/deploy/docker/.env.example"
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
export VENV_DIR

# =============================================================================
# VIRTUAL ENVIRONMENT IS MANDATORY – create it if missing
# =============================================================================
if [[ ! -d "$VENV_DIR" ]]; then
    log_info "Virtual environment not found at $VENV_DIR – creating it..."
    if ! python3 -c "import venv" 2>/dev/null; then
        log_error "python3-venv not installed. Please install it:"
        log_info "  Ubuntu/Debian: sudo apt install python3-venv"
        log_info "  macOS: brew install python3"
        exit 1
    fi
    python3 -m venv "$VENV_DIR"
    log_success "Virtual environment created at $VENV_DIR"
fi

# Activate venv
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    log_error "Virtual environment activation file not found at $VENV_DIR/bin/activate"
    exit 1
fi
source "$VENV_DIR/bin/activate"
log_success "Virtual environment activated"

# Verify venv is active
if [ -z "${VIRTUAL_ENV:-}" ]; then
    log_error "Virtual environment not active. Please activate it manually: source $VENV_DIR/bin/activate"
    exit 1
fi

# -----------------------------------------------------------------------------
# Check if .env already exists
# -----------------------------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
    log_warning ".env already exists at $ENV_FILE"

    # If --force is NOT used, exit safely (preserve existing secrets)
    if [[ "$FORCE" != true ]]; then
        log_info "To regenerate all secrets (which will break existing services), use --force and --regenerate-secrets."
        log_info "If you only need to update the password, edit the .env file manually."
        exit 0
    fi

    if [[ "$REGENERATE_SECRETS" != true ]]; then
        log_info "Use --regenerate-secrets to actually regenerate the secrets."
        log_info "Skipping regeneration."
        exit 0
    fi

    log_warning "You have requested to regenerate ALL secrets in .env."
    # If --auto is also used, regenerate silently (CI/CD)
    if [[ "$AUTO" == true ]]; then
        log_info "Auto mode with --force: regenerating secrets without confirmation."
    else
        # Interactive confirmation
        echo ""
        echo -e "${RED}WARNING: You are about to OVERWRITE all existing secrets in .env.${NC}"
        echo -e "${RED}This will break all running services (Odoo, LangGraph, Nvidia Dynamo, etc.).${NC}"
        echo -e "${YELLOW}Do you have a backup of your current .env file? (y/N)${NC}"
        read -p "> " backup_confirm
        if [[ ! "$backup_confirm" =~ ^[Yy]$ ]]; then
            log_error "Aborting. Please back up your current .env and try again."
            exit 1
        fi

        echo ""
        echo -e "${YELLOW}Proceed with regeneration? This action CANNOT be undone. (type 'YES' to confirm)${NC}"
        read -p "> " final_confirm
        # Case-insensitive check
        if [[ "${final_confirm^^}" != "YES" ]]; then
            log_info "Aborted."
            exit 0
        fi
    fi

    log_info "User confirmed – proceeding with regeneration."
else
    log_info ".env not found – will create a new one."
fi

# -----------------------------------------------------------------------------
# Generate .env
# -----------------------------------------------------------------------------
log_step "Preparing .env file..."

# Create from template if it exists
if [[ -f "$ENV_EXAMPLE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log_success "Copied .env from template"
else
    log_error ".env.example not found at $ENV_EXAMPLE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Generate secure secrets (with user prompt for PostgreSQL password)
# -----------------------------------------------------------------------------
log_step "Generating secure secrets..."

# =============================================================================
# Safe password generator (alphanumeric only, for compatibility)
# =============================================================================
generate_safe_password() {
    openssl rand -base64 24 | tr -d '+/=' | tr -d '\n' | cut -c1-24
}

generate_safe_api_key() {
    openssl rand -base64 48 | tr -d '+/=' | tr -d '\n' | cut -c1-48
}

# =============================================================================
# Password retry function – gives up to 5 attempts on mismatch or empty
# =============================================================================
read_password_with_retry() {
    local prompt="$1"
    local password1=""
    local password2=""
    local attempts=0
    local max_attempts=5

    while [ $attempts -lt $max_attempts ]; do
        read -s -p "$prompt" password1
        echo
        read -s -p "Confirm password: " password2
        echo

        if [ "$password1" = "$password2" ] && [ -n "$password1" ]; then
            # Validate alphanumeric only (no special chars, spaces, newlines)
            if [[ "$password1" =~ ^[a-zA-Z0-9]+$ ]]; then
                echo "$password1"
                return 0
            else
                echo -e "${RED}❌ Password must contain only letters and numbers (no special characters). Please try again.${NC}"
                attempts=$((attempts + 1))
                continue
            fi
        else
            attempts=$((attempts + 1))
            if [ $attempts -lt $max_attempts ]; then
                echo -e "${RED}❌ Passwords do not match or are empty. Please try again. (Attempt $attempts/$max_attempts)${NC}"
            else
                echo -e "${RED}❌ Too many failed attempts. Exiting.${NC}"
                return 1
            fi
        fi
    done
}

# =============================================================================
# Handle PostgreSQL password safely
# =============================================================================

# Determine if we should ask for a password or generate one
if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" == true ]]; then
    # We are regenerating an existing .env after user confirmation – ask for a new password
    echo ""
    echo -e "${YELLOW}Enter a NEW PostgreSQL password for the 'odoo' user:${NC}"
    echo -e "${YELLOW}(This password will be used for PostgreSQL, Odoo, and all services)${NC}"
    # Use the retry function for the regeneration case
    if ! POSTGRES_PASSWORD=$(read_password_with_retry "Password: "); then
        log_error "Password entry failed. Exiting."
        exit 1
    fi
elif [[ "$AUTO" == true ]]; then
    # Auto mode: generate a random password (only for fresh installs)
    POSTGRES_PASSWORD=$(generate_safe_password)
    log_info "Auto mode: generated random PostgreSQL password"
else
    # Interactive mode (fresh install or no --force): prompt for password
    echo ""
    echo -e "${YELLOW}Enter a PostgreSQL password for the 'odoo' user:${NC}"
    echo -e "${YELLOW}(This password will be used for PostgreSQL, Odoo, and all services)${NC}"
    # Use the retry function for the interactive case
    if ! POSTGRES_PASSWORD=$(read_password_with_retry "Password: "); then
        log_error "Password entry failed. Exiting."
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Generate other secrets (only after we have a valid password)
# -----------------------------------------------------------------------------
ODOO_ADMIN_PASSWORD=$(generate_safe_password)
SECRET_KEY=$(generate_safe_password)
JWT_SECRET=$(generate_safe_password)
VLLM_API_KEY=$(generate_safe_password)
PROXY_API_KEY=$(generate_safe_password)
WIREGUARD_PRIVATE_KEY=$(generate_wireguard_key)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey 2>/dev/null || echo "manual")
GRAFANA_PASSWORD=$(generate_safe_password)
PROMETHEUS_PASSWORD=$(generate_safe_password)
DYNAMO_API_KEY=$(generate_safe_api_key)   # NEW – replaces GPUStack

# Generate LangGraph API key (strong, alphanumeric)
LANGGRAPH_API_KEY=$(generate_safe_api_key)

# -----------------------------------------------------------------------------
# Write secrets to .env using safe_sed_replace (handles special characters)
# -----------------------------------------------------------------------------
safe_sed_replace "$ENV_FILE" "POSTGRES_PASSWORD" "$POSTGRES_PASSWORD"
safe_sed_replace "$ENV_FILE" "ADMIN_PASSWORD" "$ODOO_ADMIN_PASSWORD"
safe_sed_replace "$ENV_FILE" "SECRET_KEY" "$SECRET_KEY"
safe_sed_replace "$ENV_FILE" "JWT_SECRET" "$JWT_SECRET"
safe_sed_replace "$ENV_FILE" "VLLM_API_KEY" "$VLLM_API_KEY"
safe_sed_replace "$ENV_FILE" "PROXY_API_KEY" "$PROXY_API_KEY"
safe_sed_replace "$ENV_FILE" "WIREGUARD_PRIVATE_KEY" "$WIREGUARD_PRIVATE_KEY"
safe_sed_replace "$ENV_FILE" "WIREGUARD_PUBLIC_KEY" "$WIREGUARD_PUBLIC_KEY"
safe_sed_replace "$ENV_FILE" "GRAFANA_PASSWORD" "$GRAFANA_PASSWORD"
safe_sed_replace "$ENV_FILE" "PROMETHEUS_PASSWORD" "$PROMETHEUS_PASSWORD"
safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"
safe_sed_replace "$ENV_FILE" "LANGGRAPH_API_KEY" "$LANGGRAPH_API_KEY"
safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$PROXY_API_KEY"  # Ensure sync
# Ensure ODOO_API_KEY and PROXY_API_KEY are identical
safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$PROXY_API_KEY"

# =============================================================================
# CRITICAL FIX: Do NOT modify DATABASE_URL – keep the template's placeholder.
# The template uses ${POSTGRES_PASSWORD} which will be expanded at runtime.
# =============================================================================
# The following line is REMOVED to prevent corruption:
# safe_sed_replace "$ENV_FILE" "DATABASE_URL" "postgresql://odoo:${POSTGRES_PASSWORD}@postgres:5432/odoo"

# -----------------------------------------------------------------------------
# NEW: Configure DOMAIN and ADMIN_EMAIL (auto-detect + interactive prompt)
# -----------------------------------------------------------------------------
configure_domain_email() {
    # Detect primary IP address
    detect_ip() {
        # Use hostname -I as primary (more reliable on WSL)
        local ip=$(hostname -I 2>/dev/null | awk '{print $1}')
        # If that fails, try ip route
        if [[ -z "$ip" || "$ip" =~ ^[0-9]+$ ]]; then
            ip=$(ip -4 route get 1 2>/dev/null | awk '{print $NF;exit}')
        fi
        # Fallback to localhost
        [[ -z "$ip" ]] && ip="localhost"
        echo "$ip"
    }

    # Read current values from .env
    CURRENT_DOMAIN=$(grep "^DOMAIN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")
    CURRENT_EMAIL=$(grep "^ADMIN_EMAIL=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")
    # If DOMAIN is invalid (empty, placeholder, or not a valid domain/IP), we set it.
    if [[ -z "$CURRENT_DOMAIN" || "$CURRENT_DOMAIN" == "changeit" || "$CURRENT_DOMAIN" == "nettrades.ai" ]] || ! is_valid_domain_or_ip "$CURRENT_DOMAIN"; then
        DETECTED_IP=$(detect_ip)

        if [[ "$AUTO" == true ]]; then
            DOMAIN="$DETECTED_IP"
            log_info "Auto mode: using detected IP $DOMAIN as DOMAIN"
        else
            echo ""
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo " Domain Configuration"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "Enter the domain name or IP address where this platform will be accessible."
            echo "If you have a domain (e.g., ai.mycompany.com), enter it here."
            echo "Otherwise, press Enter to use the detected IP: $DETECTED_IP"
            echo ""
            read -rp "Domain/IP (default: $DETECTED_IP): " USER_DOMAIN
            if [[ -n "$USER_DOMAIN" ]]; then
                DOMAIN="$USER_DOMAIN"
            else
                DOMAIN="$DETECTED_IP"
            fi
            log_info "Using domain: $DOMAIN"
        fi

        safe_sed_replace "$ENV_FILE" "DOMAIN" "$DOMAIN"
    else
        log_info "DOMAIN already set to: $CURRENT_DOMAIN (skipping prompt)"
        DOMAIN="$CURRENT_DOMAIN"
    fi

    # Warn if DOMAIN is an IP address (Let's Encrypt doesn't work with IP)
    if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_warning "DOMAIN is set to an IP address ($DOMAIN). Let's Encrypt requires a valid domain name with DNS resolution."
        log_warning "HTTPS certificates will not be obtained automatically. You can either set a domain or accept the self-signed certificate."
        if [[ "$AUTO" != true ]]; then
            read -rp "Continue with IP? (y/N): " continue_ip
            if [[ ! "$continue_ip" =~ ^[Yy]$ ]]; then
                log_error "Exiting. Please set a domain name in .env and re-run."
                exit 1
            fi
        fi
    fi

    # Admin email
    if [[ "$CURRENT_EMAIL" == "changeit" || "$CURRENT_EMAIL" == "admin@nettrades.ai" || -z "$CURRENT_EMAIL" ]]; then
        if [[ "$AUTO" == true ]]; then
            ADMIN_EMAIL="admin@localhost"
            log_info "Auto mode: using default admin email $ADMIN_EMAIL"
        else
            echo ""
            read -rp "Admin email (for Let's Encrypt, default: admin@localhost): " USER_EMAIL
            if [[ -n "$USER_EMAIL" ]]; then
                ADMIN_EMAIL="$USER_EMAIL"
            else
                ADMIN_EMAIL="admin@localhost"
            fi
        fi
        safe_sed_replace "$ENV_FILE" "ADMIN_EMAIL" "$ADMIN_EMAIL"
    else
        log_info "ADMIN_EMAIL already set to: $CURRENT_EMAIL (skipping prompt)"
    fi
}

# Run the domain/email configuration after secrets are written
configure_domain_email

# -----------------------------------------------------------------------------
# Default Landing Page
# -----------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Default Landing Page"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Choose which page users see when they visit https://${DOMAIN}"
echo "  1) Odoo homepage (recommended)  - /odoo"
echo "  2) AI Chat UI                   - http://localhost:3002"
echo "  3) Custom landing page          - a simple HTML page (you can edit later)"
echo ""
read -rp "Enter 1, 2, or 3 (default: 1): " landing_choice

case "$landing_choice" in
    2) DEFAULT_LANDING_PAGE="ui" ;;
    3) DEFAULT_LANDING_PAGE="custom" ;;
    *) DEFAULT_LANDING_PAGE="odoo" ;;
esac
log_info "Default landing page: $DEFAULT_LANDING_PAGE"

safe_sed_replace "$ENV_FILE" "DEFAULT_LANDING_PAGE" "$DEFAULT_LANDING_PAGE"

# -----------------------------------------------------------------------------
# Set secure permissions
# -----------------------------------------------------------------------------
chmod 600 "$ENV_FILE"
log_success ".env generated with secure secrets"

# -----------------------------------------------------------------------------
# After generating secrets, sync to Odoo DB
# -----------------------------------------------------------------------------
sync_secrets_to_odoo() {
    if curl -s --connect-timeout 2 http://odoo:8069 >/dev/null 2>&1; then  
        local secrets=$(cat "$ENV_FILE" | grep -v '^#' | grep '=' | sed 's/^ *//;s/ *$//')
        local odoo_url="http://odoo:8069"

        # Use Odoo's XML-RPC to sync secrets
        echo "$secrets" | while IFS= read -r line; do
            key=$(echo "$line" | cut -d'=' -f1)
            value=$(echo "$line" | cut -d'=' -f2- | tr -d "'")

            # Sync to Odoo DB
            curl -X POST "${odoo_url}/api/secrets" \
                -H "Content-Type: application/json" \
                -d "{\"key\":\"$key\",\"value\":\"$value\",\"description\":\"Synced from .env\"}"
        done
    else
          log_info "Odoo not running yet – skipping secret sync."
    fi
}

# Call after generating all secrets
sync_secrets_to_odoo

# -----------------------------------------------------------------------------
# Install RAPIDS cuVS if requested
# -----------------------------------------------------------------------------
if [[ "$WITH_CUVS" == true ]]; then
    # Check for NVIDIA GPU
    if command -v nvidia-smi &>/dev/null; then
        log_step "NVIDIA GPU detected. Installing RAPIDS cuVS..."
        local cuvs_req="$PROJECT_ROOT/requirements-cuvs.txt"
        if [[ -f "$cuvs_req" ]]; then
            if [[ "$USE_UV" != false ]] && command -v uv &>/dev/null; then
                if ! uv pip install --verbose --index-url https://pypi.org/simple/ -r "$cuvs_req"; then
                    log_error "uv cuVS installation failed. Falling back to pip."
                    pip install --verbose -r "$cuvs_req" || { log_error "cuVS installation failed."; exit 1; }
                fi
            else
                pip install --verbose -r "$cuvs_req" || { log_error "cuVS installation failed."; exit 1; }
            fi
            log_success "RAPIDS cuVS installed successfully."
        else
            log_warning "requirements-cuvs.txt not found – cuVS installation skipped."
        fi
    else
        log_warning "No NVIDIA GPU detected. RAPIDS cuVS requires a GPU. Skipping installation."
        log_info "To install cuVS, ensure an NVIDIA GPU with CUDA drivers is available."
    fi
else
    log_info "Skipping RAPIDS cuVS (use --with-cuvs to enable)."
fi

# -----------------------------------------------------------------------------
# Display important information (only in interactive mode, not auto)
# -----------------------------------------------------------------------------
if [[ "$AUTO" != true ]]; then
    # Reload the updated values from .env for display
    DOMAIN_DISPLAY=$(grep "^DOMAIN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")
    ADMIN_EMAIL_DISPLAY=$(grep "^ADMIN_EMAIL=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")

    echo ""
    echo -e "${YELLOW}Important credentials (save these):${NC}"
    echo "  POSTGRES_PASSWORD: $POSTGRES_PASSWORD"
    echo "  ODOO_ADMIN_PASSWORD: $ODOO_ADMIN_PASSWORD"
    echo "  PROXY_API_KEY: $PROXY_API_KEY"
    echo "  VLLM_API_KEY: $VLLM_API_KEY"
    echo "  GRAFANA_PASSWORD: $GRAFANA_PASSWORD"
    echo "  PROMETHEUS_PASSWORD: $PROMETHEUS_PASSWORD"
    echo "  DYNAMO_API_KEY: $DYNAMO_API_KEY"
    echo "  LANGGRAPH_API_KEY: $LANGGRAPH_API_KEY"
    echo ""
    echo -e "${YELLOW}Domain & Admin Email:${NC}"
    echo "  DOMAIN: $DOMAIN_DISPLAY"
    echo "  ADMIN_EMAIL: $ADMIN_EMAIL_DISPLAY"
    echo ""
    echo -e "${YELLOW}WireGuard keys:${NC}"
    echo "  Private key: $WIREGUARD_PRIVATE_KEY"
    echo "  Public key: $WIREGUARD_PUBLIC_KEY"
    echo ""
    echo -e "${RED}Save these credentials securely. They will not be shown again.${NC}"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 1
log_success "Phase 1 completed – .env generated"