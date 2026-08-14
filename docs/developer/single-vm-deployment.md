
# Single VM Deployment (Docker Compose)

This guide walks you through deploying the NETTRADES.AI platform on a single Ubuntu 24.04 virtual machine using Docker Compose.

## Architecture Diagram

```mermaid
graph TB
    subgraph VM["Ubuntu 24.04 VM (Docker Compose)"]
        Traefik["Traefik v3.6 (reverse proxy + Let's Encrypt)"]
        Traefik --> Odoo
        Traefik --> Grafana
        Traefik --> LangGraph
        Traefik --> Redirector

        Odoo["Odoo 19 CE"] --> PG["PostgreSQL 17 + pgvector"]
        Odoo --> Valkey["Valkey 8"]

        LangGraph["LangGraph Agent"] --> Dynamo["NVIDIA Dynamo"]
        LangGraph --> llama_cpp["llama.cpp (CPU Fallback)"]
        LangGraph --> OdooProxy["Odoo Proxy"]

        Dynamo --> vLLM["vLLM (GPU)"]
        Dynamo --> llama_cpp

        Redirector["Redirector (nginx)"] --> LandingPage["Landing Page"]

        Prometheus["Prometheus"] --> Odoo
        Prometheus --> PG
        Prometheus --> LangGraph

        Grafana["Grafana"] --> Prometheus
    end

    User["End User"] --> Traefik
    User --> Launcher["NETTRADES Launcher (Electron)"]
    Launcher --> Odoo
    Launcher --> LangGraph
    Launcher --> Dynamo

```


## Inference Architecture

The platform uses a layered inference architecture:
		
| Priority | Backend | Description |
|---------|-------------|-----------|
| 1	| **NVIDIA Dynamo with vLLM** | Production-grade distributed inference, GPU-accelerated |
| 2	| **NVIDIA Dynamo (CPU mode)** | Runs on CPU when GPU unavailable |
| 3	| **llama.cpp** | Zero-dependency CPU fallback, runs on port 8080 |


## Services Overview


| Service | Port | Purpose |
|---------|-------------|-----------|
| **Traefik** | 80, 443 | Reverse proxy with Let's Encrypt SSL |
| **Odoo** | 8069 | ERP, Marketplace, AI Hub (Governance Layer) |
| **Odoo Proxy** | 8090 | HTTP JSON-RPC shim for Odoo |
| **LangGraph** | 8000 | Multi-agent orchestration with state persistence |
| **NVIDIA Dynamo** | 8001 | Primary inference engine (vLLM + llama.cpp) |
| **llama.cpp** | 8080 | CPU inference fallback |
| **NETTRADES-UI** | 3002 | Chat interface |
| **PostgreSQL** | 5432 | Database with pgvector |
| **Valkey** | 6379 | In-memory store (sessions, cache, bus) |
| **Prometheus** | 9090 | Metrics collection |
| **Grafana** | 3001 | Visualisation dashboards |
| **Redirector** | 80 | Landing page redirector |
| **WireGuard** | 51821 | Admin VPN server |


## Security Hardening


The deployment automatically applies security hardening:

| Security Feature | Description |
|---------|-------------|
| **SSH Hardening** | Root login disabled, key-based authentication, port 2222 rescue port |
| **UFW Firewall** | Only necessary ports open (22, 80, 443, 51821) |
| **WireGuard VPN** | Secure admin VPN server on port 51821 |
| **gVisor** | Container isolation for CPU services (Odoo, LangGraph) |
| **fail2ban** | Protection against brute force attacks |
| **RBAC** | Role-based access control in Odoo |
| **Audit Logging** | All administrative actions logged |


## GPU Support


## NVIDIA GPU Setup

If you have an NVIDIA GPU, the deployment will automatically:

* Detect the GPU using nvidia-smi

* Install NVIDIA drivers (version 550+)

* Install NVIDIA Container Toolkit

* Configure Docker for GPU runtime


## AMD GPU Setup

For AMD GPUs (ROCm):

* Detect the GPU using rocminfo

* Install ROCm drivers (if not present)

* Install ROCm container runtime


## Intel GPU Setup

For Intel GPUs:

* Detect the GPU using clinfo

* Install Intel GPU drivers (intel-gpu-tools, intel-opencl-icd)


## One-Command Deployment

```bash

git clone -b main https://github.com/nettrades/nettrades-platform.git
cd nettrades-platform
chmod +x scripts/nettrades-setup.sh
sudo ./scripts/nettrades-setup.sh all --force
```

## Deployment Phases

| Phase | Description |
| **Phase 0** | System Preparation & Hardening (Docker, UFW, SSH, WireGuard, fail2ban) |
| **Phase 1** | Development Environment (Python virtual environment, dependencies) |
| **Phase 2** | Single-VM Deployment (Docker Compose, Odoo, LangGraph, Dynamo, llama.cpp) |
| **Phase 3** | Kubernetes Scaling (optional – future) |
| **Phase 4** | Module Installation (NETTRADES Odoo modules) |
| **Phase 5** | Monitoring Setup (Prometheus, Grafana) |


## Accessing Services

After deployment, access the platform at:


| Service	| URL | Credentials |
|---------|-------------|---------|
| **NETTRADES Launcher** | `http://localhost:3002` | No login required |
| **Odoo** | `https://your-domain/odoo` | admin / (from .env) |
| **Grafana** | `https://grafana.your-domain` | admin / (from .env) |
| **Prometheus** | `https://prometheus.your-domain` | admin / (from .env) |
| **NETTRADES-UI Chat** | `http://localhost:3002` | No login required |
| **llama.cpp UI** | `http://localhost:8080` | 	No login required |
| **Dynamo API** | `http://localhost:8001/v1` | Bearer token (from .env) |


## Troubleshooting


### Check Service Status

```bash

cd /root/nettrades-platform/deploy/docker
docker compose ps
```

### View Logs

```bash

# All services
docker compose logs

# Specific service
docker compose logs odoo
docker compose logs langgraph-server
docker compose logs dynamo
```

### Restart Services

```bash

docker compose restart odoo
docker compose restart langgraph-server
docker compose restart dynamo
```

### Full Redeployment

```bash

cd /root/nettrades-platform
rm -f .phase-*-complete
sudo ./scripts/nettrades-setup.sh all --force
```

## Next Steps

* [NVIDIA Dynamo Integration](nvidia-dynamo-integration.md) – Dynamo integration guide

* [gVisor Integration](gvisor-integration.md) – Container isolation

* [GPU Node Deployment](gpu-node-deployment.md) – Add GPU nodes

* [Backup & Restore](backup-and-restore.md) – Backup your data

* [Performance Tuning](performance-tuning.md) – Optimise performance

* [Troubleshooting](troubleshooting.md) – Common issues and solutions