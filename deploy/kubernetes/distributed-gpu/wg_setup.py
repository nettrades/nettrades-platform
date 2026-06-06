# =============================================================================
# Section H – WireGuard interface management for the GPU agent.
# 
# =============================================================================
import subprocess
from pathlib import Path

WG_DIR = Path("/etc/wireguard")

def generate_keys():
    privkey = subprocess.run(["wg", "genkey"], capture_output=True, text=True, check=True).stdout.strip()
    pubkey = subprocess.run(["wg", "pubkey"], input=privkey, capture_output=True, text=True, check=True).stdout.strip()
    WG_DIR.mkdir(parents=True, exist_ok=True)
    (WG_DIR / "privatekey").write_text(privkey)
    (WG_DIR / "publickey").write_text(pubkey)
    return privkey, pubkey

def create_config(interface, privkey, address, peers):
    conf = f"[Interface]\nPrivateKey = {privkey}\nAddress = {address}\n"
#    if dns:
#        config += f"DNS = {dns}\n"    
    for peer in peers:
        conf += f"\n[Peer]\nPublicKey = {peer['public_key']}\nAllowedIPs = {peer['allowed_ips']}\n"
        if peer.get('endpoint'):
            conf += f"Endpoint = {peer['endpoint']}\n"
        if peer.get('persistent_keepalive'):
            conf += f"PersistentKeepalive = {peer['persistent_keepalive']}\n"
    return conf

def apply_config(interface, config_path):
    subprocess.run(["wg-quick", "down", interface], capture_output=True)
    subprocess.run(["cp", config_path, str(WG_DIR / f"{interface}.conf")], check=True)
    subprocess.run(["wg-quick", "up", interface], check=True)