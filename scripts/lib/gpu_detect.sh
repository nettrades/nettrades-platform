#!/bin/bash
# =============================================================================
# FILE: scripts/lib/gpu_detect.sh
# =============================================================================
# PURPOSE:
#   Centralized GPU hardware detection for NETTRADES deployment scripts.
# =============================================================================

detect_primary_ip() {
    # Uses ip route to find the IP of the interface handling the default route.
    # This is significantly more reliable than `hostname -I` which may list
    # Docker bridge IPs or unconfigured interfaces.
    local ip=""
    ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')
    if [[ -z "$ip" ]]; then
        ip=$(hostname -I 2>/dev/null | awk '{print $1}')
    fi
    echo "${ip:-127.0.0.1}"
}

detect_gpu_vendor() {
    if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
        echo "nvidia"
    elif command -v rocminfo >/dev/null 2>&1 && rocminfo >/dev/null 2>&1; then
        echo "amd"
    else
        echo "none"
    fi
}

detect_nvidia_compute_cap() {
    nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' '
}

detect_nvlink_present() {
    if ! command -v nvidia-smi >/dev/null 2>&1; then echo "false"; return; fi
    if nvidia-smi topo -m 2>/dev/null | grep -qE 'NV[0-9]+'; then
        echo "true"
    else
        echo "false"
    fi
}

select_inference_backend() {
    local vendor=$(detect_gpu_vendor)
    
    if [[ "$vendor" != "nvidia" ]]; then
        echo "llamacpp"
        return
    fi

    local cap=$(detect_nvidia_compute_cap)
    local major="${cap%%.*}"

    # Volta (V100) -> vLLM (1Cat-vLLM fork)
    if [[ "$major" == "7" ]]; then
        echo "vllm"
        return
    fi

    # Ampere/Ada/Hopper -> Dynamo (if available)
    if [[ "$major" -ge 8 ]] 2>/dev/null; then
        if docker image inspect nvcr.io/nvidia/ai-dynamo/dynamo-frontend:1.3.1 >/dev/null 2>&1; then
            echo "dynamo"
        else
            echo "vllm"
        fi
        return
    fi

    echo "llamacpp"
}