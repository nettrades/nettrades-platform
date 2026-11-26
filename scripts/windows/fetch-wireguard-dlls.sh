#!/bin/bash
# =============================================================================
# FILE: scripts/windows/fetch-wireguard-dlls.sh
# PURPOSE:
#   Ensures the WireGuard DLLs (tunnel.dll and wireguard.dll) are present.
#   If they are not, it calls build-wireguard-dlls.sh to build them from source.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR/../../nettrades-netsvc"

# Check if all required DLLs are already present for all architectures
all_present=true
for arch in amd64 x86 arm64; do
    if [[ ! -f "$SERVICE_DIR/$arch/tunnel.dll" ]] || [[ ! -f "$SERVICE_DIR/$arch/wireguard.dll" ]]; then
        all_present=false
        break
    fi
done

if [[ "$all_present" == "true" ]]; then
    echo "✅ All WireGuard DLLs are already present. Skipping build."
    exit 0
fi

echo "--- WireGuard DLLs are missing. Starting build process..."
bash "$SCRIPT_DIR/build-wireguard-dlls.sh"