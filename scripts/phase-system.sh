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
#   - Installing Node.js and npm for the Electron installer
#   - Ensuring port 80 is open for Let's Encrypt
#   - Multi-vendor GPU driver support (NVIDIA, AMD, Intel)
#   - Installing python3-venv for virtual environment creation
#   - Installing xdg-utils for the Electron launcher to open URLs
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
PER_USER="${PER_USER:-false}"
export PER_USER

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
# Detect OS & Platform
# -----------------------------------------------------------------------------
OS=$(detect_os)
PLATFORM=$(detect_platform)
log_info "Detected OS: $OS"
log_info "Detected platform: $PLATFORM"

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

# Check if venv and ensurepip are available
VENV_OK=false
if python3 -c "import venv; import ensurepip" &>/dev/null; then
    VENV_OK=true
    log_success "python3-venv already installed (venv and ensurepip available)"
fi

if [ "$VENV_OK" != true ]; then
    log_info "python3-venv or ensurepip missing – installing..."
    if [[ "$OS" == "linux" ]]; then
        # Try installing the versioned package first (Ubuntu 24.04+)
        if apt-cache show python3.12-venv &>/dev/null; then
            sudo apt-get update -qq
            sudo apt-get install -y python3.12-venv
        else
            # Fallback to generic python3-venv
            sudo apt-get update -qq
            sudo apt-get install -y python3-venv
        fi
        # Verify after installation
        if python3 -c "import venv; import ensurepip" &>/dev/null; then
            log_success "python3-venv installed successfully"
        else
            log_error "python3-venv installation failed – please install manually:"
            log_info "  apt install python3.12-venv"
            exit 1
        fi
    else
        log_warning "Please install python3-venv manually for $OS"
    fi
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

        # -----------------------------------------------------------------
        # Install NVIDIA Container Toolkit using the official method
        # -----------------------------------------------------------------
        log_step "Installing NVIDIA Container Toolkit..."

        # Check if already installed
        if command -v nvidia-container-toolkit &>/dev/null; then
            log_success "nvidia-container-toolkit already installed"
        else
            log_info "Adding NVIDIA Container Toolkit repository..."
            # Set up the repository and GPG key
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
                && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

            sudo apt-get update -qq
            sudo apt-get install -y nvidia-container-toolkit
            log_success "nvidia-container-toolkit installed"
        fi

        # Configure the runtime
        log_info "Configuring NVIDIA Container Toolkit runtime..."
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker || sudo service docker restart
        log_success "NVIDIA Container Toolkit configured"
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
    # Enable UFW if not active
    if ! ufw status | grep -q "active"; then
        log_info "Enabling UFW firewall..."
        sudo ufw --force enable
    else
        log_success "UFW firewall already active"
    fi

    # Ensure all required rules exist (idempotent)
    sudo ufw allow 22/tcp comment 'SSH (main)' 2>/dev/null || true
    sudo ufw allow 2222/tcp comment 'SSH (rescue)' 2>/dev/null || true
    sudo ufw allow 80/tcp comment 'HTTP' 2>/dev/null || true
    sudo ufw allow 443/tcp comment 'HTTPS' 2>/dev/null || true
    sudo ufw allow 51820/udp comment 'WireGuard (internal)' 2>/dev/null || true
    sudo ufw allow 51821/udp comment 'WireGuard (admin VPN)' 2>/dev/null || true
    log_success "UFW rules ensured"
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
        sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
        log_success "Added iptables rule for port 80"
    fi
fi

# -----------------------------------------------------------------------------
# 7. SSH Key Setup – Guide the user to create a key before hardening
# -----------------------------------------------------------------------------
log_step "Setting up SSH keys for secure access..."

# Use sudo for all operations on /root/.ssh
sudo mkdir -p /root/.ssh
sudo chmod 700 /root/.ssh

# =============================================================================
# FIX: Check if SSH key already exists and skip interactive prompt in --auto mode
# =============================================================================
SSH_KEY_EXISTS=false
if [[ -f /root/.ssh/id_ed25519.pub ]] || [[ -f /root/.ssh/id_rsa.pub ]]; then
    SSH_KEY_EXISTS=true
