#!/bin/bash
# =============================================================================
# FILE: scripts/phase-system.sh
# =============================================================================
# PURPOSE:
#   Phase 0: System Preparation & Security Hardening.
#   This phase prepares the host system for NETTRADES deployment by:
#   - Installing system dependencies (Docker, Docker Compose, NVIDIA drivers)
#   - Configuring firewall (UFW/iptables)
#   - Hardening SSH (disable root login, key-only auth)
#   - Installing fail2ban
#   - Configuring system limits for high-performance workloads
#   - Setting up WireGuard (if requested)
#   - Enabling gVisor runtime for container isolation (if on Kubernetes)
#
#   It is idempotent and safe to re-run.
#
# USAGE:
#   ./phase-system.sh [--auto] [--force]
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
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "0"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 0; then
    log_warning "Phase 0 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Detect OS
# -----------------------------------------------------------------------------
OS=$(detect_os)
log_info "Detected OS: $OS"

if [[ "$OS" != "linux" ]]; then
    log_warning "Phase 0 is primarily designed for Linux. Some steps may not work on $OS."
    if [[ "$AUTO" != true ]]; then
        read -rp "Continue anyway? (y/N): " continue_anyway
        if [[ ! "$continue_anyway" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 1. Install Docker
# -----------------------------------------------------------------------------
log_step "Checking Docker installation..."
if ! command -v docker &>/dev/null; then
    log_info "Installing Docker..."
    if [[ "$OS" == "linux" ]]; then
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
    else
        log_error "Please install Docker manually for $OS"
        exit 1
    fi
else
    log_success "Docker already installed"
fi

# -----------------------------------------------------------------------------
# 2. Install Docker Compose (standalone) & (plugin)
# -----------------------------------------------------------------------------
log_step "Checking Docker Compose installation..."
if ! docker compose version &>/dev/null; then
    log_info "Installing Docker Compose plugin..."
    if [[ "$OS" == "linux" ]]; then
        # Add Docker's official repository if not already present
        if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
            log_info "Adding Docker's official repository..."
            sudo install -m 0755 -d /etc/apt/keyrings
            sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
            sudo chmod a+r /etc/apt/keyrings/docker.asc
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update
        fi
        sudo apt-get install -y docker-compose-plugin
        log_success "Docker Compose plugin installed"
    else
        log_error "Please install Docker Compose manually for $OS"
        exit 1
    fi
else
    log_success "Docker Compose already installed"
fi

# -----------------------------------------------------------------------------
# 3. Check Python and pip
# -----------------------------------------------------------------------------
log_step "Checking Python and pip installation..."
if ! command -v python3 &>/dev/null; then
    log_error "Python3 not found. Please install Python 3.10 or higher."
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [[ "$(printf '%s\n' "3.10" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.10" ]]; then
    log_error "Python version $PYTHON_VERSION detected. Need 3.10+."
    exit 1
fi
log_success "Python $PYTHON_VERSION detected."

# Check pip3 – use apt for Ubuntu/Debian
if ! command -v pip3 &>/dev/null; then
    log_warning "pip3 not found. Installing via apt..."
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y python3-pip
        log_success "pip3 installed via apt"
    else
        log_error "Please install pip3 manually for $OS"
        exit 1
    fi
else
    log_success "pip3 already installed"
fi

# -----------------------------------------------------------------------------
# 4. Install NVIDIA drivers (if GPU is present or requested)
# -----------------------------------------------------------------------------
if detect_gpu; then
    log_success "NVIDIA GPU detected: $(get_gpu_name)"

    log_step "Checking NVIDIA drivers..."
    if ! nvidia-smi &>/dev/null; then
        log_info "Installing NVIDIA drivers..."
        if [[ "$OS" == "linux" ]]; then
            sudo apt-get update
            sudo apt-get install -y nvidia-driver-550 nvidia-utils-550
        else
            log_warning "Please install NVIDIA drivers manually for $OS"
        fi
    else
        log_success "NVIDIA drivers already installed"
    fi

    log_step "Installing NVIDIA Container Toolkit..."
    if ! command -v nvidia-container-toolkit &>/dev/null; then
        if [[ "$OS" == "linux" ]]; then
            distribution=$(. /etc/os-release; echo "$ID$VERSION_ID")
            curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
            curl -s -L "https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list" | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
            sudo apt-get update
            sudo apt-get install -y nvidia-container-toolkit
            sudo nvidia-ctk runtime configure --runtime=docker
            sudo systemctl restart docker
            log_success "NVIDIA Container Toolkit installed"
        else
            log_warning "Please install NVIDIA Container Toolkit manually for $OS"
        fi
    else
        log_success "NVIDIA Container Toolkit already installed"
    fi
else
    log_info "No NVIDIA GPU detected – skipping GPU driver installation"
fi

# -----------------------------------------------------------------------------
# 5. Firewall configuration (UFW)
# -----------------------------------------------------------------------------
log_step "Configuring firewall..."
if command -v ufw &>/dev/null; then
    if ! ufw status | grep -q "active"; then
        log_info "Enabling UFW firewall..."
        sudo ufw allow 22/tcp comment 'SSH'
        sudo ufw allow 80/tcp comment 'HTTP'
        sudo ufw allow 443/tcp comment 'HTTPS'
        sudo ufw allow 51820/udp comment 'WireGuard'
        sudo ufw --force enable
    else
        log_success "UFW firewall already active"
    fi
else
    log_warning "UFW not found – skipping firewall configuration"
fi

# -----------------------------------------------------------------------------
# 6. SSH hardening
# -----------------------------------------------------------------------------
log_step "Hardening SSH configuration..."
if [[ -f /etc/ssh/sshd_config ]]; then
    # Disable root login
    if ! grep -q "^PermitRootLogin no" /etc/ssh/sshd_config; then
        sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
        sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
    fi

    # Disable password authentication
    if ! grep -q "^PasswordAuthentication no" /etc/ssh/sshd_config; then
        sudo sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
        sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    fi

    sudo systemctl restart sshd 2>/dev/null || sudo systemctl restart ssh 2>/dev/null || true
    log_success "SSH hardened"
else
    log_warning "sshd_config not found – skipping SSH hardening"
fi

# -----------------------------------------------------------------------------
# 7. Install fail2ban
# -----------------------------------------------------------------------------
log_step "Installing fail2ban..."
if command -v fail2ban-client &>/dev/null; then
    log_success "fail2ban already installed"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get install -y fail2ban
        sudo systemctl enable fail2ban
        sudo systemctl start fail2ban
        log_success "fail2ban installed"
    else
        log_warning "Please install fail2ban manually"
    fi
fi

# -----------------------------------------------------------------------------
# Install dos2unix (for fixing line endings in Windows ↔ Linux environments) and Install jq
# -----------------------------------------------------------------------------
log_step "Installing dos2unix..."
if command -v dos2unix &>/dev/null; then
    log_success "dos2unix already installed"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y dos2unix
        log_success "dos2unix installed"
        sudo apt-get install -y curl wget git jq
    else
        log_warning "Please install dos2unix manually for $OS"
    fi
fi

# -----------------------------------------------------------------------------
# 8. Configure system limits
# -----------------------------------------------------------------------------
log_step "Configuring system limits..."
LIMITS_FILE="/etc/security/limits.conf"
if [[ -f "$LIMITS_FILE" ]]; then
    if ! grep -q "nofile 65535" "$LIMITS_FILE"; then
        echo "* soft nofile 65535" | sudo tee -a "$LIMITS_FILE"
        echo "* hard nofile 65535" | sudo tee -a "$LIMITS_FILE"
        echo "* soft nproc 65535" | sudo tee -a "$LIMITS_FILE"
        echo "* hard nproc 65535" | sudo tee -a "$LIMITS_FILE"
        log_success "System limits configured"
    else
        log_success "System limits already configured"
    fi
else
    log_warning "limits.conf not found – skipping"
fi

# -----------------------------------------------------------------------------
# 9. Check gVisor installation
# -----------------------------------------------------------------------------
log_step "Checking gVisor installation..."
if command -v runsc &>/dev/null; then
    log_success "gVisor already installed"
else
    log_info "gVisor not installed – will be installed during Kubernetes phase if needed"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 0
log_success "Phase 0 completed – system is prepared and hardened"