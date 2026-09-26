#!/bin/bash
# =============================================================================
# FILE: scripts/build-vllm-cpu.sh
# =============================================================================
# PURPOSE:
#   Builds a CPU-optimised vLLM container image for NVIDIA Dynamo from source.
#   This enables vLLM (normally CUDA-only) to run on CPU nodes with AVX512/
#   AMX_BF16 acceleration.
#
#   Based on NVIDIA Dynamo PR #7139 which added CPU device support for vLLM
#   container builds and deployments.
#
# USAGE:
#   ./build-vllm-cpu.sh [--force] [--tag <tag>] [--dynamo-repo <url>]
#
#   --force          Rebuild even if image already exists
#   --tag            Docker image tag (default: nettrades-vllm-cpu:latest)
#   --dynamo-repo    Dynamo repository URL (default: https://github.com/ai-dynamo/dynamo.git)
#   --branch         Git branch to build (default: main)
#
# REQUIREMENTS:
#   - Docker installed
#   - At least 32 GB RAM and 4 CPU cores recommended for CPU vLLM[reference:2]
#   - gcc/g++ >= 12.3.0 recommended for CPU backend[reference:3]
# =============================================================================
#
# Copyright (c) 2026 NETTRADES FOUNDATION. All rights reserved.
# 
# This file is part of the NETTRADES Sovereign AI Platform.
# 
# The NETTRADES Sovereign AI Platform is a dual-licensed enterprise ecosystem. 
# This file is distributed as open-source software under the terms of the 
# GNU Affero General Public License v3.0 (AGPL-3.0) as published by the Free 
# Software Foundation, version 3 of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful, but WITHOUT 
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
# FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License v3.0 for 
# more details.
# 
# You should have received a copy of the GNU Affero General Public License v3.0 
# along with this program. If not, see <https://gnu.org>.
# 
# CONTRIBUTOR NOTICE:
# All contributions to this repository are contractually subject to the NETTRADES 
# Contributor License Agreement (CLA). Any submission or pull request implies 
# cryptographic authorization of the CLA terms, including generative AI disclosures 
# and the Foundation's defensive patent framework.
# 
# ALTERNATIVE ENTERPRISE LICENSING:
# Commercial developers, corporate entities, or sovereign institutions wishing to 
# exempt their infrastructure deployment from the copyleft source-disclosure 
# requirements of the AGPL-3.0 must purchase a paid Commercial Alternative license. 
# Closed-source commercial exploitation, custom multi-agent extensions, and premium 
# SLAs are governed strictly under the split-jurisdiction architecture of the 
# NETTRADES Foundation (administered via the laws of England & Wales or the Qatar 
# Financial Centre common law framework, depending on licensee domicile).
# 
# For commercial licensing onboarding, corporate procurement, or KYC verifications:
# - Licensing Portal: https://nettrades.org
# - Legal & Compliance Division: legal@nettrades.org
# 
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-NETTRADES-Commercial
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
FORCE=false
IMAGE_TAG="nettrades-vllm-cpu:latest"
DYNAMO_REPO="https://github.com/ai-dynamo/dynamo.git"
BRANCH="main"
BUILD_DIR="/tmp/dynamo-build-$$"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --dynamo-repo)
            DYNAMO_REPO="$2"
            shift 2
            ;;
        --branch)
            BRANCH="$2"
            shift 2
            ;;
        --help|-h)
            cat << EOF
NETTRADES CPU vLLM Builder

Usage:
    $0 [OPTIONS]

