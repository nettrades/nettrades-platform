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

# -----------------------------------------------------------------------------
# Safe sed replacement (escapes special characters)
# -----------------------------------------------------------------------------
safe_sed_replace() {
    local file="$1"
    local pattern="$2"
    local replacement="$3"
    # Escape single quotes inside the replacement: ' -> '\''
    local escaped_replacement="${replacement//\'/\'\\\'\'}"
    # Write as VAR='escaped_replacement'
    sed -i "s|^${pattern}=.*|${pattern}='${escaped_replacement}'|" "$file"
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