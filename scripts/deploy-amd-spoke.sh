#!/bin/bash
# =============================================================================
# FILE: scripts/deploy-amd-spoke.sh
# =============================================================================
# PURPOSE:
#   One-command deploy of the AMD rig as a NETTRADES RPC spoke.
#
#   Orchestrates:
#     1. Pre-flight: hub reachability, token format, 6 AMD GPUs visible
#     2. install-spoke.sh (ROCm + llama.cpp build + systemd unit + register)
#     3. Verification: 6 rpc-servers listening, registration logged
#
# PREREQUISITES:
#   - Ubuntu 24.04 (Desktop or Server) on the AMD rig, freshly installed
#   - openssh-server enabled
#   - Repository cloned to ~/nettrades-platform on branch dev-deployment1
#   - 6x AMD Radeon RX 6700 XT
#   - V100 hub is up + you have the spoke token from deploy-v100-hub.sh
#
# USAGE:
#   cd ~/nettrades-platform
#   sudo ./scripts/deploy-amd-spoke.sh \
#       --hub-host=192.168.1.56 \
#       --token=<token>
#
# FLAGS:
#   --skip-build    Skip the 15-25 minute llama.cpp build (use on re-run)
#   --node-name=X   Override the default (amd-mining-rig)
#
# IDEMPOTENT:
#   Safe to re-run. Use --skip-build on subsequent runs to save time.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

set -uo pipefail

HUB_HOST=""
TOKEN=""
NODE_NAME="amd-mining-rig"
INFERENCE_CAPABILITY="rpc_worker"
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hub-host=*)              HUB_HOST="${1#*=}"; shift ;;
        --hub-host)                HUB_HOST="$2"; shift 2 ;;
        --token=*)                 TOKEN="${1#*=}"; shift ;;
        --token)                   TOKEN="$2"; shift 2 ;;
        --node-name=*)             NODE_NAME="${1#*=}"; shift ;;
        --node-name)               NODE_NAME="$2"; shift 2 ;;
        --inference-capability=*)  INFERENCE_CAPABILITY="${1#*=}"; shift ;;
        --skip-build)              SKIP_BUILD=true; shift ;;
        -h|--help)
            sed -n '2,/^# =\{20\}/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }

