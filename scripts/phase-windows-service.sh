#!/bin/bash
# =============================================================================
# phase-windows-service.sh
# PURPOSE: Register the NETTRADES Networking Service on Windows hosts.
# Called automatically at the end of the Hub deployment when running on WSL.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Only run on WSL.
if ! grep -qi microsoft /proc/version 2>/dev/null; then
    echo "[windows-service] Not running on WSL. Skipping."
    exit 0
fi

echo "[windows-service] Registering NETTRADES Networking Service..."

# Copy the service binary and supporting scripts to a Windows-accessible path.
WIN_SERVICE_DIR="/mnt/c/ProgramData/NETTRADES/service"
mkdir -p "$WIN_SERVICE_DIR"
cp "$PROJECT_ROOT/installer/service/nettrades-netsvc.exe" "$WIN_SERVICE_DIR/"
cp "$PROJECT_ROOT/installer/service/install-netsvc.ps1" "$WIN_SERVICE_DIR/"

powershell.exe -ExecutionPolicy Bypass -File "$WIN_SERVICE_DIR/install-netsvc.ps1"

# Copy the WireGuard DLLs. The architecture must match the Windows host.
# On WSL2, the architecture is determined by the Windows host, not WSL.
# wslpath and uname give the WSL kernel arch, which matches the host on
# x86_64 and arm64.
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  WG_ARCH="amd64" ;;
    aarch64) WG_ARCH="arm64" ;;
    *)       WG_ARCH="amd64" ;;
esac

WG_SRC_DIR="$PROJECT_ROOT/nettrades-netsvc/$WG_ARCH"
if [[ -d "$WG_SRC_DIR" ]]; then
    cp "$WG_SRC_DIR/tunnel.dll" "$WIN_SERVICE_DIR/" 2>/dev/null || \
        echo "[windows-service] WARNING: tunnel.dll not found for $WG_ARCH"
    cp "$WG_SRC_DIR/wireguard.dll" "$WIN_SERVICE_DIR/" 2>/dev/null || \
        echo "[windows-service] WARNING: wireguard.dll not found for $WG_ARCH"
    echo "[windows-service] Copied WireGuard DLLs for $WG_ARCH"
else
    echo "[windows-service] WARNING: $WG_SRC_DIR not found. Run scripts/windows/fetch-wireguard-dlls.sh first."
fi