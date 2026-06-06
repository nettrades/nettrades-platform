#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 3: Add GPU to Existing Deployment
# =============================================================================
# Detects an NVIDIA GPU, installs the container toolkit, migrates
# inference from llama.cpp (CPU) to vLLM (GPU), and enables GPUStack
# workers on the GPU.
#
# Checks:
#   • Phase 2 (single-VM deployment) has been run — if not, runs it first.
#   • An NVIDIA GPU is present and drivers are installed.
#   • The docker-compose stack is currently running.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PLATFORM_DIR/deploy/docker"

# Ensure Phase 2 is done
if [ ! -f "$DEPLOY_DIR/.env" ] || [ ! -f "$DEPLOY_DIR/docker-compose.yml" ]; then
    echo "Phase 2 (single-VM deployment) has not been run yet."
    echo "Running it now automatically — this will deploy the stack WITHOUT a GPU."
    echo "After it completes, the GPU migration will run."
    echo ""
    bash "$SCRIPT_DIR/phase-deploy.sh"
fi

# Pre-flight: NVIDIA GPU must be present
if ! command -v nvidia-smi &>/dev/null; then
    echo "ERROR: nvidia-smi not found.  NVIDIA drivers are not installed." >&2
    echo "Install NVIDIA drivers: https://www.nvidia.com/download/index.aspx" >&2
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    echo "ERROR: NVIDIA GPU not detected or drivers not loaded." >&2
    echo "Run 'nvidia-smi' manually to verify." >&2
    exit 1
fi

echo "NVIDIA GPU detected: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

# Pre-flight: docker-compose stack should be running
cd "$DEPLOY_DIR"
if ! docker compose ps 2>/dev/null | grep -q "Up"; then
    echo "ERROR: The Docker Compose stack is not running." >&2
    echo "Run 'docker compose up -d' first." >&2
    exit 1
fi

# GPU migration
echo "=== Running GPU migration ==="
sudo bash "$DEPLOY_DIR/migrate-to-gpu.sh"

echo ""
echo "GPU migration complete.  Inference now uses vLLM."