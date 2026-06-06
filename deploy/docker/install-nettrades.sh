#!/bin/bash
# =============================================================================
# NETTRADES.AI – Interactive Installation Wizard (Valkey edition)
# =============================================================================
# Auto-detects hardware, asks for confirmation, generates secure passwords,
# and calls the idempotent deploy script.
# =============================================================================
set -euo pipefail
source /usr/local/bin/nettrades-ai-detect

DEFAULT_DOMAIN="nettrades.ai"
DEFAULT_EMAIL="admin@${DEFAULT_DOMAIN}"
DEFAULT_IP=$(detect_public_ip)
DEFAULT_CORES=$(detect_cpu_cores)
DEFAULT_RAM=$(detect_total_ram_gb)

if detect_gpu; then DEFAULT_ENGINE="GPU (vLLM)"; else DEFAULT_ENGINE="CPU (llama.cpp)"; fi

echo "=== NETTRADES.AI Installation Wizard ==="
echo "Detected system parameters:"
echo "  Domain name:      ${DEFAULT_DOMAIN}"
echo "  Admin email:      ${DEFAULT_EMAIL}"
echo "  Public IP:        ${DEFAULT_IP}"
echo "  CPU cores:        ${DEFAULT_CORES}"
echo "  Total RAM (GB):   ${DEFAULT_RAM}"
echo "  Inference engine: ${DEFAULT_ENGINE}"
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

# ---- Generate all secrets (NEVER printed to console) ----
POSTGRES_PASSWORD=$(openssl rand -base64 24)
ADMIN_PASSWORD=$(openssl rand -base64 24)
FORGEJO_DB_PASSWORD=$(openssl rand -base64 24)
FORGEJO_SECRET_KEY=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -base64 32)
GRAFANA_PASSWORD=$(openssl rand -base64 12)
LLAMA_API_KEY="dummy"
LANGGRAPH_API_KEY=$(openssl rand -base64 32)
ODOO_API_KEY=$(openssl rand -base64 24)
MCP_API_KEY=$(openssl rand -base64 32)
GPUSTACK_JWT_SECRET=$(openssl rand -base64 32)

# WireGuard keypair for the controller
wg genkey > /tmp/wg_priv
WIREGUARD_PRIVATE_KEY=$(cat /tmp/wg_priv)
WIREGUARD_PUBLIC_KEY=$(echo "$WIREGUARD_PRIVATE_KEY" | wg pubkey)
rm -f /tmp/wg_priv

# ---- Write the .env file ----
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
MCP_API_KEY=${MCP_API_KEY}
GPUSTACK_JWT_SECRET=${GPUSTACK_JWT_SECRET}
WIREGUARD_PRIVATE_KEY=${WIREGUARD_PRIVATE_KEY}
WIREGUARD_PUBLIC_KEY=${WIREGUARD_PUBLIC_KEY}
EOF
chmod 600 .env

# ---- Execute the main deploy script ----
export DOMAIN ADMIN_EMAIL IP_ADDRESS INFERENCE_CORES
./deploy-single.sh --auto