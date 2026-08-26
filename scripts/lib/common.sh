#!/bin/bash
# =============================================================================
# FILE: scripts/lib/common.sh
# =============================================================================
# PURPOSE:
#   Shared utility functions for all phase scripts.
#   Sourced by nettrades-setup.sh and all phase-*.sh scripts.
# =============================================================================

# Source logging if not already loaded
if [[ -z "${log_info:-}" ]]; then
    source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logging.sh"
fi

# -----------------------------------------------------------------------------
# OS Detection
# -----------------------------------------------------------------------------
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# -----------------------------------------------------------------------------
# Platform Detection (for cross-platform decisions)
# -----------------------------------------------------------------------------
detect_platform() {
    local os
    os=$(detect_os)
    if [[ "$os" == "linux" ]]; then
        if grep -qi "microsoft" /proc/version 2>/dev/null; then
            echo "wsl"
        else
            echo "linux"
        fi
    elif [[ "$os" == "darwin" ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

# -----------------------------------------------------------------------------
# WSL Detection
# -----------------------------------------------------------------------------
detect_wsl() {
    if grep -qi "microsoft" /proc/version 2>/dev/null; then
        echo "true"
    else
        echo "false"
    fi
}

# -----------------------------------------------------------------------------
# GPU Detection
# -----------------------------------------------------------------------------
detect_gpu() {
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        return 0
    else
        return 1
    fi
}

get_gpu_name() {
    if detect_gpu; then
        nvidia-smi --query-gpu=name --format=csv,noheader | head -1
    else
        echo "none"
    fi
}

# -----------------------------------------------------------------------------
# Phase Marker Functions (idempotency)
# -----------------------------------------------------------------------------
get_phase_marker() {
    local phase="$1"
    echo "$PROJECT_ROOT/.phase-${phase}-complete"
}

phase_completed() {
    local phase="$1"
    local marker="$PROJECT_ROOT/.phase-${phase}-complete"
    if [[ -f "$marker" ]] && [[ "${FORCE:-false}" != "true" ]]; then
        return 0
    else
        return 1
    fi
}

mark_phase_complete() {
    local phase="$1"
    local marker
    marker=$(get_phase_marker "$phase")
    echo "$(date -Iseconds)" > "$marker"
    log_success "Phase $phase completed"
}

confirm_force_production() {
    local phase_name="$1"
    local env="${ENVIRONMENT:-development}"
    if [[ "${FORCE:-false}" != "true" ]]; then
        return 0
    fi
    if [[ "$env" == "production" ]]; then
        echo ""
        echo "      WARNING      "
        echo ""
        echo "You are running '--force' on Phase $phase_name in a PRODUCTION environment."
        echo "This will OVERWRITE existing configuration and may cause data loss."
        echo ""
        echo "This action CANNOT be undone."
        echo ""
        read -p "Type 'YES' to continue: " CONFIRM
        if [[ "$CONFIRM" != "YES" ]]; then
            echo "Aborted."
            exit 1
        fi
        echo ""
    fi
}

# -----------------------------------------------------------------------------
# Checks for a valid domain name or IP address, forcing auto-detection
# -----------------------------------------------------------------------------

is_valid_domain_or_ip() {
    local domain="$1"
    # Accept IPs (IPv4), localhost, and valid domain names with dots
    if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$domain" == "localhost" ]]; then
        return 0
    fi
    if [[ "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$ ]]; then
        return 0
    fi
    return 1
}

# -----------------------------------------------------------------------------
# Docker & Kubernetes Tool Checks
# -----------------------------------------------------------------------------
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker not found. Please install Docker."
        return 1
    fi
    if ! docker info &>/dev/null; then
        log_error "Docker daemon not running."
        return 1
    fi
    return 0
}

check_kubectl() {
    if ! command -v kubectl &>/dev/null; then
        log_error "kubectl not found. Please install kubectl."
        return 1
    fi
    return 0
}

check_helm() {
    if ! command -v helm &>/dev/null; then
        log_error "helm not found. Please install helm."
        return 1
    fi
    return 0
}

check_talosctl() {
    if ! command -v talosctl &>/dev/null; then
        log_error "talosctl not found. Please install talosctl."
        return 1
    fi
    return 0
}

# -----------------------------------------------------------------------------
# WireGuard Helper
# -----------------------------------------------------------------------------
generate_wireguard_key() {
    if command -v wg &>/dev/null; then
        wg genkey | tr -d '\n'
    else
        openssl rand -base64 32 | tr -d '\n'
    fi
}

# -----------------------------------------------------------------------------
# Secret Generation
# -----------------------------------------------------------------------------
generate_secret() {
    openssl rand -base64 32 | tr -d '\n'
}

generate_password() {
    openssl rand -base64 24 | tr -d '\n'
}

# =============================================================================
# SAFE SED REPLACEMENT – ROBUST VERSION USING PYTHON
# =============================================================================
# Replaces a line in a .env file with a new value, properly quoting the value.
# Handles ANY special character (including single quotes, backslashes, etc.)
# without breaking the shell or sed.
#
# Usage: safe_sed_replace <file> <key> <new_value>
# Example: safe_sed_replace .env POSTGRES_PASSWORD "p@ssw'ord"
# =============================================================================
safe_sed_replace() {
    local file="$1"
    local pattern="$2"
    local replacement="$3"
    # Use Python to safely replace the line
    python3 -c "
import sys
file, pattern, repl = sys.argv[1], sys.argv[2], sys.argv[3]
with open(file, 'r') as f:
    lines = f.readlines()
with open(file, 'w') as f:
    for line in lines:
        if line.startswith(pattern + '='):
            # Use repr to safely quote the replacement (handles all special chars)
            f.write(f'{pattern}={repr(repl)}\n')
        else:
            f.write(line)
" "$file" "$pattern" "$replacement"
}

# -----------------------------------------------------------------------------
# Model Download Functions
# -----------------------------------------------------------------------------
download_llm_model() {
    local model_name="$1"
    local output_dir="$2"
    local force="${3:-false}"
    
    # Map model names to Hugging Face URLs
    case "$model_name" in
        "deepseek-1.5b")
            local MODEL_URL="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
            local MODEL_FILE="DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
            ;;
        "deepseek-7b")
            local MODEL_URL="https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"
            local MODEL_FILE="deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
            ;;
        *)
            log_error "Unknown model: $model_name"
            return 1
            ;;
    esac
    
    mkdir -p "$output_dir"
    local output_path="$output_dir/$MODEL_FILE"
    
    if [[ -f "$output_path" ]] && [[ "$force" != "true" ]]; then
        log_success "Model already cached: $output_path"
        return 0
    fi
    
    log_info "Downloading $model_name from Hugging Face..."
    log_info "This may take several minutes depending on your connection speed."
    
    if command -v wget &>/dev/null; then
        wget -O "$output_path" "$MODEL_URL" --progress=dot:giga
    elif command -v curl &>/dev/null; then
        curl -L -o "$output_path" "$MODEL_URL" --progress-bar
    else
        log_error "Neither wget nor curl found. Please install one of them."
        return 1
    fi
    
    if [[ -f "$output_path" ]]; then
        log_success "Model downloaded successfully: $output_path"
        return 0
    else
        log_error "Failed to download model."
        return 1
    fi
}

# -----------------------------------------------------------------------------
# WireGuard Helper Functions
# -----------------------------------------------------------------------------

# Generate a WireGuard client configuration
# Usage: generate_wireguard_client <client_name> <server_public_key> <server_endpoint> <client_ip>
generate_wireguard_client() {
    local client_name="$1"
    local server_pubkey="$2"
    local server_endpoint="$3"
    local client_ip="$4"

    local client_priv=$(wg genkey)
    local client_pub=$(echo "$client_priv" | wg pubkey)

    cat << EOF
[Interface]
PrivateKey = $client_priv
Address = $client_ip/24
DNS = 8.8.8.8

[Peer]
PublicKey = $server_pubkey
Endpoint = $server_endpoint
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
}

# ----------------------------------------------------------------------
# pull_with_retry - Attempt to pull a Docker image with retries and fallback
# Usage: pull_with_retry <image_name> [max_attempts] [fallback_mirror]
# ----------------------------------------------------------------------
pull_with_retry() {
    local image="$1"
    local max_attempts="${2:-5}"
    local fallback_mirror="${3:-https://docker.mirror.example.com}"
    local attempt=1
    local delay=2

    echo "Pulling Docker image: $image"
    while [ $attempt -le $max_attempts ]; do
        if docker pull "$image" 2>/dev/null; then
            echo "Successfully pulled $image"
            return 0
        fi

        echo "Pull failed (attempt $attempt/$max_attempts). Retrying in ${delay}s..." >&2
        sleep $delay
        delay=$((delay * 2))
        attempt=$((attempt + 1))
    done

    echo "All $max_attempts attempts failed. Trying fallback mirror: $fallback_mirror" >&2
    if docker pull "$image" --registry-mirror="$fallback_mirror" 2>/dev/null; then
        echo "Successfully pulled $image via fallback mirror"
        return 0
    fi

    echo "ERROR: Failed to pull $image after all retries and fallback." >&2
    return 1
}

# -----------------------------------------------------------------------------
# CPU Feature Detection
# -----------------------------------------------------------------------------

# Detect CPU features (AVX512, AMX, etc.)
# Usage: detect_cpu_features
# Returns: Space-separated list of features
detect_cpu_features() {
    local features=""
    if [[ -f /proc/cpuinfo ]]; then
        if grep -q "avx512" /proc/cpuinfo 2>/dev/null; then
            features+=" avx512"
        fi
        if grep -q "avx512_vnni" /proc/cpuinfo 2>/dev/null; then
            features+=" avx512_vnni"
        fi
        if grep -q "amx" /proc/cpuinfo 2>/dev/null; then
            features+=" amx"
        fi
        if grep -q "amx_bf16" /proc/cpuinfo 2>/dev/null; then
            features+=" amx_bf16"
        fi
        if grep -q "avx" /proc/cpuinfo 2>/dev/null; then
            features+=" avx"
        fi
    fi
    echo "$features"
}

# Check if CPU supports specific feature
# Usage: cpu_has_feature <feature>
cpu_has_feature() {
    local feature="$1"
    local features
    features=$(detect_cpu_features)
    if echo "$features" | grep -q "$feature"; then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# GPU Vendor Detection (extended)
# -----------------------------------------------------------------------------

# Detect GPU vendor (nvidia, amd, intel, or none)
# Usage: detect_gpu_vendor
detect_gpu_vendor() {
    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        echo "nvidia"
    elif command -v rocminfo &>/dev/null && rocminfo &>/dev/null; then
        echo "amd"
    elif command -v clinfo &>/dev/null && clinfo &>/dev/null; then
        # Check if Intel GPU
        if clinfo 2>/dev/null | grep -qi "intel"; then
            echo "intel"
        else
            echo "other"
        fi
    else
        echo "none"
    fi
}

# Get detailed GPU information
# Usage: get_gpu_details
# Returns: JSON-like string with GPU details
get_gpu_details() {
    local vendor
    vendor=$(detect_gpu_vendor)
    local details="{\"vendor\":\"$vendor\""
    
    case "$vendor" in
        nvidia)
            local model=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
            local memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1 | tr -d ' MiB')
            local compute=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)
            details+=",\"model\":\"$model\",\"memory_mb\":$memory,\"compute_capability\":\"$compute\""
            ;;
        amd)
            if command -v rocminfo &>/dev/null; then
                local model=$(rocminfo 2>/dev/null | grep "Name:" | head -1 | cut -d: -f2 | sed 's/^ //')
                details+=",\"model\":\"$model\""
            fi
            ;;
        intel)
            if command -v clinfo &>/dev/null; then
                local model=$(clinfo 2>/dev/null | grep "Device Name" | head -1 | cut -d: -f2 | sed 's/^ //')
                details+=",\"model\":\"$model\""
            fi
            ;;
    esac
    details+="}"
    echo "$details"
}

