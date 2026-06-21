
# Operations FAQ – Frequently Asked Questions

This page answers common questions from system administrators and DevOps engineers deploying and maintaining the NETTRADES.AI platform.

---

## Deployment

### What are the minimum hardware requirements for a single-VM deployment?

- 4 CPU cores
- 16 GB RAM
- 100 GB NVMe SSD
- Ubuntu 24.04 LTS
- Ports 80, 443, and 22 open (and 51820 if using WireGuard)

See [System Requirements](system-requirements.md) for details.

### Can I deploy on a server without a GPU?

Yes. The platform uses `llama.cpp` for CPU-based inference. If you add a GPU later, you can migrate to vLLM with the `migrate-to-gpu.sh` script.

### How do I migrate from a single VM to Kubernetes?

Run `phase-scale.sh` in the project's scripts folder. This will deploy the platform on a Talos Kubernetes cluster, preserving your data.

### What is the recommended backup strategy?

Perform daily PostgreSQL dumps, weekly filestore backups, and regularly backup your configuration files. See [Backup & Restore](backup-and-restore.md) for full details.

---

## Networking & Security

### How do I secure my deployment?

- Run `security-harden.sh` to configure UFW, fail2ban, and disable root SSH.
- Use Let's Encrypt TLS via Traefik (automatic).
- Change default passwords (Grafana, GPUStack).
- Restrict SSH access to trusted IPs.

### Why is WireGuard required?

WireGuard provides kernel-level network isolation for GPU nodes. It ensures that only authorised peers can communicate, preventing unauthorised access to the GPU network.

### Can I use another VPN instead of WireGuard?

No. The platform is tightly integrated with WireGuard for AllowedIPs enforcement and performance. Replacing it would require significant changes to the GPU agent and peer manager.

### How do I expose services externally?

Traefik acts as the ingress controller. It automatically obtains SSL certificates and routes traffic based on hostnames. Configure your DNS with wildcard records (e.g., `*.nettrades.ai`) to enable subdomain routing.

---

## Monitoring & Alerts

### What monitoring tools are included?

- **Prometheus** for metrics collection.
- **Grafana** for dashboards.
- **Alertmanager** for alerting.
- Built-in GPU health watchdog and utilisation alerts.

### How do I view logs?

For Docker Compose: `docker compose logs --tail=100 <service>`.
For Kubernetes: `kubectl logs -n <namespace> <pod>`.

### How do I set up alerts?

Modify `deploy/docker/alert-rules.yml` (or the Kubernetes equivalent) to define custom alert conditions. The platform includes default alerts for node health, GPU utilisation, and database connectivity.

### Can I integrate with external monitoring (e.g., Datadog, New Relic)?

Yes. You can export Prometheus metrics to external systems using the Prometheus remote write feature or use the Prometheus exporter endpoints.

---

## Scalability

### How do I add more GPU nodes?

Deploy the GPU agent on new machines using the installer script. They will automatically register with the central Odoo instance and join the pool.

### How do I scale the platform horizontally?

Move to Kubernetes (Talos) and use Horizontal Pod Autoscalers. You can also add more worker nodes and adjust replica counts.

### What is the maximum number of users the platform can support?

The platform is designed to scale. With proper hardware and Kubernetes, it can support millions of users. The single-VM deployment is limited to a few hundred concurrent users.

### How do I handle high inference load?

Add more GPU nodes, enable vLLM with tensor parallelism, and use GPUStack's scheduling policies. For very high load, consider distributed inference across multiple clusters.

---

## Maintenance & Upgrades

### How do I update the platform?

For Docker Compose:
```bash
cd /opt/nettrades-ai
docker compose pull
docker compose up -d
