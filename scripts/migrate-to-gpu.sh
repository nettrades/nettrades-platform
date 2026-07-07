# =============================================================================
# FILE: scripts/migrate-to-gpu.sh
# =============================================================================
# PURPOSE:
#   Migrates the inference engine from CPU (llama.cpp) to GPU (vLLM).
#   This script is IDEMPOTENT and can be re-run safely.
#
#   Steps performed:
#     1. Check for root privileges (NVIDIA toolkit installation requires sudo).
#     2. Detect NVIDIA GPU and verify drivers.
#     3. Install NVIDIA Container Toolkit if missing.
#     4. Configure Docker to use NVIDIA runtime.
#     5. Stop and remove the llama-cpp container.
#     6. (Optional) Comment out the llama-cpp service in docker-compose.yaml.
#     7. Ensure directories for both engines exist.
#     8. Download the Hugging Face model for vLLM (if not already present).
#     9. Add vLLM service definition to docker-compose.yaml.
#     10. Start the stack with vLLM.
#     11. Verify vLLM health.
#
#   This script does NOT modify .env – that is handled by phase-add-gpu.sh.
#   All model files for vLLM are stored in ./vllm-data (separate from llama-cpp).
#
# USAGE:
#   ./migrate-to-gpu.sh [--auto]
#     --auto: Skip confirmation prompts.
# =============================================================================

set -euo pipefail
mkdir -p ./llama-cpp-data/models ./vllm-data/models

# -----------------------------------------------------------------------------
# Source shared libraries (with fallback)
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_DIR/lib/colors.sh" ]]; then
    source "$SCRIPT_DIR/lib/colors.sh"
else
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
fi

if [[ -f "$SCRIPT_DIR/lib/logging.sh" ]]; then
    source "$SCRIPT_DIR/lib/logging.sh"
else
    log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
    log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
    log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
    log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
fi

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
    log_error "This script must be run as root (use sudo)."
    exit 1
fi

# -----------------------------------------------------------------------------
# Detect NVIDIA GPU using full path (handles WSL, Ubuntu, Talos)
# -----------------------------------------------------------------------------
find_nvidia_smi() {
    # List of possible locations (including WSL2)
    local candidates=(
        nvidia-smi
        /usr/bin/nvidia-smi
        /usr/local/bin/nvidia-smi
        /usr/lib/wsl/lib/nvidia-smi
    )
    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    return 1
}

NVIDIA_SMI=$(find_nvidia_smi)
if [ -z "$NVIDIA_SMI" ]; then
    log_error "nvidia-smi not found. NVIDIA drivers may not be installed."
    log_info "Please install NVIDIA drivers first."
    exit 1
fi

# Verify that the GPU is accessible
if ! $NVIDIA_SMI &>/dev/null; then
    log_error "nvidia-smi failed. NVIDIA GPU may not be available."
    exit 1
fi

GPU_NAME=$($NVIDIA_SMI --query-gpu=name --format=csv,noheader | head -1)
log_success "NVIDIA GPU detected: ${GPU_NAME}"

# -----------------------------------------------------------------------------
# Check if already migrated (vLLM container exists)
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
log_step "Checking NVIDIA Container Toolkit..."
if command -v nvidia-ctk &>/dev/null; then
    log_success "NVIDIA Container Toolkit already installed."
else
    log_info "Installing NVIDIA Container Toolkit..."
    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
    log_success "NVIDIA Container Toolkit installed"
fi

# -----------------------------------------------------------------------------
# Configure Docker to use NVIDIA runtime
# -----------------------------------------------------------------------------
log_step "Configuring Docker for NVIDIA runtime..."
if docker info 2>/dev/null | grep -q "nvidia"; then
    log_info "Docker already configured for NVIDIA runtime."
else
    log_info "Configuring Docker..."
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    log_success "Docker configured for NVIDIA runtime"
fi

# -----------------------------------------------------------------------------
# Stop and remove llama-cpp container
# -----------------------------------------------------------------------------
log_step "Stopping and removing llama-cpp container..."
if docker ps -a --format '{{.Names}}' | grep -q "llama-cpp"; then
    docker stop llama-cpp 2>/dev/null || true
    docker rm llama-cpp 2>/dev/null || true
    log_success "llama-cpp container removed"
