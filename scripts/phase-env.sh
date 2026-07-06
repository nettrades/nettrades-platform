#!/bin/bash
# =============================================================================
# FILE: scripts/phase-env.sh
# =============================================================================
# PURPOSE:
#   Phase 1: Environment & Secrets Generation.
#   This phase generates all required secrets (passwords, API keys, WireGuard keys)
#   and creates the .env file for the deployment.
#
#   SAFETY FEATURES:
#   - If .env already exists, the script will NOT modify it unless --force is used.
#   - With --force, the user is prompted for explicit confirmation and a new password.
#   - With --auto and --force, the script ABORTS to prevent automated overwrites.
#   - In production, additional confirmation is required (see confirm_force_production).
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
# Production Safety Check (already defined in lib/common.sh)
# This prompts for explicit confirmation if ENVIRONMENT=production and --force is used.
# -----------------------------------------------------------------------------
confirm_force_production "1"

# -----------------------------------------------------------------------------
# Phase marker
# If phase already completed and --force not used, exit safely.
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
        log_info "To regenerate all secrets (which will break existing services), use --force."
        log_info "If you only need to update the password, edit the .env file manually."
        exit 0
    fi

    # --force is used – we need to confirm regeneration
    log_warning "You have requested to regenerate ALL secrets in .env."

    # If --auto is also used, we abort (cannot get interactive confirmation)
    if [[ "$AUTO" == true ]]; then
        log_error "Auto mode with --force and existing .env is not allowed for safety."
        log_error "If you really want to regenerate secrets, remove --auto and run interactively."
        log_error "Alternatively, delete the existing .env file and run again."
        exit 1
    fi

    # Interactive confirmation (--force, not --auto)
    echo ""
    echo -e "${RED}WARNING: You are about to OVERWRITE all existing secrets in .env.${NC}"
    echo -e "${RED}This will break all running services (Odoo, LangGraph, GPUStack, etc.).${NC}"
    echo -e "${YELLOW}Do you have a backup of your current .env file? (y/N)${NC}"
    read -p "> " backup_confirm
    if [[ ! "$backup_confirm" =~ ^[Yy]$ ]]; then
        log_error "Aborting. Please back up your current .env and try again."
        exit 1
    fi

    echo ""
    echo -e "${YELLOW}Proceed with regeneration? This action CANNOT be undone. (type 'YES' to confirm)${NC}"
    read -p "> " final_confirm
    if [[ "$final_confirm" != "YES" ]]; then
        log_info "Aborted."
        exit 0
    fi

    # If we get here, user confirmed – we will overwrite .env
    log_info "User confirmed – proceeding with regeneration."
else
    # .env does not exist – we will create it from template
    log_info ".env not found – will create a new one."
fi

# -----------------------------------------------------------------------------
# Generate .env (either from template or fresh)
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
        log_error "Passwords do not match. Please re-run phase-env.sh"
        exit 1
    fi
    if [[ -z "$POSTGRES_PASSWORD" ]]; then
        log_error "Password cannot be empty"
        exit 1
    fi
elif [[ "$AUTO" == true ]]; then
    # Auto mode: generate a random password (only for fresh installs)
    POSTGRES_PASSWORD=$(generate_password)
    log_info "Auto mode: generated random password"
else
    # Interactive mode, .env does not exist – prompt for password
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
fi

# -----------------------------------------------------------------------------
# Generate other secrets (only after we have a valid password)
# -----------------------------------------------------------------------------
ODOO_ADMIN_PASSWORD=$(generate_password)
SECRET_KEY=$(generate_secret)
JWT_SECRET=$(generate_secret)
VLLM_API_KEY=$(generate_secret)
PROXY_API_KEY=$(generate_secret)
WIREGUARD_PRIVATE_KEY=$(generate_wireguard_key)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey 2>/dev/null || echo "manual")

# -----------------------------------------------------------------------------
# Write secrets to .env
# -----------------------------------------------------------------------------
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

# Set secure permissions
chmod 600 "$ENV_FILE"
log_success ".env generated with secure secrets"

# -----------------------------------------------------------------------------
# REMOVED: Writing to odoo.conf
# The local odoo.conf is no longer used (volume mount commented out in docker-compose.yaml).
# Odoo reads database settings from environment variables (HOST, PORT, USER, PASSWORD).
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Display important information (only in interactive mode)
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