#!/bin/bash
# =============================================================================
# FILE: scripts/phase-env.sh
# =============================================================================
# PURPOSE:
#   Phase 1: Environment & Secrets Generation.
#   This phase generates all required secrets (passwords, API keys, WireGuard keys)
#   and creates the .env file for the deployment.
#
#   MODIFIED: Asks the user for the PostgreSQL password instead of generating a
#   random one. This ensures the same password is used everywhere.
#
# USAGE:
#   ./phase-env.sh [--auto] [--force]
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
ODOO_CONF="$PROJECT_ROOT/deploy/docker/config/odoo.conf"

# -----------------------------------------------------------------------------
# Generate .env
# -----------------------------------------------------------------------------
log_step "Generating .env file..."

if [[ -f "$ENV_FILE" ]] && [[ "$FORCE" != true ]]; then
    log_warning ".env already exists. Use --force to regenerate."
    exit 0
fi

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
# FIX: Ask the user for the PostgreSQL password instead of generating random
# =============================================================================
if [[ "$AUTO" != true ]]; then
    echo ""
    echo -e "${YELLOW}Enter a PostgreSQL password for the 'odoo' user:${NC}"
    echo -e "${YELLOW}(This password will be used for PostgreSQL, Odoo, and all services)${NC}"
    read -s -p "Password: " POSTGRES_PASSWORD
    echo ""
    read -s -p "Confirm password: " POSTGRES_PASSWORD_CONFIRM
    echo ""
    if [[ "$POSTGRES_PASSWORD" != "$POSTGRES_PASSWORD_CONFIRM" ]]; then
        log_error "Passwords do not match. Please re-run phase-env.sh"
        exit 1
    fi
    if [[ -z "$POSTGRES_PASSWORD" ]]; then
        log_error "Password cannot be empty"
        exit 1
    fi
else
    # Auto mode: generate a random password (for CI/CD)
    POSTGRES_PASSWORD=$(generate_password)
    log_info "Auto mode: generated random password"
fi

# Generate other secrets (no user interaction needed)
ODOO_ADMIN_PASSWORD=$(generate_password)
SECRET_KEY=$(generate_secret)
JWT_SECRET=$(generate_secret)
VLLM_API_KEY=$(generate_secret)
PROXY_API_KEY=$(generate_secret)
WIREGUARD_PRIVATE_KEY=$(generate_wireguard_key)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey 2>/dev/null || echo "manual")

# Update .env file with generated secrets
# Using '|' as delimiter to avoid conflict with '/' in secrets

# PostgreSQL password
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" "$ENV_FILE"

# Odoo admin password
sed -i "s|^ODOO_ADMIN_PASSWORD=.*|ODOO_ADMIN_PASSWORD=$ODOO_ADMIN_PASSWORD|" "$ENV_FILE"

# Secret keys
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" "$ENV_FILE"
sed -i "s|^VLLM_API_KEY=.*|VLLM_API_KEY=$VLLM_API_KEY|" "$ENV_FILE"
sed -i "s|^PROXY_API_KEY=.*|PROXY_API_KEY=$PROXY_API_KEY|" "$ENV_FILE"

# WireGuard keys
sed -i "s|^WIREGUARD_PRIVATE_KEY=.*|WIREGUARD_PRIVATE_KEY=$WIREGUARD_PRIVATE_KEY|" "$ENV_FILE"
sed -i "s|^WIREGUARD_PUBLIC_KEY=.*|WIREGUARD_PUBLIC_KEY=$WIREGUARD_PUBLIC_KEY|" "$ENV_FILE"

# Generate random domain if not set
if ! grep -q "^DOMAIN=.*" "$ENV_FILE" || grep -q "^DOMAIN=$" "$ENV_FILE"; then
    RANDOM_DOMAIN="nettrades-$(openssl rand -hex 4).local"
    sed -i "s|^DOMAIN=.*|DOMAIN=$RANDOM_DOMAIN|" "$ENV_FILE"
    log_warning "DOMAIN not set – using $RANDOM_DOMAIN"
fi

chmod 600 "$ENV_FILE"
log_success ".env generated with secure secrets"

# =============================================================================
# REMOVED THIS: Hardcode the same password in odoo.conf
# The Odoo container does not use the odoo.config file (the volume mount is commented out in docker-compose.yaml).
#
# Odoo gets its database settings from the environment variables (HOST, PORT, USER, PASSWORD), which are correctly passed from your .env file.
# REMOVED THE ODOO.CONFIG FILE TOO
# =============================================================================
#log_step "Hardcoding PostgreSQL password in odoo.conf..."
#
# Ensure config directory exists
#mkdir -p "$(dirname "$ODOO_CONF")"
#
# Update or add db_password in odoo.conf (handles spaces)
#if grep -q "^db_password\s*=" "$ODOO_CONF"; then
#    sed -i "s|^db_password\s*=.*|db_password=$POSTGRES_PASSWORD|" "$ODOO_CONF"
#else
#    echo "db_password=$POSTGRES_PASSWORD" >> "$ODOO_CONF"
#fi
#
#log_success "Password hardcoded in odoo.conf"
#
# -----------------------------------------------------------------------------
# Display important information
# -----------------------------------------------------------------------------
if [[ "$AUTO" != true ]]; then
    echo ""
    echo -e "${YELLOW}Important credentials (save these):${NC}"
    echo "  POSTGRES_PASSWORD: $POSTGRES_PASSWORD"
    echo "  ODOO_ADMIN_PASSWORD: $ODOO_ADMIN_PASSWORD"
    echo "  PROXY_API_KEY: $PROXY_API_KEY"
    echo "  VLLM_API_KEY: $VLLM_API_KEY"
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