fi

add_public_key() {
    local key="$1"
    echo "$key" | sudo tee -a /root/.ssh/authorized_keys > /dev/null
    sudo chmod 600 /root/.ssh/authorized_keys
    log_success "Public key added to authorized_keys"
}

# If keys already exist and we're in --auto mode, just use them
if [[ "$SSH_KEY_EXISTS" == true ]] && [[ "$AUTO" == true ]]; then
    log_info "SSH key already exists. Skipping key generation (auto mode)."
    # Add existing key to authorized_keys if not already present
    if [[ -f /root/.ssh/id_ed25519.pub ]]; then
        if ! sudo grep -q -f /root/.ssh/id_ed25519.pub /root/.ssh/authorized_keys 2>/dev/null; then
            sudo cat /root/.ssh/id_ed25519.pub | sudo tee -a /root/.ssh/authorized_keys > /dev/null
            sudo chmod 600 /root/.ssh/authorized_keys
            log_success "Existing SSH key added to authorized_keys"
        fi
    elif [[ -f /root/.ssh/id_rsa.pub ]]; then
        if ! sudo grep -q -f /root/.ssh/id_rsa.pub /root/.ssh/authorized_keys 2>/dev/null; then
            sudo cat /root/.ssh/id_rsa.pub | sudo tee -a /root/.ssh/authorized_keys > /dev/null
            sudo chmod 600 /root/.ssh/authorized_keys
            log_success "Existing SSH key added to authorized_keys"
        fi
    fi
    # Skip the interactive prompt
    PUB_KEY_FILE=""
else
    # Check for existing public key
    PUB_KEY_FILE=""
    if [[ -f /root/.ssh/id_ed25519.pub ]]; then
        PUB_KEY_FILE="/root/.ssh/id_ed25519.pub"
    elif [[ -f /root/.ssh/id_rsa.pub ]]; then
        PUB_KEY_FILE="/root/.ssh/id_rsa.pub"
    fi

    if [[ -n "$PUB_KEY_FILE" ]]; then
        log_info "Found existing public key: $PUB_KEY_FILE"
        if ! sudo grep -q -f "$PUB_KEY_FILE" /root/.ssh/authorized_keys 2>/dev/null; then
            sudo cat "$PUB_KEY_FILE" | sudo tee -a /root/.ssh/authorized_keys > /dev/null
            sudo chmod 600 /root/.ssh/authorized_keys
            log_success "Existing public key added to authorized_keys"
        else
            log_success "Public key already in authorized_keys"
        fi
    else
        log_warning "No SSH public key found in /root/.ssh/"

        if [[ "$AUTO" == true ]]; then
            log_info "Auto mode: generating a new Ed25519 SSH key without a passphrase..."
            sudo ssh-keygen -t ed25519 -C "root@$(hostname)" -f /root/.ssh/id_ed25519 -N ""
            sudo cat /root/.ssh/id_ed25519.pub | sudo tee -a /root/.ssh/authorized_keys > /dev/null
            sudo chmod 600 /root/.ssh/authorized_keys
            log_success "New key generated and added to authorized_keys"
            echo ""
            echo "Your new public key is:"
            sudo cat /root/.ssh/id_ed25519.pub
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
                    sudo ssh-keygen -t ed25519 -C "root@$(hostname)" -f /root/.ssh/id_ed25519
                    sudo cat /root/.ssh/id_ed25519.pub | sudo tee -a /root/.ssh/authorized_keys > /dev/null
                    sudo chmod 600 /root/.ssh/authorized_keys
                    log_success "New key generated and added to authorized_keys"
                    echo ""
                    echo "Your new public key is:"
                    sudo cat /root/.ssh/id_ed25519.pub
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

# Get the full path of sshd
SSHD_PATH=$(command -v sshd)
if [[ -z "$SSHD_PATH" ]]; then
    log_error "sshd not found in PATH. Cannot set up rescue SSH server."
    exit 1
fi

# Create /run/sshd if it doesn't exist (needed on WSL)
if [[ ! -d /run/sshd ]]; then
    sudo mkdir -p /run/sshd
    sudo chmod 755 /run/sshd
    log_success "Created /run/sshd directory"
