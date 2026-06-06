#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES AI GPU Agent – runs on every GPU node.
# =============================================================================
# This agent detects GPUs, generates a hardware-bound node ID, registers with
# Odoo, brings up WireGuard, and starts the GPUStack worker inside the
# appropriate isolation runtime (gVisor for public pools, Docker for internal).
#
# gVisor is the recommended runtime for both Trusted and Untrusted networks
# because it avoids the memory-hoarding problem of VM-based solutions (like
# Kata) and provides syscall-level isolation with negligible overhead.
#
# Hardware-backed Confidential Computing (TEE) capabilities are auto-detected
# and reported to Odoo, enabling the platform to prefer TEE-capable nodes
# for high-sensitivity workloads.
#
# Edge-device information (Jetson, Raspberry Pi, Coral TPU) is also detected
# and reported so that the platform can automatically deploy appropriately
# quantized models on edge hardware.
#
# The WireGuard DNS watchdog runs as a daemon thread to keep the tunnel alive
# when the ISP changes the freelancer's IP address.
#
# REQUIREMENTS:
#   Python 3.12+
#   NVIDIA drivers + nvidia-smi (for GPU detection)
#   WireGuard tools (wg, wg-quick)
#   GPUStack worker binary (installed by the agent installer)
#
# SETUP:
#   Place API_KEY in /etc/nettrades-agent/agent.env
#   Run as root: python3 agent.py
#   Or install as systemd service via install-agent.sh
#
# FUTURE ENHANCEMENTS:
#   - Add a health-check HTTP endpoint for monitoring.
#   - Support AMD ROCm GPU detection.
#   - Auto-update the agent binary from Odoo.
# =============================================================================
import os
import sys
import subprocess
import requests
import socket
import json
import uuid
import time
import logging
import platform
import hashlib
from pathlib import Path
from functools import wraps

# Import our isolation module, TEE detection, edge detection, and DNS watchdog.
from isolate import start_isolated
from tee_detect import get_tee_summary
from edge_detect import get_edge_device_info

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---- Configuration ----
CONFIG_FILE = Path("/etc/nettrades-agent/agent.env")
NODE_ID_FILE = Path("/etc/nettrades-agent/node_id")
WORKER_TOKEN_FILE = Path("/etc/nettrades-agent/worker_token")
ODOO_URL = os.environ.get("ODOO_URL", "https://nettrades.ai")
MAX_RETRIES = 5
RETRY_BACKOFF = [1, 2, 4, 8, 16]   # seconds


