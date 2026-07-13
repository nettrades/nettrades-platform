#!/bin/bash
# =============================================================================
# add-wireguard-user.sh – Generate WireGuard client configurations
# =============================================================================
# Usage: add-wireguard-user.sh <username>
# Example: add-wireguard-user.sh alice
#
# This script generates a client configuration file and adds the peer to the
# server's WireGuard configuration.
# =============================================================================

set -euo pipefail

USERNAME="$1"
if [[ -z "$USERNAME" ]]; then
    echo "Usage: $0 <username>"
    exit 1
fi

WG_ADMIN_DIR="/etc/wireguard/admin"
CLIENT_DIR="/root/wireguard-clients"
mkdir -p "$CLIENT_DIR"

# Generate client keys
CLIENT_PRIV=$(wg genkey)
CLIENT_PUB=$(echo "$CLIENT_PRIV" | wg pubkey)

# Find next available IP (10.10.10.2 - 10.10.10.254)
LAST_IP=$(grep -oP '10\.10\.10\.\d+' "$WG_ADMIN_DIR/wg0.conf" | sort -t. -k4 -n | tail -1 | cut -d. -f4)
NEXT_IP=$((LAST_IP + 1))
if [[ -z "$LAST_IP" ]] || [[ "$LAST_IP" -lt 2 ]]; then
    NEXT_IP=2
fi
CLIENT_IP="10.10.10.$NEXT_IP"

# Add peer to server config
cat >> "$WG_ADMIN_DIR/wg0.conf" << PEER

[Peer]
PublicKey = $CLIENT_PUB
AllowedIPs = $CLIENT_IP/32
PEER

# Reload WireGuard
wg syncconf wg0 <(wg-quick strip wg0)

# Create client config
cat > "$CLIENT_DIR/$USERNAME.conf" << CLIENT
[Interface]
PrivateKey = $CLIENT_PRIV
Address = $CLIENT_IP/24
DNS = 8.8.8.8

[Peer]
PublicKey = $(cat "$WG_ADMIN_DIR/publickey")
Endpoint = 161.97.136.27:51821
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
CLIENT

echo " Client configuration created: $CLIENT_DIR/$USERNAME.conf"
echo " Public key: $CLIENT_PUB"
echo " Client IP: $CLIENT_IP"
echo ""
echo "Send $CLIENT_DIR/$USERNAME.conf to the user."