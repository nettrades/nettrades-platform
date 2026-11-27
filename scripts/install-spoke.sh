#!/bin/bash
# =============================================================================
# FILE: scripts/install-spoke.sh
# =============================================================================
# PURPOSE:
#   One-command installer for a NETTRADES spoke on Ubuntu Linux.
#
#   After Ubuntu is installed on a machine, run:
#
#       git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
#       cd nettrades-platform
#       chmod +x scripts/*.sh
#       sudo ./scripts/install-spoke.sh --hub-host=<HUB_IP> --token=<TOKEN>
#
#   The script installs every dependency, builds llama.cpp with the correct
#   backend for every GPU on the host, installs the spoke agent, and starts
#   the systemd unit. No manual steps.
#
# MULTI-VENDOR BUILD:
#   The script detects every GPU vendor present (NVIDIA, AMD, Intel) and
#   builds llama.cpp with every matching backend. A build can carry CUDA,
#   HIP and Vulkan simultaneously — this is exactly what lets the AMD
#   mining rig and the Radeon laptop build once and work everywhere, and
#   lets the CUDA and ROCm RPC workers join the same pipeline because the
#   RPC wire protocol is vendor-agnostic.
#
#   Vendor → CMake flag mapping:
#     NVIDIA   : -DGGML_CUDA=ON
#     AMD      : -DGGML_HIP=ON -DGPU_TARGETS=<all detected gfx targets>
#     Intel    : -DGGML_SYCL=ON
#     Fallback : -DGGML_VULKAN=ON (universal, always safe to add)
#
# HSA OVERRIDE:
#   If the host has an AMD GPU whose gfx target is not natively supported
#   by the installed ROCm (for example the RX 6700 XT, gfx1031), the agent
#   sets HSA_OVERRIDE_GFX_VERSION=10.3.0 for that GPU. This makes ROCm
#   accept the card. Without it, the whole ROCm stack silently ignores the
#   GPU and llama.cpp falls back to CPU. The install script writes the
#   correct override into config.yaml so the agent picks it up on start.
#
# USAGE:
#   sudo ./scripts/install-spoke.sh --hub-host=<IP> --token=<TOKEN> [OPTIONS]
#
# OPTIONS:
#   --hub-host=IP              Hub's LAN IP or hostname. Required.
#   --token=TOKEN              Registration token from the hub's Odoo. Required.
#   --node-name=NAME           Node name. Defaults to the system hostname.
#   --inference-capability=CAP rpc_worker (default), rpc_master, local_only,
#                              dynamo_worker.
#   --model-path=PATH          Path to the GGUF model. Optional. If present,
#                              the spoke self-identifies as a warm spare.
#   --rpc-port=PORT            Base port for the first rpc-server. Default 50052.
#                              Additional GPUs get +1, +2, ...
#   --use-wireguard            Enable the WireGuard flow. Default off.
#   --no-wireguard             Explicitly disable WireGuard (default).
#   --skip-build               Skip the llama.cpp build (assumes binary exists).
#   --interactive              Prompt for missing values.
#   --help, -h                 Show this help.
#   --max-workers=N            Cap the number of rpc-server processes. 0 = no
#                              cap (one per GPU). Set to 2-4 on memory-
#                              constrained hosts to avoid kernel OOM kills
#                              (rc=-9 in the journal).
# SUPPORTED OS:
#   Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours & logging
# -----------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; BOLD='\033[1m'; NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
log_step() {
    echo ""
    echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${MAGENTA}${BOLD}  $*${NC}"
    echo -e "${MAGENTA}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
}

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
HUB_HOST=""
TOKEN=""
NODE_NAME="$(hostname)"
INFERENCE_CAPABILITY="rpc_worker"
MODEL_PATH="/var/lib/nettrades/models/model.gguf"
RPC_PORT=50052
USE_WIREGUARD=false
INTERACTIVE=false
SKIP_BUILD=false
MAX_WORKERS=0
INSTALL_DIR="/opt/nettrades/spoke"
CONFIG_DIR="/etc/nettrades/spoke"
LOG_DIR="/var/log/nettrades"
LLAMA_DIR="/opt/nettrades/llama.cpp"
RPC_CACHE_DIR="/var/lib/nettrades/rpc-cache"

