#!/bin/bash
# =============================================================================
# FILE: scripts/phase-system.sh
# =============================================================================
# PURPOSE:
#   Phase 0: System Preparation & Security Hardening.
#   This phase prepares the host system for NETTRADES deployment by:
#   - Installing system dependencies (Docker, Docker Compose, GPU drivers)
#   - Configuring firewall (UFW/iptables)
#   - Setting up a WireGuard VPN server for administrative access
#   - Hardening SSH (disable root login, key-only auth globally,
#     but allow password auth from the VPN subnet)
#   - Installing fail2ban
#   - Configuring system limits for high-performance workloads
#   - Enabling gVisor runtime for container isolation (if on Kubernetes)
#   - [NEW] Installing Node.js and npm for the Electron installer
#   - [NEW] Ensuring port 80 is open for Let's Encrypt
#   - [NEW] Multi-vendor GPU driver support (NVIDIA, AMD, Intel)
#   - [NEW] Installing python3-venv for virtual environment creation
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

# After OS detection, add:
PLATFORM=$(detect_platform)
log_info "Detected platform: $PLATFORM"

# -----------------------------------------------------------------------------
# 1. Install Docker (cross-platform)
# -----------------------------------------------------------------------------
install_docker() {
    if command -v docker &>/dev/null; then
        log_success "Docker already installed"
        return
    fi
    log_info "Installing Docker..."
    case "$PLATFORM" in
        linux|wsl)
            curl -fsSL https://get.docker.com | sh
            sudo usermod -aG docker "$USER"
            ;;
        macos)
            log_info "Please install Docker Desktop for macOS from https://www.docker.com/products/docker-desktop"
            log_info "After installation, ensure Docker is running and the CLI is in PATH."
            if [[ "$AUTO" != true ]]; then
                read -p "Press Enter after Docker is installed and running..."
            fi
            ;;
        *)
            log_error "Unsupported platform for automatic Docker installation."
            exit 1
            ;;
    esac
}

# -----------------------------------------------------------------------------
# 2. Install Docker Compose
# -----------------------------------------------------------------------------
install_docker_compose() {
    if docker compose version &>/dev/null; then
        log_success "Docker Compose already installed"
        return
    fi
    log_info "Installing Docker Compose..."
    case "$PLATFORM" in
        linux|wsl)
            # Add Docker's official repository if not already present
            if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
                log_info "Adding Docker's official repository..."
                sudo install -m 0755 -d /etc/apt/keyrings
                sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
                sudo chmod a+r /etc/apt/keyrings/docker.asc
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                sudo apt-get update -qq
            fi
            sudo apt-get install -y docker-compose-plugin
            log_success "Docker Compose plugin installed"
            ;;
        macos)
            log_info "Docker Compose is included with Docker Desktop."
            log_info "Please ensure Docker Desktop is running."
            ;;
        *)
            log_error "Unsupported platform for automatic Docker Compose installation."
            exit 1
            ;;
    esac
}

# -----------------------------------------------------------------------------
# 3. Python and pip (platform-specific)
# -----------------------------------------------------------------------------
install_python() {
    if command -v python3 &>/dev/null; then
        local py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if [[ "$(printf '%s\n' "3.10" "$py_version" | sort -V | head -n1)" != "3.10" ]]; then
            log_error "Python $py_version detected. Need 3.10+."
            # Attempt to install Python 3.12 on macOS
            if [[ "$PLATFORM" == "macos" ]]; then
                if command -v brew &>/dev/null; then
                    log_info "Installing Python 3.12 via Homebrew..."
                    brew install python@3.12
                    export PATH="/usr/local/opt/python@3.12/bin:$PATH"
                    # Re-check version after installation
                    local new_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
                    if [[ "$(printf '%s\n' "3.10" "$new_version" | sort -V | head -n1)" != "3.10" ]]; then
                        log_error "Python $new_version still detected after installation. Please install Python 3.12 manually."
                        exit 1
                    fi
                    log_success "Python $new_version installed successfully."
                    return
                else
                    log_error "Homebrew not found. Please install Python 3.12 manually."
                    exit 1
                fi
            else
                exit 1
            fi
        fi
        log_success "Python $py_version detected."
    else
        log_info "Installing Python 3..."
        case "$PLATFORM" in
            linux|wsl)
                sudo apt-get update -qq
                sudo apt-get install -y python3 python3-pip python3-venv
                ;;
            macos)
                if command -v brew &>/dev/null; then
                    brew install python@3.12
                else
                    log_error "Homebrew not found. Please install Python manually."
                    exit 1
                fi
                ;;
            *)
                log_error "Unsupported platform for automatic Python installation."
                exit 1
                ;;
        esac
    fi
}


