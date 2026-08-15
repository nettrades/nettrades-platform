# Quick Start – Operations

This guide provides a **5-minute** walkthrough to get NETTRADES.AI running on a single server for evaluation or small-scale production.

## Prerequisites

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **Operating System** | Windows 10/11 Pro + WSL2, or Ubuntu 22.04+ | Ubuntu 24.04 |
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 16 GB | 32+ GB |
| **Storage** | 50 GB free | 100+ GB SSD |
| **Python** | 3.12.9 | 3.12.9 |
| **PostgreSQL** | 18 | 18 with pgvector |
| **Docker** | 27.x | 27.x |
| **Git** | Latest | Latest |
| **Internet** | Broadband | Stable broadband |

If it will be used externally to host a website:

- A fresh Ubuntu 24.04 server with root access.
- A domain name pointing to your server's public IP if it will be used externally to host a website.
- Ports 80 and 443 open.

## Installation

## Step 1: Install WSL2 (Windows Only)

### 1.1 If on windows also enable WSL and Virtual Machine Platform

Open PowerShell as Administrator and run these command:

```powershell

Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux

# Restart when prompted
Enable-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform

# Restart again
wsl --set-default-version 2

```

### 1.2 Install Ubuntu 24.04

Open Microsoft Store, search for "Ubuntu 24.04", and install it.

Launch Ubuntu and complete the initial setup.

## Step 2: Clone the Repository (WSL)

Inside your WSL terminal carry on with the the remaining scripts:


```bash
# Upgrade Ubuntu if it is a new machine
apt update && apt upgrade -y
# Clone the repository
cd /mnt/c/
git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
cd /mnt/c/nettrades-platform

```

## Step 3: Set Up the Development Environment

### 3.1 Make Scripts Executable

```bash

# If you want to rerun everything and over write everything
rm -f .phase-*-complete

# Make the script executable
chmod +x scripts/*.sh
chmod +x scripts/lib/*.sh
chmod +x installer/*.js
chmod +x scripts/nettrades-setup.sh

```

### 3.2 Run the Deployment

```bash

# Run the full deployment (automatic)
sudo ./scripts/nettrades-setup.sh all --force

```


### 3.3 On a new Ubuntu Server 

If it a totally new installation on a new Ubuntu Server run these commands

```bash

# Update the system
apt update && apt upgrade -y

# Clone the repository
cd /root
git clone -b dev-deployment1 https://github.com/nettrades/nettrades-platform.git
cd nettrades-platform

# Make the script executable
chmod +x scripts/nettrades-setup.sh

# Run the full deployment
sudo ./scripts/nettrades-setup.sh all --force

```

The --force overwrites everything so don't use this on an existing system.

## Deployment Phases

	

| Phase | Description |
|------|--------|
| **Phase 0** | System Preparation & Hardening (Docker, UFW, SSH, WireGuard, fail2ban) |
| **Phase 1** | Development Environment (Python virtual environment, dependencies) |
| **Phase 2** | Single-VM Deployment (Docker Compose, Odoo, LangGraph, Dynamo, llama.cpp) |
| **Phase 3** | Kubernetes Scaling (optional – future) |
| **Phase 4** | Module Installation (NETTRADES Odoo modules) |
| **Phase 5** | Monitoring Setup (Prometheus, Grafana) |

## After Deployment

### Check Services

```bash

cd /root/nettrades-platform/deploy/docker
docker compose ps

```


## Step 4: Building the Launcher Installer

If you want to build the installer for distribution, run these commands on your development machine:

```bash

cd installer
npm install
npm run build:all   # or build:win / build:mac / build:linux
npm run build:win
npm run build:linux
npm start
```

## Step 5: Updating Dependencies

Before release, update the lock files:

```bash

cd /mnt/c/nettrades-platform
pip install pip-tools
pip-compile requirements.in -o requirements-lock.txt
pip-compile requirements-dev.in -o requirements-dev-lock.txt
```

Commit the lock files.

To generate hashes for security (recommended), add --generate-hashes:

```bash

pip-compile requirements.in -o requirements-lock.txt --generate-hashes
pip-compile requirements-dev.in -o requirements-dev-lock.txt --generate-hashes
```

## Step 6: Accessing Services

After deployment, access the platform at:
		