# -----------------------------------------------------------------------------
# Inference Backend Selection
# -----------------------------------------------------------------------------

# Determine the optimal inference backend based on hardware
# Usage: select_inference_backend
# Returns: One of: dynamo-gpu, dynamo-cpu-vllm, dynamo-frontend, llama-cpp
select_inference_backend() {
    local gpu_vendor
    gpu_vendor=$(detect_gpu_vendor)
    local cpu_features
    cpu_features=$(detect_cpu_features)
    
    case "$gpu_vendor" in
        nvidia)
            # Check if we have a modern NVIDIA GPU with sufficient VRAM
            local vram
            vram=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1 | tr -d ' MiB' 2>/dev/null || echo 0)
            if [[ "$vram" -gt 4096 ]]; then
                echo "dynamo-gpu"
            else
                # Low VRAM - use llama.cpp with GPU offload
                echo "llama-cpp"
            fi
            ;;
        amd)
            # AMD GPU support via ROCm
            echo "dynamo-gpu"  # Will use ROCm-enabled vLLM
            ;;
        intel)
            # Intel GPU support via OpenVINO
            echo "dynamo-gpu"  # Will use OpenVINO-enabled vLLM
            ;;
        none)
            # No GPU - check CPU capabilities
            if cpu_has_feature "avx512" || cpu_has_feature "amx"; then
                # CPU with AVX512/AMX - can run CPU-optimised vLLM
                echo "dynamo-cpu-vllm"
            else
                # Standard CPU - use llama.cpp
                echo "llama-cpp"
            fi
            ;;
        *)
            echo "llama-cpp"  # Fallback
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Feature Flag Helpers
# -----------------------------------------------------------------------------
# Read feature flags from .env (if exists)
read_feature_flags() {
    local env_file="$PROJECT_ROOT/deploy/docker/.env"
    if [[ -f "$env_file" ]]; then
        # Source only the FEATURE_* variables
        set -a
        source "$env_file"
        set +a
    fi
    # Defaults if not set
    FEATURE_ASK_SOMEONE="${FEATURE_ASK_SOMEONE:-true}"
    FEATURE_GOOD_ANSWER="${FEATURE_GOOD_ANSWER:-true}"
    FEATURE_GPU_MARKETPLACE="${FEATURE_GPU_MARKETPLACE:-false}"
    FEATURE_ROUTER="${FEATURE_ROUTER:-false}"
    FEATURE_TRAINING="${FEATURE_TRAINING:-false}"
    FEATURE_ENTERPRISE="${FEATURE_ENTERPRISE:-false}"
    FEATURE_FORGEJO="${FEATURE_FORGEJO:-false}"
    FEATURE_RECRUITMENT="${FEATURE_RECRUITMENT:-false}"
    FEATURE_LEAD_GEN="${FEATURE_LEAD_GEN:-false}"
    FEATURE_FREELANCE="${FEATURE_FREELANCE:-false}"
    export FEATURE_ASK_SOMEONE FEATURE_GOOD_ANSWER FEATURE_GPU_MARKETPLACE \
           FEATURE_ROUTER FEATURE_TRAINING FEATURE_ENTERPRISE \
           FEATURE_FORGEJO FEATURE_RECRUITMENT FEATURE_LEAD_GEN FEATURE_FREELANCE
}