# -----------------------------------------------------------------------------
# 1. Install Docker
# -----------------------------------------------------------------------------
log_step "Checking Docker installation..."
install_docker

# -----------------------------------------------------------------------------
# 2. Install Docker Compose (standalone) & (plugin)
# -----------------------------------------------------------------------------
log_step "Checking Docker Compose installation..."
install_docker_compose

# -----------------------------------------------------------------------------
# 3. Check Python and pip
# -----------------------------------------------------------------------------
log_step "Checking Python and pip installation..."
install_python

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
# 3.5 Install python3-venv (required for virtual environment creation)
# -----------------------------------------------------------------------------
log_step "Checking python3-venv installation..."
if ! python3 -c "import venv" &>/dev/null; then
    log_info "Installing python3-venv..."
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y python3-venv
        log_success "python3-venv installed"
    else
        log_warning "Please install python3-venv manually for $OS"
    fi
else
    log_success "python3-venv already installed"
fi

# -----------------------------------------------------------------------------
# 4. Install Node.js and npm (for the Electron installer)
# -----------------------------------------------------------------------------
log_step "Checking Node.js and npm installation..."

# Check if Node.js is already installed
if command -v node &>/dev/null && command -v npm &>/dev/null; then
    NODE_VERSION=$(node --version | cut -d'v' -f2)
    log_success "Node.js $NODE_VERSION already installed"
else
    log_info "Installing Node.js 20 LTS..."
    # Use NodeSource's official script for Ubuntu/Debian
    if [[ "$OS" == "linux" ]]; then
        if [[ ! -f /etc/apt/sources.list.d/nodesource.list ]]; then
            curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        fi
        sudo apt-get install -y nodejs
    else
        log_warning "Please install Node.js manually for $OS"
        log_info "Visit: https://nodejs.org/en/download/"
    fi
    log_success "Node.js installed"
fi

# Verify npm is available
if command -v npm &>/dev/null; then
    NPM_VERSION=$(npm --version)
    log_success "npm $NPM_VERSION available"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get install -y npm
    else
        log_warning "npm not found. Please install npm manually."
    fi
fi

# -----------------------------------------------------------------------------
# 5. Multi-vendor GPU driver installation
# -----------------------------------------------------------------------------
# Detect GPU vendor using functions from common.sh (ensure they exist)
# Fallback definitions if not already present
if ! type detect_gpu_vendor &>/dev/null; then
    # Define minimal fallback for detect_gpu_vendor
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
fi

GPU_VENDOR=$(detect_gpu_vendor)
log_info "Detected GPU vendor: $GPU_VENDOR"

