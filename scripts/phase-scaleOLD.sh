#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 4: Scale to Kubernetes
# =============================================================================
# Upgrades from a single-VM deployment to a full Kubernetes cluster
# running Talos Linux on Proxmox.
#
# Checks:
#   • kubernetes manifests exist.
#   • Required tools (talosctl, kubectl, helm, tofu) are installed.
#   • terraform.tfvars has been configured.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
K8S_DIR="$PLATFORM_DIR/deploy/kubernetes"

if [ ! -d "$K8S_DIR" ]; then
    echo "ERROR: Kubernetes manifests not found at $K8S_DIR" >&2
    echo ""
    echo "The Kubernetes manifests should be in deploy/kubernetes/."
    echo "If you have not cloned the infrastructure project yet, do so now."
    exit 1
fi

# Pre-flight: required tools
MISSING_TOOLS=()
for cmd in talosctl kubectl helm tofu; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING_TOOLS+=("$cmd")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "ERROR: The following required tools are missing:" >&2
    for tool in "${MISSING_TOOLS[@]}"; do
        echo "  - $tool" >&2
    done
    echo ""
    echo "Installation guides:" >&2
    echo "  talosctl: https://www.talos.dev/latest/talos-guides/install/talosctl/" >&2
    echo "  kubectl:  https://kubernetes.io/docs/tasks/tools/" >&2
    echo "  helm:     https://helm.sh/docs/intro/install/" >&2
    echo "  tofu:     https://opentofu.org/docs/intro/install/" >&2
    exit 1
fi

# Pre-flight: terraform.tfvars must be configured
if [ ! -f "$K8S_DIR/talos/talos-proxmox/terraform.tfvars" ]; then
    echo "ERROR: terraform.tfvars not found." >&2
    echo ""
    echo "Copy the example file and fill in your Proxmox credentials:"
    echo "  cp $K8S_DIR/talos/talos-proxmox/terraform.tfvars.example \\"
    echo "     $K8S_DIR/talos/talos-proxmox/terraform.tfvars"
    echo "  # then edit terraform.tfvars with your Proxmox API token and IP addresses"
    exit 1
fi

# Main deployment
echo "=== Step 1: Provision Talos VMs ==="
cd "$K8S_DIR/talos/talos-proxmox"

tofu init
tofu apply -auto-approve
bash deploy-infra.sh

echo ""
echo "=== Step 2: Deploy applications ==="
cd "$K8S_DIR"

if [ ! -f .env ]; then
    cp .env.example .env
    echo "A default .env has been created at $K8S_DIR/.env"
    echo "EDIT IT with strong passwords before continuing."
    echo ""
    echo "After editing .env, re-run:  ./scripts/nettrades-setup.sh  and select phase 4"
    exit 0
fi

bash deploy-k8s-base.sh

echo ""
echo "============================================================="
echo " Kubernetes deployment complete!"
echo "============================================================="
echo "Odoo:       https://nettrades.ai"
echo "Grafana:    https://grafana.nettrades.ai"
echo "Argo CD:    https://argo.nettrades.ai"