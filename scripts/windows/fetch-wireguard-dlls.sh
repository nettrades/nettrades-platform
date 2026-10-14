#!/bin/bash
# =============================================================================
# FILE: scripts/windows/fetch-wireguard-dlls.sh
# PURPOSE:
#   Downloads the WireGuard NT SDK and the WireGuard Windows MSI, extracts
#   the architecture-specific wireguard.dll and tunnel.dll, and places them
#   in nettrades-netsvc/{x86,amd64,arm64}/.
#
#   These DLLs are required for the NETTRADES Networking Service's WireGuard
#   tunnel management. They are NOT committed to the repository — they are
#   downloaded at build time and bundled by the NSIS installer.
#
# WHAT IT DOWNLOADS:
#   1. wireguard-nt-1.1.zip
#      https://download.wireguard.com/wireguard-nt/wireguard-nt-1.1.zip
#      Contains bin/{x86,amd64,arm64}/wireguard.dll
#
#   2. wireguard-{amd64,x86,arm64}-1.1.msi
#      https://download.wireguard.com/windows-client/wireguard-amd64-1.1.msi
#      https://download.wireguard.com/windows-client/wireguard-x86-1.1.msi
#      https://download.wireguard.com/windows-client/wireguard-arm64-1.1.msi
#      Contains {x86,amd64,arm64}/tunnel.dll
#
# PREREQUISITES:
#   - curl or wget
#   - unzip (for wireguard-nt-1.1.zip)
#   - msiextract (from msitools) OR 7z (from p7zip-full)
#     On Ubuntu/WSL: sudo apt install msitools unzip
#
# USAGE:
#   ./scripts/windows/fetch-wireguard-dlls.sh
#
# OUTPUT:
#   nettrades-netsvc/x86/wireguard.dll
#   nettrades-netsvc/x86/tunnel.dll
#   nettrades-netsvc/amd64/wireguard.dll
#   nettrades-netsvc/amd64/tunnel.dll
#   nettrades-netsvc/arm64/wireguard.dll
#   nettrades-netsvc/arm64/tunnel.dll
#
# IDEMPOTENT:
#   Re-running is safe. Existing files are overwritten.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_DIR="$PROJECT_ROOT/nettrades-netsvc"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/nettrades/wireguard-dlls"

# -----------------------------------------------------------------------------
# Version constants
# -----------------------------------------------------------------------------
WIREGUARD_NT_VERSION="1.1"
WIREGUARD_WINDOWS_VERSION="1.1"

WIREGUARD_NT_URL="https://download.wireguard.com/wireguard-nt/wireguard-nt-${WIREGUARD_NT_VERSION}.zip"
WIREGUARD_MSI_BASE="https://download.wireguard.com/windows-client"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
log_info()    { echo -e "\033[0;34m[INFO]\033[0m    $*"; }
log_success() { echo -e "\033[0;32m[OK]\033[0m      $*"; }
log_warning() { echo -e "\033[1;33m[WARN]\033[0m    $*"; }
log_error()   { echo -e "\033[0;31m[ERROR]\033[0m   $*"; }

# -----------------------------------------------------------------------------
# Dependency check
# -----------------------------------------------------------------------------
check_dependencies() {
    local missing=()

    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || missing+=("curl or wget")
    command -v unzip >/dev/null 2>&1 || missing+=("unzip")

    # We need either msiextract (msitools) or 7z (p7zip-full) to extract the MSI.
    if ! command -v msiextract >/dev/null 2>&1 && ! command -v 7z >/dev/null 2>&1; then
        missing+=("msitools or p7zip-full (for MSI extraction)")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools:"
        for tool in "${missing[@]}"; do
            echo "  - $tool"
        done
        echo ""
        log_info "Install with:"
        echo "  sudo apt install -y unzip msitools p7zip-full"
        exit 1
    fi
}

# -----------------------------------------------------------------------------
# Download helper (curl or wget)
# -----------------------------------------------------------------------------
download() {
    local url="$1"
    local dest="$2"

    if [[ -f "$dest" ]]; then
        log_info "Using cached download: $(basename "$dest")"
        return 0
    fi

    log_info "Downloading $(basename "$dest")..."

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$dest" "$url"
    else
        log_error "Neither curl nor wget found."
        return 1
    fi

    if [[ ! -s "$dest" ]]; then
        log_error "Download failed or produced an empty file: $url"
        rm -f "$dest"
        return 1
    fi

    log_success "Downloaded $(basename "$dest")"
}

