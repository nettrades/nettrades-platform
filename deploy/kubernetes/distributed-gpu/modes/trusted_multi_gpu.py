# Section H – Trusted multi-GPU mode (company internal).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wg_setup import generate_keys, create_config, apply_config

def setup_trusted_multi_gpu(controller_ip, mesh_cidr, node_ip, controller_pubkey):
    priv, pub = generate_keys()
    config = create_config(
        interface="wg0",
        privkey=priv,
        address=f"{node_ip}/{mesh_cidr.split('/')[1] if '/' in mesh_cidr else '24'}",
        peers=[{
            "public_key": controller_pubkey,
            "allowed_ips": mesh_cidr,
            "endpoint": f"{controller_ip}:51820",
            "persistent_keepalive": 25
        }]
    )
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(config)
    apply_config("wg0", "/etc/wireguard/wg0.conf")
    # Start GPUStack worker with internal pool token
    # (handled by agent main)
    return pub