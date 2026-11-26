#!/bin/bash
# =============================================================================
# FILE: scripts/windows/build-wireguard-dlls.sh
# =============================================================================
# PURPOSE:
#   Orchestrates the build of the WireGuard DLLs (tunnel.dll and wireguard.dll)
#   using a dedicated Docker build container. Called by fetch-wireguard-dlls.sh.
#
# UPDATES (2026-11):
#   - Builder image is now golang:1.26-bookworm (was debian:bookworm-slim
#     with golang-go, which is Go 1.19 — too old for wireguard-windows).
#   - Build commands are written to a file on the host and executed via
#     `bash /cache/build-inside.sh` inside the container. This eliminates
#     all quoting issues that arose from embedding the script in `bash -c`.
#   - `go mod tidy` runs in the module root before building. The go.mod
#     that wireguard-windows ships declares `go 1.26.0` (patch component
#     rejected by the toolchain) AND has a stale dependency graph. Both
#     are fixed before `go build`.
#   - Every step uses `set -eux` so failures surface immediately and each
#     command is echoed.
#   - After the container exits, all four output files are verified on
#     the host. If the build "succeeded" but produced nothing, we fail
#     loudly rather than let the next stage discover the problem.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_DIR="$PROJECT_ROOT/nettrades-netsvc"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/nettrades/wireguard-dlls"
BUILDER_IMAGE="nettrades/wireguard-dll-builder:latest"
BUILDER_DIR="$SCRIPT_DIR/builder"

MIN_GO_MAJOR=1
MIN_GO_MINOR=26

WIREGUARD_NT_VERSION="1.1"
WIREGUARD_NT_URL="https://download.wireguard.com/wireguard-nt/wireguard-nt-${WIREGUARD_NT_VERSION}.zip"

log_info()    { echo -e "\033[0;34m[INFO]\033[0m    $*"; }
log_success() { echo -e "\033[0;32m[OK]\033[0m      $*"; }
log_warning() { echo -e "\033[0;33m[WARN]\033[0m    $*"; }
log_error()   { echo -e "\033[0;31m[ERROR]\033[0m   $*"; }

REBUILD=false
for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD=true ;;
        *) log_error "Unknown argument: $arg"; exit 1 ;;
    esac
done

if [[ ! -f "$BUILDER_DIR/Dockerfile" ]]; then
    log_error "Builder Dockerfile missing: $BUILDER_DIR/Dockerfile"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Build (or rebuild) the builder image
# -----------------------------------------------------------------------------
if [[ "$REBUILD" == true ]] || ! docker image inspect "$BUILDER_IMAGE" &>/dev/null; then
    log_info "Building builder image from $BUILDER_DIR/Dockerfile..."
    if [[ "$REBUILD" == true ]]; then
        docker build --no-cache -t "$BUILDER_IMAGE" "$BUILDER_DIR"
    else
        docker build -t "$BUILDER_IMAGE" "$BUILDER_DIR"
    fi
fi

# -----------------------------------------------------------------------------
# 2. Verify the builder's Go version
# -----------------------------------------------------------------------------
BUILDER_GO_RAW=$(docker run --rm --entrypoint go "$BUILDER_IMAGE" version 2>/dev/null || true)
if [[ -z "$BUILDER_GO_RAW" ]]; then
    log_error "Could not run 'go version' inside the builder image."
    exit 1
fi
log_info "Builder Go: $BUILDER_GO_RAW"

GO_VER=$(echo "$BUILDER_GO_RAW" | grep -oE 'go[0-9]+\.[0-9]+' | head -1 | sed 's/^go//')
GO_MAJOR=$(echo "$GO_VER" | cut -d. -f1)
GO_MINOR=$(echo "$GO_VER" | cut -d. -f2)

if [[ -z "$GO_MAJOR" ]] || [[ -z "$GO_MINOR" ]] || \
   [[ "$GO_MAJOR" -lt "$MIN_GO_MAJOR" ]] || \
   { [[ "$GO_MAJOR" -eq "$MIN_GO_MAJOR" ]] && [[ "$GO_MINOR" -lt "$MIN_GO_MINOR" ]]; }; then
    log_error "Builder Go version $GO_VER is older than ${MIN_GO_MAJOR}.${MIN_GO_MINOR}."
    log_error "Edit $BUILDER_DIR/Dockerfile to use golang:${MIN_GO_MAJOR}.${MIN_GO_MINOR}-bookworm,"
    log_error "then re-run with: $0 --rebuild"
    exit 1
