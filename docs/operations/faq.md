# Operations FAQ – Frequently Asked Questions

This page answers common questions from system administrators and DevOps engineers deploying and maintaining the NETTRADES.AI platform.

## Deployment

### What are the minimum hardware requirements for a single-VM deployment?

- 4 CPU cores
- 16 GB RAM
- 100 GB NVMe SSD
- Ubuntu 24.04 LTS
- Ports 80, 443, and 22 open (and 51820 if using WireGuard)

See [System Requirements](system-requirements.md) for details.

### Can I deploy on a server without a GPU?

Yes. The platform uses `llama.cpp` for CPU-based inference. If you add a GPU later, you can migrate to vLLM using the **`phase-add-gpu.sh`** script (or `migrate-to-gpu.sh`).

### How do I migrate from a single VM to Kubernetes?

Run `./scripts/nettrades-setup.sh k8s --auto` to deploy the platform on a Talos Kubernetes cluster. This will preserve your data.

### What is the recommended backup strategy?

Perform daily PostgreSQL dumps, weekly filestore backups, and regularly backup your configuration files. See [Backup & Restore](backup-and-restore.md) for full details.

### How do I install the Odoo modules after deployment?

Run `./scripts/install-modules.sh --force` from the project root. If the command‑line tool fails, you can install the modules via the Odoo UI:

1. Log in to Odoo (`http://localhost:8069`) as `admin` / `admin`
2. Go to **Apps** → Click **Update Apps List**
3. Search for each `nettrades_*` module and click **Install**

### How do I upgrade Odoo modules?

Run `./scripts/install-modules.sh --upgrade --force` to upgrade all NETTRADES modules to the latest version.

### Why do modules show "Activate" instead of "Upgrade"?

This means the modules are **not installed yet** – they are available but not active. Click **Install** (which becomes "Activate") to install them. If you have run `install-modules.sh` and they still show "Activate", the installation may have failed due to a database connection issue. Check the logs and ensure `db_password` in `odoo.conf` matches `POSTGRES_PASSWORD` in `.env`.

## Networking & Security

### How do I secure my deployment?

- Run `phase-system.sh` (Phase 0) to configure UFW, fail2ban, and disable root SSH.
- Use Let's Encrypt TLS via Traefik (automatic).
- Change default passwords (Grafana, GPUStack).
- Restrict SSH access to trusted IPs.

### Why is WireGuard required?

WireGuard provides kernel-level network isolation for GPU nodes. It ensures that only authorised peers can communicate, preventing unauthorised access to the GPU network.

### Can I use another VPN instead of WireGuard?

No. The platform is tightly integrated with WireGuard for AllowedIPs enforcement and performance. Replacing it would require significant changes to the GPU agent and peer manager.

### How do I expose services externally?

Traefik acts as the ingress controller. It automatically obtains SSL certificates and routes traffic based on hostnames. Configure your DNS with wildcard records (e.g., `*.nettrades.ai`) to enable subdomain routing.

### How do I check if the platform is healthy?

Run `./scripts/health-check.sh` (if created) or manually check:
- Odoo: `curl http://localhost:8069`
- LangGraph: `curl http://localhost:8000/health`
- PostgreSQL: `docker exec docker-postgres-1 pg_isready -U odoo`

## Monitoring & Alerts

### What monitoring tools are included?

- **Prometheus** for metrics collection.
- **Grafana** for dashboards.
- **Alertmanager** for alerting.
- Built-in GPU health watchdog and utilisation alerts.

### How do I view logs?

For Docker Compose: `docker compose logs --tail=100 <service>`. For Kubernetes: `kubectl logs -n <namespace> <pod>`.

### How do I set up alerts?

Modify `deploy/docker/alert-rules.yml` (or the Kubernetes equivalent) to define custom alert conditions. The platform includes default alerts for node health, GPU utilisation, and database connectivity.

### Can I integrate with external monitoring (e.g., Datadog, New Relic)?

Yes. You can export Prometheus metrics to external systems using the Prometheus remote write feature or use the Prometheus exporter endpoints.

## Scalability

### How do I add more GPU nodes?

Deploy the GPU agent on new machines using the installer script. They will automatically register with the central Odoo instance and join the pool.

### How do I scale the platform horizontally?

Move to Kubernetes (Talos) and use Horizontal Pod Autoscalers. You can also add more worker nodes and adjust replica counts.

### What is the maximum number of users the platform can support?

