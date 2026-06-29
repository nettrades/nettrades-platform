#!/bin/bash
# =============================================================================
# FILE: deploy/docker/install-nettrades.sh
# =============================================================================
# PURPOSE:
#   Interactive installation wizard for the NETTRADES platform.
#   Auto-detects hardware, asks for confirmation, generates secure passwords,
#   and calls the idempotent deploy script.
#   Interactive installer that also generates .env.
# USAGE:
#   sudo ./install-nettrades.sh
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source detection library
# -----------------------------------------------------------------------------
source /usr/local/bin/nettrades-ai-detect 2>/dev/null || true

# ---- Default values ----
DEFAULT_DOMAIN="nettrades.ai"
DEFAULT_EMAIL="admin@${DEFAULT_DOMAIN}"
DEFAULT_IP=$(detect_public_ip 2>/dev/null || echo "127.0.0.1")
DEFAULT_CORES=$(detect_cpu_cores 2>/dev/null || echo "2")
DEFAULT_RAM=$(detect_total_ram_gb 2>/dev/null || echo "4")

if detect_gpu 2>/dev/null; then
    DEFAULT_ENGINE="GPU (vLLM)"
else
    DEFAULT_ENGINE="CPU (llama.cpp)"
fi

echo "=== NETTRADES.AI Installation Wizard ==="
echo ""
echo "Detected system parameters:"
echo "  Domain name:    ${DEFAULT_DOMAIN}"
echo "  Admin email:    ${DEFAULT_EMAIL}"
echo "  Public IP:      ${DEFAULT_IP}"
echo "  CPU cores:      ${DEFAULT_CORES}"
echo "  Total RAM (GB): ${DEFAULT_RAM}"
echo "  Inference:      ${DEFAULT_ENGINE}"
echo ""

read -rp "Use these values? (Y/n): " confirm

if [[ "$confirm" =~ ^[Nn]$ ]]; then
    read -rp "Domain name: " DOMAIN
    read -rp "Admin email: " ADMIN_EMAIL
    read -rp "Public IP: " IP_ADDRESS
    read -rp "CPU cores for inference: " INFERENCE_CORES
    DOMAIN=${DOMAIN:-$DEFAULT_DOMAIN}
    ADMIN_EMAIL=${ADMIN_EMAIL:-$DEFAULT_EMAIL}
    IP_ADDRESS=${IP_ADDRESS:-$DEFAULT_IP}
    INFERENCE_CORES=${INFERENCE_CORES:-$DEFAULT_CORES}
else
    DOMAIN=$DEFAULT_DOMAIN
    ADMIN_EMAIL=$DEFAULT_EMAIL
    IP_ADDRESS=$DEFAULT_IP
    INFERENCE_CORES=$DEFAULT_CORES
fi

# -----------------------------------------------------------------------------
# Generate all secrets (NEVER printed to console)
# -----------------------------------------------------------------------------
POSTGRES_PASSWORD=$(openssl rand -base64 24)
ADMIN_PASSWORD=$(openssl rand -base64 24)
FORGEJO_DB_PASSWORD=$(openssl rand -base64 24)
FORGEJO_SECRET_KEY=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -base64 32)
GRAFANA_PASSWORD=$(openssl rand -base64 12)
LLAMA_API_KEY="dummy"
LANGGRAPH_API_KEY=$(openssl rand -base64 32)
ODOO_API_KEY=$(openssl rand -base64 24)

# ---- NEW: Generate PROXY_API_KEY (shared secret between langgraph and odoo-proxy) ----
PROXY_API_KEY=$(openssl rand -base64 32)

GPUSTACK_JWT_SECRET=$(openssl rand -base64 32)

# ---- WireGuard keypair for the controller ----
wg genkey > /tmp/wg_priv
WIREGUARD_PRIVATE_KEY=$(cat /tmp/wg_priv)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey)
rm -f /tmp/wg_priv

# -----------------------------------------------------------------------------
# Write the .env file
# -----------------------------------------------------------------------------
cat > .env << EOF
DOMAIN=${DOMAIN}
ADMIN_EMAIL=${ADMIN_EMAIL}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
FORGEJO_DB_PASSWORD=${FORGEJO_DB_PASSWORD}
FORGEJO_SECRET_KEY=${FORGEJO_SECRET_KEY}
JWT_SECRET=${JWT_SECRET}
GRAFANA_PASSWORD=${GRAFANA_PASSWORD}
LLAMA_API_KEY=${LLAMA_API_KEY}
LANGGRAPH_API_KEY=${LANGGRAPH_API_KEY}
ODOO_API_KEY=${ODOO_API_KEY}

# ---- NEW: Odoo Proxy shared secret ----
PROXY_API_KEY=${PROXY_API_KEY}
ODOO_PROXY_URL=http://odoo-proxy:3000
USE_ODOO_PROXY=true

GPUSTACK_JWT_SECRET=${GPUSTACK_JWT_SECRET}
WIREGUARD_PRIVATE_KEY=${WIREGUARD_PRIVATE_KEY}
WIREGUARD_PUBLIC_KEY=${WIREGUARD_PUBLIC_KEY}
EOF

chmod 600 .env

# -----------------------------------------------------------------------------
# Execute the main deploy script
# -----------------------------------------------------------------------------
export DOMAIN ADMIN_EMAIL IP_ADDRESS INFERENCE_CORES
./deploy-single.sh --auto