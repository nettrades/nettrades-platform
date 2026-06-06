#!/bin/bash
# =============================================================================
# NETTRADES.AI – Shared Detection Library
# =============================================================================
# Source this file to use the detection functions in any installer script.
# =============================================================================

NETTRADES_STATE="/opt/nettrades-ai/state"
mkdir -p "$NETTRADES_STATE"

function detect_os() {
    . /etc/os-release
    echo "$ID $VERSION_ID"
}

function detect_cpu_cores() {
    nproc
}

function detect_total_ram_gb() {
    free -g | awk '/^Mem:/{print $2}'
}

function detect_public_ip() {
    curl -s ifconfig.me || curl -s icanhazip.com || echo "UNKNOWN"
}

function detect_gpu() {
    command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null
}

function install_nvidia_docker() {
    if ! detect_gpu; then return; fi
    if ! dpkg -l | grep -q nvidia-container-toolkit; then
        echo "Installing NVIDIA Container Toolkit..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
        sudo apt update
        sudo apt install -y nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
    fi
}