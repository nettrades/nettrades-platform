terraform {
  required_providers {
    proxmox = {
      source  = "telmate/proxmox"
      version = "~> 2.9"
    }
    talos = {
      source  = "siderolabs/talos"
      version = "~> 0.6"
    }
  }
}

provider "proxmox" {
  pm_api_url          = var.proxmox_api_url
  pm_api_token_id     = var.proxmox_api_token_id
  pm_api_token_secret = var.proxmox_api_token_secret
  pm_tls_insecure     = true
}

# Use a numeric template ID, not a data source name
variable "talos_template_id" {
  type    = number
  default = 9000   # adjust to your Proxmox template ID
}

resource "proxmox_vm_qemu" "talos_control_plane" {
  count       = var.control_plane_count
  name        = "${var.cluster_name}-cp-${count.index + 1}"
  target_node = var.proxmox_node
  clone       = var.talos_template_id    # FIX G24: numeric template ID
  full_clone  = true
  cores       = var.control_plane_cores
  memory      = var.control_plane_memory
  scsihw      = "virtio-scsi-pci"

  disk {
    slot    = 0
    size    = var.control_plane_disk_size
    type    = "scsi"
    storage = var.proxmox_storage
  }

  network {
    model  = "virtio"
    bridge = var.network_bridge
    macaddr = "02:00:00:${format("%02x", count.index + 10)}:00:01"
  }
  # ipconfig0 removed – Talos handles its own networking via config patches
}

resource "proxmox_vm_qemu" "talos_worker" {
  count       = var.worker_count
  name        = "${var.cluster_name}-worker-${count.index + 1}"
  target_node = var.proxmox_node
  clone       = var.talos_template_id
  full_clone  = true
  cores       = var.worker_cores
  memory      = var.worker_memory
  scsihw      = "virtio-scsi-pci"

  disk {
    slot    = 0
    size    = var.worker_disk_size
    type    = "scsi"
    storage = var.proxmox_storage
  }

  network {
    model  = "virtio"
    bridge = var.network_bridge
    macaddr = "02:00:00:${format("%02x", count.index + 20)}:00:01"
  }
}

# Generate Talos machine configuration with per-node patches
resource "talos_machine_configuration" "controlplane" {
  count          = var.control_plane_count
  cluster_name   = var.cluster_name
  machine_type   = "controlplane"
  machine_secrets = file(var.talos_secrets_file)

  config_patches = [
    templatefile("${path.module}/patches/controlplane.yaml.tpl", {
      node_ip = var.control_plane_ips[count.index]
    })
  ]
}

resource "talos_machine_configuration" "worker" {
  count          = var.worker_count
  cluster_name   = var.cluster_name
  machine_type   = "worker"
  machine_secrets = file(var.talos_secrets_file)

  config_patches = [
    templatefile("${path.module}/patches/worker.yaml.tpl", {
      node_ip = var.worker_ips[count.index]
    })
  ]
}