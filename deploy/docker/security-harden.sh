#!/bin/bash
# =============================================================================
# NETTRADES.AI – Security Hardening Script
# =============================================================================
# Run once on a fresh Ubuntu 24.04 VM before deploying the platform.
# Disables root SSH, configures UFW, fail2ban, and Docker securely.
# =============================================================================
set -e

apt update && apt upgrade -y
apt install -y ufw fail2ban unattended-upgrades auditd aide apparmor-profiles \
  curl wget git vim htop net-tools software-properties-common \
  ca-certificates gnupg lsb-release jq wireguard wireguard-tools

# SSH hardening
cat >> /etc/ssh/sshd_config << 'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
EOF
systemctl restart sshd

# UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw allow 51820/udp comment 'WireGuard'
ufw --force enable

# Fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
[sshd]
enabled = true
[odoo-login]
enabled = true
port = http,https
filter = odoo
logpath = /var/log/odoo/odoo.log
maxretry = 3
EOF

cat > /etc/fail2ban/filter.d/odoo.conf << 'EOF'
[Definition]
failregex = ^.* WARNING .* login\?.* from <HOST>$
EOF

systemctl enable fail2ban --now

# Docker installation
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list
apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {"max-size": "10m", "max-file": "3"},
  "icc": false,
  "userland-proxy": false,
  "live-restore": true,
  "iptables": true
}
EOF

systemctl restart docker
usermod -aG docker ubuntu

echo "Security hardening complete. Reboot recommended."