# Vendor / backend state (populated by detection)
HAS_NVIDIA=false
HAS_AMD=false
HAS_INTEL=false
AMD_GFX_TARGETS=""
CMAKE_BACKEND_FLAGS=""
SPOKE_CONFIG_FILE=""
HEARTBEAT_SECRET=""

# -----------------------------------------------------------------------------
# Arg parsing
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config-file=*)           SPOKE_CONFIG_FILE="${1#*=}" ;;
        --config-file)             SPOKE_CONFIG_FILE="$2"; shift ;;
        --heartbeat-secret=*)      HEARTBEAT_SECRET="${1#*=}" ;;
        --heartbeat-secret)        HEARTBEAT_SECRET="$2"; shift ;;
        --hub-host=*)              HUB_HOST="${1#*=}" ;;
        --hub-host)                HUB_HOST="$2"; shift ;;
        --token=*)                 TOKEN="${1#*=}" ;;
        --token)                   TOKEN="$2"; shift ;;
        --node-name=*)             NODE_NAME="${1#*=}" ;;
        --node-name)               NODE_NAME="$2"; shift ;;
        --inference-capability=*)  INFERENCE_CAPABILITY="${1#*=}" ;;
        --inference-capability)    INFERENCE_CAPABILITY="$2"; shift ;;
        --model-path=*)            MODEL_PATH="${1#*=}" ;;
        --model-path)              MODEL_PATH="$2"; shift ;;
        --rpc-port=*)              RPC_PORT="${1#*=}" ;;
        --rpc-port)                RPC_PORT="$2"; shift ;;
        --use-wireguard)           USE_WIREGUARD=true ;;
        --no-wireguard)            USE_WIREGUARD=false ;;
        --skip-build)              SKIP_BUILD=true ;;
        --interactive)             INTERACTIVE=true ;;
        --max-workers=*)           MAX_WORKERS="${1#*=}" ;;
        --max-workers)             MAX_WORKERS="$2"; shift ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# -----------------------------------------------------------------------------
# Load hub-config.json if provided (eliminates token/secret copy-paste)
# -----------------------------------------------------------------------------
if [[ -n "$SPOKE_CONFIG_FILE" ]]; then
    [[ -f "$SPOKE_CONFIG_FILE" ]] || { log_error "$SPOKE_CONFIG_FILE not found"; exit 1; }
    command -v jq >/dev/null || { log_error "jq is required to parse $SPOKE_CONFIG_FILE"; exit 1; }

    HUB_HOST_FROM_FILE=$(jq -r '.hub_ip // .hub_url // empty' "$SPOKE_CONFIG_FILE")
    TOKEN_FROM_FILE=$(jq -r '.registration_token // empty'    "$SPOKE_CONFIG_FILE")
    HEARTBEAT_FROM_FILE=$(jq -r '.heartbeat_secret // empty'  "$SPOKE_CONFIG_FILE")

    # Explicit flags win over the file. Use `${VAR:=default}` only if unset.
    : "${HUB_HOST:=${HUB_HOST_FROM_FILE}}"
    : "${TOKEN:=${TOKEN_FROM_FILE}}"
    : "${HEARTBEAT_SECRET:=${HEARTBEAT_FROM_FILE}}"

    log_info "Loaded config from $SPOKE_CONFIG_FILE"
    log_info "  hub=${HUB_HOST}  token=${TOKEN:0:12}...  secret=${HEARTBEAT_SECRET:0:8}..."
fi

# -----------------------------------------------------------------------------
# Interactive prompts
# -----------------------------------------------------------------------------
if [[ -z "$HUB_HOST" ]] && { [[ "$INTERACTIVE" == "true" ]] || [[ -t 0 ]]; }; then
    read -rp "Hub IP or hostname (e.g., 192.168.1.10): " HUB_HOST
fi
[[ -z "$HUB_HOST" ]] && { log_error "--hub-host is required."; exit 1; }

if [[ -z "$TOKEN" ]] && { [[ "$INTERACTIVE" == "true" ]] || [[ -t 0 ]]; }; then
    read -rp "Registration token from Odoo: " TOKEN