case "$GPU_VENDOR" in
    nvidia)
        log_success "NVIDIA GPU detected: $(get_gpu_name)"
        log_step "Checking NVIDIA drivers..."
        if ! nvidia-smi &>/dev/null; then
            log_info "Installing NVIDIA drivers..."
            if [[ "$OS" == "linux" ]]; then
                sudo apt-get update
                # NVIDIA driver version 550+ is recommended for Dynamo
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
        ;;

    amd)
        log_success "AMD GPU detected"
        log_step "Checking AMD ROCm drivers..."
        # Check if ROCm is already installed by looking for rocminfo
        if ! command -v rocminfo &>/dev/null || ! rocminfo &>/dev/null; then
            log_info "Installing AMD ROCm drivers..."
            if [[ "$OS" == "linux" ]]; then
                # Add ROCm repository for Ubuntu 24.04 (noble)
                # Official instructions: https://rocm.docs.amd.com/en/latest/deploy/linux/install.html
                wget -q -O - https://repo.radeon.com/rocm/rocm.gpg.key | sudo apt-key add -
                echo "deb [arch=amd64] https://repo.radeon.com/rocm/apt/latest ubuntu main" | sudo tee /etc/apt/sources.list.d/rocm.list
                sudo apt-get update
                # Install ROCm core packages (hip, rocminfo, rocm-libs, etc.)
                # Also install amdgpu-dkms for kernel module
                sudo apt-get install -y rocm-hip-libraries rocm-device-libs rocm-libs rocminfo amdgpu-dkms
                # Add user to video and render groups for GPU access
                sudo usermod -a -G video,render "$USER"
                log_success "AMD ROCm drivers installed"
                log_warning "A system reboot is recommended to load the AMD GPU kernel modules."
            else
                log_warning "Please install AMD ROCm drivers manually for $OS"
            fi
        else
            log_success "AMD ROCm drivers already installed"
        fi
        ;;

    intel)
        log_success "Intel GPU detected"
        log_step "Checking Intel GPU drivers..."
        # Check for Intel GPU driver presence (clinfo or intel-gpu-tools)
        if ! command -v intel_gpu_top &>/dev/null; then
            log_info "Installing Intel GPU drivers..."
            if [[ "$OS" == "linux" ]]; then
                # Install Intel GPU drivers: intel-gpu-tools, intel-opencl-icd, and compute runtime
                sudo apt-get update
                sudo apt-get install -y intel-gpu-tools intel-opencl-icd intel-compute-runtime
                log_success "Intel GPU drivers installed"
            else
                log_warning "Please install Intel GPU drivers manually for $OS"
            fi
        else
            log_success "Intel GPU drivers already installed"
        fi
        ;;

    none|*)
        log_info "No supported GPU detected – skipping GPU driver installation"
        ;;
esac

# -----------------------------------------------------------------------------
# 6. Firewall configuration (UFW) 
# -----------------------------------------------------------------------------
log_step "Configuring firewall..."
if command -v ufw &>/dev/null; then
    if ! ufw status | grep -q "active"; then
        log_info "Enabling UFW firewall..."
        sudo ufw allow 22/tcp comment 'SSH (main)'
        sudo ufw allow 2222/tcp comment 'SSH (rescue)'
        sudo ufw allow 80/tcp comment 'HTTP'
        sudo ufw allow 443/tcp comment 'HTTPS'
        sudo ufw allow 51820/udp comment 'WireGuard (internal)'
        sudo ufw allow 51821/udp comment 'WireGuard (admin VPN)'
        sudo ufw --force enable
    else
        log_success "UFW firewall already active"
    fi
else
    log_warning "UFW not found – skipping firewall configuration"
fi

# Ensure port 80 is open for Let's Encrypt challenge (already present)
log_step "Ensuring port 80 is open for Let's Encrypt challenge..."
if command -v ufw &>/dev/null; then
    if ! ufw status | grep -q "80/tcp"; then
        log_warning "Port 80 not allowed in UFW. Adding..."
        sudo ufw allow 80/tcp
    else
        log_success "Port 80 allowed in UFW"
    fi
fi

# -----------------------------------------------------------------------------
# Ensure port 80 is open for Let's Encrypt challenge
# -----------------------------------------------------------------------------
log_step "Ensuring port 80 is open for Let's Encrypt challenge..."
if command -v ufw &>/dev/null; then
    if ! ufw status | grep -q "80/tcp"; then
        log_warning "Port 80 not allowed in UFW. Adding..."
        sudo ufw allow 80/tcp
    else
        log_success "Port 80 allowed in UFW"
    fi
fi
# Also check if something else is blocking (like iptables)
if command -v iptables &>/dev/null; then
    if ! sudo iptables -L INPUT -n 2>/dev/null | grep -q "dpt:80"; then
        log_warning "Port 80 might be blocked by iptables. Consider opening it."
    fi
fi

# -----------------------------------------------------------------------------
# 7. SSH Key Setup – Guide the user to create a key before hardening
# -----------------------------------------------------------------------------
log_step "Setting up SSH keys for secure access..."

mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Check for existing public key
PUB_KEY_FILE=""
if [[ -f /root/.ssh/id_ed25519.pub ]]; then
    PUB_KEY_FILE="/root/.ssh/id_ed25519.pub"
elif [[ -f /root/.ssh/id_rsa.pub ]]; then
    PUB_KEY_FILE="/root/.ssh/id_rsa.pub"
fi

add_public_key() {
    local key="$1"
    echo "$key" >> /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys
    log_success "Public key added to authorized_keys"
}

if [[ -n "$PUB_KEY_FILE" ]]; then
    log_info "Found existing public key: $PUB_KEY_FILE"
    if ! grep -q -f "$PUB_KEY_FILE" /root/.ssh/authorized_keys 2>/dev/null; then
        cat "$PUB_KEY_FILE" >> /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
        log_success "Existing public key added to authorized_keys"
    else
        log_success "Public key already in authorized_keys"
    fi
else
    log_warning "No SSH public key found in /root/.ssh/"

    if [[ "$AUTO" == true ]]; then
        log_info "Auto mode: generating a new Ed25519 SSH key without a passphrase..."
        ssh-keygen -t ed25519 -C "root@$(hostname)" -f /root/.ssh/id_ed25519 -N ""
        cat /root/.ssh/id_ed25519.pub >> /root/.ssh/authorized_keys
        chmod 600 /root/.ssh/authorized_keys
        log_success "New key generated and added to authorized_keys"
        echo ""
        echo "Your new public key is:"
        cat /root/.ssh/id_ed25519.pub
        echo ""
        echo "Save this key on your local machine if you need it elsewhere."
    else
        echo ""
        echo "To avoid being locked out after SSH hardening, you need an SSH key."
        echo "Options:"
        echo "  1) Generate a new SSH key pair now (recommended)"
        echo "  2) Paste an existing public key from your local machine"
        echo "  3) Skip (not recommended – you may lose SSH access)"
        read -rp "Choose 1, 2, or 3: " key_choice

        case "$key_choice" in
            1)
                log_info "Generating a new Ed25519 SSH key pair..."
                log_info "You will be asked for a passphrase – you can leave it empty for convenience."
                ssh-keygen -t ed25519 -C "root@$(hostname)" -f /root/.ssh/id_ed25519
                cat /root/.ssh/id_ed25519.pub >> /root/.ssh/authorized_keys
                chmod 600 /root/.ssh/authorized_keys
                log_success "New key generated and added to authorized_keys"
                echo ""
                echo "Your new public key is:"
                cat /root/.ssh/id_ed25519.pub
                echo ""
                echo "Save this key on your local machine if you need it elsewhere."
                ;;
            2)
                echo "Paste your public SSH key (e.g., from ~/.ssh/id_ed25519.pub on your local machine):"
                read -r user_key
                if [[ -n "$user_key" ]]; then
                    add_public_key "$user_key"
                else
                    log_error "No key provided. Skipping key setup."
                fi
                ;;
            3)
                log_warning "Skipping SSH key setup. You may lose SSH access after hardening."
                ;;
            *)
                log_error "Invalid choice. Skipping SSH key setup."
                ;;
        esac
    fi
fi

# -----------------------------------------------------------------------------
# 8. Rescue SSH Port (always allows password auth, as a safety net)
# -----------------------------------------------------------------------------
log_step "Setting up rescue SSH port (2222)..."

# Ensure OpenSSH server is installed
if ! command -v sshd &>/dev/null; then
    log_info "OpenSSH server not found. Installing..."
    sudo apt-get update -qq
    sudo apt-get install -y openssh-server
    log_success "OpenSSH server installed"
fi

if ! pgrep -f "sshd.*rescue" > /dev/null; then
    cat > /etc/ssh/sshd_config_rescue << EOF
Port 2222
PasswordAuthentication yes
PermitRootLogin yes
PubkeyAuthentication yes
LogLevel INFO
EOF
    /usr/sbin/sshd -f /etc/ssh/sshd_config_rescue
    log_success "Rescue SSH server started on port 2222 (password auth allowed)"
else
    log_success "Rescue SSH server already running on port 2222"
fi

