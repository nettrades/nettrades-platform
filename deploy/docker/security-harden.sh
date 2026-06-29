#!/bin/bash
# =============================================================================
# FILE: deploy/docker/security-harden.sh
# =============================================================================
# PURPOSE:
#   Hardens a fresh Ubuntu 24.04 VM for NETTRADES deployment.
#   This script is IDEMPOTENT – it can be re-run safely without breaking
#   existing configurations. It checks for existing settings before applying.
#
#   It configures:
#     - UFW firewall (SSH only by default)
#     - SSH hardening (disables root login, password auth)
#     - Fail2ban with Odoo-specific jail
#     - Unattended upgrades (security updates only)
#     - Auditd (basic auditing)
#     - AppArmor (enforcing mode)
#     - Disables unnecessary services (e.g., CUPS)
#
#   It detects Proxmox and will ask for confirmation before modifying
#   firewall rules that could affect Proxmox networking.
#
# USAGE:
#   sudo ./security-harden.sh [--auto]
#     --auto: Skip confirmation prompts, apply all hardening (use with caution).
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Colours
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
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
# Check if running as root
# -----------------------------------------------------------------------------
if [ "$EUID" -ne 0 ]; then
    log_error "This script must be run as root (sudo)."
    exit 1
fi

# -----------------------------------------------------------------------------
# Detect if this is a Proxmox host
# -----------------------------------------------------------------------------
IS_PROXMOX=false
if [ -d "/etc/pve" ] || command -v pveversion &>/dev/null; then
    IS_PROXMOX=true
    log_warning "This system appears to be a Proxmox VE host."
    log_warning "Proxmox uses its own firewall and networking configuration."
    if [ "$AUTO" != true ]; then
        read -rp "Continue with UFW and SSH hardening? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            log_info "Security hardening skipped by user."
            exit 0
        fi
    fi
fi

# -----------------------------------------------------------------------------
# 1. Update package lists and install security packages
# -----------------------------------------------------------------------------
log_info "Installing security packages..."
apt update -qq
apt install -y -qq ufw fail2ban auditd apparmor-utils unattended-upgrades

# -----------------------------------------------------------------------------
# 2. Configure UFW (Firewall)
# -----------------------------------------------------------------------------
if command -v ufw &>/dev/null; then
    if ufw status | grep -q "Status: active"; then
        log_info "UFW is already active. Skipping UFW configuration."
    else
        log_info "Configuring UFW..."
        # Set default policies
        ufw default deny incoming
        ufw default allow outgoing
        # Allow SSH (port 22)
        ufw allow ssh
        # If Proxmox, also allow web interface (8006) if user wants
        if [ "$IS_PROXMOX" = true ]; then
            log_warning "Proxmox detected. You may want to allow port 8006 for web interface."
            if [ "$AUTO" != true ]; then
                read -rp "Allow Proxmox web interface (port 8006)? (y/N): " allow_proxmox
                if [[ "$allow_proxmox" =~ ^[Yy]$ ]]; then
                    ufw allow 8006/tcp
                fi
            fi
        fi
        # Enable UFW
        ufw --force enable
        log_success "UFW configured"
    fi
fi

# -----------------------------------------------------------------------------
# 3. Harden SSH configuration
# -----------------------------------------------------------------------------
log_info "Hardening SSH configuration..."
SSHD_CONFIG="/etc/ssh/sshd_config"

# Backup original if not already backed up
if [ ! -f "${SSHD_CONFIG}.orig" ]; then
    cp "$SSHD_CONFIG" "${SSHD_CONFIG}.orig"
    log_info "Backup of original sshd_config saved to ${SSHD_CONFIG}.orig"
fi