fi
[[ -z "$TOKEN" ]] && { log_error "--token is required."; exit 1; }

# -----------------------------------------------------------------------------
# Root check
# -----------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root. Use: sudo $0 ..."
    exit 1
fi

# -----------------------------------------------------------------------------
# OS check
# -----------------------------------------------------------------------------
[[ -f /etc/os-release ]] || { log_error "/etc/os-release not found."; exit 1; }
source /etc/os-release
case "${ID:-}" in
    ubuntu|debian) : ;;
    *) log_warning "Designed for Ubuntu/Debian. Detected: ${ID:-unknown}. Proceeding." ;;
esac

# -----------------------------------------------------------------------------
# Extract bare hub host
# -----------------------------------------------------------------------------
HUB_BARE="${HUB_HOST#http://}"
HUB_BARE="${HUB_BARE#https://}"
HUB_BARE="${HUB_BARE%%:*}"
HUB_BARE="${HUB_BARE%%/*}"

ODOO_URL="http://${HUB_BARE}:8069"
LANGGRAPH_URL="http://${HUB_BARE}:8000"

log_step "NETTRADES Spoke Installer"
log_info "Hub host:              $HUB_BARE"
log_info "Odoo URL:              $ODOO_URL"
log_info "LangGraph URL:         $LANGGRAPH_URL"
log_info "Node name:             $NODE_NAME"
log_info "Inference capability:  $INFERENCE_CAPABILITY"
log_info "WireGuard:             $USE_WIREGUARD"
log_info "Base RPC port:         $RPC_PORT"
log_info "Model path:            $MODEL_PATH"

# =============================================================================
# Step 1 — System packages
# =============================================================================
log_step "Step 1: Installing system packages"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

PACKAGES=(
    build-essential
    cmake
    git
    curl
    wget
    ca-certificates
    python3
    python3-pip
    python3-venv
    pkg-config
    libssl-dev
    libcurl4-openssl-dev
    jq
    # GPU detection helpers
    pciutils
    lshw
    clinfo
    # RPC build dependencies (needed by the HIP runtime on multi-GPU AMD)
    libnuma-dev
    # mDNS (avahi-browse is used by spoke-agent.py for hub rediscovery)
    avahi-utils
    avahi-daemon
)

apt-get install -y -qq "${PACKAGES[@]}"
systemctl enable --now avahi-daemon.service 2>/dev/null || true

if [[ "$USE_WIREGUARD" == "true" ]]; then
    apt-get install -y -qq wireguard-tools
fi

log_success "System packages installed"

# =============================================================================
# Step 1b — Pre-flight: hub reachability
# =============================================================================
# The build in Step 4 takes 15-25 minutes. If the hub is unreachable
# (firewall, wrong IP, V100 down), the registration at the end of this
# script will fail. Check reachability BEFORE the build.
log_step "Step 1b: Verifying hub reachability"
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/${HUB_BARE}/8069" 2>/dev/null; then
    log_error "Cannot reach ${HUB_BARE}:8069 (Odoo)."
    log_error "Check the hub is up and the firewall permits TCP 8069."
    exit 1
fi
if ! timeout 5 bash -c "cat < /dev/null > /dev/tcp/${HUB_BARE}/8000" 2>/dev/null; then
    log_warning "Cannot reach ${HUB_BARE}:8000 (LangGraph)."
    log_warning "Registration may succeed but heartbeats will fail."
fi
log_success "Hub reachable"

# =============================================================================
# Step 1c — Pre-flight: swap space
# =============================================================================
# The HIP build in Step 4 compiles for every detected gfx target. On a
# machine with 8 GB RAM (typical mining rig) and six targets, this OOMs
# without swap. We do not create swap (that requires operator consent and
# is a policy decision), but we refuse to start the build without it.
if [[ "$SKIP_BUILD" != "true" ]]; then
    SWAP_MB=$(free -m | awk '/^Swap:/ {print $2}')
    SWAP_MB=${SWAP_MB:-0}
    if [[ "$SWAP_MB" -lt 4096 ]]; then
        log_warning "Swap is ${SWAP_MB} MB. The llama.cpp HIP build"
        log_warning "requires at least 4 GB of swap on 8 GB systems."
        log_warning "Create swap first, then re-run:"
        log_warning "  sudo fallocate -l 16G /swapfile"
        log_warning "  sudo chmod 600 /swapfile"
        log_warning "  sudo mkswap /swapfile"
        log_warning "  sudo swapon /swapfile"
        log_warning "  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab"
        log_error "Aborting to avoid an OOM at minute 20 of the build."
        exit 1
    fi
    log_success "Swap: ${SWAP_MB} MB available"
