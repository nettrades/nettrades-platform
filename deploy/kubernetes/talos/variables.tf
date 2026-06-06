# =============================================================================
# Section: G – Input variables for the Talos/Proxmox module.
# =============================================================================
variable "proxmox_api_url"          { type = string, sensitive = true }
variable "proxmox_api_token_id"     { type = string, sensitive = true }
variable "proxmox_api_token_secret" { type = string, sensitive = true }
variable "proxmox_node"             { type = string, default = "pve1" }
variable "proxmox_storage"          { type = string, default = "local-lvm" }
variable "network_bridge"           { type = string, default = "vmbr0" }
variable "gateway"                  { type = string, default = "192.168.1.1" }
variable "cluster_name"             { type = string, default = "nettrades" }
variable "control_plane_count"      { type = number, default = 3 }
variable "worker_count"             { type = number, default = 3 }
variable "control_plane_cores"      { type = number, default = 4 }
variable "control_plane_memory"     { type = number, default = 8192 }
variable "control_plane_disk_size"  { type = number, default = 50 }
variable "worker_cores"             { type = number, default = 8 }
variable "worker_memory"            { type = number, default = 16384 }
variable "worker_disk_size"         { type = number, default = 100 }
variable "control_plane_ips"        { type = list(string) }
variable "worker_ips"               { type = list(string) }
variable "talos_secrets_file"       { type = string, default = "./secrets.yaml" }