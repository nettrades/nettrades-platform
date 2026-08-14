# Developer Documentation

Welcome to the NETTRADES.AI developer documentation. This section is designed for developers and contributors who want to extend, customize, or contribute to the platform.

---

## What Can You Build?

### 🤖 New LangGraph Agents
Add new AI agents to handle specific business domains – recruitment, lead generation, customer service, or anything else.

[Learn about building agents →](building-agents.md)

### 🧩 New Odoo Modules
Extend the platform with new business functionality – new data models, views, workflows, or integrations.

[Learn about building Odoo modules →](building-odoo-modules.md)

### 🌉 Bridge Module
The hub-and-spoke routing module that enables client companies to use local AI for internal operations while seamlessly accessing global services.

[Learn about the Bridge Module →](bridge-module.md)

### 🔄 Self-Improving AI
The closed-loop learning architecture that continuously improves the platform's AI models through data collection, trigger detection, fine-tuning, and deployment.

[Learn about Self-Improving AI →](self-improving.md)

### ⚖️ Fairness & Bias Detection
The fairness system that evaluates AI responses for rationality and bias, with configurable thresholds, automated filtering, and audit logging.

[Learn about Fairness & Bias →](fairness.md)

### 🖥️ Custom Dashboard Widgets
Add new widgets to the GPU Admin Panel or create custom dashboards for specific user roles.

