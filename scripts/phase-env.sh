#!/bin/bash
# =============================================================================
# FILE: scripts/phase-env.sh
# =============================================================================
# PURPOSE:
#   Phase 1: Environment & Secrets Generation.
#   This phase generates all required secrets (passwords, API keys, WireGuard keys)
#   and creates the .env file for the deployment.
#
#   It is idempotent – if .env already exists, it will only update missing variables
#   (or regenerate everything with --force).
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
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/deploy/docker/.env.example"

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
# Generate secure secrets
# -----------------------------------------------------------------------------
log_step "Generating secure secrets..."

# Generate passwords and keys
POSTGRES_PASSWORD=$(generate_password)
ODOO_ADMIN_PASSWORD=$(generate_password)
SECRET_KEY=$(generate_secret)
JWT_SECRET=$(generate_secret)
VLLM_API_KEY=$(generate_secret)
PROXY_API_KEY=$(generate_secret)
WIREGUARD_PRIVATE_KEY=$(generate_wireguard_key)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey 2>/dev/null || echo "manual")

# Update .env file with generated secrets
# Using '|' as delimiter to avoid conflict with '/' in secrets
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASSWORD|" "$ENV_FILE"
sed -i "s|^POSTGRES_PASSWORD=.*|DB_PASSWORD=$POSTGRES_PASSWORD|" "$ENV_FILE"
sed -i "s|^ODOO_ADMIN_PASSWORD=.*|ODOO_ADMIN_PASSWORD=$ODOO_ADMIN_PASSWORD|" "$ENV_FILE"
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" "$ENV_FILE"
sed -i "s|^VLLM_API_KEY=.*|VLLM_API_KEY=$VLLM_API_KEY|" "$ENV_FILE"
sed -i "s|^PROXY_API_KEY=.*|PROXY_API_KEY=$PROXY_API_KEY|" "$ENV_FILE"
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

# -----------------------------------------------------------------------------
# Display important information
# -----------------------------------------------------------------------------
if [[ "$AUTO" != true ]]; then
    echo ""
    echo -e "${YELLOW}Important credentials (save these):${NC}"
    echo "  POSTGRES_PASSWORD: $POSTGRES_PASSWORD"
    echo "  DB_PASSWORD=${POSTGRES_PASSWORD}"
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
