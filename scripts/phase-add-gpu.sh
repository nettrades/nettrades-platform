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
# Set up paths early (so they are available for all steps)
# -----------------------------------------------------------------------------
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"

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
# Ensure model is available for vLLM (shared with llama.cpp)
# -----------------------------------------------------------------------------
log_step "Ensuring model is available for vLLM..."

SHARED_MODELS_DIR="$DEPLOY_DIR/models"
MODEL_NAME="${MODEL_NAME:-deepseek-1.5b}"

if [[ ! -f "$SHARED_MODELS_DIR/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf" ]]; then
    log_info "Model not found in shared directory. Downloading..."
    if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
        bash "$SCRIPT_DIR/download-model.sh" --model "$MODEL_NAME" --dir "$SHARED_MODELS_DIR"
    else
        log_warning "download-model.sh not found – please place the model manually."
    fi
else
    log_success "Model found in shared directory."
fi

# -----------------------------------------------------------------------------
# Update .env with GPU variables (BEFORE migration)
# -----------------------------------------------------------------------------
log_step "Updating .env for GPU inference..."

cd "$DEPLOY_DIR"

# Add VLLM_API_KEY and VLLM_BASE_URL if missing
if ! grep -q "^VLLM_API_KEY=" .env; then
    echo "VLLM_API_KEY=dummy" >> .env
fi
if ! grep -q "^VLLM_BASE_URL=" .env; then
    echo "VLLM_BASE_URL=http://vllm:8000/v1" >> .env
fi

# Set LLM_BASE_URL for LangGraph (override the default fallback)
if grep -q "^LLM_BASE_URL=" .env; then
    sed -i 's|^LLM_BASE_URL=.*|LLM_BASE_URL=http://vllm:8000/v1|' .env
else
    echo "LLM_BASE_URL=http://vllm:8000/v1" >> .env
fi

log_success ".env updated for GPU inference"

# -----------------------------------------------------------------------------
# Check NVIDIA Container Toolkit (optional – migrate-to-gpu.sh also does this)
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
# Run GPU migration (now .env is already set)
# This also adds /usr/lib/wsl/lib to the PATH when running under sudo, without breaking other environments.
# -----------------------------------------------------------------------------
log_step "Running GPU migration..."
if [[ -f "$SCRIPT_DIR/migrate-to-gpu.sh" ]]; then
    # Ensure WSL path is included for sudo
    export WSL_PATH="/usr/lib/wsl/lib"
    if [[ "$AUTO" == true ]]; then
        sudo -E env PATH="$PATH:$WSL_PATH" bash "$SCRIPT_DIR/migrate-to-gpu.sh" --auto
    else
        sudo -E env PATH="$PATH:$WSL_PATH" bash "$SCRIPT_DIR/migrate-to-gpu.sh"
    fi
else
    log_error "migrate-to-gpu.sh not found in $SCRIPT_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Restart LangGraph to ensure it picks up the new LLM_BASE_URL
# (Even though .env was updated before the compose up, restart to be safe)
# -----------------------------------------------------------------------------
log_step "Restarting LangGraph to apply GPU configuration..."
cd "$DEPLOY_DIR"
docker compose restart langgraph

# -----------------------------------------------------------------------------
# Verify vLLM is running
# -----------------------------------------------------------------------------
log_step "Verifying vLLM deployment..."
sleep 10
if curl -s http://localhost:8001/health >/dev/null 2>&1; then
    log_success "vLLM is running and healthy"
else
    log_warning "vLLM health check failed – please check logs"
fi

# -----------------------------------------------------------------------------
# Configure GPUStack for distributed GPU orchestration (optional)
# -----------------------------------------------------------------------------
if [[ -f "$DEPLOY_DIR/gpustack-config.yaml" ]]; then
    log_step "Configuring GPUStack..."
    log_info "GPUStack configuration found at $DEPLOY_DIR/gpustack-config.yaml"
    if [[ "$FORCE" == true ]] || ! docker exec gpustack gpustack status &>/dev/null; then
        docker compose restart gpustack
        log_success "GPUStack restarted"
    fi
else
    log_warning "gpustack-config.yaml not found – skipping GPUStack configuration"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
cd "$PROJECT_ROOT"
mark_phase_complete 3
log_success "Phase 3 completed – GPU migration successful"
echo ""
echo "  GPU:           $GPU_NAME"
echo "  Inference:     vLLM (GPU)"
echo "  GPUStack:      $(docker compose -f "$DEPLOY_DIR/docker-compose.yaml" ps gpustack --format '{{.Status}}' 2>/dev/null || echo 'unknown')"
echo ""
echo "Next steps:"
echo "  - LangGraph is now using vLLM at http://vllm:8000/v1"
echo "  - To revert to CPU, uncomment the llama-cpp service in docker-compose.yaml and remove vLLM"