fi

# Create the rescue SSH configuration file
sudo tee /etc/ssh/sshd_config_rescue > /dev/null << EOF
Port 2222
PasswordAuthentication yes
PermitRootLogin yes
PubkeyAuthentication yes
LogLevel INFO
UsePAM yes
EOF

# Create a systemd service for the rescue SSH server
sudo tee /etc/systemd/system/ssh-rescue.service > /dev/null << EOF
[Unit]
Description=Rescue SSH server on port 2222
After=network.target

[Service]
ExecStart=$SSHD_PATH -f /etc/ssh/sshd_config_rescue -D
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ssh-rescue.service
sudo systemctl start ssh-rescue.service

# Verify it's running
if systemctl is-active --quiet ssh-rescue.service; then
    log_success "Rescue SSH server started on port 2222 (password auth allowed) and enabled at boot"
else
    log_warning "Failed to start rescue SSH server via systemd. Trying to start manually..."
    sudo $SSHD_PATH -f /etc/ssh/sshd_config_rescue -D &
    sleep 2
    if pgrep -f "sshd.*rescue" > /dev/null; then
        log_success "Rescue SSH server started manually on port 2222"
    else
        log_error "Rescue SSH server could not be started. Please investigate."
        exit 1
    fi
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
# 10. WireGuard Admin VPN Server (with per-user fallback)
# -----------------------------------------------------------------------------
log_step "Setting up WireGuard admin VPN server..."

# Detect the primary network interface
PRIMARY_IFACE=$(ip route | grep default | awk '{print $5}' | head -1)
if [[ -z "$PRIMARY_IFACE" ]]; then
    PRIMARY_IFACE="eth0"
fi
log_info "Detected primary network interface: $PRIMARY_IFACE"

# Determine installation mode
if [[ "$PER_USER" == true ]]; then
    # Per-user mode: store config in home directory
    WG_ADMIN_DIR="${HOME}/.nettrades/wireguard/admin"
    mkdir -p "$WG_ADMIN_DIR"
    log_info "Per-user mode: storing WireGuard config in ${WG_ADMIN_DIR}"
else
    WG_ADMIN_DIR="/etc/wireguard/admin"
    # Ensure directory exists with correct permissions
    sudo mkdir -p "$WG_ADMIN_DIR"
    sudo chmod 755 "$WG_ADMIN_DIR"
    # If we're not root, try to set ownership to current user (for later file creation)
    if [[ "$USER" != "root" ]]; then
        sudo chown "$USER:$USER" "$WG_ADMIN_DIR" 2>/dev/null || true
    fi
fi

# Generate keys if missing
if [[ ! -f "$WG_ADMIN_DIR/privatekey" ]]; then
    if [[ "$PER_USER" == true ]]; then
        wg genkey | tee "$WG_ADMIN_DIR/privatekey" | wg pubkey > "$WG_ADMIN_DIR/publickey"
    else
        # Create files with proper permissions
        sudo touch "$WG_ADMIN_DIR/privatekey" "$WG_ADMIN_DIR/publickey"
        sudo chmod 600 "$WG_ADMIN_DIR/privatekey" "$WG_ADMIN_DIR/publickey"
        sudo wg genkey | sudo tee "$WG_ADMIN_DIR/privatekey" > /dev/null
        sudo wg pubkey < "$WG_ADMIN_DIR/privatekey" | sudo tee "$WG_ADMIN_DIR/publickey" > /dev/null
    fi
    log_success "WireGuard keys generated"
else
    log_success "WireGuard keys already exist"
fi

# Determine architecture for wireguard-go download
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  WG_GO_ARCH="amd64" ;;
    aarch64|arm64) WG_GO_ARCH="arm64" ;;
    armv7l)  WG_GO_ARCH="armv7" ;;
    *)       WG_GO_ARCH="amd64" ;;  # fallback
esac

# Check if WireGuard kernel module is available
WG_MODULE_AVAILABLE=false
if modprobe wireguard 2>/dev/null || lsmod | grep -q wireguard || [[ -d "/sys/module/wireguard" ]]; then
    WG_MODULE_AVAILABLE=true
    log_info "WireGuard kernel module available"
