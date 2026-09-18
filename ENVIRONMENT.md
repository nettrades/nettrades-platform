# Development Environment Reference

## Host

- OS: WSL2 on Windows
- Distribution: Ubuntu 24.04 (assumed from apt paths)
- Kernel: Microsoft WSL kernel (see `/proc/version`)
- Primary GPU: NVIDIA GeForce RTX 5070 Ti (16 GB VRAM)
- GPU driver: installed on Windows, exposed via WSL CUDA

## Toolchain

| Tool | Version | Where |
|---|---|---|
| Python | 3.12.3 | `/usr/bin/python3` |
| pip | latest | `/usr/bin/pip3` |
| Node.js | 20.20.2 | system PATH |
| npm | 10.8.2 | system PATH |
| Docker | latest | installed on Windows, exposed to WSL |
| Docker Compose | 5.5.1 | `docker compose` |
| uv | 0.12.10 | `~/.local/bin/uv` |
| Wine | (optional) | for Windows launcher builds |

## Paths

| Purpose | Path |
|---|---|
| Project root | `~/nettrades-platform` |
| Python venv | `~/nettrades-platform/.venv` |
| Odoo source | `~/nettrades-platform/third-party/odoo` |
| Odoo modules (source) | `~/nettrades-platform/odoo-modules/` |
| Odoo modules (deploy) | `~/nettrades-platform/deploy/docker/odoo-modules/` |
| Docker compose file | `~/nettrades-platform/deploy/docker/docker-compose.yaml` |
| .env file | `~/nettrades-platform/deploy/docker/.env` |
| Install logs | `~/nettrades-platform/logs/install-modules-*.log` |
| Emergency access | `~/.nettrades/emergency/credentials.txt` |

## Ports

| Service | Host port | Container port | Protocol |
|---|---|---|---|
| Odoo | 8069 | 8069 | HTTP |
| AI Chat UI | 3002 | 8000 | HTTP |
| LangGraph | 8000 | 8000 | HTTP |
| Enterprise Gateway (odoo_proxy) | 8090 | 8080 | HTTP |
| Dynamo | 8001 | 8000 | HTTP |
| llama.cpp | 8080 | 8080 | HTTP |
| RPC master | 8081 | 8080 | HTTP |
| PostgreSQL | (internal) | 5432 | TCP |
| Valkey | (internal) | 6379 | TCP |
| Grafana | 3001 | 3000 | HTTP |
| Prometheus | 9090 | 9090 | HTTP |
| Traefik HTTP | 80 | 80 | HTTP |
| Traefik HTTPS | 443 | 443 | HTTPS |
| WireGuard (hub) | 51820 | 51820 | UDP |
| WireGuard (admin) | 51821 | (n/a) | UDP |
| RPC worker (per spoke) | 50052 | 50052 | TCP |

## Database

The Docker Compose stack runs one PostgreSQL instance (`docker-postgres-1`)
with (eventually) three logical databases:

- `odoo` — Odoo ORM tables (business data + checkpoints)
- `nettrades_infra` — agent infrastructure tables (planned)

Credentials are in `.env`. Do not paste them into logs.

## Test Users

Created by the seed script (if run):

- `admin` / `<from .env ODOO_ADMIN_PASSWORD>` — system admin
- `emergency` / `<random>` — created at deploy time, in
  `~/.nettrades/emergency/credentials.txt`

## External Dependencies

| Dependency | Purpose | Where configured |
|---|---|---|
| ModelScope mirror | HF and GGUF model downloads | `scripts/download-model.sh` |
| WireGuard tools | Spoke tunnel management | system apt |
| NVIDIA Container Toolkit | GPU access in containers | system config |
| bcrypt (Python) | Prometheus password hashing | venv |