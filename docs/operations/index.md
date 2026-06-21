# Operations Documentation

Welcome to the NETTRADES.AI operations documentation. This section is designed for system administrators, DevOps engineers, and anyone deploying or managing the platform.

---

## Overview

NETTRADES.AI can be deployed in two ways:

| Deployment Type | Best For | Complexity | Scalability |
|-----------------|----------|------------|-------------|
| **Single VM (Docker Compose)** | Small to medium deployments, testing, proof of concept | Low | Limited (single machine) |
| **Kubernetes on Talos** | Production, high availability, enterprise scaling | High | Unlimited (horizontal scaling) |

---

## Quick Start

### For a Single VM Deployment

1. Prepare an Ubuntu 24.04 VM with root access.
2. Run the one-command installer:

```bash
curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash
```

3. Follow the interactive wizard (auto-detects hardware).
4. Access your platform at https://<your-domain>.
[Full Single VM Guide](operations/single-vm-deployment.md) →

### For Kubernetes on Talos
1. Prepare a Proxmox host (or bare metal) and create Talos VMs.
2. Bootstrap the Kubernetes cluster with talosctl.
3. Deploy services using the provided manifests.
[Full Kubernetes Guide](operations/kubernetes-deployment.md) →

### Deployment Options Comparison

| Feature | Single VM | Kubernetes |
|-----------------|----------|-------------|
| High Availability | 	❌ No	| ✅ Yes (3+ replicas)|
| Auto-scaling	|  ❌ No	| ✅ Yes (HPA)|
| Rolling Updates | 	❌ Manual	| ✅ Automated|
| GPU Support | 	✅ Yes (single node)	| ✅ Yes (multiple GPU nodes)|
| Monitoring | 	✅ Prometheus/Grafana included	| ✅ Prometheus/Grafana included|
| Backups | ✅ Daily (cron)	| ✅ CNPG scheduled backups|
| GitOps | 	❌ No	| ✅ Argo CD|
| Multi-region|	❌ No	| ✅ Yes (with Karmada)|

### Key Operations Tasks

| Task | Guide |
|-----------------|-------------|
| Deploy the platform	| [Single VM](operations/single-vm-deployment.md) or [Kubernetes](operations/kubernetes-deployment.md)|
| Add a GPU node	| [GPU node deployment](operations/gpu-node-deployment.md)|
| Configure monitoring	| [Prometheus & Grafana](operations/kubernetes-deployment#deploy-monitoring.md)|
| Troubleshoot issues	| [Troubleshooting guide](operations/troubleshooting.md)|
| Backup and restore	| [Backup & Restore](operations/backup-and-restore.md)|
| Scale the platform	| [Kubernetes scaling](operations/kubernetes-deployment#scaling.md)|
| Optimise performance	| [Performance Tuning](operations/performance-tuning.md)|

### System Requirements
Before you deploy, review the [System Requirements](operations/system-requirements) page to ensure your infrastructure meets the minimum hardware, OS, and network specifications.

### Monitoring & Observability
The platform includes built-in monitoring:

| Tool | Purpose | Access |
|-----------------|----------|-------------|
|`Prometheus`|	Metrics collection	|https://prometheus.<your-domain>|
|`Grafana`	|Dashboards and visualization	|https://grafana.<your-domain> (admin / password from .env)|
|`Alertmanager`	|Alerting	|Configured via alertmanager.yml|

### Command-Line Reference
    • [Odoo CLI](operations/single-vm-deployment#command-line-reference.md) →
    • [Docker Compose Commands](operations/single-vm-deployment#docker-compose-commands.md) →
    • [Talos CLI](operations/kubernetes-deployment#talos-cli-commands.md) →
    • [GPU Node Agent Commands](operations/gpu-node-deployment#gpu-node-agent-commands.md) →

### Security Best Practices
    1. Change default passwords – Immediately change admin/admin for GPUStack and Grafana.
    2. Use HTTPS – Traefik with Let's Encrypt provides automatic TLS.
    3. Restrict SSH – Use the security-harden.sh script.
    4. Regular backups – Ensure daily database backups are running.
    5. Update regularly – Run docker compose pull or kubectl apply for updates.

### Troubleshooting
    • [Troubleshooting Quick Reference](operations/troubleshooting-quickref.md) – One-page cheat sheet
    • [Troubleshooting Decision Tree](operations/troubleshooting-guide.md) – Visual step-by-step guide
    • [Full Troubleshooting Guide](operations/troubleshooting.md) – Detailed error list and solutions

### FAQ
    • Operations FAQ(operations/faq.md) – Frequently asked questions for operators

### Next Steps
    • [Single VM Deployment](operations/single-vm-deployment.md) →
    • [Kubernetes Deployment](operations/kubernetes-deployment.md) →
    • [GPU Node Deployment](operations/gpu-node-deployment.md) →
    • [Troubleshooting](operations/troubleshooting.md) →
