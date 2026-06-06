#!/bin/bash
# =============================================================================
# NETTRADES.AI – Talos Infrastructure Bootstrap
# =============================================================================
# Run after `tofu apply`.  Applies per-node Talos configs, bootstraps the
# Kubernetes control plane, retrieves kubeconfig, and installs Cilium,
# Longhorn, and Traefik.  Argo CD is optional.
# =============================================================================
set -euo pipefail
trap 'echo "ERROR: script failed at line $LINENO with exit code $?." >&2' ERR

# DOMAIN="${DOMAIN:-nettrades.ai}"
# CLUSTER_NAME="${CLUSTER_NAME:-nettrades}"

# Tool checks
for cmd in talosctl tofu helm kubectl jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed." >&2
        exit 1
    fi
done

echo "=== Step 1: Generate Talos secrets (if not already present) ==="
if [ ! -f secrets.yaml ]; then
    talosctl gen secrets -o secrets.yaml
fi

echo "=== Step 2: Retrieve per-node configs from OpenTofu state ==="
# Assumes tofu state is local; adjust if using remote state.
CONTROL_PLANE_IPS=$(tofu output -json control_plane_ips | jq -r '.[]')
WORKER_IPS=$(tofu output -json worker_ips | jq -r '.[]')

echo "=== Step 3: Apply Talos configs ==="
for ip in $CONTROL_PLANE_IPS; do
    echo "Applying control plane config to $ip..."
    talosctl apply-config --insecure --nodes "$ip" --file "./talosconfigs/controlplane-${ip}.yaml"
done
# Apply control plane configs with per-node IP patches
for ip in $WORKER_IPS; do
    echo "Applying worker config to $ip..."
    talosctl apply-config --insecure --nodes "$ip" --file "./talosconfigs/worker-${ip}.yaml"
done

echo "=== Step 4: Set Talos endpoints and bootstrap ==="
FIRST_CP=$(echo "$CONTROL_PLANE_IPS" | head -1)
talosctl config endpoint $CONTROL_PLANE_IPS
talosctl config nodes "$FIRST_CP"
talosctl bootstrap

echo "=== Step 5: Wait for control plane health ==="
sleep 30
talosctl health --nodes "$FIRST_CP"

echo "=== Step 6: Retrieve kubeconfig ==="
talosctl kubeconfig kubeconfig --force
export KUBECONFIG=$(pwd)/kubeconfig

echo "=== Step 7: Install Cilium CNI ==="
helm repo add cilium https://helm.cilium.io/
helm upgrade --install cilium cilium/cilium --namespace kube-system \
    --set ipam.mode=kubernetes \
    --set encryption.wireguard.enabled=true \
    --set cluster.name=nettrades-prod \
    --version 1.19.3

echo "=== Step 8: Install Longhorn storage ==="
helm repo add longhorn https://charts.longhorn.io
helm upgrade --install longhorn longhorn/longhorn --namespace longhorn-system --create-namespace \
    --set defaultSettings.allowRecurringJobWhileVolumeDetached=true \
    --version 1.11.1

echo "=== Step 9: Install Traefik ingress ==="
helm repo add traefik https://traefik.github.io/charts
helm upgrade --install traefik traefik/traefik --namespace ingress --create-namespace \
    --set service.type=LoadBalancer \
    --set ingressClass.enabled=true \
    --set ingressClass.isDefaultClass=true \
    --version 3.6.13

echo "=== Step 10: (Optional) Argo CD ==="
read -rp "Install Argo CD? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.3.8/manifests/install.yaml
    echo "Argo CD installed.  Retrieve admin password:"
    echo "kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
fi

echo "=== Infrastructure ready. Use 'kubectl --kubeconfig kubeconfig get nodes' to verify. ==="