banner() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $*${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════════${NC}"
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# =============================================================================
# PRE-FLIGHT
# =============================================================================
banner "NETTRADES AMD Spoke Deploy — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Project root: $PROJECT_ROOT"
echo "  Logs:         $LOG_DIR"
echo ""

if [[ $EUID -ne 0 ]]; then
    log_error "Must run as root. Use: sudo $0 $*"
    exit 1
fi

[[ -z "$HUB_HOST" ]] && { log_error "--hub-host is required."; exit 1; }
[[ -z "$TOKEN" ]]    && { log_error "--token is required."; exit 1; }
log_info "Hub host:             $HUB_HOST"
log_info "Node name:            $NODE_NAME"
log_info "Inference capability: $INFERENCE_CAPABILITY"
log_info "Skip build:           $SKIP_BUILD"

if [[ ! -d "$PROJECT_ROOT/.git" ]]; then
    log_error "$PROJECT_ROOT is not a git repository."
    exit 1
fi
cd "$PROJECT_ROOT"
log_info "Git branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"

if [[ ! -x "$PROJECT_ROOT/scripts/install-spoke.sh" ]]; then
    log_error "scripts/install-spoke.sh not executable."
    log_error "Run: chmod +x scripts/*.sh scripts/lib/*.sh"
    exit 1
fi

# --- Hub reachability ---
banner "Pre-flight: hub reachability"
log_info "Testing TCP $HUB_HOST:8069 (Odoo)..."
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$HUB_HOST/8069" 2>/dev/null; then
    log_error "Cannot reach $HUB_HOST:8069."
    log_error ""
    log_error "The V100 hub is not up, or a firewall blocks TCP 8069."
    log_error "Verify from this machine:"
    log_error "  nc -zv $HUB_HOST 8069"
    log_error ""
    log_error "On the V100, run: ./scripts/nettrades-setup.sh hub --force --auto"
    exit 1
fi
log_success "Hub Odoo reachable at $HUB_HOST:8069"

log_info "Testing TCP $HUB_HOST:8000 (LangGraph)..."
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/$HUB_HOST/8000" 2>/dev/null; then
    log_warning "Cannot reach $HUB_HOST:8000 (LangGraph)."
    log_warning "Install will continue, but heartbeats will fail until it's up."
else
    log_success "Hub LangGraph reachable at $HUB_HOST:8000"
fi

# --- Token sanity ---
if [[ ${#TOKEN} -lt 16 ]]; then
    log_error "Token '$TOKEN' is too short (${#TOKEN} chars)."
    log_error "Expected 32-char alphanumeric. Re-run deploy-v100-hub.sh for a fresh token."
    exit 1
fi
log_success "Token looks structurally valid (${#TOKEN} chars)"

# --- AMD GPU detection ---
banner "Pre-flight: AMD GPU detection"
if ! command -v lspci >/dev/null 2>&1; then
    log_info "Installing pciutils..."
    apt-get update -qq && apt-get install -y -qq pciutils
fi
AMD_GPU_COUNT=$(lspci 2>/dev/null | grep -icE "VGA.*(AMD|Radeon)|Display.*(AMD|Radeon)|3D.*(AMD|Radeon)" || true)
AMD_GPU_COUNT=${AMD_GPU_COUNT:-0}
log_info "AMD GPUs visible via lspci: $AMD_GPU_COUNT"
if [[ "$AMD_GPU_COUNT" -lt 6 ]]; then
    log_warning "Expected 6 GPUs, found $AMD_GPU_COUNT."
    log_warning "Check: lspci | grep -i radeon"
    log_warning "Continuing — installer will detect whatever is present."
fi

# =============================================================================
# STEP 1: install-spoke.sh
# =============================================================================
banner "Step 1/2 — install-spoke.sh"
echo "  Log: $LOG_DIR/amd-install.log"
if [[ "$SKIP_BUILD" == "true" ]]; then
    echo "  --skip-build: skipping llama.cpp build"
else
    echo "  Build will take 15-25 minutes on first run."
fi
echo ""

INSTALL_ARGS=(
    "--hub-host=$HUB_HOST"
    "--token=$TOKEN"
    "--node-name=$NODE_NAME"
    "--inference-capability=$INFERENCE_CAPABILITY"
    "--no-wireguard"
)
if [[ "$SKIP_BUILD" == "true" ]]; then
    INSTALL_ARGS+=("--skip-build")
fi

bash "$PROJECT_ROOT/scripts/install-spoke.sh" "${INSTALL_ARGS[@]}" 2>&1 | tee "$LOG_DIR/amd-install.log"
INSTALL_EXIT=${PIPESTATUS[0]}

if [[ $INSTALL_EXIT -ne 0 ]]; then
    log_error "install-spoke.sh failed (exit $INSTALL_EXIT)."
    log_error "See: $LOG_DIR/amd-install.log"
    log_error ""
    log_error "Common causes:"
    log_error "  - ROCm install failed (network, apt mirror, codename mismatch)"
    log_error "  - llama.cpp build failed (check -DGGML_HIP flags in log)"
    log_error "  - Token rejected: look for 'HTTP 401' in the log"
    exit 1
fi
log_success "install-spoke.sh completed"

# =============================================================================
# STEP 2: Verification
# =============================================================================
banner "Step 2/2 — Verification"

FAIL=0
check() {
    local label="$1"; shift
    if "$@" >/dev/null 2>&1; then
        echo -e "  ${GREEN}OK${NC}   $label"
    else
        echo -e "  ${RED}FAIL${NC} $label"
        FAIL=1
    fi
}

check "systemd unit active"  systemctl is-active --quiet nettrades-spoke
check "rpc-server binary"    test -x /usr/local/bin/rpc-server
check "spoke-agent.py"       test -x /opt/nettrades/spoke/spoke-agent.py
check "config.yaml present"  test -f /etc/nettrades/spoke/config.yaml

if ! command -v ss >/dev/null 2>&1; then
    log_info "Installing iproute2 (ss)..."
    apt-get install -y -qq iproute2
fi

# 6 rpc-server sockets on 50052-50057
RPC_COUNT=$(ss -ltn 2>/dev/null | grep -cE ':5005[2-7]\b' || true)
RPC_COUNT=${RPC_COUNT:-0}
if [[ "$RPC_COUNT" -ge 6 ]]; then
    echo -e "  ${GREEN}OK${NC}   6 rpc-servers listening (ports 50052-50057)"
else
    echo -e "  ${RED}FAIL${NC} Expected 6 rpc-servers, found $RPC_COUNT"
    echo "         Check: ss -ltn | grep 5005"
    echo "         And:   journalctl -u nettrades-spoke -n 50"
    FAIL=1
fi

if command -v rocminfo >/dev/null 2>&1; then
    log_success "ROCm already installed (rocminfo present)"
else
    log_info "ROCm not installed — installer will install it"
fi

# ROCm + gfx targets
if command -v rocminfo >/dev/null 2>&1; then
    GFX_COUNT=$(rocminfo 2>/dev/null | grep -c 'gfx' || true)
    GFX_COUNT=${GFX_COUNT:-0}
    if [[ "$GFX_COUNT" -ge 6 ]]; then
        echo -e "  ${GREEN}OK${NC}   rocminfo reports $GFX_COUNT GPU agents"
    else
        echo -e "  ${YELLOW}WARN${NC} rocminfo reports $GFX_COUNT GPU agents (expected 6)"
        echo "         Check: rocminfo | grep gfx"
    fi
fi

# Registration log
if journalctl -u nettrades-spoke -n 200 --no-pager 2>/dev/null | grep -q "registered with hub"; then
    NODE_ID=$(journalctl -u nettrades-spoke -n 200 --no-pager 2>/dev/null | grep "registered with hub" | tail -1 | grep -oE 'node_id=[0-9]+' | cut -d= -f2)
    echo -e "  ${GREEN}OK${NC}   Spoke registered with hub (node_id=$NODE_ID)"
else
    echo -e "  ${RED}FAIL${NC} Spoke did not register with hub"
    echo "         Check: journalctl -u nettrades-spoke -n 100 --no-pager"
    FAIL=1
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
if [[ $FAIL -eq 0 ]]; then
    banner "AMD spoke is READY"
    echo ""
    echo "  Node name:  $NODE_NAME"
    echo "  Hub:        $HUB_HOST"
    echo ""
    echo "  -- Verify on the V100 --"
    echo ""
    echo "    curl -s -H \"X-API-Key: \$(grep LANGGRAPH_API_KEY deploy/docker/.env | cut -d= -f2)\" \\"
    echo "        http://localhost:8000/nodes | python3 -m json.tool"
    echo ""
    echo "  -- Live logs on this AMD --"
    echo ""
    echo "    journalctl -u nettrades-spoke -f"
    echo ""
    echo "  -- Test drain (do once before the demo) --"
    echo ""
    echo "    sudo systemctl stop nettrades-spoke"
    echo "    # On V100, watch /nodes: is_healthy should flip false within 10s"
    echo "    sudo systemctl start nettrades-spoke"
    echo ""
else
    banner "AMD spoke has FAILURES"
    echo ""
    echo "  Fix the FAIL items above."
    echo "  Logs: $LOG_DIR/amd-install.log"
    echo "        journalctl -u nettrades-spoke -n 100 --no-pager"
    echo ""
    exit 1
fi