| Service | URL | Notes |Credentials |
|-------------|---------|-------------|---------|
| Odoo | http://localhost:8069 | ERP, Marketplace, AI Hub | admin / (from .env) |
| LangGraph API | http://localhost:8000 | Agent orchestration | Bearer token (from .env) |
| Grafana | http://localhost:3001 | Monitoring dashboards | admin / (from .env) |
| NETTRADES-UI | http://localhost:3002 | Chat interface | No login required |
| llama.cpp UI | http://localhost:8080 | CPU inference fallback | No login required |
| Dynamo API | http://localhost:8001 | NVIDIA Dynamo inference | |


### First Steps

#### 1. Open the Launcher

Navigate to `http://localhost:3002` in your browser.

OR

Navigate to `http://your-server-ip:3002` in your browser.

OR

Navigate to `http://your domain name:3002` in your browser.

#### 2. Download a Model

Click **Models -> Download Model** -> Select a model (e.g., DeepSeek 1.5B) -> Click **Download**

#### 3. Start Chatting

Click **Chat** -> Type a message -> Press Enter

#### 4. Manage GPUs

Click **GPUs -> Scan** to detect available GPUs -> **Register GPU** to add to the marketplace

#### 5. Add a VPN Peer

Click **Network -> Add Peer** -> Enter a name -> Click **Add Peer** -> Get a QR code for mobile


### Test Endpoints

```bash

curl http://localhost:8069  # Odoo
curl http://localhost:8000/health  # LangGraph

```

### View Logs

```bash

docker compose logs --tail=50

```


## Step 7: Checking Services Are Up

After deployment, verify all services are running:
```bash

cd /root/nettrades-platform/deploy/docker
docker compose ps
```

Test individual endpoints:

```bash

curl http://localhost:8069  # Odoo
curl http://localhost:8000/health  # LangGraph
```

## Step 8: Viewing Logs

```bash

# LangGraph logs
docker compose logs langgraph-server
docker compose logs langgraph-server --tail=20

# PostgreSQL logs
docker logs docker-postgres-1 --tail=50

# Check PostgreSQL process
docker exec docker-postgres-1 ps aux | grep postgres

# Test PostgreSQL connection
docker exec -it docker-postgres-1 psql -U odoo -d odoo -c "SELECT 1"
```

## Step 9: Testing Traefik Routing

Verify the API route is working correctly:

```bash

# Test with Host header
curl -v -k -H "Host: nettrades.ai" https://localhost/api/health

# Check Traefik logs for the request
docker compose logs traefik | grep "api/health"

# Check Traefik router configuration
docker compose logs traefik | grep "langgraph-api"

# Inspect container labels
docker inspect langgraph-server --format='{{json .Config.Labels}}' | jq | grep "entrypoints"
```

You should see:

```text

"traefik.http.routers.langgraph-api.entrypoints": "web,websecure"

```

## Step 10: Full Diagnostic Commands

For comprehensive troubleshooting, use the diagnostic commands in the Troubleshooting Guide.

Key commands:

```bash

# Check all services
docker compose ps

# View combined logs
docker compose logs --tail=100 2>&1 | tee /root/all-logs.txt

# Check failed services
docker compose ps --filter "status=exited" --filter "status=dead" --filter "status=restarting"
```

Step 11: Common Developer Tasks

### Reinstalling Modules

```bash

cd /root/nettrades-platform
./scripts/install-modules.sh --force
```

### Full Redeployment

```bash

cd /root/nettrades-platform
rm -f .phase-*-complete
sudo ./scripts/nettrades-setup.sh all --force
```

### Restarting Services

```bash

cd /root/nettrades-platform/deploy/docker
docker compose restart odoo
docker compose restart langgraph-server
docker compose restart dynamo

```


## Troubleshooting

For detailed diagnostic commands, see the [Troubleshooting Guide](troubleshooting.md).

## Quick Checks

```bash

# Check if deployment completed
ls -la /tmp/nettrades-phase2-completed

# Check PostgreSQL connection
docker compose exec -T postgres pg_isready -U odoo

# Check LangGraph health
curl -s http://localhost:8000/health

```

## Next Steps

[Single VM Deployment](single-vm-deployment.md) – Detailed deployment guide

[GPU Node Deployment](gpu-node-deployment.md) – Add GPU nodes

[Backup & Restore](backup-and-restore.md) – Backup your data

[Performance Tuning](performance-tuning.md) – Optimise performance

[Troubleshooting](troubleshooting.md) – Common issues and solutions

[Building Agents](building-agents.md) – Create custom LangGraph agents

[Building Odoo Modules](building-odoo-modules.md) – Extend the platform

[API Reference](api-reference.md) – API documentation