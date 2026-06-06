# =============================================================================
# Section: G – Outputs printed after `tofu apply`.
# =============================================================================
output "control_plane_ips" { value = var.control_plane_ips }
output "worker_ips"        { value = var.worker_ips }
output "kubeconfig_command" {
  value = "talosctl kubeconfig --nodes ${var.control_plane_ips[0]}"
}