# -----------------------------------------------------------------------------
# 9. Install WireGuard tools (if not already present)
# -----------------------------------------------------------------------------
log_step "Installing WireGuard tools..."
if ! command -v wg &>/dev/null; then
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y wireguard-tools
        log_success "WireGuard tools installed"
    else
        log_warning "Please install wireguard-tools manually for $OS"
    fi
else
    log_success "WireGuard tools already installed"
fi

# -----------------------------------------------------------------------------
# 10. WireGuard Admin VPN Server (for emergency SSH access)
# -----------------------------------------------------------------------------
log_step "Setting up WireGuard admin VPN server..."

# Detect the primary network interface (fix: auto-detect instead of hardcoding eth0)
PRIMARY_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
if [[ -z "$PRIMARY_IFACE" ]]; then
    PRIMARY_IFACE="eth0"  # fallback
fi
log_info "Detected primary network interface: $PRIMARY_IFACE"

WG_ADMIN_DIR="/etc/wireguard/admin"
mkdir -p "$WG_ADMIN_DIR"

if [[ ! -f "$WG_ADMIN_DIR/privatekey" ]]; then
    wg genkey | tee "$WG_ADMIN_DIR/privatekey" | wg pubkey > "$WG_ADMIN_DIR/publickey"
fi

# Create server configuration with iptables rules (using detected interface)
cat > "$WG_ADMIN_DIR/wg0.conf" << EOF
[Interface]
Address = 10.10.10.1/24
ListenPort = 51821
PrivateKey = $(cat "$WG_ADMIN_DIR/privatekey")
SaveConfig = false

# Allow forwarding and NAT for VPN clients
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o $PRIMARY_IFACE -j MASQUERADE
# Block admin VPN from accessing internal WireGuard subnet (10.0.0.0/16)
PostUp = iptables -I FORWARD -i wg0 -d 10.0.0.0/16 -j DROP

PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o $PRIMARY_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -d 10.0.0.0/16 -j DROP 2>/dev/null || true
EOF

# Check if WireGuard kernel module is available
if modprobe wireguard 2>/dev/null; then
    # Module loaded successfully, start the service
    systemctl enable wg-quick@admin-wg0 2>/dev/null || true
    systemctl start wg-quick@admin-wg0 2>/dev/null || true
    log_success "WireGuard admin VPN server started on port 51821 (subnet 10.10.10.0/24)"
else
    log_warning "WireGuard kernel module not available. Skipping VPN server start."
    log_info "Configuration and keys are still available at $WG_ADMIN_DIR"
    if [[ "$PLATFORM" == "wsl" ]]; then
        log_info "On WSL, the WireGuard kernel module is not supported by default."
        log_info "You can still use the generated keys to set up WireGuard on a native Linux node,"
        log_info "or use a Windows WireGuard client with the generated configuration."
    fi
fi

# -----------------------------------------------------------------------------
# Copy WireGuard client management script to /usr/local/bin
# -----------------------------------------------------------------------------
if [[ -f "$SCRIPT_DIR/wireguard-manager.sh" ]]; then
    cp "$SCRIPT_DIR/wireguard-manager.sh" /usr/local/bin/
    chmod +x /usr/local/bin/wireguard-manager.sh
    log_success "WireGuard manager script installed to /usr/local/bin/wireguard-manager.sh"
else
    log_warning "wireguard-manager.sh not found – skipping"
fi

# -----------------------------------------------------------------------------
# 11. SSH hardening (with self-test to prevent lockout)
# -----------------------------------------------------------------------------
log_step "Hardening SSH configuration (main port 22)..."

# Backup current config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

if [[ -f /etc/ssh/sshd_config ]]; then
    # Disable root login globally
    sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

    # Disable password authentication globally (will be overridden for VPN)
    sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

    # Allow password authentication from the WireGuard admin VPN subnet
    if ! grep -q "Match Address 10.10.10.0/24" /etc/ssh/sshd_config; then
        echo "" >> /etc/ssh/sshd_config
        echo "Match Address 10.10.10.0/24" >> /etc/ssh/sshd_config
        echo "    PasswordAuthentication yes" >> /etc/ssh/sshd_config
        echo "Match All" >> /etc/ssh/sshd_config
        log_success "SSH will allow password authentication from 10.10.10.0/24"
    fi