# -----------------------------------------------------------------------------
# Dependency Locking Helpers
# -----------------------------------------------------------------------------

# Install pip-tools inside the virtual environment
install_pip_tools() {
    if command -v pip &>/dev/null; then
        log_info "Installing pip-tools in virtual environment..."
        pip install pip-tools
        log_success "pip-tools installed"
    else
        log_error "pip not found in virtual environment"
        return 1
    fi
}

# Generate lock files from requirements.in files
generate_lock_files() {
    log_step "Generating lock files..."
    cd "$PROJECT_ROOT"
    if [[ -f "requirements.in" ]]; then
        if command -v pip-compile &>/dev/null; then
            pip-compile requirements.in -o requirements-lock.txt --generate-hashes
            log_success "Generated requirements-lock.txt"
        else
            log_warning "pip-compile not found. Skipping lock file generation."
        fi
    fi
    if [[ -f "requirements-dev.in" ]]; then
        if command -v pip-compile &>/dev/null; then
            pip-compile requirements-dev.in -o requirements-dev-lock.txt --generate-hashes
            log_success "Generated requirements-dev-lock.txt"
        fi
    fi
}

# Install dependencies based on environment
install_dependencies() {
    local env="${1:-development}"
    cd "$PROJECT_ROOT"
    if [[ "$env" == "production" ]]; then
        if [[ -f "requirements-lock.txt" ]]; then
            log_info "Installing from locked requirements (production)..."
            pip install -r requirements-lock.txt
        elif [[ -f "requirements.txt" ]]; then
            log_warning "requirements-lock.txt not found. Falling back to requirements.txt"
            pip install -r requirements.txt
        else
            log_error "No requirements file found"
            return 1
        fi
    else
        if [[ -f "requirements.txt" ]]; then
            log_info "Installing from requirements.txt (development)..."
            pip install -r requirements.txt
        else
            log_error "requirements.txt not found"
            return 1
        fi
    fi
    return 0
}