[Learn about the GPU Admin Panel →](building-odoo-modules.md#extending-the-gpu-admin-panel)

---

## Core Models Reference

The platform includes several custom Odoo models that form the foundation of the business logic.

| Model | Description |
|-------|-------------|
| `nettrades.field` | Professional field configuration |
| `nettrades.experience` | User work experience |
| `nettrades.review` | User ratings and reviews |
| `good.answer.vote` | Good Answer votes |
| `user_field_reputation` | Reputation per field |
| `ft.dataset` | Fine-tuning datasets |
| `expert.session` | Expert consultation sessions |
| `gpu.node` | GPU node management |
| `data.episode` | Self-improving interaction episode |
| `trigger.config` | Self-improving trigger configuration |
| `loop.cycle` | Self-improving loop cycle |
| `nettrades.fairness.audit` | Fairness audit log |
| `nettrades.fairness.flag` | Fairness flag for human review |

[Full core models reference →](core-models.md)

---

## Getting Started as a Developer

1. **Set up your development environment** – Install Python, PostgreSQL, Docker, and clone the repository.
2. **Run the platform locally** – Start Odoo and the LangGraph service.
3. **Explore the codebase** – Understand the architecture and key components.
4. **Build your first agent or module** – Use our templates and guides.

[Full developer getting started guide →](getting-started.md)

---

## Key Architecture Components

| Component | Location | Description |
|-----------|----------|-------------|
| **LangGraph Supervisor** | `src/core/supervisor.py` | Central orchestrator that classifies intents and routes to sub-agents |
| **FastAPI Application** | `src/core/app.py` | Entry point for AI inference requests `/invoke` |
| **Sub-Agents** | `src/core/agents/` | Specialised business agents (Recruitment, Freelance, Lead Gen, GPU Management) |
| **Distributed GPU Agent** | `src/agent/agent.py` | Runs on each GPU node, manages WireGuard and NVIDIA Dynamo |
| **Odoo Modules** | `odoo-modules/` | Business logic, UI, and administration |
| **Bridge Module** | `odoo-modules/nettrades_bridge/` | Hub-and-spoke routing engine |
| **Self-Improving Modules** | `odoo-modules/nettrades_data_collection/`, `nettrades_trigger/`, `nettrades_loop/`, `nettrades_self_improving_config/` | Closed-loop learning system |
| **Fairness Module** | `odoo-modules/nettrades_fairness/` | Fairness, rationality, and bias detection |
| **MCP-Odoo Bridge** | `third-party/mcp-odoo/` | Allows AI agents to interact with Odoo data |

[Full architecture overview →](architecture.md)

---

## Project Status

| Component | Status | Notes |
|-----------|--------|-------|
| LangGraph Supervisor | ✅ Core logic exists | Medical screening loop needs fixing |
| Sub-Agents | ⚠️ Placeholders | Real code in `src/agent/` needs moving |
| FastAPI Application | ✅ Core endpoints exist | Authentication needs fixing |
| GPU Node Agent | ✅ Full implementation | `requirements.txt` needs fixing |
| Odoo `nettrades.field` | ⚠️ Sparse | 24+ fields missing |
| Odoo `gpu.node` | ⚠️ Sparse | 15+ fields and methods missing |
| Odoo `gpu.cluster` | ❌ Broken | Indentation bug, missing methods |
| Odoo `nettrades.experience` | ✅ Complete | Work experience model |
| Odoo `nettrades.review` | ✅ Complete | User review model |
| **Bridge Module** | ✅ Complete | Hub-and-spoke routing |
| **Self-Improving Modules** | ✅ Complete | MAPE loop implementation |
| **Fairness Module** | ✅ Complete | Bias detection and rationality evaluation |
| Deployment Scripts | ✅ Full | Phase-based orchestrator works |

[Full roadmap →](./governance/roadmap.md)

---

## Code Style & Standards

We follow the OCA (Odoo Community Association) conventions for Odoo modules and PEP 8 for Python code.

- **Python**: PEP 8, type hints, docstrings
- **Odoo**: OCA conventions, LGPL-3.0 license for modules
- **JavaScript**: Owl framework conventions
- **XML**: Prefix XML IDs with module name

[Full style guide →](style-guide.md)

---

## API Reference

- [LangGraph `/invoke` API →](api-reference.md#langgraph-invoke-api)
- [GPU Node Registration →](api-reference.md#gpu-node-registration-api)
- [NVIDIA Dynamo Token Refresh →](api-reference.md#NVIDIAdynamo-token-refresh-api)
- [WebSocket Bus API →](api-reference.md#websocket-bus-api)
- [Bridge API →](bridge-module.md#api-endpoints.md)

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](./governance/contributing.md) before submitting PRs.

Key points:
- **CLA required** – All contributors must sign the CLA
- **LGPL-3.0 for Odoo modules** – Your contributions must be LGPL-3.0 compatible
- **AGPL-3.0 for core** – Your contributions to `src/` must be AGPL-3.0 compatible
- **Code review** – All PRs require review

---

## Need Help?

- **GitHub Issues**: [github.com/nettrades/nettrades-platform/issues](https://github.com/nettrades/nettrades-platform/issues)
- **Discord**: [Join our community](https://discord.gg/nettrades)
- **Email**: [dev@nettrades.ai](mailto:dev@nettrades.ai)


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
| Install/upgrade Odoo modules | ./scripts/install-modules.sh --force |

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

* Navigate to Settings → Technical → Fairness → Global Configuration.

* Enable or disable features as needed. 

* Adjust thresholds for rationality and bias. 

* Select the evaluation model. 

* Configure protected attributes for bias detection.

### Fairness Monitoring

* Navigate to Settings → Technical → Fairness → Dashboard.

* View recent audits and flags.

* Review flagged responses manually.

* Accept or reject flagged responses.

[Full Fairness Documentation](./developer/fairness.md)

### System Requirements
    
Before you deploy, review the [System Requirements](system-requirements.md) page for hardware and software prerequisites.


### Common Operations
#### Viewing Logs

```bash

# Docker Compose
cd deploy/docker
docker compose logs -f [service]

# Kubernetes
kubectl logs -n <namespace> <pod>
```

#### Restarting a Service

```bash

# Docker Compose
docker compose restart <service>

# Kubernetes
kubectl rollout restart deployment/<deployment> -n <namespace>
```

#### Updating the Platform

```bash

# Pull latest changes
git pull

# Re-run deployment (idempotent)
./scripts/nettrades-setup.sh all --auto --force
```

#### Installing Odoo Modules

```bash

./scripts/install-modules.sh --force
```

#### Checking Platform Health

```bash

# Check all containers
docker ps

# Check service health endpoints
curl http://localhost:8069          # Odoo
curl http://localhost:8000/health   # LangGraph
curl http://localhost:9090          # Prometheus
```

#### Environment Variables

The platform uses a .env file for configuration. Key variables include:

| Variable | Purpose	| Default |
|---------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | `odoo123` |
| `ODOO_ADMIN_PASSWORD` | Odoo admin password | `admin` |
| `DOMAIN` | Public domain for SSL | `localhost` |
| `ADMIN_EMAIL` | Email for Let's Encrypt | (empty) |
| `LANGGRAPH_API_KEY` | API key for LangGraph | (empty – must be set) |
| `PROXY_API_KEY` | Odoo proxy API key | (generated) |
| `GRAFANA_PASSWORD` | Grafana admin password | `admin` |

#### Security Considerations
Default Passwords

* Odoo: `admin` / `admin`

* Grafana: `admin` / `admin`

* PostgreSQL: `odoo` / `odoo123`

Change these before production deployment.

#### Firewall

* Port 22 (SSH) – restrict to trusted IPs

* Port 80 (HTTP) – required for Let's Encrypt

* Port 443 (HTTPS) – public access

* Port 51820 (WireGuard) – GPU node communication

#### TLS / SSL

* Traefik automatically obtains Let's Encrypt certificates when DOMAIN is set.

* For local development, use `http://localhost`.

#### gVisor Sandboxing

* Untrusted code (freelancer workloads) runs in gVisor sandboxes.

* Trusted workloads (company-owned) run without sandbox overhead.

* Configurable via Odoo admin screens.

#### Troubleshooting Quick Reference

Issue	Solution
Password authentication failed	`ALTER USER odoo WITH PASSWORD 'odoo123';`
Modules show "Activate"	Install via UI: Apps → Update Apps List → Install
postgres host not found	Use Docker Compose, not direct `odoo-bin`
Odoo 502	Wait for PostgreSQL; check logs
LangGraph 500	Check `LANGGRAPH_API_KEY` in `.env`

#### Next Steps

After deploying, consider:

* Configuring fairness settings: Settings → Technical → Fairness → Global Configuration

* Setting up GPU registration tokens: GPU → Registration Tokens

* Enabling bridge routing: Settings → Technical → Bridge → Global Configuration

* Configuring self-service onboarding: Settings → General Settings → Sign Up → Allow external users to sign up

* Installing all NETTRADES modules: `./scripts/install-modules.sh --force`

#### Support

* [GitHub Issues](https://github.com/nettrades/nettrades-platform/issues)

* [Documentation](https://nettrades.github.io/nettrades-platform/)

* Community channels (coming soon)  


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
1. Change default passwords – Immediately change admin/admin for NVIDIA Dynamo and Grafana.
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