def retry_on_exception(exceptions, max_retries=MAX_RETRIES, backoff=RETRY_BACKOFF):
    """Decorator: retry the function on specified exceptions with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except tuple(exceptions) as e:
                    last_exception = e
                    sleep_time = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                    logger.warning("%s failed (attempt %d/%d): %s. Retrying in %ds...",
                                   func.__name__, attempt + 1, max_retries, e, sleep_time)
                    time.sleep(sleep_time)
            logger.error("%s failed after %d retries: %s", func.__name__, max_retries, last_exception)
            raise last_exception
        return wrapper
    return decorator


# --------------- WireGuard auto-installation ---------------
def ensure_wireguard():
    """Install WireGuard if not already present on Linux.  Exits on failure."""
    if subprocess.run(["which", "wg"], capture_output=True).returncode == 0:
        return
    system = platform.system().lower()
    if system == "linux":
        distro = ""
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("ID="):
                        distro = line.split("=")[1].strip().strip('"')
        except FileNotFoundError:
            logger.critical("Cannot detect Linux distribution. Install WireGuard manually.")
            sys.exit(1)
        logger.info("WireGuard not found. Installing...")
        try:
            if distro in ("ubuntu", "debian"):
                subprocess.run(["apt-get", "update"], check=True)
                subprocess.run(["apt-get", "install", "-y", "wireguard"], check=True)
            elif distro in ("centos", "rhel", "fedora"):
                subprocess.run(["yum", "install", "-y", "wireguard-tools"], check=True)
            else:
                raise RuntimeError(f"Unsupported Linux distribution: {distro}.")
        except subprocess.CalledProcessError as e:
            logger.critical("WireGuard installation failed: %s. Install manually.", e)
            sys.exit(1)
    elif system == "windows":
        logger.info("Please install WireGuard from https://www.wireguard.com/install/")
    else:
        raise RuntimeError(f"Unsupported OS: {system}.")


# --------------- Hardware-bound node ID ---------------
def get_mac_address_hash():
    """Return SHA-256 of the primary MAC address as a fallback node ID."""
    import netifaces
    for iface in netifaces.interfaces():
        addrs = netifaces.ifaddresses(iface)
        if netifaces.AF_LINK in addrs and addrs[netifaces.AF_LINK][0].get('addr'):
            mac = addrs[netifaces.AF_LINK][0]['addr']
            return hashlib.sha256(mac.encode()).hexdigest()
    raise RuntimeError("No MAC address found.")


def get_tpm_ek_hash():
    """Return SHA-256 of the TPM Endorsement Key public key if TPM 2.0 is available."""
    try:
        result = subprocess.run(
            ['tpm2_getpubek', '-c', '0x81010000', '-f', 'pem'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and '-----BEGIN PUBLIC KEY-----' in result.stdout:
            return hashlib.sha256(result.stdout.encode()).hexdigest()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_or_create_node_id():
    """Persist a hardware-bound node_id.  Prefers TPM EK, falls back to MAC hash."""
    if NODE_ID_FILE.exists():
        return NODE_ID_FILE.read_text().strip()
    tpm_hash = get_tpm_ek_hash()
    if tpm_hash:
        node_id = tpm_hash
        logger.info("Using TPM Endorsement Key as node_id.")
    else:
        node_id = get_mac_address_hash()
        logger.warning("TPM not available; using MAC address hash as node_id.")
    NODE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    NODE_ID_FILE.write_text(node_id)
    return node_id


# --------------- GPU detection ---------------
def get_gpu_info():
    """Detect NVIDIA GPUs via nvidia-smi.  Returns a list of GPU dicts."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, check=True
        )
        gpus = []
        for line in result.stdout.strip().split('\n'):
            if line:
                parts = [p.strip() for p in line.split(',')]
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "memory_mb": int(parts[2].replace(' MiB', ''))
                })
        return gpus
    except Exception as e:
        logger.error("GPU detection failed: %s", e)
        return []


# --------------- WireGuard helpers ---------------
def get_wireguard_pubkey():
    """Return the local WireGuard public key, or empty string if not yet generated."""
    key_file = Path("/etc/wireguard/publickey")
    if key_file.exists():
        return key_file.read_text().strip()
    return ""


def generate_wireguard_keys():
    """Generate a new WireGuard keypair and store under /etc/wireguard."""
    privkey = subprocess.run(["wg", "genkey"], capture_output=True, text=True).stdout.strip()
    pubkey = subprocess.run(["wg", "pubkey"], input=privkey, capture_output=True, text=True).stdout.strip()
    Path("/etc/wireguard").mkdir(parents=True, exist_ok=True)
    (Path("/etc/wireguard") / "privatekey").write_text(privkey)
    (Path("/etc/wireguard") / "publickey").write_text(pubkey)
    return privkey, pubkey


