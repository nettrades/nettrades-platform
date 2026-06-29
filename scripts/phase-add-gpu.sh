#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 3: Add GPU to Existing Deployment
# =============================================================================
# FILE: scripts/phase-add-gpu.sh
#
# PURPOSE:
#   Detects an NVIDIA GPU, installs the container toolkit, migrates
#   inference from llama.cpp (CPU) to vLLM (GPU), and enables GPUStack
#   workers on the GPU.
#
# CHECKS:
#   • Phase 2 (single-VM deployment) has been run — if not, runs it first.
#   • An NVIDIA GPU is present and drivers are installed.
#   • The docker-compose stack is currently running.
#
# USAGE:
#   ./scripts/phase-add-gpu.sh [--force]
#
# OPTIONS:
#   --force    Re-run even if already completed (idempotency).
#
# =============================================================================

set -euo pipefail

# Phase completion marker
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PLATFORM_DIR/deploy/docker"
PHASE_MARKER="$PLATFORM_DIR/.phase-3-complete"

# Check for --force flag
FORCE=false
for arg in "$@"; do
    if [[ "$arg" == "--force" ]]; then
        FORCE=true
    fi
done

# If phase already completed and not forcing, exit
if [ -f "$PHASE_MARKER" ] && [ "$FORCE" != true ]; then
    echo -e "${YELLOW}[WARNING] Phase 3 already completed. Use --force to re-run.${NC}"
    exit 0
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# =============================================================================
# Ensure Phase 2 is done
# =============================================================================
if [ ! -f "$DEPLOY_DIR/.env" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    echo -e "${YELLOW}Phase 2 (single-VM deployment) has not been run yet.${NC}"
    echo "Running it now automatically — this will deploy the stack WITHOUT a GPU."
    echo "After it completes, the GPU migration will run."
    echo ""
    bash "$SCRIPT_DIR/phase-deploy.sh"
fi

# =============================================================================
# Pre-flight: NVIDIA GPU must be present
# =============================================================================
if ! command -v nvidia-smi &>/dev/null; then
    echo -e "${RED}ERROR: nvidia-smi not found. NVIDIA drivers are not installed.${NC}"
    echo "Install NVIDIA drivers: https://www.nvidia.com/download/index.aspx"
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    echo -e "${RED}ERROR: NVIDIA GPU not detected or drivers not loaded.${NC}"
    echo "Run 'nvidia-smi' manually to verify."
    exit 1
fi

echo -e "${GREEN}NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)${NC}"

# =============================================================================
# Pre-flight: docker-compose stack should be running
# =============================================================================
cd "$DEPLOY_DIR"
if ! docker compose ps 2>/dev/null | grep -q "Up"; then
    echo -e "${RED}ERROR: The Docker Compose stack is not running.${NC}"
    echo "Run 'docker compose up -d' first."
    exit 1
fi

# =============================================================================
# GPU migration
# =============================================================================
echo ""
echo "=== Running GPU migration ==="
sudo bash "$DEPLOY_DIR/migrate-to-gpu.sh"

echo ""
echo -e "${GREEN}GPU migration complete. Inference now uses vLLM.${NC}"

# Mark phase complete
echo "$(date -Iseconds)" > "$PHASE_MARKER"

echo ""
echo "Next steps:"
echo "  1. Update LLM_BASE_URL in .env to use vLLM:"
echo "     LLM_BASE_URL=http://vllm:8000/v1"
echo "  2. Restart the langgraph service:"
echo "     docker compose restart langgraph"