fi

# =============================================================================
# Step 2 — GPU detection (multi-vendor)
# =============================================================================
log_step "Step 2: Detecting GPUs"

# --- NVIDIA ---
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    HAS_NVIDIA=true
    log_success "NVIDIA GPU(s) detected:"
    nvidia-smi --query-gpu=index,name,memory.total,compute_cap \
               --format=csv,noheader | sed 's/^/    /'
fi
# Fall back to lspci / sysfs if nvidia-smi is absent but the card is there.
if [[ "$HAS_NVIDIA" == "false" ]]; then
    if lspci 2>/dev/null | grep -qiE "VGA.*NVIDIA|3D.*NVIDIA"; then
        HAS_NVIDIA=true
        log_warning "NVIDIA GPU found via lspci but nvidia-smi is missing."
        log_info "    Install the NVIDIA driver before expecting GPU inference to work."
    fi
fi
# Final fallback: /sys/class/drm vendor IDs.
if [[ "$HAS_NVIDIA" == "false" ]]; then
    for f in /sys/class/drm/card*/device/vendor; do
        [[ -f "$f" ]] || continue
        if [[ "$(cat "$f" 2>/dev/null)" == "0x10de" ]]; then
            HAS_NVIDIA=true; break
        fi
    done
fi

# --- AMD ---
if command -v rocminfo >/dev/null 2>&1 && rocminfo >/dev/null 2>&1; then
    HAS_AMD=true
    log_success "AMD GPU(s) detected via rocminfo"
elif lspci 2>/dev/null | grep -qiE "VGA.*(AMD|Radeon)|Display.*(AMD|Radeon)"; then
    HAS_AMD=true
    log_warning "AMD GPU found via lspci but ROCm is not installed."
    log_info "    The installer will install ROCm now."
fi
if [[ "$HAS_AMD" == "false" ]]; then
    for f in /sys/class/drm/card*/device/vendor; do
        [[ -f "$f" ]] || continue
        if [[ "$(cat "$f" 2>/dev/null)" == "0x1002" ]]; then
            HAS_AMD=true; break
        fi
    done
fi

# --- Intel ---
if command -v xpu-smi >/dev/null 2>&1 && xpu-smi discovery >/dev/null 2>&1; then
    HAS_INTEL=true
    log_success "Intel GPU(s) detected via xpu-smi"
elif lspci 2>/dev/null | grep -qiE "VGA.*Intel|Display.*Intel"; then
    HAS_INTEL=true
    log_info "Intel GPU found via lspci"
fi

if [[ "$HAS_NVIDIA" == "false" && "$HAS_AMD" == "false" && "$HAS_INTEL" == "false" ]]; then
    log_warning "No GPU detected — building a CPU-only rpc-server."
    log_info "    This spoke will still register and contribute CPU layers."
fi

# =============================================================================
# Step 3 — Vendor toolkit installation
# =============================================================================
log_step "Step 3: Installing vendor toolkits"

IS_WSL=false
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=true