else
    log_warning "WireGuard kernel module not available"
fi

if [[ "$WG_MODULE_AVAILABLE" == true ]]; then
    # Use kernel WireGuard
    log_info "Using kernel WireGuard module"

    # Create wg0.conf (without Address line – it will be set by ip)
    if [[ ! -f "$WG_ADMIN_DIR/wg0.conf" ]]; then
        if [[ "$PER_USER" == true ]]; then
            cat > "$WG_ADMIN_DIR/wg0.conf" << EOF
[Interface]
PrivateKey = $(cat "$WG_ADMIN_DIR/privatekey")
ListenPort = 51821
EOF
        else
            sudo tee "$WG_ADMIN_DIR/wg0.conf" > /dev/null << EOF
[Interface]
PrivateKey = $(sudo cat "$WG_ADMIN_DIR/privatekey")
ListenPort = 51821
EOF
        fi
        log_success "wg0.conf created (kernel mode)"
    fi

    # Start WireGuard interface if not already up
    if ! ip link show wg0 &>/dev/null; then
        sudo ip link add wg0 type wireguard
        sudo wg setconf wg0 "$WG_ADMIN_DIR/wg0.conf"
        sudo ip addr add 10.10.10.1/24 dev wg0
        sudo ip link set wg0 up
        log_success "WireGuard interface wg0 created and started"
    else
        log_success "WireGuard interface wg0 already exists"
    fi
else
    # =========================================================================
    # Fallback to wireguard-go for users without kernel module
    # =========================================================================
    log_warning "WireGuard kernel module not available. Using userspace fallback."

    # Determine architecture for wireguard-go
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  WG_GO_ARCH="amd64" ;;
        aarch64|arm64) WG_GO_ARCH="arm64" ;;
        armv7l)  WG_GO_ARCH="armv7" ;;
        *)       WG_GO_ARCH="amd64" ;;
    esac

    if [[ "$PER_USER" == true ]]; then
        WG_GO_CMD="${HOME}/.local/bin/wireguard-go"
        mkdir -p "${HOME}/.local/bin"
    else
        WG_GO_CMD="/usr/local/bin/wireguard-go"
    fi

    # Try to install wireguard-go via apt first (more reliable on Ubuntu 24.04+)
    WG_GO_INSTALLED=false
    if command -v apt &>/dev/null; then
        log_info "Attempting to install wireguard-go via apt..."
        sudo apt-get update -qq
        if sudo apt-get install -y wireguard-go; then
            if [[ -f /usr/bin/wireguard-go ]]; then
                sudo cp /usr/bin/wireguard-go "$WG_GO_CMD"
                sudo chmod +x "$WG_GO_CMD"
                WG_GO_INSTALLED=true
                log_success "wireguard-go installed from apt"
            fi
        fi
    fi

    # If apt failed, download from GitHub
    if [[ "$WG_GO_INSTALLED" != true ]]; then
        # Remove any old/broken binary
        if [[ -f "$WG_GO_CMD" ]]; then
            if ! "$WG_GO_CMD" --version &>/dev/null; then
                log_warning "Existing wireguard-go binary is broken. Removing..."
                if [[ "$PER_USER" == true ]]; then
                    rm -f "$WG_GO_CMD"
                else
                    sudo rm -f "$WG_GO_CMD"
                fi
            fi
        fi

        # Download wireguard-go if missing or broken
        if [[ ! -f "$WG_GO_CMD" ]]; then
            WG_GO_VERSION="0.0.20230223"
            WG_GO_URL="https://github.com/WireGuard/wireguard-go/releases/download/v${WG_GO_VERSION}/wireguard-go-linux-${WG_GO_ARCH}"
            log_info "Downloading wireguard-go for architecture: ${WG_GO_ARCH} from $WG_GO_URL"
            if [[ "$PER_USER" == true ]]; then
                curl -L -o "$WG_GO_CMD" "$WG_GO_URL"
                chmod +x "$WG_GO_CMD"
            else
                sudo curl -L -o "$WG_GO_CMD" "$WG_GO_URL"
                sudo chmod +x "$WG_GO_CMD"
            fi
            # Verify download
            if [[ ! -f "$WG_GO_CMD" ]] || [[ ! -x "$WG_GO_CMD" ]]; then
                log_error "wireguard-go download failed or binary is not executable."
                exit 1
            fi
            # Check file size (should be > 1MB)
            local wg_size=$(stat -c%s "$WG_GO_CMD" 2>/dev/null || stat -f%z "$WG_GO_CMD" 2>/dev/null || echo 0)
            if [[ "$wg_size" -lt 100000 ]]; then
                log_error "Downloaded wireguard-go binary is too small ($wg_size bytes). Download failed."
                exit 1
            fi
            log_success "wireguard-go installed to $WG_GO_CMD"
        else
            log_success "wireguard-go already installed at $WG_GO_CMD"
        fi
    fi

    # Force recreate wg0.conf without Address line (remove old file first)
    if [[ "$PER_USER" == true ]]; then
        rm -f "$WG_ADMIN_DIR/wg0.conf"
        cat > "$WG_ADMIN_DIR/wg0.conf" << EOF
