# Section H - Untrusted public sharing (freelancer GPU).
# Hub-and-spoke WireGuard with AllowedIPs restricted to the controller only.
# GPUStack worker runs inside gVisor isolation (nvproxy GPU support).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wg_setup import generate_keys, create_config, apply_config

def setup_untrusted_public(controller_ip, controller_pubkey, node_ip):
    priv, pub = generate_keys()
    config = create_config(
        interface="wg0",
        privkey=priv,
        address=node_ip,
        peers=[{
            "public_key": controller_pubkey,
            "allowed_ips": f"{controller_ip}/32",
            "endpoint": f"{controller_ip}:51820",
            "persistent_keepalive": 25
        }]
    )
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(config)
    apply_config("wg0", "/etc/wireguard/wg0.conf")
    return pub