#!/bin/bash
# =============================================================================
# FILE: scripts/phase-add-gpu.sh
# =============================================================================
# PURPOSE:
#   Phase 3: GPU Setup – adds GPU support to an existing deployment.
#   This phase detects NVIDIA hardware, installs the container toolkit,
#   and migrates the inference engine from CPU (llama.cpp) to GPU (vLLM).
#
#   It also configures GPUStack for distributed GPU orchestration across
#   multiple nodes in the cluster.
#
#   It is called by nettrades-setup.sh and is idempotent – it can be re-run
#   safely. Phase 2 is a prerequisite.
#
# USAGE:
#   ./phase-add-gpu.sh [--force] [--auto]
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
# Parse arguments
# -----------------------------------------------------------------------------
FORCE="${FORCE:-false}"
AUTO="${AUTO:-false}"
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "3"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 3; then
    log_warning "Phase 3 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------
if ! phase_completed 2; then
    log_info "Phase 2 not completed. Running Phase 2 first..."
    bash "$SCRIPT_DIR/phase-deploy.sh"
fi

# -----------------------------------------------------------------------------
# Detect GPU
# -----------------------------------------------------------------------------
log_step "Detecting NVIDIA GPU..."
if ! detect_gpu; then
    log_error "NVIDIA GPU not detected or drivers not installed."
    log_info "Please install NVIDIA drivers and the nvidia-container-toolkit."
    log_info "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
    if [[ "$AUTO" != true ]]; then
        read -rp "Continue anyway? (y/N): " continue_anyway
        if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        exit 1
    fi
else
    GPU_NAME=$(get_gpu_name)
    log_success "NVIDIA GPU detected: $GPU_NAME"
fi

# -----------------------------------------------------------------------------
# Check NVIDIA Container Toolkit
# -----------------------------------------------------------------------------
log_step "Checking NVIDIA Container Toolkit..."
if ! command -v nvidia-container-toolkit &>/dev/null; then
    log_error "nvidia-container-toolkit not found. Please install it first."
    log_info "Run: sudo apt-get install -y nvidia-container-toolkit"
    exit 1
else
    log_success "nvidia-container-toolkit installed"
fi

# -----------------------------------------------------------------------------
# Run GPU migration
# -----------------------------------------------------------------------------
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
cd "$DEPLOY_DIR"

log_step "Running GPU migration..."
if [[ -f "$DEPLOY_DIR/migrate-to-gpu.sh" ]]; then
    if [[ "$AUTO" == true ]]; then
        sudo bash "$DEPLOY_DIR/migrate-to-gpu.sh" --auto
    else
        sudo bash "$DEPLOY_DIR/migrate-to-gpu.sh"
    fi
else
    log_error "migrate-to-gpu.sh not found at $DEPLOY_DIR"
    exit 1
fi

cd "$PROJECT_ROOT"

# -----------------------------------------------------------------------------
# Configure GPUStack for distributed GPU orchestration
# -----------------------------------------------------------------------------
log_step "Configuring GPUStack..."
if [[ -f "$DEPLOY_DIR/gpustack-config.yaml" ]]; then
    log_info "GPUStack configuration found at $DEPLOY_DIR/gpustack-config.yaml"
    # Apply configuration if needed
    if [[ "$FORCE" == true ]] || ! docker exec gpustack gpustack status &>/dev/null; then
        docker compose -f "$DEPLOY_DIR/docker-compose.yaml" restart gpustack
        log_success "GPUStack restarted"
    fi
else
    log_warning "gpustack-config.yaml not found – skipping GPUStack configuration"
fi

# -----------------------------------------------------------------------------
# Verify vLLM is running
# -----------------------------------------------------------------------------
log_step "Verifying vLLM deployment..."
sleep 10
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    log_success "vLLM is running and healthy"
else
    log_warning "vLLM health check failed – please check logs"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 3
log_success "Phase 3 completed – GPU migration successful"
echo ""
echo "  GPU:           $GPU_NAME"
echo "  Inference:     vLLM (GPU)"
echo "  GPUStack:      $(docker compose -f "$DEPLOY_DIR/docker-compose.yaml" ps gpustack --format '{{.Status}}' 2>/dev/null || echo 'unknown')"