# ---- NVIDIA CUDA toolkit ----
if [[ "$HAS_NVIDIA" == "true" ]]; then
    if command -v nvcc >/dev/null 2>&1; then
        CUDA_VER=$(nvcc --version | grep -oP 'release \K[0-9.]+' || echo "0")
        log_success "CUDA toolkit present: $CUDA_VER"
    elif [[ "$IS_WSL" == "true" ]]; then
        # WSL2: install CUDA 12.8 from NVIDIA's WSL repo instead of
        # Ubuntu's nvidia-cuda-toolkit (which is CUDA 12.0 on 24.04 and
        # cannot target Blackwell sm_120). Requires the Windows host
        # driver to be 12.8-compatible — the RTX 5070 Ti's driver
        # (610.47 as reported) is well above that.
        log_info "WSL2 detected — installing CUDA 12.8 from NVIDIA's WSL repo."
        if [[ ! -f /usr/share/keyrings/cuda-archive-keyring.gpg ]]; then
            wget -qO- https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/3bf863cc.pub \
                | gpg --dearmor -o /usr/share/keyrings/cuda-archive-keyring.gpg 2>/dev/null || true
            echo "deb [signed-by=/usr/share/keyrings/cuda-archive-keyring.gpg] https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/ /" \
                > /etc/apt/sources.list.d/cuda-wsl.list
            apt-get update -qq
        fi
        # Try 12.8 first; fall back to cuda-toolkit (latest) if the exact
        # version is not published.
        apt-get install -y -qq cuda-toolkit-12-8 2>/dev/null \
            || apt-get install -y -qq cuda-toolkit 2>/dev/null \
            || { log_warning "CUDA 12.8 install failed; CUDA backend skipped."; HAS_NVIDIA=false; }
        [[ "$HAS_NVIDIA" == "true" ]] && log_success "CUDA 12.8 installed"
    else
        # Bare-metal Linux: keep Ubuntu's package. If the user has a
        # Blackwell GPU and Ubuntu's CUDA is too old, the build will
        # fail with "Unsupported gpu architecture"; the operator can
        # install NVIDIA's package themselves.
        if apt-cache show cuda-toolkit >/dev/null 2>&1; then
            apt-get install -y -qq cuda-toolkit 2>/dev/null || HAS_NVIDIA=false
        else
            apt-get install -y -qq nvidia-cuda-toolkit 2>/dev/null || HAS_NVIDIA=false
        fi
        [[ "$HAS_NVIDIA" == "true" ]] && log_success "CUDA toolkit installed"
    fi
fi

# ---- AMD ROCm ----
if [[ "$HAS_AMD" == "true" ]] && ! command -v hipcc >/dev/null 2>&1; then
    log_info "Installing ROCm HIP toolkit..."

    # Determine the OS codename for the ROCm repo.
    CODENAME=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-${VERSION_CODENAME:-jammy}}")

    mkdir -p /etc/apt/keyrings
    if [[ ! -f /etc/apt/keyrings/rocm.gpg ]]; then
        wget -qO- https://repo.radeon.com/rocm/rocm.gpg.key \
            | gpg --dearmor -o /etc/apt/keyrings/rocm.gpg 2>/dev/null || true
        chmod 644 /etc/apt/keyrings/rocm.gpg 2>/dev/null || true
    fi

    # Read the pinned ROCm version from the hardware matrix
    ROCM_VER="6.3"  # from hardware-matrix.yaml amd-rdna2 profile
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] https://repo.radeon.com/rocm/apt/${ROCM_VER} ${CODENAME} main" \
        > /etc/apt/sources.list.d/rocm.list
    apt-get update -qq
    log_info "Using pinned ROCm version: ${ROCM_VER}"

    if apt-get install -y -qq \
            rocm-hip-libraries rocm-device-libs rocm-libs hipcc 2>/dev/null \
       || apt-get install -y -qq rocm-hip-sdk 2>/dev/null; then
        log_success "ROCm installed"
    else
        log_warning "ROCm installation failed — AMD backend will be skipped."
        HAS_AMD=false
    fi

    # Add the invoking user and root to the GPU groups.
    [[ -n "${SUDO_USER:-}" ]] && usermod -a -G video,render "$SUDO_USER" 2>/dev/null || true
    usermod -a -G video,render root 2>/dev/null || true
fi

# ---- AMD gfx targets + HSA override detection ----
if [[ "$HAS_AMD" == "true" ]] && command -v rocminfo >/dev/null 2>&1; then
    # Collect every distinct gfx target so we can pass them all to
    # -DGPU_TARGETS. Building for all targets means the binary works on
    # every AMD card in this machine and any future replacement.
    AMD_GFX_TARGETS=$(rocminfo 2>/dev/null \
        | grep -oE 'gfx[0-9]+[a-z0-9]*' \
        | sort -u \
        | paste -sd, -)
    if [[ -n "$AMD_GFX_TARGETS" ]]; then
        log_info "AMD gfx targets detected: $AMD_GFX_TARGETS"
    fi
