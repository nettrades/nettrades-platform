#!/bin/bash
# =============================================================================
# NETTRADES.AI – Company GPUStack Server Installer
# =============================================================================
# Deploys a GPUStack server on the company's internal Kubernetes namespace
# and generates WireGuard mesh configuration for GPU worker nodes.
# =============================================================================
set -euo pipefail
trap 'echo "ERROR: Company installer failed at line $LINENO." >&2' ERR

echo "=== NETTRADES AI – Company GPUStack Server Installer ==="
read -rp "WireGuard mesh subnet (e.g. 10.100.1.0/24): " MESH_SUBNET
if [ -z "$MESH_SUBNET" ]; then
    echo "ERROR: Mesh subnet is required." >&2
    exit 1
fi
read -rp "Controller WireGuard IP (e.g. 10.100.1.1): " CONTROLLER_IP
if [ -z "$CONTROLLER_IP" ]; then
    echo "ERROR: Controller IP is required." >&2
    exit 1
fi

echo "=== Deploying GPUStack server ==="
kubectl apply -f distributed-gpu/controller/gpustack-company-server.yaml

echo "=== Generating WireGuard mesh config ==="
if [ ! -f /etc/wireguard/privatekey ]; then
    wg genkey | tee /etc/wireguard/privatekey | wg pubkey > /etc/wireguard/publickey
fi
echo "Controller public key: $(cat /etc/wireguard/publickey)"
echo "Mesh subnet: ${MESH_SUBNET}"
echo "=== Done. Add GPU nodes from the Odoo GPU Admin Panel. ==="