The platform is designed to scale. With proper hardware and Kubernetes, it can support millions of users. The single-VM deployment is limited to a few hundred concurrent users.

### How do I handle high inference load?

Add more GPU nodes, enable vLLM with tensor parallelism, and use GPUStack's scheduling policies. For very high load, consider distributed inference across multiple clusters.

## Maintenance & Upgrades

### How do I update the platform?

For Docker Compose: `git pull` and run `./scripts/nettrades-setup.sh all --auto --force`. For Kubernetes: update the manifests and let Argo CD sync.

### How do I change the database password?

1. Update `POSTGRES_PASSWORD` in `.env`
2. Update `db_password` in `deploy/docker/config/odoo.conf`
3. Run `docker exec -it docker-postgres-1 psql -U odoo -c "ALTER USER odoo WITH PASSWORD 'new_password';"`
4. Restart Odoo: `docker compose restart odoo`

### What is the recommended way to run Odoo for development?

Use Docker Compose: `cd deploy/docker && docker compose up -d`. This ensures all services (PostgreSQL, Odoo, LangGraph, etc.) are properly networked. Avoid running `odoo-bin` directly from Windows or WSL, as it will fail to resolve the `postgres` hostname.

### Where are the Odoo logs stored?

Inside the container at `/var/log/odoo/odoo.log`. If you have mounted `./odoo-logs:/var/log/odoo` in `docker-compose.yaml`, logs will appear in `deploy/docker/odoo-logs/odoo.log` on the host.

### How do I view Odoo logs?

```bash
# From the deploy/docker directory
docker compose logs -f odoo

# Or, if you mounted logs to the host
tail -f odoo-logs/odoo.log



### How do I check if all modules are installed?

Log in to Odoo, go to Apps → search for nettrades. All installed modules will show the Upgrade button; uninstalled modules show Install.

### Troubleshooting Common Issues

#### Password authentication failed for user "odoo"

##### Symptom: Odoo logs show FATAL: password authentication failed for user "odoo".

##### Solution:

* Check the password in `odoo.conf`: `grep db_password deploy/docker/config/odoo.conf`

* Check the password in PostgreSQL: `docker exec docker-postgres-1 printenv POSTGRES_PASSWORD`

* Reset the password if they don't match:

```bash

    docker exec -it docker-postgres-1 psql -U odoo -c "ALTER USER odoo WITH PASSWORD 'odoo123';"
```

#### Odoo modules show "Activate" not "Upgrade"

##### Symptom: After running install-modules.sh --force, modules still show the Activate button.

Root cause: The modules are not installed. This can happen if the installation script failed due to database connection issues (password mismatch) or if modules have unmet dependencies.

##### Solution:

Ensure the database password is correct (see above).

    Run the installation script again with verbose output:
    ```bash

    ./scripts/install-modules.sh --force
    ```

If it still fails, install manually via Odoo UI:

* Log in to Odoo

* Go to Apps → Update Apps List

* Search for `nettrades_core` → Install

* Repeat for all `nettrades_*` modules


#### Could not translate host name "postgres"

##### Symptom: When running `odoo-bin` directly, you see `could not translate host name "postgres" to address`.

Root cause: You are running Odoo outside Docker, so the hostname `postgres` is not resolvable on your Windows/WSL host.

##### Solution:

* Use Docker Compose: `cd deploy/docker && docker compose up -d`

* Or if you must run Odoo directly, change `db_host = localhost` in `odoo.conf` and ensure PostgreSQL is running on `localhost`.

#### Odoo returns 502 / Connection refused

##### Symptom: `http://localhost:8069` returns `502 Bad Gateway` or `Connection refused`.

##### Solution:

* Check if Odoo is running: `docker ps | grep odoo`

* Check logs: `docker compose logs odoo --tail 50`

* Wait 30 seconds for PostgreSQL to become healthy.

* Restart Odoo: `docker compose restart odoo`

#### Next Steps

After deploying, consider:

* Configuring fairness settings: Settings → Technical → Fairness → Global Configuration

* Setting up GPU registration tokens: GPU → Registration Tokens

* Enabling bridge routing: Settings → Technical → Bridge → Global Configuration

* Configuring self-service onboarding: Settings → General Settings → Sign Up → Allow external users to sign up

* Installing all NETTRADES modules: `./scripts/install-modules.sh --force`

#### Support

For further assistance, open a GitHub issue or reach out on our community channels.