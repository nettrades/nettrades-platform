# WireGuard Documentation

## 1. Introduction

There are two WireGuard VPNs used in the NETTRADES platform:

* 'Admin VPN' – for secure administrative SSH access.

* 'Internal WireGuard' – for encrypted communication between platform microservices.

---

## 2. Overview


| VPN | Port | Subnet |Purpose |Who Uses It |
|--------|---------|--------------|--------------|--------------|
| `Admin VPN` | 51821 | 10.10.10.0/24 | Secure SSH access for administrators| Secure SSH access for administrators|
| `Internal WireGuard` | 51820 | 10.0.0.0/16 | Service-to-service encryption | Microservices (LangGraph, NVIDIA dynamo, etc.) |

The two VPNs are isolated – the admin VPN cannot reach the internal WireGuard subnet (10.0.0.0/16) thanks to iptables rules applied during deployment.

### Admin VPN (For Administrators)

###  Why Use It?

* `No SSH port exposed to the internet` – port 22 is not reachable from the public internet.

* `Password authentication is allowed` only from the VPN subnet (10.10.10.0/24).

* `You can connect from anywhere` (no static IP required), as long as you have the WireGuard client and the configuration file.

### How It Works


* The server runs a WireGuard server on port 51821 with subnet 10.10.10.0/24.

* Each administrator gets a unique IP (e.g., 10.10.10.2, 10.10.10.3, …).

* Administrators install a WireGuard client on their device, import a .conf file, and connect.

* Once connected, they can SSH to the server using the server’s VPN IP (10.10.10.1).



### Generating a Client Configuration

On the server, run the script (created during deployment):
```bash
/usr/local/bin/add-wireguard-user.sh <username>
```
(A copy of it is in the scripts folder)

Example:
```bash

/usr/local/bin/add-wireguard-user.sh alice
```

This will:

* Generate a new private/public key pair for the user.

* Assign the next available IP in the 10.10.10.0/24 range.

* Add the user’s public key to the server’s WireGuard configuration.

* Create a .conf file at /root/wireguard-clients/alice.conf.

Send this .conf file to the user securely (e.g., encrypted email, shared via a secure channel).

### Connecting from a Client


#### Windows / macOS

* Download and install WireGuard.

* Open WireGuard ? Import tunnel(s) from file.

* Select the .conf file.

* Click Activate.

#### Linux

```bash

sudo wg-quick up ./alice.conf
```

#### Android / iOS

* Install the WireGuard app.

* Add a new tunnel ? Import from file or scan a QR code (you can generate a QR code from the .conf file using qrencode -t ansiutf8 < alice.conf).

### SSH Access

Once connected to the VPN, SSH to the server:
```bash

ssh root@10.10.10.1
# or
ssh ubuntu@10.10.10.1
```

You can use your password (allowed from the VPN subnet) or an SSH key if you have one set up.

### Internal WireGuard (For Microservices)

#### Purpose

* Ensures `encrypted communication` between platform components (LangGraph, NVIDIA dynamo, PostgreSQL, etc.).

* Used in the `hub and spoke` architecture (central hub ? client company spokes).

* Also used in the `GPU marketplace` to secure traffic between GPU nodes.

#### How It Works

* The internal WireGuard is fully automated – no human intervention required.

* The deployment scripts (phase-env.sh) generate keys for each service.

* Keys are stored in the .env file and are consumed by the services.

* The internal WireGuard configuration is not exposed to administrators.

#### Configuration File (Kubernetes / GPU Marketplace)

When deploying the GPU marketplace on Kubernetes, the ConfigMap wireguard-peers (in namespace NVIDIAdynamo) defines the WireGuard configuration. Example:

```yaml

apiVersion: v1
kind: ConfigMap
metadata:
  name: wireguard-peers
  namespace: NVIDIAdynamo
data:
  wg0.conf: |
    [Interface]
    Address = 10.100.0.1/24
    ListenPort = 51820
    PrivateKey = ${WG_PRIVATE_KEY}   # injected from Secret
    [Peer]
    PublicKey = ${PEER1_PUBLIC_KEY}
    AllowedIPs = 10.100.0.2/32
    PersistentKeepalive = 25
```

* The subnet `10.100.0.0/24` is used for the GPU marketplace.

* This subnet is `outside` the `10.0.0.0/16` range, so it is `not blocked` by the admin VPN isolation rules.

* The actual keys are stored in a Kubernetes `Secret` (not in the ConfigMap) to keep them secure.

No User Action Required

Administrators do not need to interact with the internal WireGuard. It is set up during deployment and runs automatically.

### Security Notes

#### Admin VPN Isolation

The admin VPN is isolated from the internal WireGuard network. The iptables rule in phase-system.sh prevents traffic from the admin VPN (wg0) to the internal subnet (10.0.0.0/16):
```bash

iptables -I FORWARD -i wg0 -d 10.0.0.0/16 -j DROP
```

This ensures that administrators cannot accidentally (or maliciously) reach internal services like LangGraph or NVIDIA dynamo over the VPN.

#### Ports and Firewall
Port	Protocol	Purpose
51820	UDP	Internal WireGuard
51821	UDP	Admin VPN
22	TCP	SSH (main) – key?only
2222	TCP	SSH (rescue) – password auth

* UFW is configured to allow these ports.

* The rescue SSH port (2222) is a fallback if you ever lose access to the main SSH port.

#### Key Management

* Admin VPN: Each user has their own key pair; keys can be revoked by removing the peer from the server config.

* Internal WireGuard: Keys are managed by the deployment scripts and stored in .env or Kubernetes Secrets.

###  Troubleshooting

#### Admin VPN not starting

Check the service status:

```bash

systemctl status wg-quick@admin-wg0
```

If it fails, ensure WireGuard tools are installed:

```bash

apt install -y wireguard-tools
```

Then restart:

```bash

systemctl restart wg-quick@admin-wg0
```

#### Cannot SSH via VPN

* Ensure you are connected to the VPN (wg show should show a handshake).

* Try SSH to 10.10.10.1 with a password.

* Check if the SSH server allows password auth from 10.10.10.0/24 (it should, as configured in sshd_config).

#### Revoking a user

Remove the user’s [Peer] block from /etc/wireguard/admin/wg0.conf, then reload:
```bash

wg syncconf wg0 <(wg-quick strip wg0)

```

### Useful Commands

| Command | Description |
|--------|---------|
| `wg show` | Show current WireGuard connections |
| `wg genkey` | Generate a new private key |
| `wg genpsk` | Generate a pre-shared key |
| `systemctl status wg-quick@admin-wg0` | Check admin VPN status |
| `cat /root/wireguard-clients/*.conf` | List all generated client configs |

### References

[WireGuard Official Site](https://www.wireguard.com/)

[NETTRADES Platform Documentation](https://github.com/nettrades/nettrades-platform/tree/main/docs)