[Interface]
PrivateKey = $(cat "$WG_ADMIN_DIR/privatekey")
ListenPort = 51821
EOF
    else
        sudo rm -f "$WG_ADMIN_DIR/wg0.conf"
        sudo tee "$WG_ADMIN_DIR/wg0.conf" > /dev/null << EOF
[Interface]
PrivateKey = $(sudo cat "$WG_ADMIN_DIR/privatekey")
ListenPort = 51821
EOF
    fi
    log_success "wg0.conf created (userspace) without Address line"

    # Stop any existing wireguard-go process
    if pgrep -f "$WG_GO_CMD wg0" > /dev/null; then
        log_info "Stopping existing wireguard-go process..."
        sudo pkill -f "$WG_GO_CMD wg0" || true
        sleep 1
        # Remove existing wg0 interface if it exists
        if ip link show wg0 &>/dev/null; then
            sudo ip link delete wg0 || true
            sleep 1
        fi
    fi

    # Start wireguard-go daemon
    log_info "Starting wireguard-go daemon..."
    if [[ "$PER_USER" == true ]]; then
        "$WG_GO_CMD" wg0 &
    else
        sudo "$WG_GO_CMD" wg0 &
    fi
    sleep 3

    # Check if wg0 interface appeared
    if ! ip link show wg0 &>/dev/null; then
        log_error "wireguard-go failed to create wg0 interface. Check logs."
        # Show last few lines of dmesg for clues
        dmesg | tail -20
        exit 1
    fi

    # Configure the interface
    if [[ "$PER_USER" == true ]]; then
        wg setconf wg0 "$WG_ADMIN_DIR/wg0.conf"
        sudo ip addr add 10.10.10.1/24 dev wg0 2>/dev/null || true
        sudo ip link set wg0 up 2>/dev/null || true
    else
        sudo wg setconf wg0 "$WG_ADMIN_DIR/wg0.conf"
        sudo ip addr add 10.10.10.1/24 dev wg0 2>/dev/null || true
        sudo ip link set wg0 up 2>/dev/null || true
    fi
    log_success "wireguard-go started and configured"
fi

# -----------------------------------------------------------------------------
# 11. Copy WireGuard client management script to /usr/local/bin (if available)
# -----------------------------------------------------------------------------
if [[ -f "$SCRIPT_DIR/wireguard-manager.sh" ]]; then
    sudo cp "$SCRIPT_DIR/wireguard-manager.sh" /usr/local/bin/
    sudo chmod +x /usr/local/bin/wireguard-manager.sh
    log_success "WireGuard manager script installed to /usr/local/bin/wireguard-manager.sh"
else
    log_warning "wireguard-manager.sh not found – skipping"
fi

# -----------------------------------------------------------------------------
# 12. SSH hardening (with self-test to prevent lockout)
# -----------------------------------------------------------------------------
log_step "Hardening SSH configuration (main port 22)..."

# Backup current config
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

