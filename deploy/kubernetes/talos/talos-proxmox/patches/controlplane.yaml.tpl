# =============================================================================
# Section: G – Per-node Talos config patch.
# Assigns a static IP to the eth1 (internal) interface.
# The eth0 interface uses DHCP for Proxmox host connectivity.
# =============================================================================
machine:
  network:
    interfaces:
      - interface: eth0
        dhcp: true
      - interface: eth1
        addresses:
          - ${node_ip}/24
        routes:
          - network: 0.0.0.0/0
            gateway: 192.168.1.1