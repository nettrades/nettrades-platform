#!/bin/bash
# =============================================================================
# FILE: scripts/phase-add-gpu.sh
# =============================================================================
# PURPOSE:
#   Phase 3: GPU Setup – adds GPU support to an existing deployment.
#   This phase detects NVIDIA hardware, installs the container toolkit,
#   and migrates the inference engine from CPU (llama.cpp) to GPU (vLLM).
#
#   It is called by nettrades-setup.sh and is idempotent – it can be re-run
#   safely. Phase 2 is a prerequisite, but if not completed this script will
#   automatically run it.
#
# USAGE:
#   ./phase-add-gpu.sh [--force] [--auto]
#
#   --force  Re-run migration even if phase marker exists.
#   --auto   Run in non-interactive mode (skip confirmations).
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours for output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
FORCE=false
AUTO=false
for arg in "$@"; do
    case $arg in
        --force)
            FORCE=true
            shift
            ;;
        --auto)
            AUTO=true
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Get script directory and project root
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"

# -----------------------------------------------------------------------------
# Phase completion marker
# -----------------------------------------------------------------------------
PHASE_MARKER="$PROJECT_ROOT/.phase-3-complete"
if [ -f "$PHASE_MARKER" ] && [ "$FORCE" != true ]; then
    log_warning "Phase 3 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Ensure Phase 2 (deployment) is complete – if not, run it automatically
# -----------------------------------------------------------------------------
if [ ! -f "$DEPLOY_DIR/.env" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    log_info "Phase 2 not completed. Running phase-deploy.sh automatically..."
    cd "$SCRIPT_DIR"
    if [ "$AUTO" = true ]; then
        bash phase-deploy.sh --auto
    else
        bash phase-deploy.sh
    fi
    cd "$PROJECT_ROOT"
fi

# -----------------------------------------------------------------------------
# Ensure Docker Compose stack is running
# -----------------------------------------------------------------------------
cd "$DEPLOY_DIR"
if ! docker compose ps &>/dev/null; then
    log_error "Docker Compose stack is not running. Please start it first."
    exit 1
fi
cd "$PROJECT_ROOT"

# -----------------------------------------------------------------------------
# Detect NVIDIA GPU
# -----------------------------------------------------------------------------
if ! command -v nvidia-smi &>/dev/null; then
    log_error "nvidia-smi not found. NVIDIA drivers may not be installed."
    log_info "Please install NVIDIA drivers first."
    if [ "$AUTO" != true ]; then
        read -rp "Continue anyway? (y/N): " continue_anyway
        if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    # Proceed anyway, but migration will likely fail.
fi

if nvidia-smi &>/dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    log_success "NVIDIA GPU detected: ${GPU_NAME}"
else
    GPU_NAME="unknown"
    log_warning "nvidia-smi failed – no GPU detected or driver issue."
fi

# -----------------------------------------------------------------------------
# Run GPU migration (uses sudo for NVIDIA toolkit installation)
# -----------------------------------------------------------------------------
cd "$DEPLOY_DIR"

if [ -f "migrate-to-gpu.sh" ]; then
    log_info "Running migrate-to-gpu.sh..."
    if [ "$AUTO" = true ]; then
        sudo bash migrate-to-gpu.sh --auto
    else
        sudo bash migrate-to-gpu.sh
    fi
else
    log_error "migrate-to-gpu.sh not found in $DEPLOY_DIR"
    exit 1
fi

cd "$PROJECT_ROOT"

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
echo "$(date -Iseconds)" > "$PHASE_MARKER"
log_success "Phase 3 completed"

echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}  Phase 3 completed successfully!${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo "  GPU:           ${GPU_NAME}"
echo "  Inference:     vLLM (GPU)"
echo ""
echo "Next steps:"
echo "  1. Update LLM_BASE_URL in .env to use vLLM:"
echo "     LLM_BASE_URL=http://vllm:8000/v1"
echo "  2. Restart the langgraph service:"
echo "     docker compose restart langgraph"