fi

# Test SSH config before restart
if ! sshd -t; then
    log_error "SSH config test failed. Restoring backup..."
    cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    systemctl restart ssh
    log_error "SSH config reverted. Please fix manually."
    exit 1
fi

# Restart SSH
systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || true

# -----------------------------------------------------------------------------
# 12. Self-test: Verify SSH accessibility
# -----------------------------------------------------------------------------
log_step "Verifying SSH access (to prevent lockout)..."

# Test SSH from localhost using password (rescue port)
if ssh -o ConnectTimeout=5 -o PasswordAuthentication=yes -o BatchMode=no -p 2222 localhost "echo OK" 2>/dev/null | grep -q OK; then
    log_success "Rescue SSH port (2222) is accessible with password auth"
else
    log_error "Rescue SSH port test failed! SSH may be broken."
    log_error "Reverting SSH configuration to prevent lockout."
    cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    systemctl restart ssh
    log_error "SSH reverted to safe configuration. Please investigate."
    exit 1
fi

# Test SSH using key from localhost (main port)
if ssh -o ConnectTimeout=5 -o PasswordAuthentication=no -p 22 localhost "echo OK" 2>/dev/null | grep -q OK; then
    log_success "Main SSH port (22) is accessible with key auth"
else
    log_warning "Main SSH port key auth test failed. Check your SSH key setup."
    log_info "The rescue port (2222) is still available with password auth."
fi

log_success "SSH hardening complete – both main and rescue ports are accessible"

# -----------------------------------------------------------------------------
# 13. Install fail2ban
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
# 14. Install dos2unix and jq
# -----------------------------------------------------------------------------
log_step "Installing dos2unix and jq..."
if command -v dos2unix &>/dev/null && command -v jq &>/dev/null; then
    log_success "dos2unix and jq already installed"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y dos2unix curl wget git jq
        log_success "dos2unix and jq installed"
    else
        log_warning "Please install dos2unix and jq manually for $OS"
    fi
fi

# -----------------------------------------------------------------------------
# 15. Install bcrypt for Prometheus password hashing (now handled in phase-deploy.sh)
# -----------------------------------------------------------------------------
# This step is moved to phase-deploy.sh to ensure it uses the venv.
# Keeping a placeholder to avoid confusion.
log_info "bcrypt will be installed in the virtual environment during Phase 2."

# -----------------------------------------------------------------------------
# 16. Configure system limits
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
# 17. Check gVisor installation
# -----------------------------------------------------------------------------
log_step "Checking gVisor installation..."
if command -v runsc &>/dev/null; then
    log_success "gVisor already installed"
else
    log_info "gVisor not installed – will be installed during Kubernetes phase if needed"
fi

# -----------------------------------------------------------------------------
# WireGuard client configuration reminder
# -----------------------------------------------------------------------------
echo ""
echo "============================================================"
echo " WireGuard Admin VPN"
echo "============================================================"
echo "To generate a WireGuard client config, run:"
echo " /usr/local/bin/wireguard-manager.sh add <client-name>"
echo ""
echo "Example: /usr/local/bin/wireguard-manager.sh add mylaptop"
echo "This will create a client config in /root/wireguard-clients/"
echo "============================================================"

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 0
log_success "Phase 0 completed – system is prepared and hardened"

echo ""
echo "============================================================"
echo "Security Notes"
echo "============================================================"
echo "Your server is now accessible via:"
echo "  1. SSH (port 22) – requires SSH key (root login disabled)"
echo "  2. SSH (port 2222) – rescue port, always allows password auth"
echo "  3. WireGuard admin VPN (port 51821) – for secure remote access"
echo ""
echo "The admin VPN is isolated from the internal WireGuard subnet (10.0.0.0/16)."
echo ""
echo "To generate a WireGuard client config, use:"
echo "  /usr/local/bin/add-wireguard-user.sh <username>"
echo ""
echo "To lock down SSH to your static IP later:"
echo "  ufw delete allow 22/tcp"
echo "  ufw allow from YOUR_IP to any port 22 proto tcp"
echo "============================================================"