fi
log_success "Builder Go version is acceptable (>= ${MIN_GO_MAJOR}.${MIN_GO_MINOR})"

# -----------------------------------------------------------------------------
# 3. Write the build script to a file
# -----------------------------------------------------------------------------
# Using a file instead of inline `bash -c "..."` avoids all quoting issues
# with sed patterns, $ symbols, and backslashes.
# -----------------------------------------------------------------------------
mkdir -p "$CACHE_DIR"
mkdir -p "$SERVICE_DIR/amd64" "$SERVICE_DIR/x86"

BUILD_SCRIPT="$CACHE_DIR/build-inside.sh"
cat > "$BUILD_SCRIPT" <<'INNER_EOF'
#!/bin/bash
set -eux

echo '=== Cloning wireguard-windows ==='
git clone --depth 1 https://git.zx2c4.com/wireguard-windows /src

echo '=== Patching go.mod (strip patch component from go directive) ==='
sed -i -E 's/^go ([0-9]+\.[0-9]+)\.[0-9]+$/go \1/' /src/go.mod
grep '^go ' /src/go.mod

echo '=== Running go mod tidy in module root ==='
cd /src
go mod tidy

echo '=== Building tunnel.dll for amd64 ==='
cd /src/embeddable-dll-service
mkdir -p /out/amd64
CC=x86_64-w64-mingw32-gcc GOOS=windows GOARCH=amd64 CGO_ENABLED=1 \
    go build -buildmode=c-shared -ldflags='-s -w' -o /out/amd64/tunnel.dll .

echo '=== Building tunnel.dll for x86 ==='
mkdir -p /out/x86
CC=i686-w64-mingw32-gcc GOOS=windows GOARCH=386 CGO_ENABLED=1 \
    go build -buildmode=c-shared -ldflags='-s -w' -o /out/x86/tunnel.dll .

echo '=== Copying wireguard.dll from NT SDK ==='
SDK_ZIP=/cache/wireguard-nt-1.1.zip
if [ ! -f "$SDK_ZIP" ]; then
    curl -fsSL -o "$SDK_ZIP" https://download.wireguard.com/wireguard-nt/wireguard-nt-1.1.zip
fi
unzip -o -q "$SDK_ZIP" -d /tmp/wg-nt
cp /tmp/wg-nt/wireguard-nt/bin/amd64/wireguard.dll /out/amd64/
cp /tmp/wg-nt/wireguard-nt/bin/x86/wireguard.dll   /out/x86/

echo '=== Verifying output files inside container ==='
ls -la /out/amd64/
ls -la /out/x86/

echo '=== Build complete ==='
INNER_EOF
chmod +x "$BUILD_SCRIPT"

# -----------------------------------------------------------------------------
# 4. Run the build
# -----------------------------------------------------------------------------
log_info "Starting Docker build container to compile tunnel.dll..."
log_warning "This will take 5-10 minutes. Do not abort."

docker run --rm \
    -v "${SERVICE_DIR}:/out" \
    -v "${CACHE_DIR}:/cache" \
    "$BUILDER_IMAGE" \
    /bin/bash /cache/build-inside.sh

# -----------------------------------------------------------------------------
# 5. Verify output files on the HOST (this is what was missing before)
# -----------------------------------------------------------------------------
EXPECTED=(
    "$SERVICE_DIR/amd64/tunnel.dll"
    "$SERVICE_DIR/amd64/wireguard.dll"
    "$SERVICE_DIR/x86/tunnel.dll"
    "$SERVICE_DIR/x86/wireguard.dll"
)
MISSING=0
for f in "${EXPECTED[@]}"; do
    if [[ ! -f "$f" ]]; then
        log_error "Missing: $f"
        MISSING=$((MISSING + 1))
    else
        SIZE=$(du -h "$f" | cut -f1)
        log_info "  ✓ $f ($SIZE)"
    fi
done

if [[ "$MISSING" -gt 0 ]]; then
    log_error "Build reported success but $MISSING file(s) are missing on the host."
    log_error "Check that $SERVICE_DIR is writable and the mount is not on a read-only filesystem."
    exit 1
fi

log_success "WireGuard DLLs built successfully."