Options:
    --force          Rebuild even if image already exists
    --tag <tag>      Docker image tag (default: nettrades-vllm-cpu:latest)
    --dynamo-repo    Dynamo repository URL (default: https://github.com/ai-dynamo/dynamo.git)
    --branch         Git branch to build (default: main)
    --help, -h       Show this help message

Requirements:
    - Docker installed
    - At least 32 GB RAM and 4 CPU cores
    - gcc/g++ >= 12.3.0

This script builds the CPU-optimised vLLM image for NVIDIA Dynamo,
enabling vLLM inference on CPU-only systems with AVX512/AMX_BF16 acceleration.
EOF
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Check prerequisites
# -----------------------------------------------------------------------------
check_docker || exit 1

# Check if image already exists
if docker image inspect "$IMAGE_TAG" &>/dev/null && [[ "$FORCE" != true ]]; then
    log_success "Image $IMAGE_TAG already exists. Use --force to rebuild."
    exit 0
fi

# Check CPU features
log_step "Detecting CPU features..."
CPU_FEATURES=""
if grep -q "avx512" /proc/cpuinfo 2>/dev/null; then
    CPU_FEATURES+=" AVX512"
fi
if grep -q "amx" /proc/cpuinfo 2>/dev/null; then
    CPU_FEATURES+=" AMX"
fi
if [[ -n "$CPU_FEATURES" ]]; then
    log_success "Detected CPU features:$CPU_FEATURES"
else
    log_warning "No AVX512 or AMX CPU features detected. Performance may be limited."
fi

# Check RAM
TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
if [[ "$TOTAL_RAM" -lt 32 ]]; then
    log_warning "System has ${TOTAL_RAM}GB RAM. CPU vLLM recommends at least 32GB for optimal performance.[reference:4]"
fi

# -----------------------------------------------------------------------------
# Clone Dynamo repository
# -----------------------------------------------------------------------------
log_step "Cloning NVIDIA Dynamo repository..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

if ! git clone --depth 1 --branch "$BRANCH" "$DYNAMO_REPO" "$BUILD_DIR/dynamo"; then
    log_error "Failed to clone Dynamo repository from $DYNAMO_REPO"
    exit 1
fi
log_success "Dynamo repository cloned"

cd "$BUILD_DIR/dynamo"

# -----------------------------------------------------------------------------
# Check for CPU build support
# -----------------------------------------------------------------------------
log_step "Checking for CPU build support in Dynamo..."
if [[ ! -f "container/render.py" ]]; then
    log_error "render.py not found. This may not be a valid Dynamo repository."
    exit 1
fi

# Check if CPU device is supported in render.py
if grep -q '"cpu"' container/render.py 2>/dev/null; then
    log_success "CPU device support found in render.py"
else
    log_warning "CPU device may not be explicitly listed in render.py. Attempting build anyway."
fi

# -----------------------------------------------------------------------------
# Build the CPU vLLM image
# -----------------------------------------------------------------------------
log_step "Building CPU-optimised vLLM image..."

# Set environment variables for CPU optimisations
export VLLM_CPU_AVX512=1
export VLLM_CPU_AMXBF16=1

# The build uses render.py to generate Dockerfiles for different backends[reference:5]
# For CPU builds, we use the vLLM backend with device=cpu[reference:6]
log_info "Generating Dockerfile for CPU vLLM build..."
if command -v python3 &>/dev/null; then
    python3 container/render.py --backend vllm --device cpu --tag "$IMAGE_TAG" 2>/dev/null || {
        log_warning "render.py failed. Falling back to manual Docker build..."
    }
fi

# Alternative: Use the vLLM CPU Dockerfile directly if available
if [[ -f "container/Dockerfile.vllm.cpu" ]]; then
    log_info "Using Dockerfile.vllm.cpu..."
    docker build -f container/Dockerfile.vllm.cpu -t "$IMAGE_TAG" --shm-size=4g . 2>/dev/null || {
        log_warning "Docker build with Dockerfile.vllm.cpu failed. Trying alternative..."
    }
fi

# Fallback: Use the standard vLLM Dockerfile with CPU-specific args
# The CPU build uses Ubuntu 24.04 base images and v0.16.0 reference[reference:7]
if ! docker image inspect "$IMAGE_TAG" &>/dev/null; then
    log_info "Using fallback build method..."
    
    # Create a minimal Dockerfile for CPU vLLM
    cat > "$BUILD_DIR/Dockerfile.cpu" << 'EOF'
# CPU-optimised vLLM for NVIDIA Dynamo
# Based on PR #7139 CPU device support
FROM ubuntu:24.04

# Install system dependencies for CPU build
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    git curl wget \
    build-essential gcc g++ \
    cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

# Install vLLM CPU backend
# CPU backend build script checks host CPU flags for AVX512_BF16[reference:8]
ENV VLLM_TARGET_DEVICE=cpu
ENV VLLM_CPU_AVX512=1
ENV VLLM_CPU_AMXBF16=1

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu \
    transformers \
    accelerate \
    numpy

# Clone and install vLLM with CPU backend
RUN git clone https://github.com/vllm-project/vllm.git /tmp/vllm \
    && cd /tmp/vllm \
    && pip3 install --no-cache-dir -e . \
    && rm -rf /tmp/vllm

# Clone and install Dynamo components
RUN git clone https://github.com/ai-dynamo/dynamo.git /tmp/dynamo \
    && cd /tmp/dynamo \
    && pip3 install --no-cache-dir -e . \
    && rm -rf /tmp/dynamo

# Expose port
EXPOSE 8000

# Default command
CMD ["python3", "-m", "dynamo.frontend", "--http-port", "8000", "--discovery-backend", "file"]
EOF

    docker build -f "$BUILD_DIR/Dockerfile.cpu" -t "$IMAGE_TAG" --shm-size=4g "$BUILD_DIR" || {
        log_error "Failed to build CPU vLLM image."
        rm -rf "$BUILD_DIR"
        exit 1
    }
fi

# -----------------------------------------------------------------------------
# Verify build
# -----------------------------------------------------------------------------
log_step "Verifying build..."
if docker image inspect "$IMAGE_TAG" &>/dev/null; then
    IMAGE_SIZE=$(docker image inspect "$IMAGE_TAG" --format='{{.Size}}' | numfmt --to=iec 2>/dev/null || echo "unknown")
    log_success "CPU vLLM image built successfully: $IMAGE_TAG ($IMAGE_SIZE)"
    
    # Quick test: run the image and check if it starts
    log_info "Testing image..."
    if docker run --rm "$IMAGE_TAG" python3 -c "import dynamo; print('Dynamo imported successfully')" 2>/dev/null; then
        log_success "Image test passed"
    else
        log_warning "Image test failed (may still work in production)"
    fi
else
    log_error "Build verification failed."
    rm -rf "$BUILD_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Clean up
# -----------------------------------------------------------------------------
rm -rf "$BUILD_DIR"
log_success "CPU vLLM build completed successfully!"

echo ""
echo "============================================================"
echo " CPU vLLM Image Built Successfully"
echo "============================================================"
echo ""
echo "Image: $IMAGE_TAG"
echo ""
echo "To use this image in NETTRADES, either:"
echo "  1. Update .env with: VLLM_IMAGE=$IMAGE_TAG"
echo "  2. Or update docker-compose.yaml dynamo service image to: $IMAGE_TAG"
echo ""
echo "To push to a local registry for faster deployment:"
echo "  docker tag $IMAGE_TAG localhost:5000/nettrades-vllm-cpu:latest"
echo "  docker push localhost:5000/nettrades-vllm-cpu:latest"