else
    log_info "llama-cpp container not running – skipping."
fi

# -----------------------------------------------------------------------------
# Comment out llama-cpp service in docker-compose.yaml
# -----------------------------------------------------------------------------
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
cd "$DEPLOY_DIR"

COMPOSE_FILE="docker-compose.yaml"

if grep -q "^  llama-cpp:" "$COMPOSE_FILE"; then
    log_info "Commenting out llama-cpp service to prevent accidental re-creation..."
    sed -i '/^  llama-cpp:/,/^  [^ ]/ s/^/# /' "$COMPOSE_FILE"
    log_success "llama-cpp service commented out."
else
    log_info "llama-cpp service not found in compose file – skipping."
fi

# -----------------------------------------------------------------------------
# Ensure directories for both engines exist
# -----------------------------------------------------------------------------
mkdir -p ./llama-cpp-data ./vllm-data
log_info "Ensured directories: ./llama-cpp-data and ./vllm-data exist."

# -----------------------------------------------------------------------------
# Download Hugging Face model for vLLM into ./vllm-data/models
# -----------------------------------------------------------------------------
log_step "Downloading Hugging Face model for vLLM..."

if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
    if ! bash "$SCRIPT_DIR/download-model.sh" --model deepseek-1.5b --format hf --dir ./vllm-data/models; then
        log_warning "HF model download failed. Please download manually."
        if [ "$AUTO" != true ]; then
            read -rp "Continue anyway? (y/N): " continue_anyway
            if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
                exit 1
            fi
        fi
    else
        log_success "HF model downloaded successfully into ./vllm-data/models"
    fi
else
    log_error "download-model.sh not found. Please ensure it exists in $SCRIPT_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Add vLLM service to docker-compose.yaml (if not already present)
# -----------------------------------------------------------------------------
log_step "Adding vLLM service to docker-compose.yaml..."

if grep -q "vllm:" "$COMPOSE_FILE"; then
    log_info "vLLM service already present in docker-compose.yaml"
else
    cp "$COMPOSE_FILE" "${COMPOSE_FILE}.bak"
    cat >> "$COMPOSE_FILE" << 'EOF'

  vllm:
    image: vllm/vllm-openai:latest
    container_name: vllm
    restart: unless-stopped
    ports:
      - "8001:8000"
    networks:
      - internal
    volumes:
      - ./vllm-data/models:/models          # Mount the models subfolder
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
    log_success "vLLM service added to docker-compose.yaml"
fi

# -----------------------------------------------------------------------------
# Start the new stack (will start vLLM, and everything else)
# -----------------------------------------------------------------------------
log_step "Starting Docker Compose stack with vLLM..."
docker compose up -d

# -----------------------------------------------------------------------------
# Verify vLLM is running (using the host port 8001)
# -----------------------------------------------------------------------------
log_step "Verifying vLLM health..."
sleep 10
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health 2>/dev/null | grep -q "200"; then
    log_success "vLLM is healthy and responding"
else
    log_warning "vLLM health check failed – please check logs with: docker compose logs vllm"
fi

# -----------------------------------------------------------------------------
# Display completion message
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}=============================================================${NC}"
echo -e "${GREEN} GPU migration complete!${NC}"
echo -e "${GREEN}=============================================================${NC}"
echo ""
echo " GPU:           ${GPU_NAME}"
echo " Inference:     vLLM (GPU)"
echo " API endpoint:  http://vllm:8000/v1"
echo " Model folder:  ./vllm-data/DeepSeek-R1-Distill-Qwen-1.5B"
echo ""
echo "Next steps:"
echo "  1. Ensure LLM_BASE_URL is updated in .env (handled by phase-add-gpu.sh)"
echo "  2. Restart LangGraph to pick up the new URL: docker compose restart langgraph"
echo ""
log_info "If you want to revert to CPU, uncomment the llama-cpp service in docker-compose.yaml"
echo "and remove the vLLM service, then run: docker compose up -d"