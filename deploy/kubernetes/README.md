# NETTRADES.AI Infrastructure (nettrades-infra)

This repository contains all Kubernetes manifests, Talos provisioning code, and deployment scripts for the scalable NETTRADES.AI platform.

## Quick Start

Prerequisites

    Proxmox host with Talos Linux QCOW2 images uploaded.

    talosctl, kubectl, helm, opentofu installed on your workstation.

    Access to a public IP for MetalLB.

1. **Provision Talos VMs** (Proxmox only):
   ```bash
   cd talos/talos-proxmox
   cp terraform.tfvars.example terraform.tfvars   # fill in your values
   tofu init && tofu apply -auto-approve
   ./deploy-infra.sh
   
2.     Configure secrets:

 ( In the past Generated Talos secrets:
    bash

    talosctl gen secrets -o talos/secrets.yaml
 )
    
    bash

    cp .env.example .env
    # Edit .env with strong passwords

    Deploy applications:
    bash

    ./deploy-k8s-base.sh

    Access the platform:

        Odoo: https://nettrades.ai

        Grafana: https://grafana.nettrades.ai

        Argo CD: https://argo.nettrades.ai

Repository Structure

    talos/ — Talos Linux VM provisioning (OpenTofu)

    apps/ — Kubernetes manifests (Kustomize)

    distributed-gpu/ — GPU controller and WireGuard peer manager

    ingress/ — Traefik Ingress resources

    argocd/ — Argo CD application definition

Maintenance

    Upgrade Talos: talosctl upgrade --image ghcr.io/siderolabs/installer:v1.13.0

    Upgrade CNPG: helm upgrade cnpg cnpg/cloudnative-pg --namespace cnpg-system

    Backup: Daily CNPG backups are scheduled; test restore quarterly.