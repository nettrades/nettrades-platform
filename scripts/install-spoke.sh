#!/bin/bash
# =============================================================================
# FILE: scripts/install-spoke.sh
# =============================================================================
# PURPOSE:
#   Install a NETTRADES spoke on Windows (via WSL) or Linux.
#
#   The spoke:
#     1. Joins the WireGuard mesh at the sub-hub.
#     2. Runs llama.cpp's rpc-server on port 50052.
#     3. Runs the heartbeat agent.
#
#   No Odoo, no PostgreSQL, no LangGraph. Compute node only.
#
# USAGE:
#   sudo ./scripts/install-spoke.sh \
#     --hub-host=<WG_PUBLIC_IP_OR_DNS> \
#     --token=<REGISTRATION_TOKEN> \
#     [--node-name=<NAME>] \
#     [--rpc-server=/path/to/rpc-server]
# =============================================================================

set -euo pipefail

HUB_HOST=""
TOKEN=""
NODE_NAME="$(hostname)"
RPC_SERVER_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hub-host=*)    HUB_HOST="${1#*=}" ;;
        --hub-host)      HUB_HOST="$2"; shift ;;
        --token=*)       TOKEN="${1#*=}" ;;
        --token)         TOKEN="$2"; shift ;;
        --node-name=*)   NODE_NAME="${1#*=}" ;;
        --node-name)     NODE_NAME="$2"; shift ;;
        --rpc-server=*)  RPC_SERVER_PATH="${1#*=}" ;;
        --rpc-server)    RPC_SERVER_PATH="$2"; shift ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ -z "$HUB_HOST" || -z "$TOKEN" ]]; then
    echo "ERROR: --hub-host and --token are required" >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: must be run as root" >&2
    exit 1
fi

AGENT_DIR="/opt/nettrades/spoke"
CONFIG_DIR="/etc/nettrades/spoke"
AGENT_BIN="$AGENT_DIR/spoke-agent.py"

echo "Installing NETTRADES spoke..."
echo "  Hub:       $HUB_HOST"
echo "  Node:      $NODE_NAME"

# -- 1. System packages ------------------------------------------------
if ! command -v wg >/dev/null 2>&1; then
    echo "Installing wireguard-tools..."
    apt-get update -qq
    apt-get install -y wireguard-tools
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required" >&2
    exit 1
fi

# -- 2. rpc-server -----------------------------------------------------
if [[ -n "$RPC_SERVER_PATH" ]]; then
    install -m 0755 "$RPC_SERVER_PATH" /usr/local/bin/rpc-server
elif ! command -v rpc-server >/dev/null 2>&1; then
    echo "rpc-server not found."
    echo "Please install a llama.cpp build that includes rpc-server"
    echo "(compile with -DGGML_RPC=ON) and place it on PATH, or pass"
    echo "--rpc-server=/path/to/rpc-server."
    echo ""
    echo "Example build:"
    echo "  git clone https://github.com/ggml-org/llama.cpp"
    echo "  cd llama.cpp"
    echo "  cmake -B build -DGGML_RPC=ON -DGGML_CUDA=ON"
    echo "  cmake --build build --config Release -j"
    echo "  sudo install -m 0755 build/bin/rpc-server /usr/local/bin/"
    exit 1
fi

# -- 3. Python deps ----------------------------------------------------
PY_DEPS="requests pyyaml"
python3 -c "import requests, yaml" 2>/dev/null || {
    pip3 install --break-system-packages $PY_DEPS || \
    pip3 install $PY_DEPS
}

# -- 4. Copy agent -----------------------------------------------------
mkdir -p "$AGENT_DIR" "$CONFIG_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m 0755 "$SCRIPT_DIR/spoke-agent.py" "$AGENT_BIN"

# -- 5. Config ---------------------------------------------------------
cat > "$CONFIG_DIR/config.yaml" <<EOF
sub_hub_url: http://${HUB_HOST}:8080
node_name: ${NODE_NAME}
heartbeat_interval: 10
registration_token: ${TOKEN}
EOF
chmod 600 "$CONFIG_DIR/config.yaml"

# -- 6. systemd unit ---------------------------------------------------
cat > /etc/systemd/system/nettrades-spoke.service <<EOF
[Unit]
Description=NETTRADES Spoke Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${AGENT_BIN} --config ${CONFIG_DIR}/config.yaml
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nettrades-spoke.service
systemctl restart nettrades-spoke.service

echo "Spoke installed. Check status with:"
echo "  systemctl status nettrades-spoke"
echo "  journalctl -u nettrades-spoke -f"