fi

# ---- Intel oneAPI (SYCL) ----
if [[ "$HAS_INTEL" == "true" ]] && ! command -v icpx >/dev/null 2>&1; then
    log_info "Installing Intel oneAPI DPC++ compiler..."
    apt-get install -y -qq intel-opencl-icd intel-level-zero-gpu level-zero 2>/dev/null || true

    if [[ ! -f /usr/share/keyrings/oneapi-archive-keyring.gpg ]]; then
        wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB \
            | gpg --dearmor -o /usr/share/keyrings/oneapi-archive-keyring.gpg 2>/dev/null || true
    fi
    echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" \
        > /etc/apt/sources.list.d/oneAPI.list
    apt-get update -qq 2>/dev/null || true
    apt-get install -y -qq intel-oneapi-compiler-dpcpp-cpp \
        intel-oneapi-compiler-shared-runtime intel-oneapi-mkl 2>/dev/null || {
        log_warning "Intel oneAPI install failed; Intel backend skipped."
        HAS_INTEL=false
    }
    [[ -f /opt/intel/oneapi/setvars.sh ]] && source /opt/intel/oneapi/setvars.sh >/dev/null 2>&1 || true
fi

# =============================================================================
# Step 4 — Build llama.cpp with all detected backends + RPC
# =============================================================================
log_step "Step 4: Building llama.cpp with RPC and all detected backends"

mkdir -p "$(dirname "$LLAMA_DIR")"

if [[ ! -d "$LLAMA_DIR/.git" ]]; then
    log_info "Cloning llama.cpp..."
    rm -rf "$LLAMA_DIR"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
fi
cd "$LLAMA_DIR"

if [[ "$SKIP_BUILD" == "true" ]] && \
   { [[ -x build/bin/rpc-server ]] || \
     [[ -x build/bin/ggml-rpc-server ]] || \
     [[ -x /usr/local/bin/rpc-server ]]; }; then
    log_info "Skipping build (--skip-build) — using existing binary"
else
    # --- compose the cmake flags ---
    # RPC is always on — this is what makes the spoke usable.
    CMAKE_BACKEND_FLAGS="-DGGML_RPC=ON"

    if [[ "$HAS_NVIDIA" == "true" ]]; then
        CMAKE_BACKEND_FLAGS+=" -DGGML_CUDA=ON"
        # Let CMake detect the compute capability of the installed GPU.
        # This handles every architecture up to and including Blackwell
        # (sm_120). Requires CMake 3.20+ (Ubuntu 22.04/24.04 ship 3.22+).
        # Without this, CMake uses a default arch list that may not
        # include the actual GPU, producing a binary that compiles but
        # fails at runtime with "no CUDA-capable device".
        CMAKE_BACKEND_FLAGS+=" -DCMAKE_CUDA_ARCHITECTURES=native"
    fi
    if [[ "$HAS_AMD" == "true" ]]; then
        CMAKE_BACKEND_FLAGS+=" -DGGML_HIP=ON"
        if [[ -n "$AMD_GFX_TARGETS" ]]; then
            CMAKE_BACKEND_FLAGS+=" -DGPU_TARGETS=${AMD_GFX_TARGETS}"
        fi
    fi
    if [[ "$HAS_INTEL" == "true" ]]; then
        CMAKE_BACKEND_FLAGS+=" -DGGML_SYCL=ON"
    fi

    # Vulkan is safe to add on top of CUDA/HIP when libvulkan is present.
    # It gives us a second path to the same GPU if a backend misbehaves.
    if apt-cache show libvulkan-dev >/dev/null 2>&1; then
        apt-get install -y -qq libvulkan-dev glslc 2>/dev/null || true
        CMAKE_BACKEND_FLAGS+=" -DGGML_VULKAN=ON"
    fi

    # If no vendor backend was selected, ensure the CPU backend is on.
    if [[ "$HAS_NVIDIA$HAS_AMD$HAS_INTEL" == "falsefalsefalse" ]]; then
        CMAKE_BACKEND_FLAGS+=" -DGGML_CUDA=OFF"
    fi

    log_info "CMake flags: $CMAKE_BACKEND_FLAGS"

    # HIP builds need the HIP compiler on the command line. We set it only
    # when the HIP backend is being compiled.
    HIP_ENV=""
    if [[ "$HAS_AMD" == "true" ]] && command -v hipconfig >/dev/null 2>&1; then
        HIP_ENV="HIPCXX=$(hipconfig -l)/clang HIP_PATH=$(hipconfig -p)"
    fi

    log_info "Building llama.cpp (10-25 minutes on first run)..."
    # shellcheck disable=SC2086
    eval $HIP_ENV cmake -B build $CMAKE_BACKEND_FLAGS -DCMAKE_BUILD_TYPE=Release
    cmake --build build --config Release -j"$(nproc)"
