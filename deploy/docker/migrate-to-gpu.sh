#!/bin/bash
# =============================================================================
# FILE: deploy/docker/migrate-to-gpu.sh
# =============================================================================
# PURPOSE:
#   Migrates the inference engine from CPU (llama.cpp) to GPU (vLLM).
#   This script is IDEMPOTENT and can be re-run safely. It checks for
#   existing GPU support before making changes.
#
#   It detects an NVIDIA GPU, installs the NVIDIA Container Toolkit,
#   stops and removes the llama-cpp container, adds the vLLM service,
#   and regenerates the .env file.
#
# USAGE:
#   ./migrate-to-gpu.sh [--auto]
#     --auto: Skip confirmation prompts.
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
AUTO=false
for arg in "$@"; do
    case $arg in
        --auto)
            AUTO=true
            shift
            ;;
    esac
done

# -----------------------------------------------------------------------------
# Check if running as root (required for NVIDIA toolkit installation)
# -----------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (sudo)."
    exit 1
fi

# -----------------------------------------------------------------------------
# Detect NVIDIA GPU
# -----------------------------------------------------------------------------
if ! command -v nvidia-smi &>/dev/null; then
    log_error "nvidia-smi not found. NVIDIA drivers may not be installed."
    log_info "Please install NVIDIA drivers first."
    exit 1
fi

if ! nvidia-smi &>/dev/null; then
    log_error "nvidia-smi failed. NVIDIA GPU may not be available."
    exit 1
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
log_success "NVIDIA GPU detected: ${GPU_NAME}"

# -----------------------------------------------------------------------------
# Check if already migrated
# -----------------------------------------------------------------------------
if docker ps -a --format '{{.Names}}' | grep -q "vllm"; then
    log_info "vLLM container already exists. Already migrated to GPU?"
    if [ "$AUTO" != true ]; then
        read -rp "Re-run migration anyway? (y/N): " re_run
        if [[ ! "$re_run" =~ ^[Yy]$ ]]; then
            log_info "Skipping migration."
            exit 0
        fi
    fi
fi

# -----------------------------------------------------------------------------
# Install NVIDIA Container Toolkit
# -----------------------------------------------------------------------------
if command -v nvidia-ctk &>/dev/null; then
    log_info "NVIDIA Container Toolkit already installed."
else
    log_info "Installing NVIDIA Container Toolkit..."
    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
    log_success "NVIDIA Container Toolkit installed"
fi

# -----------------------------------------------------------------------------
# Configure Docker to use NVIDIA runtime
# -----------------------------------------------------------------------------
if docker info | grep -q "runc" && docker info | grep -q "nvidia"; then
    log_info "Docker already configured for NVIDIA runtime."
else
    log_info "Configuring Docker for NVIDIA runtime..."
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    log_success "Docker configured for NVIDIA runtime"
fi

# -----------------------------------------------------------------------------
# Stop and remove llama-cpp container
# -----------------------------------------------------------------------------
if docker ps -a --format '{{.Names}}' | grep -q "llama-cpp"; then
    log_info "Stopping and removing llama-cpp container..."
    docker stop llama-cpp 2>/dev/null || true
    docker rm llama-cpp 2>/dev/null || true
    log_success "llama-cpp container removed"
fi

# -----------------------------------------------------------------------------
# Add vLLM service to docker-compose.yml
# -----------------------------------------------------------------------------
COMPOSE_FILE="docker-compose.yml"
if grep -q "vllm:" "$COMPOSE_FILE"; then
    log_info "vLLM service already present in docker-compose.yml"
else
    log_info "Adding vLLM service to docker-compose.yml..."
    # Create a backup
    cp "$COMPOSE_FILE" "${COMPOSE_FILE}.bak"
    # Insert vLLM service before the last service
    cat >> "$COMPOSE_FILE" << 'EOF'

  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm
    restart: unless-stopped
    ports:
      - "8000:8000"
    networks:
      - internal
    volumes:
      - ./vllm-data:/models
    environment:
      - VLLM_MODEL=/models/DeepSeek-R1-Distill-Qwen-1.5B
      - VLLM_GPU_MEMORY_UTILIZATION=0.9
      - VLLM_MAX_MODEL_LEN=4096
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    command: ["--model", "/models/DeepSeek-R1-Distill-Qwen-1.5B", "--tensor-parallel-size", "1"]
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
EOF
    log_success "vLLM service added to docker-compose.yml"
fi

# -----------------------------------------------------------------------------
# Update .env with GPU variables
# -----------------------------------------------------------------------------
if grep -q "VLLM_API_KEY" .env; then
    log_info "VLLM_API_KEY already set in .env"
else
    log_info "Adding VLLM_API_KEY to .env..."
    echo "VLLM_API_KEY=dummy" >> .env
    echo "VLLM_BASE_URL=http://vllm:8000/v1" >> .env
    log_success ".env updated"
fi

# -----------------------------------------------------------------------------
# Start the new stack
# -----------------------------------------------------------------------------
log_info "Starting Docker Compose stack with vLLM..."
docker compose up -d

echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN}  GPU migration complete!${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo "  GPU:           ${GPU_NAME}"
echo "  Inference:     vLLM (GPU)"
echo "  API endpoint:  http://localhost:8000/v1"
echo ""
log_info "Note: You may need to update LLM_BASE_URL in .env to use vLLM."