#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: src/agent/gpu_agent.py
# =============================================================================
# PURPOSE:
#   GPU node auto‑discovery, registration, and WireGuard setup.
#   This script runs on each GPU machine and registers it with the Odoo
#   controller. It also maintains a heartbeat and automatically applies
#   the WireGuard configuration.
#
# USAGE:
#   export ODOO_URL="http://odoo:8069"
#   export GPU_TOKEN="nt-abc123..."
#   python3 gpu_agent.py
#
# =============================================================================

import os
import sys
import json
import time
import logging
import subprocess
import requests
import socket
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
TOKEN = os.getenv("GPU_TOKEN", "")
HOSTNAME = socket.gethostname()
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"
PRIVATE_KEY_FILE = "/etc/wireguard/privatekey"
PUBLIC_KEY_FILE = "/etc/wireguard/publickey"
REGISTRATION_RETRY_DELAY = 30  # seconds
HEARTBEAT_INTERVAL = 60  # seconds

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def detect_gpus():
    """Run nvidia-smi and return a list of GPU info."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            text=True
        )
        gpus = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            parts = line.split(', ')
            if len(parts) >= 3:
                idx, name, mem = parts[0], parts[1], parts[2]
                gpus.append({
                    'index': int(idx),
                    'name': name.strip(),
                    'memory_mb': int(float(mem))
                })
            else:
                logger.warning("Skipping malformed GPU line: %s", line)
        return gpus
    except FileNotFoundError:
        logger.warning("nvidia-smi not found. No GPUs detected.")
        return []
    except Exception as e:
        logger.error("Failed to detect GPUs: %s", e)
        return []

def generate_wireguard_keys():
    """Generate WireGuard private/public keys if not already present."""
    if not os.path.exists(PRIVATE_KEY_FILE):
        try:
            with open(PRIVATE_KEY_FILE, 'w') as f:
                subprocess.check_call(["wg", "genkey"], stdout=f)
            os.chmod(PRIVATE_KEY_FILE, 0o600)
            logger.info("Generated WireGuard private key.")
        except Exception as e:
            logger.error("Failed to generate private key: %s", e)
            sys.exit(1)

    with open(PRIVATE_KEY_FILE, 'r') as f:
        private_key = f.read().strip()

    if not os.path.exists(PUBLIC_KEY_FILE):
        try:
            with open(PUBLIC_KEY_FILE, 'w') as f:
                subprocess.check_call(["wg", "pubkey"], stdin=open(PRIVATE_KEY_FILE, 'r'), stdout=f)
            os.chmod(PUBLIC_KEY_FILE, 0o644)
            logger.info("Generated WireGuard public key.")
        except Exception as e:
            logger.error("Failed to generate public key: %s", e)
            sys.exit(1)

    with open(PUBLIC_KEY_FILE, 'r') as f:
        public_key = f.read().strip()

    return private_key, public_key

def register_node():
    """Send registration request to Odoo and apply WireGuard config."""
    private_key, public_key = generate_wireguard_keys()
    gpus = detect_gpus()
    arch = subprocess.check_output(['uname', '-m'], text=True).strip()
    try:
        model = subprocess.check_output(['hostnamectl', '--json=short', 'status'], text=True).strip()
        # Extract model from hostnamectl output
        try:
            import json as jsonlib
            data = jsonlib.loads(model)
            model = data.get('HardwareModel', data.get('Deployment', 'unknown'))
        except:
            pass
    except:
        model = 'unknown'

    payload = {
        'token': TOKEN,
        'hostname': HOSTNAME,
        'public_key': public_key,
        'gpus': gpus,
        'os': 'linux',
        'arch': arch,
        'model': model,
    }

    url = f"{ODOO_URL}/api/gpu/register"
    try:
        logger.info("Registering node with Odoo at %s", url)
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') == 'success':
            config = data.get('wireguard_config')
            assigned_ip = data.get('assigned_ip')
            node_id = data.get('node_id')
            if config:
                # Write WireGuard config
                with open(WG_CONFIG_PATH, 'w') as f:
                    f.write(config)
                os.chmod(WG_CONFIG_PATH, 0o600)
                logger.info("WireGuard config written to %s", WG_CONFIG_PATH)
                # Bring up interface
                try:
                    subprocess.check_call(["wg-quick", "up", "wg0"])
                    logger.info("WireGuard interface wg0 is up with IP %s", assigned_ip)
                except subprocess.CalledProcessError as e:
                    logger.error("Failed to bring up WireGuard interface: %s", e)
            else:
                logger.error("No WireGuard config returned.")
            return True
        else:
            logger.error("Registration failed: %s", data.get('error'))
            return False
    except Exception as e:
        logger.error("Registration request failed: %s", e)
        return False

def heartbeat_loop():
    """Periodically send heartbeat to Odoo."""
    public_key = None
    if os.path.exists(PUBLIC_KEY_FILE):
        with open(PUBLIC_KEY_FILE, 'r') as f:
            public_key = f.read().strip()
    if not public_key:
        logger.error("No public key found. Cannot send heartbeat.")
        return

    while True:
        try:
            util = 0.0
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    text=True
                )
                if out:
                    util = float(out.strip().split('\n')[0])
            except:
                pass
            uptime = 0.0
            try:
                with open('/proc/uptime', 'r') as f:
                    uptime = float(f.read().split()[0]) / 3600.0
            except:
                pass
            payload = {
                'public_key': public_key,
                'gpu_utilisation': util,
                'uptime_hours': uptime,
            }
            url = f"{ODOO_URL}/api/gpu/heartbeat"
            requests.post(url, json=payload, timeout=10)
            logger.debug("Heartbeat sent. Util=%.1f%% Uptime=%.1f h", util, uptime)
        except Exception as e:
            logger.warning("Heartbeat failed: %s", e)
        time.sleep(HEARTBEAT_INTERVAL)

def main():
    if not TOKEN:
        logger.error("GPU_TOKEN environment variable not set.")
        sys.exit(1)

    # Ensure WireGuard is installed
    try:
        subprocess.check_call(["wg", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        logger.error("WireGuard tools not found. Please install WireGuard.")
        sys.exit(1)

    # Registration loop with retry
    registered = False
    while not registered:
        registered = register_node()
        if not registered:
            logger.info("Retrying registration in %d seconds...", REGISTRATION_RETRY_DELAY)
            time.sleep(REGISTRATION_RETRY_DELAY)

    # Start heartbeat in a separate thread
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    logger.info("GPU agent started successfully. Running heartbeat...")
    heartbeat_thread.join()

if __name__ == "__main__":
    main()