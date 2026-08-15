# Developer FAQ – Frequently Asked Questions

This page answers common questions from developers contributing to or extending the NETTRADES.AI platform.

---

## General

### What technologies does the platform use?

- **Backend**: Python (Odoo 19 CE, LangGraph, FastAPI)
- **Database**: PostgreSQL 17 with pgvector
- **Caching**: Valkey (Redis-compatible)
- **Containerisation**: Docker and Kubernetes (Talos)
- **GPU orchestration**: NVIDIA Dynamo (with vLLM and llama.cpp)
- **Networking**: WireGuard, mDNS/Avahi
- **Security**: gVisor container isolation
- **Frontend**: Odoo's Owl framework (JavaScript), Electron (Launcher)

### How do I set up a development environment?

Follow the [Developer Getting Started Guide](getting-started.md). It covers everything from installing dependencies to running Odoo locally.

### What is the code structure?

- `src/core/` – LangGraph supervisor and sub-agents
- `src/agent/` – Distributed GPU node agent
- `odoo-modules/` – Custom Odoo modules (LGPL-3.0)
- `third-party/` – Vendored dependencies (do not modify)
- `deploy/` – Deployment scripts and configurations
- `installer/` – NETTRADES Launcher (Electron)

### What are the licensing requirements?

- `src/` is AGPL-3.0 (copyleft).
- `odoo-modules/` is LGPL-3.0.
- Third-party dependencies retain their own licenses.
- All contributors must sign a CLA. See the [License Information](../../LICENSE.txt) for details.

See the [License Information](../../LICENSE.txt) for details.

---

## Building & Extending

### How do I create a new LangGraph agent?

1. Create a new file in `src/core/agents/` (e.g., `custom_agent.py`).
2. Define your agent's state and nodes.
3. Compile the graph using `StateGraph`.
4. Register it with the supervisor in `src/core/supervisor.py`.
5. Update the intent classification to route to your agent.

Full template: [Building LangGraph Agents](building-agents.md).

### How do I create a new Odoo module?

1. Create a folder under `odoo-modules/` with the module name.
2. Add `__manifest__.py`, `__init__.py`, and subdirectories (`models/`, `views/`, `security/`, etc.).
3. Define your models, views, and access rights.
4. Install the module using the Odoo UI or CLI.

Full template: [Building Odoo Modules](building-odoo-modules.md).

### How do I extend the GPU Admin Panel dashboard?

1. Locate `odoo-modules/nettrades_gpu_admin/static/src/js/dashboard.js`.
2. Add a new Owl component.
3. Register it in the widget registry.
4. Add the template to `gpu_dashboard_templates.xml`.

### How do I integrate with NVIDIA Dynamo?

The inference integration is already handled by the `inference_tools.py` module. To use Dynamo directly:

```python
from src.core.tools.inference_tools import get_inference_backend

backend = get_inference_backend()  # Returns 'dynamo', 'vllm', or 'llama_cpp'
response = await backend.invoke(messages)



API & Integration
What authentication is required for the /invoke endpoint?

You need to set the X-API-Key header to the value of LANGGRAPH_API_KEY from your environment.
How do I test the API locally?

Run Odoo and LangGraph locally, then use curl to send requests to http://localhost:8000/invoke (or the FastAPI port).

Example:
bash

curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"input": {"messages": [{"role":"user","content":"Hello"}]}}'

How do I add a new inference backend?

    Add the backend configuration to src/core/tools/inference_tools.py

    Add health checking logic

    Update the provider router to include the new backend

    Update the LLM_BASE_URL and OPENAI_API_KEY environment variables

Troubleshooting
The virtual environment is not found

Run Phase 1 first:
bash

./scripts/nettrades-setup.sh dev --force

NVIDIA Dynamo is not starting

Check the logs:
bash

docker compose logs dynamo

Ensure the model exists in deploy/docker/dynamo-data/models/.
llama.cpp is not starting

Check that a GGUF model exists:
bash

ls -la deploy/docker/dynamo-data/models/*.gguf

If missing, download one:
bash

./scripts/download-model.sh --model deepseek-1.5b --format gguf
  
### How do I migrate from a single VM to Kubernetes?

Run `./scripts/nettrades-setup.sh k8s --auto` to deploy the platform on a Talos Kubernetes cluster. This will preserve your data.

### How do I install the Odoo modules after deployment?

Run `./scripts/install-modules.sh --force` from the project root. If the command-line tool fails, you can install the modules via the Odoo UI:

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
- Change default passwords (Grafana, NVIDIA Dynamo).
- Restrict SSH access to trusted IPs.

### Why is WireGuard required?

WireGuard provides kernel-level network isolation for GPU nodes. It ensures that only authorised peers can communicate, preventing unauthorised access to the GPU network.

### Can I use another VPN instead of WireGuard?

No. The platform is tightly integrated with WireGuard for AllowedIPs enforcement and performance. Replacing it would require significant changes to the GPU agent and peer manager.

### How do I expose services externally?

Traefik acts as the ingress controller. It automatically obtains SSL certificates and routes traffic based on hostnames. Configure your DNS with wildcard records (e.g., `*.yourdomain.com`) to enable subdomain routing.

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

Add more GPU nodes, enable vLLM with tensor parallelism, and use NVIDIA Dynamo's scheduling policies. For very high load, consider distributed inference across multiple clusters.

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
