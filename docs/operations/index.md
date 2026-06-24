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
4. Access your platform at https://your-domain
[Full Single VM Guide](single-vm-deployment.md) →

### For Kubernetes on Talos
1. Prepare a Proxmox host (or bare metal) and create Talos VMs.
2. Bootstrap the Kubernetes cluster with talosctl.
3. Deploy services using the provided manifests.
[Full Kubernetes Guide](kubernetes-deployment.md) →

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
| Deploy the platform	| [Single VM](single-vm-deployment.md) or [Kubernetes](kubernetes-deployment.md)|
| Add a GPU node	| [GPU node deployment](gpu-node-deployment.md)|
| Configure monitoring	| [Prometheus & Grafana](kubernetes-deployment.md#deploy-monitoring)|
| Troubleshoot issues	| [Troubleshooting guide](troubleshooting.md)|
| Backup and restore	| [Backup & Restore](backup-and-restore.md)|
| Scale the platform	| [Kubernetes scaling](kubernetes-deployment.md#scaling)|
| Optimise performance	| [Performance Tuning](performance-tuning.md)|
| Configure fairness	| [Fairness Configuration](fairness-configuration.md)|

### Fairness Configuration

The fairness system evaluates AI responses for rationality and bias, with configurable thresholds and automated filtering.

### Key Settings

| Setting | Description	| Default |
|---------|-------------|---------|
| rationality_evaluation_enabled | Enable rationality evaluation | True |
| bias_detection_enabled | Enable bias detection | True |
| auto_flag_for_review | Auto-flag low-quality responses | True |
| auto_filter_training | Filter training data | True |
| rationality_threshold | Minimum rationality score | 7.0 |
| bias_threshold | Maximum bias score | 3.0 |
| evaluation_model | LLM judge model | gpt-4o-mini |

### Fairness Configuration Steps

    Navigate to Settings → Technical → Fairness → Global Configuration.

    Enable or disable features as needed.

    Adjust thresholds for rationality and bias.

    Select the evaluation model.

    Configure protected attributes for bias detection.

### Fairness Monitoring

    Navigate to Settings → Technical → Fairness → Dashboard.

    View recent audits and flags.

    Review flagged responses manually.

    Accept or reject flagged responses.

[Full Fairness Documentation](./developer/fairness.md)

### System Requirements
Before you deploy, review the [System Requirements](system-requirements.md) page to ensure your infrastructure meets the minimum hardware, OS, and network specifications.

### Monitoring & Observability
The platform includes built-in monitoring:

| Tool | Purpose | Access |
|-----------------|----------|-------------|
|`Prometheus`|	Metrics collection	|https://prometheus.your-domain|
|`Grafana`	|Dashboards and visualization	|https://grafana.your-domain (admin / password from .env)|
|`Alertmanager`	|Alerting	|Configured via alertmanager.yml|

### Command-Line Reference
[Odoo CLI](single-vm-deployment.md#command-line-reference) →

[Docker Compose Commands](single-vm-deployment.md#docker-compose-commands) →

[Talos CLI](kubernetes-deployment.md#talos-cli-commands) →

[GPU Node Agent Commands](gpu-node-deployment.md#gpu-node-agent-commands) →

### Security Best Practices
1. Change default passwords – Immediately change admin/admin for GPUStack and Grafana.
2. Use HTTPS – Traefik with Let's Encrypt provides automatic TLS.
3. Restrict SSH – Use the security-harden.sh script.
4. Regular backups – Ensure daily database backups are running.
5. Update regularly – Run docker compose pull or kubectl apply for updates.

### Troubleshooting
[Troubleshooting Quick Reference](troubleshooting-quickref.md) – One-page cheat sheet

[Troubleshooting Decision Tree](troubleshooting-guide.md) – Visual step-by-step guide

[Full Troubleshooting Guide](troubleshooting.md) – Detailed error list and solutions

### FAQ
[Operations FAQ](faq.md) – Frequently asked questions for operators

### Next Steps
[Single VM Deployment](single-vm-deployment.md) →

[Kubernetes Deployment](kubernetes-deployment.md) →

[GPU Node Deployment](gpu-node-deployment.md) →

[Troubleshooting](troubleshooting.md) →
