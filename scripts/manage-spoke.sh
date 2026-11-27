#!/bin/bash
# =============================================================================
# manage-spoke.sh – Add or remove a spoke from the hub's WireGuard network
# FILE: scripts/manage-spoke.sh
# =============================================================================
# Usage: manage-spoke.sh add <spoke-name> <spoke-public-key> <spoke-ip>
#        manage-spoke.sh remove <spoke-name>
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

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

# Spoke: $NAME
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

        # Remove the peer block that begins with "# Spoke: <name>" and
        # continues until the next blank line or the end of the file.
        # Using awk keeps the edit atomic and preserves everything else
        # in the file exactly.
        python3 - "$WG_CONFIG" "$NAME" <<'PYEOF'
import sys
path, name = sys.argv[1], sys.argv[2]
with open(path) as f:
    lines = f.readlines()

out = []
skip = False
for line in lines:
    if line.strip() == f"# Spoke: {name}":
        skip = True
        continue
    if skip:
        if line.strip() == "":
            skip = False
        continue
    out.append(line)

with open(path, "w") as f:
    f.writelines(out)
PYEOF

        wg syncconf wg0 <(wg-quick strip wg0)
        echo "Spoke $NAME removed"
        ;;
    *)
        echo "Usage: $0 {add|remove} <args>"
        exit 1
        ;;
esac