#!/bin/bash
# =============================================================================
# NETTRADES.AI – Central GPU Controller Deployment
# =============================================================================
# Installs WireGuard, checks kernel version for CVE-2026-31579,
# deploys GPUStack server, builds and deploys the WireGuard peer manager,
# and applies gVisor + attestation manifests.
# =============================================================================
set -euo pipefail
trap 'echo "ERROR: Controller setup failed at line $LINENO." >&2' ERR

echo "=== 1. WireGuard kernel module ==="
if ! modprobe wireguard 2>/dev/null; then
    echo "WireGuard kernel module not present. Installing wireguard..."
    apt-get update && apt-get install -y wireguard wireguard-tools
fi

# ----------------------------------------------------------------
# WireGuard CVE-2026-31579 mitigation
# ----------------------------------------------------------------
echo "=== 2. WireGuard kernel version check ==="
REQUIRED_KERNEL_MAJOR=6
REQUIRED_KERNEL_MINOR=19
REQUIRED_KERNEL_PATCH=14

KERNEL_VERSION=$(uname -r | cut -d- -f1)
IFS='.' read -r k_major k_minor k_patch <<< "$KERNEL_VERSION"

if (( k_major < REQUIRED_KERNEL_MAJOR ||
      (k_major == REQUIRED_KERNEL_MAJOR && k_minor < REQUIRED_KERNEL_MINOR) ||
      (k_major == REQUIRED_KERNEL_MAJOR && k_minor == REQUIRED_KERNEL_MINOR && k_patch < REQUIRED_KERNEL_PATCH) )); then
    echo "WARNING: Kernel $KERNEL_VERSION is older than $REQUIRED_KERNEL_MAJOR.$REQUIRED_KERNEL_MINOR.$REQUIRED_KERNEL_PATCH"
    echo "         WireGuard CVE-2026-31579 may be present. Upgrade your kernel."
else
    echo "Kernel version $KERNEL_VERSION is OK (CVE-2026-31579 mitigated)."
fi

echo "=== 3. Generate WireGuard keypair ==="
if [ ! -f /etc/wireguard/privatekey ]; then
    wg genkey | tee /etc/wireguard/privatekey | wg pubkey > /etc/wireguard/publickey
    chmod 600 /etc/wireguard/privatekey
fi

echo "=== 4. Deploy GPUStack server ==="
kubectl apply -f distributed-gpu/controller/gpustack-server.yaml

echo "=== 5. Build and deploy WireGuard peer manager ==="
cd distributed-gpu/controller/wg-peer-manager
go mod tidy
docker build -t registry.registry.svc.cluster.local:5000/wg-peer-manager:latest .
docker push registry.registry.svc.cluster.local:5000/wg-peer-manager:latest
kubectl apply -f ../../../apps/gpustack/wg-peer-manager.yaml
cd ../../..

echo "=== 6. gVisor RuntimeClass ==="
kubectl apply -f distributed-gpu/controller/gvisor-runtime-class.yaml
echo "NOTE: Ensure runsc is installed on every GPU worker node before scheduling gVisor pods."

echo "=== 7. Attestation CronJob ==="
kubectl apply -f distributed-gpu/controller/attestation-cron.yaml

echo "=== Controller deployment complete ==="