# --------------- Registration with retry ---------------
@retry_on_exception([requests.ConnectionError, requests.Timeout, requests.HTTPError])
def register_with_odoo(api_key):
    """
    Register this GPU node with the NETTRADES Odoo instance.
    Returns a dict containing the WireGuard config, GPUStack token, and server URL.
    """
    node_id = get_or_create_node_id()
    gpus = get_gpu_info()
    generate_wireguard_keys()

    # Collect all hardware capabilities
    tee_caps = get_tee_summary()
    edge_info = get_edge_device_info()

    payload = {
        "node_id": node_id,
        "hostname": socket.gethostname(),
        "gpus": gpus,
        "wireguard_public_key": get_wireguard_pubkey(),
        "os": platform.system().lower(),
        "tee_capabilities": tee_caps,
        "edge_device_info": edge_info,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(f"{ODOO_URL}/api/v1/gpu/register", json=payload,
                         headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f"Odoo registration error: {data['error']}")
    return data


@retry_on_exception([requests.ConnectionError, requests.Timeout, requests.HTTPError])
def refresh_gpustack_token(api_key):
    """Request a fresh GPUStack worker token from Odoo."""
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(f"{ODOO_URL}/api/v1/clients/gpustack_token", headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise RuntimeError(f"Token refresh error: {data['error']}")
    return data.get("gpustack_token")


def apply_wireguard_config(wg_conf):
    """Write wg0.conf and bring up the WireGuard interface."""
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(wg_conf)
    try:
        subprocess.run(["wg-quick", "up", "wg0"], check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        logger.error("wg-quick up failed:\n%s", e.stderr)
        raise RuntimeError("Could not bring up WireGuard interface.")


def start_gpustack_worker(server_url, token, pool):
    """
    Launch the GPUStack worker inside the appropriate isolation runtime.
    Public pools use gVisor (via isolate.py); internal pools use Docker directly.
    """
    WORKER_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    WORKER_TOKEN_FILE.write_text(token)

    if pool == "public":
        start_isolated(server_url, token)
    else:
        subprocess.run(
            ["gpustack", "worker", "start", "--server-url", server_url, "--token", token],
            check=True
        )


# --------------- Main ---------------
def main():
    ensure_wireguard()

    if not CONFIG_FILE.exists():
        logger.critical("Missing /etc/nettrades-agent/agent.env with API_KEY")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        api_key = None
        for line in f:
            if line.startswith("API_KEY="):
                api_key = line.strip().split("=", 1)[1]
                break
    if not api_key:
        logger.critical("API_KEY not set")
        sys.exit(1)

    if not get_wireguard_pubkey():
        generate_wireguard_keys()

    # Registration – keep trying forever with backoff
    while True:
        try:
            config = register_with_odoo(api_key)
            break
        except Exception as e:
            logger.error("Registration failed, will retry in 30s: %s", e)
            time.sleep(30)

    mesh_cfg = config.get("mesh_config", {})
    gpustack_token = config.get("gpustack_token")
    gpustack_server = config.get("gpustack_server_url", "http://gpustack:80")
    pool = config.get("pool", "public")

    # Build and apply WireGuard configuration
    wg_conf = f"""[Interface]
PrivateKey = {Path('/etc/wireguard/privatekey').read_text().strip()}
Address = {mesh_cfg.get('assigned_ip', '10.100.0.10/32')}

[Peer]
PublicKey = {mesh_cfg.get('controller_public_key')}
Endpoint = {mesh_cfg.get('controller')}
AllowedIPs = {mesh_cfg.get('assigned_ip', '10.100.0.10/32').split('/')[0]}/32
PersistentKeepalive = 25
"""
    try:
        apply_wireguard_config(wg_conf)
    except Exception as e:
        logger.critical("WireGuard setup failed: %s", e)
        sys.exit(1)

    # Start the GPUStack worker
    try:
        start_gpustack_worker(gpustack_server, gpustack_token, pool)
    except Exception as e:
        logger.critical("GPUStack worker failed to start: %s", e)
        sys.exit(1)

    # ----------------------------------------------------------------
    # Start the WireGuard DNS re-resolution watchdog as a daemon thread.
    # This keeps the tunnel alive when the ISP changes the freelancer's IP.
    # ----------------------------------------------------------------
    from wg_dns_watchdog import start_dns_watchdog
    start_dns_watchdog()

    # Token refresh loop
    while True:
        time.sleep(600)
        try:
            new_token = refresh_gpustack_token(api_key)
            if new_token:
                WORKER_TOKEN_FILE.write_text(new_token)
                # Restart worker with the new token
                subprocess.run(["gpustack", "worker", "stop"], capture_output=True)
                start_gpustack_worker(gpustack_server, new_token, pool)
        except Exception as e:
            logger.warning("Token refresh failed: %s", e)


if __name__ == "__main__":
    main()