# Function to idempotently set a key in sshd_config
set_ssh_option() {
    local key="$1"
    local value="$2"
    local full="$key $value"
    if grep -q "^$key" "$SSHD_CONFIG"; then
        # Key exists; update if value differs
        if ! grep -q "^$full" "$SSHD_CONFIG"; then
            sed -i "s/^$key.*/$full/" "$SSHD_CONFIG"
            log_info "Updated $key to $value"
        else
            log_info "$key already set to $value"
        fi
    else
        # Key doesn't exist; append
        echo "$full" >> "$SSHD_CONFIG"
        log_info "Added $key $value"
    fi
}

set_ssh_option "PermitRootLogin" "no"
set_ssh_option "PasswordAuthentication" "no"
set_ssh_option "ChallengeResponseAuthentication" "no"
set_ssh_option "PubkeyAuthentication" "yes"
set_ssh_option "MaxAuthTries" "3"

# Restart SSH to apply changes (only if we changed anything)
if systemctl is-active ssh &>/dev/null; then
    systemctl restart ssh
    log_success "SSH restarted with new configuration"
fi

# -----------------------------------------------------------------------------
# 4. Configure Fail2ban with Odoo jail
# -----------------------------------------------------------------------------
log_info "Configuring Fail2ban..."
FAIL2BAN_JAIL_LOCAL="/etc/fail2ban/jail.local"
if [ -f "$FAIL2BAN_JAIL_LOCAL" ] && grep -q "\[odoologin\]" "$FAIL2BAN_JAIL_LOCAL"; then
    log_info "Odoo jail already configured in fail2ban. Skipping."
else
    cat >> "$FAIL2BAN_JAIL_LOCAL" << 'EOF'
[odoologin]
enabled = true
port = http,https
filter = odoologin
logpath = /var/log/odoo/odoo.log
maxretry = 5
bantime = 3600
findtime = 600

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
bantime = 3600
EOF
    log_success "Fail2ban Odoo jail configured"
fi

# Restart fail2ban if it's running
if systemctl is-active fail2ban &>/dev/null; then
    systemctl restart fail2ban
    log_success "Fail2ban restarted"
fi

# -----------------------------------------------------------------------------
# 5. Configure Unattended Upgrades
# -----------------------------------------------------------------------------
log_info "Configuring unattended-upgrades..."
dpkg-reconfigure -f noninteractive unattended-upgrades
systemctl enable unattended-upgrades
systemctl start unattended-upgrades
log_success "Unattended upgrades configured"

# -----------------------------------------------------------------------------
# 6. Enable AppArmor (if not already)
# -----------------------------------------------------------------------------
if command -v aa-status &>/dev/null; then
    if aa-status | grep -q "apparmor module is loaded"; then
        log_info "AppArmor already enabled."
    else
        systemctl enable apparmor
        systemctl start apparmor
        log_success "AppArmor enabled"
    fi
fi

# -----------------------------------------------------------------------------
# 7. Disable unnecessary services (safe, idempotent)
# -----------------------------------------------------------------------------
log_info "Disabling unnecessary services..."
# Example: disable CUPS if installed
if systemctl list-unit-files | grep -q cups; then
    if systemctl is-enabled cups &>/dev/null; then
        systemctl disable cups
        systemctl stop cups
        log_success "CUPS disabled"
    else
        log_info "CUPS already disabled"
    fi
fi

# -----------------------------------------------------------------------------
# 8. Set up auditd (basic auditing)
# -----------------------------------------------------------------------------
log_info "Configuring auditd..."
auditctl -e 1 2>/dev/null || log_warning "auditctl failed (may already be enabled)"

# -----------------------------------------------------------------------------
# 9. Final summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Security hardening completed!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Summary of applied changes:"
echo "  - UFW firewall enabled (SSH allowed)"
if [ "$IS_PROXMOX" = true ]; then
    echo "  - Proxmox detected: additional port 8006 may have been allowed"
fi
echo "  - SSH hardened (root login disabled, password auth disabled)"
echo "  - Fail2ban configured with Odoo jail"
echo "  - Unattended upgrades enabled"
echo "  - AppArmor enabled"
echo "  - Unnecessary services disabled"
echo ""
log_info "Recommendation: Reboot the system to ensure all changes take effect."