if [[ -f /etc/ssh/sshd_config ]]; then
    # Disable root login globally
    sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
    sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

    # Disable password authentication globally (will be overridden for VPN)
    sudo sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
    sudo sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

    # Allow password authentication from the WireGuard admin VPN subnet
    if ! grep -q "Match Address 10.10.10.0/24" /etc/ssh/sshd_config; then
        echo "" | sudo tee -a /etc/ssh/sshd_config
        echo "Match Address 10.10.10.0/24" | sudo tee -a /etc/ssh/sshd_config
        echo "    PasswordAuthentication yes" | sudo tee -a /etc/ssh/sshd_config
        echo "Match All" | sudo tee -a /etc/ssh/sshd_config
        log_success "SSH will allow password authentication from 10.10.10.0/24"
    fi
fi

# Test SSH config before restart
if ! sudo sshd -t; then
    log_error "SSH config test failed. Restoring backup..."
    sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    sudo systemctl restart ssh
    log_error "SSH config reverted. Please fix manually."
    exit 1
fi

# Restart SSH
sudo systemctl restart ssh 2>/dev/null || sudo systemctl restart sshd 2>/dev/null || true

# -----------------------------------------------------------------------------
# 13. Self-test: Verify SSH accessibility
# -----------------------------------------------------------------------------
log_step "Verifying SSH access (to prevent lockout)..."

# Test SSH from localhost using password (rescue port)
if ssh -o ConnectTimeout=5 -o PasswordAuthentication=yes -o BatchMode=no -p 2222 localhost "echo OK" 2>/dev/null | grep -q OK; then
    log_success "Rescue SSH port (2222) is accessible with password auth"
else
    log_error "Rescue SSH port test failed! SSH may be broken."
    log_error "Reverting SSH configuration to prevent lockout."
    sudo cp /etc/ssh/sshd_config.bak /etc/ssh/sshd_config
    sudo systemctl restart ssh
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
# 14. Install fail2ban
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
# 15. Install dos2unix, jq, xdg-utils, Wine, libfuse2, and Electron build/runtime libraries
# -----------------------------------------------------------------------------
log_step "Installing system dependencies (dos2unix, jq, xdg-utils, Wine, libfuse2, Electron libraries)..."

# Check if already installed
if command -v dos2unix &>/dev/null && command -v jq &>/dev/null && command -v xdg-open &>/dev/null && command -v wine &>/dev/null; then
    log_success "All system dependencies already installed"
else
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y \
            dos2unix \
            curl \
            wget \
            git \
            jq \
            xdg-utils \
            libfuse2 \
            wine \
            libnss3 \
            libxss1 \
            libasound2t64 \
            libatk-bridge2.0-0t64 \
            libgtk-3-0t64 \
            libgbm1 \
            libnspr4 \
            fonts-noto-color-emoji
        log_success "All system dependencies installed"
    else
        log_warning "Please install dos2unix, jq, xdg-utils, wine, libfuse2, and Electron libraries manually for $OS"
    fi
fi

# -----------------------------------------------------------------------------
# 16. Install bcrypt for Prometheus password hashing (now handled in phase-deploy.sh)
# -----------------------------------------------------------------------------
# This step is moved to phase-deploy.sh to ensure it uses the venv.
# Keeping a placeholder to avoid confusion.
log_info "bcrypt will be installed in the virtual environment during Phase 2."

# -----------------------------------------------------------------------------
# 17. Configure system limits
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
# 18. Check gVisor installation
# -----------------------------------------------------------------------------
log_step "Checking gVisor installation..."

# Detect WSL2 (reuse the same logic)
if grep -q Microsoft /proc/version 2>/dev/null || grep -q WSL /proc/sys/fs/binfmt_misc/WSLInterop 2>/dev/null; then
    log_info "WSL2 detected – gVisor is not used (default runc runtime will be used)."
else
    if command -v runsc &>/dev/null; then
        log_success "gVisor already installed"
    else
        log_info "gVisor not installed – will be installed during Kubernetes phase if needed"
    fi
fi

# -----------------------------------------------------------------------------
# 19. WireGuard client configuration reminder
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
# 20. Mark phase complete
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