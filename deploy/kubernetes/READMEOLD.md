4. Build and Deploy Instructions

Prerequisites

    Proxmox host with Talos Linux QCOW2 images uploaded.

    talosctl, kubectl, helm, opentofu (or Terraform) installed on your workstation.

    Access to a public IP for MetalLB.

Step-by-Step

    Clone nettrades-infra.

    Copy terraform.tfvars.example ? terraform.tfvars and fill in Proxmox credentials.

    Generate Talos secrets:
    bash

    talosctl gen secrets -o talos/secrets.yaml

    Provision VMs and bootstrap the cluster:
    bash

    cd talos/talos-proxmox
    tofu init && tofu apply -auto-approve
    ./deploy-infra.sh

    Copy .env.example ? .env and set strong secrets.

    Build custom Docker images (Odoo, LangGraph, MCP?Odoo, wg?peer?manager) and push to the private registry.

    Run the deploy script:
    bash

    ./deploy-k8s-base.sh

    For company GPU clusters:
    bash

    ./distributed-gpu/controller/install-gpustack-company.sh

The platform is now fully operational with WireGuard isolation, GPUStack orchestration, Axolotl fine?tuning, and a complete Kubernetes?native monitoring stack.