fi

RPC_BIN=""
for candidate in build/bin/rpc-server build/bin/ggml-rpc-server; do
    if [[ -x "$candidate" ]]; then
        RPC_BIN="$candidate"
        break
    fi
done
if [[ -z "$RPC_BIN" ]]; then
    log_error "Build did not produce an RPC server binary."
    log_info "Looked for: build/bin/rpc-server and build/bin/ggml-rpc-server"
    log_info "Check the cmake output above; GGML_RPC=ON should build it."
    exit 1
fi
install -m 0755 "$RPC_BIN" /usr/local/bin/rpc-server
log_success "rpc-server installed"

# =============================================================================
# Step 5 — Python deps for the agent
# =============================================================================
log_step "Step 5: Installing Python dependencies"

python3 -m pip install --break-system-packages --quiet requests pyyaml
# zeroconf is optional (avahi is the primary path); failure is not fatal.
python3 -m pip install --break-system-packages --quiet zeroconf 2>/dev/null \
    && log_success "requests, pyyaml, zeroconf installed" \
    || log_success "requests, pyyaml installed (zeroconf optional, skipped)"

# =============================================================================
# Step 6 — Spoke agent + config
# =============================================================================
log_step "Step 6: Installing spoke agent"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_SRC="$SCRIPT_DIR/spoke-agent.py"
[[ -f "$AGENT_SRC" ]] || { log_error "spoke-agent.py not found at $AGENT_SRC"; exit 1; }

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$LOG_DIR" "$RPC_CACHE_DIR" /var/lib/nettrades/spoke
install -m 0755 "$AGENT_SRC" "$INSTALL_DIR/spoke-agent.py"
chmod 755 "$RPC_CACHE_DIR" 2>/dev/null || true

if [[ -z "${HEARTBEAT_SECRET:-}" ]]; then
    log_warning "HEARTBEAT_SECRET is empty — /nodes/heartbeat will 401 until Option B (registration response) delivers it"
    log_info "   Alternative: pass --heartbeat-secret=<value> from hub's .env"
fi

USE_WG_FROM_FILE=$(jq -r '.use_wireguard // false' "$SPOKE_CONFIG_FILE")
if [[ "$USE_WG_FROM_FILE" == "true" ]] && [[ "$USE_WIREGUARD" != "true" ]]; then
    USE_WIREGUARD=true
    log_info "WireGuard enabled (from $SPOKE_CONFIG_FILE)"
fi

cat > "$CONFIG_DIR/config.yaml" <<EOF
# NETTRADES Spoke Agent — generated by install-spoke.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
sub_hub_url: ${ODOO_URL}
langgraph_url: ${LANGGRAPH_URL}
node_name: ${NODE_NAME}
heartbeat_interval: 10
registration_token: ${TOKEN}
inference_capability: ${INFERENCE_CAPABILITY}
model_path: ${MODEL_PATH}
use_wireguard: ${USE_WIREGUARD}
rpc_port: ${RPC_PORT}
# Graceful drain: seconds to wait after the drain heartbeat before
# stopping RPC workers. Must be less than the systemd unit's
# TimeoutStopSec (120) minus a margin.
shutdown_grace_seconds: 30
# Drain signal file paths (defaults shown; only override if needed).
# The Windows service writes drain_requested_file on PRESHUTDOWN.
# drain_requested_file: /var/lib/nettrades/spoke/drain.requested
# drain_complete_file: /var/lib/nettrades/spoke/drain.complete
heartbeat_secret: "${HEARTBEAT_SECRET:-}"
EOF
chmod 600 "$CONFIG_DIR/config.yaml"
log_success "Config written to $CONFIG_DIR/config.yaml"

