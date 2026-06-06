#!/bin/bash
# =============================================================================
# NETTRADES AI GPU Agent – One-line installer for Linux and macOS
# =============================================================================
# Detects the operating system and installs WireGuard, gVisor (Linux only),
# and all agent files.  Prompts for the Odoo API key and starts the agent
# as a systemd (Linux) or launchd (macOS) service.
#
# macOS notes:
#   - WireGuard tools are installed via Homebrew.
#   - gVisor is NOT available on macOS; public GPU sharing is blocked.
#   - The agent runs as a launchd user agent.
# =============================================================================
set -euo pipefail

echo "=== NETTRADES AI GPU Agent Installer ==="
OS="$(uname -s)"

# ----------------------------------------------------------------
# Platform detection and WireGuard installation
# ----------------------------------------------------------------
if [[ "$OS" == "Linux" ]]; then
    # --- Linux: WireGuard via apt/yum ---
    if ! command -v wg &>/dev/null; then
        echo "WireGuard not found. Installing..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y wireguard
        elif command -v yum &>/dev/null; then
            sudo yum install -y wireguard-tools
        else
            echo "ERROR: Unsupported Linux distribution. Please install wireguard-tools manually." >&2
            exit 1
        fi
    fi

    # --- Linux: gVisor installation check ---
    if ! command -v runsc &>/dev/null; then
        echo "gVisor not found. Installing runsc..."
        curl -fsSL https://gvisor.dev/archive/runsc | sudo tee /usr/local/bin/runsc >/dev/null
        sudo chmod +x /usr/local/bin/runsc
        sudo runsc install
        sudo systemctl restart docker
        echo "gVisor installed. GPU support via --nvproxy."
    else
        echo "gVisor already installed: $(runsc version | head -1)"
    fi

elif [[ "$OS" == "Darwin" ]]; then
    # --- macOS: Homebrew must be present ---
    if ! command -v brew &>/dev/null; then
        echo "ERROR: Homebrew is required. Install from https://brew.sh" >&2
        exit 1
    fi
    if ! command -v wg &>/dev/null; then
        echo "Installing wireguard-tools via Homebrew..."
        brew install wireguard-tools
    fi

    # --- macOS: gVisor is NOT available ---
    echo "NOTE: gVisor is not available on macOS. Public GPU sharing is disabled."
    echo "You can still use the NETTRADES platform via your web browser."

else
    echo "ERROR: Unsupported OS ($OS)." >&2
    exit 1
fi

# ----------------------------------------------------------------
# WireGuard CVE-2026-31579 mitigation – kernel version check (Linux only)
# ----------------------------------------------------------------
if [[ "$OS" == "Linux" ]]; then
    REQUIRED_KERNEL_MAJOR=6
    REQUIRED_KERNEL_MINOR=19
    REQUIRED_KERNEL_PATCH=14

    KERNEL_VERSION=$(uname -r | cut -d- -f1)
    IFS='.' read -r k_major k_minor k_patch <<< "$KERNEL_VERSION"

    if (( k_major < REQUIRED_KERNEL_MAJOR ||
          (k_major == REQUIRED_KERNEL_MAJOR && k_minor < REQUIRED_KERNEL_MINOR) ||
          (k_major == REQUIRED_KERNEL_MAJOR && k_minor == REQUIRED_KERNEL_MINOR && k_patch < REQUIRED_KERNEL_PATCH) )); then
        echo "WARNING: Kernel $KERNEL_VERSION is older than $REQUIRED_KERNEL_MAJOR.$REQUIRED_KERNEL_MINOR.$REQUIRED_KERNEL_PATCH"
        echo "         WireGuard CVE-2026-31579 may be present. Upgrade your kernel."
    fi
fi

# ----------------------------------------------------------------
# Directory and file setup
# ----------------------------------------------------------------
sudo mkdir -p /opt/nettrades-agent /etc/nettrades-agent

# Copy all agent Python modules, including the new DNS watchdog and TEE detection
sudo cp agent.py wg_setup.py isolate.py wg_dns_watchdog.py tee_detect.py /opt/nettrades-agent/
sudo cp -r modes /opt/nettrades-agent/

# Ask for Odoo API key
read -rp "Enter your NETTRADES Odoo API key: " API_KEY
echo "API_KEY=$API_KEY" | sudo tee /etc/nettrades-agent/agent.env > /dev/null

# ----------------------------------------------------------------
# Install and start the background service
# ----------------------------------------------------------------
if [[ "$OS" == "Linux" ]]; then
    sudo cp nettrades-agent.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable nettrades-agent
    sudo systemctl start nettrades-agent
    echo "Agent installed and running (systemd)."
elif [[ "$OS" == "Darwin" ]]; then
    # macOS: create a launchd plist and load it
    PLIST="$HOME/Library/LaunchAgents/com.nettrades.agent.plist"
    cat > "$PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nettrades.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/opt/nettrades-agent/agent.py</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ODOO_URL</key>
        <string>${ODOO_URL:-https://nettrades.ai}</string>
    </dict>
    <key>WorkingDirectory</key>
    <string>/opt/nettrades-agent</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/opt/nettrades-agent/agent.log</string>
    <key>StandardErrorPath</key>
    <string>/opt/nettrades-agent/agent.log</string>
</dict>
</plist>
EOF
    launchctl load "$PLIST"
    echo "Agent installed and running (launchd)."
fi

echo "Check status:"
[[ "$OS" == "Linux" ]] && echo "  sudo systemctl status nettrades-agent"
[[ "$OS" == "Darwin" ]] && echo "  launchctl list com.nettrades.agent"