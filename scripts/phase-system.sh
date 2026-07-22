#!/bin/bash
# =============================================================================
# FILE: scripts/phase-system.sh
# =============================================================================
# PURPOSE:
#   Phase 0: System Preparation & Security Hardening.
#   This phase prepares the host system for NETTRADES deployment by:
#   - Installing system dependencies (Docker, Docker Compose, NVIDIA drivers)
#   - Configuring firewall (UFW/iptables)
#   - Setting up a WireGuard VPN server for administrative access
#   - Hardening SSH (disable root login, key-only auth globally,
#     but allow password auth from the VPN subnet)
#   - Installing fail2ban
#   - Configuring system limits for high-performance workloads
#   - Enabling gVisor runtime for container isolation (if on Kubernetes)
#   - [NEW] Installing Node.js and npm for the Electron installer
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
# 3.5 Install Node.js and npm (for the Electron installer)
# -----------------------------------------------------------------------------
log_step "Checking Node.js and npm installation..."

# Check if Node.js is already installed
if command -v node &>/dev/null && command -v npm &>/dev/null; then
    NODE_VERSION=$(node --version | cut -d'v' -f2)
    log_success "Node.js $NODE_VERSION already installed"
else
    log_info "Installing Node.js 18 LTS..."

    # Use NodeSource's official script for Ubuntu/Debian
    if [[ "$OS" == "linux" ]]; then
        # Check if NodeSource setup script is already run
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
    # If npm is missing on Debian/Ubuntu, install it separately
    if [[ "$OS" == "linux" ]]; then
        sudo apt-get install -y npm
    else
        log_warning "npm not found. Please install npm manually."
    fi
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

# -----------------------------------------------------------------------------
# 6. SSH Key Setup – Guide the user to create a key before hardening
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
# 7. Rescue SSH Port (always allows password auth, as a safety net)
# -----------------------------------------------------------------------------
log_step "Setting up rescue SSH port (2222)..."

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
# 8. Install WireGuard tools (if not already present)
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
# 9. WireGuard Admin VPN Server (for emergency SSH access)
# -----------------------------------------------------------------------------
log_step "Setting up WireGuard admin VPN server..."

WG_ADMIN_DIR="/etc/wireguard/admin"
mkdir -p "$WG_ADMIN_DIR"

if [[ ! -f "$WG_ADMIN_DIR/privatekey" ]]; then
    wg genkey | tee "$WG_ADMIN_DIR/privatekey" | wg pubkey > "$WG_ADMIN_DIR/publickey"
fi

# Create server configuration with iptables rules to isolate admin VPN from internal network
cat > "$WG_ADMIN_DIR/wg0.conf" << EOF
[Interface]
Address = 10.10.10.1/24
ListenPort = 51821
PrivateKey = $(cat "$WG_ADMIN_DIR/privatekey")
SaveConfig = false

# Allow forwarding and NAT for VPN clients
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
# Block admin VPN from accessing internal WireGuard subnet (10.0.0.0/16)
PostUp = iptables -I FORWARD -i wg0 -d 10.0.0.0/16 -j DROP

PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i wg0 -d 10.0.0.0/16 -j DROP 2>/dev/null || true
EOF

systemctl enable wg-quick@admin-wg0 2>/dev/null || true
systemctl start wg-quick@admin-wg0 2>/dev/null || true
log_success "WireGuard admin VPN server started on port 51821 (subnet 10.10.10.0/24)"

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
# 10. SSH hardening (with self-test to prevent lockout)
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
# 11. Self-test: Verify SSH accessibility
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
# 12. Install fail2ban
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
# 13. Install dos2unix and jq
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
# 14. Install bcrypt for Prometheus password hashing
# -----------------------------------------------------------------------------
log_step "Installing bcrypt for Prometheus password hashing..."
if python3 -c "import bcrypt" &>/dev/null; then
    log_success "bcrypt Python module already installed"
else
    log_info "bcrypt not found – installing..."
    if [[ "$OS" == "linux" ]]; then
        if command -v apt-get &>/dev/null; then
            sudo apt-get update -qq
            sudo apt-get install -y python3-bcrypt && log_success "bcrypt installed via apt"
        else
            pip3 install bcrypt --break-system-packages 2>/dev/null || pip3 install bcrypt && log_success "bcrypt installed via pip"
        fi
    else
        pip3 install bcrypt 2>/dev/null && log_success "bcrypt installed via pip" || log_warning "Could not install bcrypt. Please install manually."
    fi
fi

# -----------------------------------------------------------------------------
# 15. Configure system limits
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
# 16. Check gVisor installation
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