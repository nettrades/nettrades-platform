#!/bin/bash
# =============================================================================
# FILE: scripts/phase-env.sh
# =============================================================================
# PURPOSE:
#   Phase 1: Environment & Secrets Generation.
#   This phase generates all required secrets and creates the .env file.
#
#   SAFETY FEATURES:
#   - If .env already exists, the script will NOT modify it unless --force is used.
#   - With --force and --regenerate-secrets, it will regenerate (with backup).
#   - With --auto and --force, it regenerates silently (for CI/CD).
#   - In production, additional confirmation is required.
#   - NEW: Automatically detects the server IP and prompts for domain/email.
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

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
export FORCE

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
# Handle PostgreSQL password safely
# =============================================================================

# Determine if we should ask for a password or generate one
if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" == true ]]; then
    # We are regenerating an existing .env after user confirmation – ask for a new password
    echo ""
    echo -e "${YELLOW}Enter a NEW PostgreSQL password for the 'odoo' user:${NC}"
    echo -e "${YELLOW}(This password will be used for PostgreSQL, Odoo, and all services)${NC}"
    read -s -p "Password: " POSTGRES_PASSWORD
    echo ""
    read -s -p "Confirm password: " POSTGRES_PASSWORD_CONFIRM
    echo ""
    if [[ "$POSTGRES_PASSWORD" != "$POSTGRES_PASSWORD_CONFIRM" ]]; then
        log_error "Passwords do not match."
        exit 1
    fi
    if [[ -z "$POSTGRES_PASSWORD" ]]; then
        log_error "Password cannot be empty"
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
    read -s -p "Password: " POSTGRES_PASSWORD
    echo ""
    read -s -p "Confirm password: " POSTGRES_PASSWORD_CONFIRM
    echo ""
    if [[ "$POSTGRES_PASSWORD" != "$POSTGRES_PASSWORD_CONFIRM" ]]; then
        log_error "Passwords do not match."
        exit 1
    fi
    if [[ -z "$POSTGRES_PASSWORD" ]]; then
        log_error "Password cannot be empty"
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

# NEW: Generate LangGraph API key (strong, alphanumeric)
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
safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"   # NEW
safe_sed_replace "$ENV_FILE" "LANGGRAPH_API_KEY" "$LANGGRAPH_API_KEY"
safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$PROXY_API_KEY"  # Ensure sync

# Ensure ODOO_API_KEY and PROXY_API_KEY are identical
safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$PROXY_API_KEY"

# -----------------------------------------------------------------------------
# NEW: Configure DOMAIN and ADMIN_EMAIL (auto-detect + interactive prompt)
# -----------------------------------------------------------------------------
configure_domain_email() {
    # Detect primary IP address
    detect_ip() {
        local ip=$(ip route get 1 2>/dev/null | awk '{print $NF;exit}')
        if [[ -z "$ip" || "$ip" == "0" ]]; then
            ip=$(hostname -I 2>/dev/null | awk '{print $1}')
        fi
        [[ -z "$ip" ]] && ip="localhost"
        echo "$ip"
    }

    # Read current values from .env
    CURRENT_DOMAIN=$(grep "^DOMAIN=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")
    CURRENT_EMAIL=$(grep "^ADMIN_EMAIL=" "$ENV_FILE" | cut -d'=' -f2- | tr -d "'")

    # If DOMAIN is still 'changeit' or 'nettrades.ai' (default) or empty, we set it.
    if [[ "$CURRENT_DOMAIN" == "changeit" || "$CURRENT_DOMAIN" == "nettrades.ai" || -z "$CURRENT_DOMAIN" ]]; then
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
# Set secure permissions
# -----------------------------------------------------------------------------
chmod 600 "$ENV_FILE"
log_success ".env generated with secure secrets"

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