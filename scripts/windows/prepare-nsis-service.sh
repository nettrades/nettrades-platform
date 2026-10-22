#!/bin/bash
# =============================================================================
# FILE: scripts/windows/prepare-nsis-service.sh
# PURPOSE:
#   Build the NETTRADES Networking Service for Windows, fetch the WireGuard
#   DLLs, and place all four files where NSIS expects them:
#
#       installer/service/nettrades-netsvc.exe
#       installer/service/tunnel.dll
#       installer/service/wireguard.dll
#
#   This script is called by the `prebuild:win` and `prebuild:portable`
#   npm hooks (see installer/package.json). It must run before
#   `electron-builder --win` so that the customInstall macro in
#   installer/build/installer.nsh can find its input files.
#
# WHY THIS IS NEEDED:
#   electron-builder's `files` array controls what goes into the app
#   bundle (asar). It does NOT control what NSIS's `File` directive
#   pulls at installer-compile time. NSIS resolves `File "service\..."`,
#   relative to the directory where makensis runs, which is
#   installer/. Without this script, makensis fails with:
#       File: "service\nettrades-netsvc.exe" -> no files found.
#
# USAGE:
#   ./scripts/windows/prepare-nsis-service.sh
#
# ENVIRONMENT:
#   Requires either:
#     - A Linux/Windows Go toolchain (for cross-compiling the .exe), OR
#     - A pre-built nettrades-netsvc.exe already present at
#       installer/service/nettrades-netsvc.exe.
#
# IDEMPOTENT:
#   Re-running is safe. Existing files are overwritten only if the
#   source is newer, unless --force is passed.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours
# -----------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_SRC="$PROJECT_ROOT/nettrades-netsvc"
SERVICE_DST="$PROJECT_ROOT/installer/service"
FETCH_SCRIPT="$SCRIPT_DIR/fetch-wireguard-dlls.sh"

FORCE=false
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=true ;;
        *) log_error "Unknown argument: $arg"; exit 1 ;;
    esac
done

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  NETTRADES — Prepare NSIS Service Directory"
echo "════════════════════════════════════════════════════════════════════"
echo ""
log_info "Project root:      $PROJECT_ROOT"
log_info "Service source:    $SERVICE_SRC"
log_info "Service target:    $SERVICE_DST"
log_info "WireGuard fetcher: $FETCH_SCRIPT"
echo ""

# -----------------------------------------------------------------------------
# Step 1 — Ensure the target directory exists
# -----------------------------------------------------------------------------
mkdir -p "$SERVICE_DST"
log_success "Ensured $SERVICE_DST exists"

# -----------------------------------------------------------------------------
# Step 2 — Fetch WireGuard DLLs if missing
# -----------------------------------------------------------------------------
# fetch-wireguard-dlls.sh writes DLLs into nettrades-netsvc/{amd64,x86,arm64}/.
# We need the amd64 variants for the current build (all demo spokes are
# x86_64). If we ever target arm64 Windows, this loop needs extending.
# -----------------------------------------------------------------------------
AMD64_DLL_DIR="$SERVICE_SRC/amd64"

if [[ ! -f "$AMD64_DLL_DIR/wireguard.dll" || ! -f "$AMD64_DLL_DIR/tunnel.dll" ]]; then
    if [[ -x "$FETCH_SCRIPT" ]]; then
        log_info "WireGuard DLLs missing — running $FETCH_SCRIPT"
        bash "$FETCH_SCRIPT" || {
            log_error "fetch-wireguard-dlls.sh failed"
            exit 1
        }
    else
        log_error "WireGuard DLLs missing and $FETCH_SCRIPT is not executable"
        log_info "Fix: chmod +x $FETCH_SCRIPT && rerun"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Step 3 — Verify DLLs are present
# -----------------------------------------------------------------------------
for dll in wireguard.dll tunnel.dll; do
    if [[ ! -f "$AMD64_DLL_DIR/$dll" ]]; then
        log_error "Missing $AMD64_DLL_DIR/$dll"
        exit 1
    fi
done
log_success "WireGuard DLLs present in $AMD64_DLL_DIR"

# -----------------------------------------------------------------------------
# Step 4 — Build the Go service for Windows amd64
# -----------------------------------------------------------------------------
# If a pre-built exe already exists at the target and the user did not
# pass --force, we skip the Go build. This lets a developer who does not
# have Go installed still produce the installer, as long as they have a
# previously-built exe.
# -----------------------------------------------------------------------------
SERVICE_EXE="$SERVICE_DST/nettrades-netsvc.exe"

need_build=true
if [[ -f "$SERVICE_EXE" && "$FORCE" != "true" ]]; then
    # If the exe is newer than every .go source file, skip the rebuild.
    newest_go=$(find "$SERVICE_SRC" -maxdepth 1 -name '*.go' -printf '%T@\n' 2>/dev/null | sort -n | tail -1 || echo 0)
    exe_mtime=$(stat -c '%Y' "$SERVICE_EXE" 2>/dev/null || echo 0)
    if [[ -n "$newest_go" && "$newest_go" != "0" ]] && \
       [[ "$(printf '%.0f' "$newest_go")" -le "$exe_mtime" ]]; then
        need_build=false
        log_success "Service exe is up to date — skipping Go build"
    fi
fi

if [[ "$need_build" == "true" ]]; then
    if ! command -v go >/dev/null 2>&1; then
        if [[ -f "$SERVICE_EXE" ]]; then
            log_warning "Go toolchain not installed, but a pre-built exe exists — using it"
            log_warning "To rebuild, install Go: https://go.dev/dl/"
        else
            log_error "Go toolchain not installed and no pre-built exe found"
            log_info "Install Go in WSL: sudo apt install golang-go"
            log_info "  or download from: https://go.dev/dl/"
            exit 1
        fi
    else
        log_info "Building Go service for Windows amd64…"
        (
            cd "$SERVICE_SRC"
            # Check for go.mod — if absent, this is not a Go module and
            # we cannot build it.
            if [[ ! -f go.mod ]]; then
                log_error "No go.mod in $SERVICE_SRC — cannot build the service"
                log_info "The nettrades-netsvc directory must be a Go module."
                exit 1
            fi
            GOTOOLCHAIN=local GOOS=windows GOARCH=amd64 go build -ldflags "-s -w" -o "$SERVICE_EXE" . || {
	        log_error "go build failed"
                exit 1
            }
        )
        log_success "Built $SERVICE_EXE"
    fi
fi

# -----------------------------------------------------------------------------
# Step 5 — Copy the amd64 DLLs into the target directory
# -----------------------------------------------------------------------------
cp "$AMD64_DLL_DIR/wireguard.dll" "$SERVICE_DST/wireguard.dll"
cp "$AMD64_DLL_DIR/tunnel.dll"    "$SERVICE_DST/tunnel.dll"
log_success "Copied wireguard.dll and tunnel.dll into $SERVICE_DST"

# -----------------------------------------------------------------------------
# Step 6 — Verify the final layout
# -----------------------------------------------------------------------------
echo ""
log_info "Final service directory contents:"
ls -la "$SERVICE_DST" | sed 's/^/    /'
echo ""

all_ok=true
for f in nettrades-netsvc.exe wireguard.dll tunnel.dll; do
    if [[ ! -f "$SERVICE_DST/$f" ]]; then
        log_error "MISSING: $SERVICE_DST/$f"
        all_ok=false
    fi
done

if [[ "$all_ok" == "true" ]]; then
    log_success "installer/service/ is ready for electron-builder"
    exit 0
else
    log_error "installer/service/ is incomplete"
    exit 1
fi