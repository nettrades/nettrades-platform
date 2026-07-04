#!/bin/bash
# =============================================================================
# FILE: scripts/phase-k8s.sh
# =============================================================================
# PURPOSE:
#   Phase 4: Kubernetes Scaling – deploys NETTRADES to a Kubernetes cluster.
#   This phase provisions Talos Linux VMs (on Proxmox), applies all Kubernetes
#   manifests, and sets up Argo CD for GitOps.
#
#   Technology stack supported:
#   - Talos Linux (immutable Kubernetes OS)
#   - Cilium (CNI)
#   - Longhorn (storage)
#   - MetalLB (load balancing)
#   - cert-manager (TLS certificates)
#   - CloudNativePG (PostgreSQL operator)
#   - NVIDIA GPU Operator
#   - gVisor (container runtime isolation)
#   - WireGuard (secure pod-to-pod communication)
#   - Argo CD (GitOps)
#   - Prometheus & Grafana (monitoring)
#   - GPUStack (distributed GPU orchestration)
#
#   This is a FUTURE-PHASE script. It is currently a placeholder that checks
#   for required tools and applies manifests. To use it, you must have:
#   - A Proxmox host with Talos QCOW2 images uploaded
#   - talosctl, kubectl, helm, and opentofu installed
#   - A public IP for MetalLB
#
# USAGE:
#   ./phase-k8s.sh [--auto] [--force]
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "4"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 4; then
    log_warning "Phase 4 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------
if ! phase_completed 1; then
    log_info "Phase 1 not completed. Running Phase 1 first..."
    bash "$SCRIPT_DIR/phase-env.sh"
fi

# -----------------------------------------------------------------------------
# Check required tools
# -----------------------------------------------------------------------------
log_step "Checking required tools..."
MISSING_TOOLS=()
for tool in kubectl helm talosctl tofu; do
    if ! command -v "$tool" &>/dev/null; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [[ ${#MISSING_TOOLS[@]} -gt 0 ]]; then
    log_error "Missing required tools: ${MISSING_TOOLS[*]}"
    log_info "Please install:"
    log_info "  kubectl: https://kubernetes.io/docs/tasks/tools/"
    log_info "  helm: https://helm.sh/docs/intro/install/"
    log_info "  talosctl: https://www.talos.dev/docs/v1.7/introduction/getting-started/"
    log_info "  tofu: https://opentofu.org/docs/intro/install/"
    exit 1
fi
log_success "All required tools are installed"

# -----------------------------------------------------------------------------
# Deploy Talos VMs (Proxmox)
# -----------------------------------------------------------------------------
K8S_DIR="$PROJECT_ROOT/deploy/kubernetes"
TALOS_DIR="$K8S_DIR/talos/talos-proxmox"

if [[ -d "$TALOS_DIR" ]]; then
    log_step "Provisioning Talos VMs on Proxmox..."
    cd "$TALOS_DIR"

    if [[ ! -f "terraform.tfvars" ]]; then
        if [[ -f "terraform.tfvars.example" ]]; then
            cp terraform.tfvars.example terraform.tfvars
            log_warning "terraform.tfvars created from example. Please edit with your Proxmox details."
            if [[ "$AUTO" != true ]]; then
                read -rp "Press Enter to continue after editing terraform.tfvars..."
            else
                log_error "terraform.tfvars not configured. Please set up Proxmox credentials first."
                exit 1
            fi
        else
            log_error "terraform.tfvars.example not found"
            exit 1
        fi
    fi

    log_info "Running OpenTofu to provision Talos VMs..."
    tofu init || true
    tofu apply -auto-approve
    cd "$PROJECT_ROOT"
else
    log_warning "Talos provisioning directory not found – skipping VM creation"
fi

# -----------------------------------------------------------------------------
# Apply Kubernetes manifests
# -----------------------------------------------------------------------------
APPS_DIR="$K8S_DIR/apps"
if [[ -d "$APPS_DIR" ]]; then
    log_step "Applying Kubernetes manifests..."
    kubectl apply -k "$APPS_DIR" || {
        log_error "Failed to apply Kubernetes manifests"
        exit 1
    }
else
    log_error "Kubernetes manifests directory not found: $APPS_DIR"
    exit 1
fi

# -----------------------------------------------------------------------------
# Install Argo CD (GitOps)
# -----------------------------------------------------------------------------
log_step "Installing Argo CD..."
if ! kubectl get namespace argocd &>/dev/null; then
    kubectl create namespace argocd
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
    log_success "Argo CD installed"
else
    log_success "Argo CD already installed"
fi

# -----------------------------------------------------------------------------
# Install Prometheus & Grafana (if not already deployed by manifests)
# -----------------------------------------------------------------------------
log_step "Checking Prometheus & Grafana..."
if ! kubectl get namespace monitoring &>/dev/null; then
    log_info "Installing Prometheus & Grafana via Helm..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update
    helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
else
    log_success "Prometheus & Grafana already installed"
fi

# -----------------------------------------------------------------------------
# Install GPUStack (distributed GPU orchestration)
# -----------------------------------------------------------------------------
log_step "Installing GPUStack..."
if [[ -f "$K8S_DIR/distributed-gpu/controller/install-gpustack-company.sh" ]]; then
    bash "$K8S_DIR/distributed-gpu/controller/install-gpustack-company.sh"
else
    log_warning "GPUStack installer not found – skipping"
fi

# -----------------------------------------------------------------------------
# Configure WireGuard for secure pod-to-pod communication
# -----------------------------------------------------------------------------
log_step "Configuring WireGuard..."
if [[ -f "$K8S_DIR/distributed-gpu/peers/wireguard-config.yaml" ]]; then
    kubectl apply -f "$K8S_DIR/distributed-gpu/peers/wireguard-config.yaml"
    log_success "WireGuard configuration applied"
else
    log_warning "WireGuard configuration not found – skipping"
fi

# -----------------------------------------------------------------------------
# Verify deployment
# -----------------------------------------------------------------------------
log_step "Verifying Kubernetes deployment..."
kubectl get pods -A

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 4
log_success "Phase 4 completed – Kubernetes cluster is deployed"

echo ""
echo "Access your platform:"
echo "  Odoo: https://$(kubectl get svc -n ingress traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'your-domain')"
echo "  Grafana: https://grafana.$(kubectl get svc -n ingress traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'your-domain')"
echo "  Argo CD: https://argo.$(kubectl get svc -n ingress traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'your-domain')"