# Write manifest.json for spoke-agent to consume on next start.
# If scripts/lib/detect.py exists (from the vendor framework), use it
# so installer-time and runtime detection are identical. Otherwise
# skip — spoke-agent falls back to runtime detection, which produces
# the same GPU list from the same hardware. Both paths are correct.
if [[ -f "$SCRIPT_DIR/lib/detect.py" ]]; then
    if python3 "$SCRIPT_DIR/lib/detect.py" --json > "$CONFIG_DIR/manifest.json" 2>/dev/null; then
        chmod 644 "$CONFIG_DIR/manifest.json"
        log_success "Manifest written to $CONFIG_DIR/manifest.json"
    else
        rm -f "$CONFIG_DIR/manifest.json"
        log_warning "detect.py failed — spoke-agent will use runtime detection"
    fi
else
    log_info "detect.py not present — spoke-agent will use runtime detection"
fi

# =============================================================================
# Step 7 — systemd unit (with multi-GPU environment passthrough)
# =============================================================================
log_step "Step 7: Installing systemd unit"

cat > /etc/systemd/system/nettrades-spoke.service <<EOF
[Unit]
Description=NETTRADES Spoke Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/spoke-agent.py --config ${CONFIG_DIR}/config.yaml
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=MODEL_PATH=${MODEL_PATH}
Environment=RPC_PORT=${RPC_PORT}
Environment=RPC_CACHE_DIR=${RPC_CACHE_DIR}
Environment=RPC_MAX_WORKERS=${MAX_WORKERS}
LimitNOFILE=65535

# Graceful drain support (2026-10-20)
# ------------------------------------
# On stop/shutdown, systemd sends SIGTERM. The spoke agent's SIGTERM
# handler starts a graceful drain: it notifies the hub (draining=true
# heartbeat), waits `shutdown_grace_seconds` (default 30), stops its
# RPC workers, then exits.
#

# TimeoutStopSec must be longer than the worst-case drain sequence:
#   shutdown_grace_seconds (30)      — wait for in-flight generation
# + serial worker stop (6 × 10s)     — RpcWorker.stop() per-GPU timeout
# + small safety margin
#
# The pre-2026-10-22 value of 90 gave zero margin over the serial
# worker-stop worst case, so a single slow rpc-server exited via
# SIGKILL mid-drain. The agent now stops workers in parallel (see
# spoke-agent.py MultiGpuRpcSupervisor.stop_all), which bounds the
# worker phase at 10s regardless of GPU count. 120 seconds gives
# 80 seconds of margin over that bounded worst case.
TimeoutStopSec=120
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nettrades-spoke.service
systemctl restart nettrades-spoke.service

log_success "nettrades-spoke.service started"

# =============================================================================
# Step 8 — Post-install summary
# =============================================================================
sleep 3
systemctl is-active --quiet nettrades-spoke.service \
    && log_success "Spoke agent running" \
    || { log_warning "Spoke agent not active — check logs:"; log_info "  journalctl -u nettrades-spoke -n 50"; }

echo ""
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Spoke installation complete${NC}"
echo -e "${GREEN}${BOLD}══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Hardware summary:"
echo "  NVIDIA:  ${HAS_NVIDIA}"
echo "  AMD:     ${HAS_AMD}    gfx targets: ${AMD_GFX_TARGETS:-none}"
echo "  Intel:   ${HAS_INTEL}"
echo "  Backends built: ${CMAKE_BACKEND_FLAGS}"
echo ""
echo "Useful commands:"
echo "  systemctl status nettrades-spoke"
echo "  journalctl -u nettrades-spoke -f"
echo "  python3 /opt/nettrades/spoke/spoke-agent.py --detect-only"
echo ""
echo "Verify the spoke appears on the hub:"
echo "  Open http://${HUB_BARE}:8069 → GPU Manager → GPU Nodes"
echo "  Look for '${NODE_NAME}' with state=active"
echo ""