# =============================================================================
# Emergency Access Functions (Hub-and-Spoke Security)
# =============================================================================

# Check if a login is a valid emergency user
check_emergency_access() {
    local login="$1"
    local password="$2"
    local result=$(docker compose exec -T postgres psql -U odoo -d odoo -t -c "
        SELECT COUNT(*) FROM nettrades_emergency_users 
        WHERE login='$login' 
        AND password_hash = crypt('$password', password_hash)
        AND valid_until > NOW();
    " 2>/dev/null | tr -d ' ')
    
    if [[ "$result" == "1" ]]; then
        # Update last_used timestamp
        docker compose exec -T postgres psql -U odoo -d odoo -c "
            UPDATE nettrades_emergency_users 
            SET last_used = NOW() 
            WHERE login='$login';
        " 2>/dev/null
        return 0
    fi
    return 1
}

# Log emergency access actions for audit
log_emergency_action() {
    local login="$1"
    local action="$2"
    local ip="${3:-unknown}"
    
    docker compose exec -T postgres psql -U odoo -d odoo -c "
        INSERT INTO nettrades_emergency_audit (login, action, ip_address)
        VALUES ('$login', '$action', '$ip');
    " 2>/dev/null
}

# =============================================================================
# Domain Validation
# =============================================================================

validate_domain() {
    local domain="$1"
    # Basic domain validation: must not be localhost, IP, or contain dangerous chars
    if [[ -z "$domain" ]] || [[ "$domain" == "localhost" ]] || [[ "$domain" == "changeit" ]]; then
        return 1
    fi
    if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        return 1
    fi
    # Allow subdomains and hyphens
    if [[ "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$ ]]; then
        return 0
    fi
    return 1
}