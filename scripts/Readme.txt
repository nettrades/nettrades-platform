============================================================================
NETTRADES.AI – Scripts Documentation
============================================================================

This directory contains utility scripts for the NETTRADES platform.

============================================================================
1. install-modules.sh
============================================================================
Installs all NETTRADES Odoo modules in the correct dependency order.

Usage:
  ./install-modules.sh [--force] [--upgrade]

Options:
  --force    Force installation even if modules are already installed
  --upgrade  Upgrade existing modules to the latest version

Modules installed:
  - nettrades_core
  - nettrades_good_answer
  - nettrades_ask_someone
  - nettrades_gpu_admin
  - nettrades_gpustack_adapter
  - nettrades_queue
  - nettrades_bridge
  - nettrades_data_collection
  - nettrades_trigger
  - nettrades_loop
  - nettrades_self_improving_config
  - nettrades_fairness
  - nettrades_onboarding
  - nettrades_job_matching
  - nettrades_proposals
  - nettrades_lead_scoring
  - nettrades_research
  - nettrades_chatbot
  - nettrades_notifications
  - nettrades_pwa

============================================================================
2. create-nettrades-projects.sh
============================================================================
Creates the full folder structure for nettrades-platform and generates
minimal module manifests and __init__.py files for all modules.

Usage:
  ./create-nettrades-projects.sh

============================================================================
3. gpustackinstall.ps1
============================================================================
Windows PowerShell installer for GPUStack. Supports server and worker
installation with CUDA detection and port availability checks.

Usage (as Administrator):
  .\gpustackinstall.ps1

Options:
  --port <port>              Server port (default: 80 or 443 with SSL)
  --worker-port <port>       Worker port (default: 10150)
  --data-dir <path>          Data directory
  --config-file <path>       Configuration file
  --server-url <url>         Server URL for worker nodes
  --token <token>            Token for worker authentication
  --bootstrap-password <pwd> Bootstrap password
  --ssl-keyfile <path>       SSL key file for HTTPS
  --host <host>              Server host
  --system-reserved <json>   System reservation configuration

============================================================================
4. ../deploy/docker/install-nettrades.sh
============================================================================
Interactive installation wizard for the NETTRADES platform. Auto-detects
hardware, generates secrets, and deploys the full stack.

Usage:
  sudo ./install-nettrades.sh

============================================================================
5. ../deploy/docker/deploy-single.sh
============================================================================
Idempotent single‑VM deployment script. Safe to re‑run.

Usage:
  ./deploy-single.sh [--auto]

Options:
  --auto  Skip confirmation prompts and use auto-detected values.

============================================================================
6. ../deploy/docker/docker-compose.yaml
============================================================================
Docker Compose configuration for the full platform stack.

Services:
  - traefik        : Reverse proxy with Let's Encrypt SSL
  - postgres       : PostgreSQL 18 with pgvector
  - postgres-exporter : PostgreSQL metrics exporter
  - valkey         : In‑memory store (sessions, ORM cache, bus)
  - odoo           : Odoo 19 CE with all custom modules
  - forgejo        : Self‑hosted Git server
  - langgraph      : AI orchestration service
  - odoo-proxy     : HTTP JSON‑RPC shim for Odoo
  - gpustack       : GPU management and inference
  - llama-cpp      : CPU inference engine
  - prometheus     : Metrics collection
  - grafana        : Visualisation dashboard
  - node_exporter  : System metrics

============================================================================
7. ../deploy/docker/.env.example
============================================================================
Environment variable template. Copy to .env and fill in your values.

============================================================================
For more information, see the documentation in the docs/ directory.
============================================================================