#!/usr/bin/env python3
# gpu_agent.py - GPU node auto-registration and WireGuard setup
import os
import json
import subprocess
import requests
import time
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
ODOO_URL = os.getenv("ODOO_URL", "http://odoo:8069")
TOKEN = os.getenv("GPU_TOKEN", "")  # required
HOSTNAME = os.getenv("HOSTNAME", "localhost")
WG_CONFIG_PATH = "/etc/wireguard/wg0.conf"

def detect_gpus():
    """Run nvidia-smi and return GPU info list."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            text=True
        )
        gpus = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            idx, name, mem = line.split(', ')
            gpus.append({
                'index': int(idx),
                'name': name,
                'memory_mb': int(mem)
            })
        return gpus
    except Exception as e:
        logger.error(f"Failed to detect GPUs: {e}")
        return []

def generate_wireguard_keys():
    """Generate WireGuard private/public keys if not present."""
    priv_file = "/etc/wireguard/privatekey"
    pub_file = "/etc/wireguard/publickey"
    if not os.path.exists(priv_file):
        subprocess.check_call(["wg", "genkey"], stdout=open(priv_file, 'w'))
        os.chmod(priv_file, 0o600)
    with open(priv_file, 'r') as f:
        private_key = f.read().strip()
    if not os.path.exists(pub_file):
        subprocess.check_call(["wg", "pubkey"], stdin=open(priv_file, 'r'), stdout=open(pub_file, 'w'))
    with open(pub_file, 'r') as f:
        public_key = f.read().strip()
    return private_key, public_key

def register_node():
    """Register with Odoo and get WireGuard config."""
    public_key = generate_wireguard_keys()[1]
    payload = {
        'token': TOKEN,
        'hostname': HOSTNAME,
        'public_key': public_key,
        'gpus': detect_gpus(),
        'os': 'linux',
        'arch': subprocess.check_output(['uname', '-m']).decode().strip(),
        'model': subprocess.check_output(['hostnamectl', '--json=short', 'status'], text=True) or 'Unknown'
    }
    url = f"{ODOO_URL}/api/gpu/register"
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get('status') == 'success':
            config = data.get('wireguard_config')
            if config:
                # Write config
                with open(WG_CONFIG_PATH, 'w') as f:
                    f.write(config)
                # Start wg-quick
                subprocess.check_call(["wg-quick", "up", "wg0"])
                logger.info("WireGuard interface wg0 started successfully.")
            else:
                logger.error("No WireGuard config returned.")
        else:
            logger.error(f"Registration failed: {data.get('error')}")
    except Exception as e:
        logger.error(f"Registration request failed: {e}")

def heartbeat_loop():
    """Send heartbeat periodically."""
    public_key = None
    pub_file = "/etc/wireguard/publickey"
    if os.path.exists(pub_file):
        with open(pub_file, 'r') as f:
            public_key = f.read().strip()
    if not public_key:
        logger.error("No public key found, cannot send heartbeat.")
        return
    url = f"{ODOO_URL}/api/gpu/heartbeat"
    while True:
        try:
            # Optionally get GPU utilisation
            util = 0.0
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    text=True
                )
                util = float(out.strip().split('\n')[0]) if out else 0.0
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
                'uptime_hours': uptime
            }
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")
        time.sleep(60)

if __name__ == "__main__":
    if not TOKEN:
        logger.error("GPU_TOKEN environment variable not set.")
        sys.exit(1)
    register_node()
    heartbeat_loop()