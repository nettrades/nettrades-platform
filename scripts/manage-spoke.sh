#!/bin/bash
# =============================================================================
# manage-spoke.sh – Add or remove a spoke from the hub's WireGuard network
# =============================================================================
# Usage: manage-spoke.sh add <spoke-name> <spoke-public-key> <spoke-ip>
#        manage-spoke.sh remove <spoke-name>
# =============================================================================

set -euo pipefail

WG_INTERNAL_DIR="/etc/wireguard/internal"
WG_CONFIG="$WG_INTERNAL_DIR/wg0.conf"

case "${1:-}" in
    add)
        NAME="$2"
        PUBKEY="$3"
        IP="$4"
        if [[ -z "$NAME" || -z "$PUBKEY" || -z "$IP" ]]; then
            echo "Usage: $0 add <name> <public-key> <ip>"
            exit 1
        fi
        # Add peer to WireGuard config
        cat >> "$WG_CONFIG" << PEER

[Peer]
PublicKey = $PUBKEY
AllowedIPs = $IP/32
PEER
        # Reload WireGuard
        wg syncconf wg0 <(wg-quick strip wg0)
        echo "Spoke $NAME added with IP $IP"
        ;;
    remove)
        NAME="$2"
        if [[ -z "$NAME" ]]; then
            echo "Usage: $0 remove <name>"
            exit 1
        fi
        # Remove peer (this is more complex – you'd need to parse and rebuild the config)
        echo "⚠️ Manual removal required – edit $WG_CONFIG and remove the peer section"
        ;;
    *)
        echo "Usage: $0 {add|remove} <args>"
        exit 1
        ;;
esac