# -----------------------------------------------------------------------------
# Extract wireguard.dll from the NT SDK zip
# -----------------------------------------------------------------------------
extract_wireguard_dlls() {
    local zip_path="$1"
    local tmp_dir="$2"

    log_info "Extracting wireguard.dll from wireguard-nt SDK..."

    if ! unzip -q -o "$zip_path" -d "$tmp_dir"; then
        log_error "Failed to unzip $zip_path"
        return 1
    fi

    # The zip structure is:
    #   wireguard-nt/bin/amd64/wireguard.dll
    #   wireguard-nt/bin/x86/wireguard.dll
    #   wireguard-nt/bin/arm64/wireguard.dll
    local base="$tmp_dir/wireguard-nt/bin"

    for arch in amd64 x86 arm64; do
        local src="$base/$arch/wireguard.dll"
        local dst="$SERVICE_DIR/$arch/wireguard.dll"

        mkdir -p "$SERVICE_DIR/$arch"

        if [[ -f "$src" ]]; then
            cp "$src" "$dst"
            log_success "  $arch/wireguard.dll"
        else
            log_error "  $arch/wireguard.dll not found in SDK zip"
            return 1
        fi
    done
}

# -----------------------------------------------------------------------------
# Extract tunnel.dll from the WireGuard Windows MSI
# -----------------------------------------------------------------------------
extract_tunnel_dlls() {
    local tmp_dir="$1"

    log_info "Extracting tunnel.dll from WireGuard Windows MSIs..."

    for arch in amd64 x86 arm64; do
        local msi_name="wireguard-${arch}-${WIREGUARD_WINDOWS_VERSION}.msi"
        local msi_url="${WIREGUARD_MSI_BASE}/${msi_name}"
        local msi_path="$CACHE_DIR/$msi_name"
        local extract_dir="$tmp_dir/msi-${arch}"

        mkdir -p "$extract_dir"

        if ! download "$msi_url" "$msi_path"; then
            log_error "  Failed to download $msi_name"
            return 1
        fi

        # Extract the MSI.
        if command -v msiextract >/dev/null 2>&1; then
            msiextract -C "$extract_dir" "$msi_path" >/dev/null 2>&1 || true
        elif command -v 7z >/dev/null 2>&1; then
            7z x -o"$extract_dir" -y "$msi_path" >/dev/null 2>&1 || true
        fi

        # The tunnel.dll is at {arch}/tunnel.dll inside the MSI.
        local src="$extract_dir/$arch/tunnel.dll"
        local dst="$SERVICE_DIR/$arch/tunnel.dll"

        if [[ -f "$src" ]]; then
            cp "$src" "$dst"
            log_success "  $arch/tunnel.dll"
        else
            # Fallback: search for tunnel.dll anywhere in the extracted tree.
            local found
            found=$(find "$extract_dir" -name "tunnel.dll" -type f 2>/dev/null | head -1)
            if [[ -n "$found" ]]; then
                cp "$found" "$dst"
                log_success "  $arch/tunnel.dll (found via search)"
            else
                log_error "  $arch/tunnel.dll not found in MSI"
                return 1
            fi
        fi
    done
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    echo ""
    echo "════════════════════════════════════════════════════════════════════"
    echo "  NETTRADES — Fetch WireGuard DLLs"
    echo "════════════════════════════════════════════════════════════════════"
    echo ""

    check_dependencies

    mkdir -p "$CACHE_DIR"

    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf $tmp_dir" EXIT

    # -------------------------------------------------------------------------
    # 1. Download and extract wireguard.dll from the NT SDK.
    # -------------------------------------------------------------------------
    local nt_zip="$CACHE_DIR/wireguard-nt-${WIREGUARD_NT_VERSION}.zip"

    if ! download "$WIREGUARD_NT_URL" "$nt_zip"; then
        log_error "Failed to download WireGuard NT SDK."
        exit 1
    fi

    if ! extract_wireguard_dlls "$nt_zip" "$tmp_dir"; then
        log_error "Failed to extract wireguard.dll."
        exit 1
    fi

    # -------------------------------------------------------------------------
    # 2. Download and extract tunnel.dll from the Windows MSIs.
    # -------------------------------------------------------------------------
    if ! extract_tunnel_dlls "$tmp_dir"; then
        log_error "Failed to extract tunnel.dll."
        exit 1
    fi

    # -------------------------------------------------------------------------
    # 3. Verify the output.
    # -------------------------------------------------------------------------
    echo ""
    log_info "Verifying output files..."

    local all_ok=true
    for arch in amd64 x86 arm64; do
        for dll in wireguard.dll tunnel.dll; do
            local path="$SERVICE_DIR/$arch/$dll"
            if [[ -f "$path" ]]; then
                local size
                size=$(stat -c%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null || echo 0)
                log_success "  $arch/$dll ($size bytes)"
            else
                log_error "  $arch/$dll MISSING"
                all_ok=false
            fi
        done
    done

    echo ""
    if [[ "$all_ok" == "true" ]]; then
        log_success "All WireGuard DLLs fetched successfully."
        echo ""
        echo "Next step: rebuild the NETTRADES Networking Service."
        echo "  cd $SERVICE_DIR && go build -o nettrades-netsvc.exe ."
    else
        log_error "Some DLLs are missing. Check the errors above."
        exit 1
    fi
}

main "$@"