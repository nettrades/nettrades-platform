# Environment Variables Reference

This document lists all environment variables used by the NETTRADES.AI platform. They are defined in the `.env` file (or set directly in the environment) and control the behaviour of the platform components.

---

## How to Use This Reference

| Column | Description |
|--------|-------------|
| **Variable** | The name of the environment variable |
| **Purpose** | What the variable controls |
| **Default** | The default value (if any) |
| **Required** | Whether the variable must be set |
| **Used By** | Which component(s) read this variable |

---

## Core Infrastructure

### Database

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (format: `postgresql://user:pass@host:port/dbname`) | `postgresql://odoo:password@postgres:5432/odoo` | ✅ Yes | Odoo, LangGraph |
| `POSTGRES_PASSWORD` | PostgreSQL password for the `odoo` user | None | ✅ Yes | Odoo, Postgres container |
| `DB_HOST` | PostgreSQL host (single‑VM) | `localhost` | ⚠️ Optional (if `DATABASE_URL` set) | Odoo |
| `DB_PORT` | PostgreSQL port | `5432` | ⚠️ Optional | Odoo |
| `DB_USER` | PostgreSQL user | `odoo` | ⚠️ Optional | Odoo |
| `DB_NAME` | PostgreSQL database name | `odoo` | ⚠️ Optional | Odoo |

### Valkey (Redis-compatible)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `REDIS_HOST` | Valkey server hostname | `valkey` | ✅ Yes (if using cache) | Odoo, Odoo bus |
| `REDIS_PORT` | Valkey server port | `6379` | ⚠️ Optional | Odoo |
| `REDIS_PASSWORD` | Valkey authentication password | None | ⚠️ Optional | Odoo |

---

## AI & Inference

### LangGraph Service

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `LANGGRAPH_API_KEY` | API key for authenticating requests to `/invoke` endpoint | None | ✅ **Critical** | FastAPI app |
| `LANGGRAPH_LOCAL_URL` | URL of the local LangGraph service (for the bridge) | `http://langgraph:8000/invoke` | ⚠️ Optional | Bridge service |
| `LLM_MODEL` | Name of the model to use for inference | `deepseek-r1:1.5b` | ⚠️ Optional | All agents |

### Inference Backends (Auto-detection priority)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `GPUSTACK_SERVER_URL` | URL of the GPUStack server (highest priority) | None | ⚠️ Optional | Inference tools |
| `GPUSTACK_API_KEY` | API key for GPUStack | `dummy` | ⚠️ Optional | Inference tools |
| `VLLM_BASE_URL` | URL of the vLLM server (second priority) | None | ⚠️ Optional | Inference tools |
| `VLLM_API_KEY` | API key for vLLM | `dummy` | ⚠️ Optional | Inference tools |
| `LLM_BASE_URL` | URL of the llama.cpp server (lowest priority) | `http://llama-cpp:8080/v1` | ⚠️ Optional | Inference tools |
| `LLAMA_API_KEY` | API key for llama.cpp | `dummy` | ⚠️ Optional | Inference tools |

### Fairness & Bias Detection

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `OPENAI_API_KEY` | API key for OpenAI GPT models (used by fairness evaluator) | None | ⚠️ Optional | Fairness evaluator |
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude models (used by fairness evaluator) | None | ⚠️ Optional | Fairness evaluator |
| `FAIRNESS_EVALUATION_MODEL` | Default model for fairness evaluation | `gpt-4o-mini` | ⚠️ Optional | Fairness evaluator |
| `FAIRNESS_RATIONALITY_THRESHOLD` | Minimum rationality score (0-10) | `7.0` | ⚠️ Optional | Fairness config |
| `FAIRNESS_BIAS_THRESHOLD` | Maximum bias score (0-10) | `3.0` | ⚠️ Optional | Fairness config |

### Remote Brain (nettrades.ai)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `NETTRADES_REMOTE_BRAIN_URL` | URL of the remote brain (nettrades.ai) | `https://api.nettrades.ai` | ⚠️ Optional | Bridge service |
| `NETTRADES_REMOTE_API_KEY` | API key for the remote brain | None | ⚠️ Optional | Bridge service |
| `NETTRADES_BRAIN_MODE` | Mode of operation: `local`, `remote`, `hybrid` | `local` | ⚠️ Optional | Bridge service |

---

## Odoo Configuration

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `ADMIN_PASSWORD` | Master password for Odoo database creation | `admin` | ✅ Yes | Odoo |
| `ODOO_API_KEY` | API key for Odoo JSON‑RPC calls (MCP bridge) | None | ✅ Yes | MCP‑Odoo bridge |
| `ODOO_URL` | Odoo server URL for MCP bridge | `http://odoo:8069` | ⚠️ Optional | MCP‑Odoo bridge |
| `WORKERS` | Number of Odoo worker processes (set to 0 for development) | `0` | ⚠️ Optional | Odoo |
| `LOG_LEVEL` | Odoo log level (`info`, `debug`, `warn`, `error`) | `info` | ⚠️ Optional | Odoo |

---

## Monitoring & Observability

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `GRAFANA_PASSWORD` | Admin password for Grafana | None | ✅ Yes | Grafana |
| `PROMETHEUS_URL` | Prometheus server URL (for Grafana data source) | `http://prometheus:9090` | ⚠️ Optional | Grafana |

---

## GPU Cluster & WireGuard

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `WIREGUARD_PRIVATE_KEY` | Private key for the WireGuard controller | None | ✅ Yes (if using WireGuard) | WireGuard setup |
| `WIREGUARD_PUBLIC_KEY` | Public key for the WireGuard controller | None | ✅ Yes | WireGuard setup |
| `WIREGUARD_LISTEN_PORT` | UDP port for WireGuard | `51820` | ⚠️ Optional | WireGuard setup |
| `WIREGUARD_MESH_SUBNET` | WireGuard subnet in CIDR notation | `10.100.0.0/24` | ⚠️ Optional | WireGuard setup |
| `GPUSTACK_JWT_SECRET` | JWT secret for GPUStack authentication | None | ✅ Yes | GPUStack |
| `GPUSTACK_SERVER_URL` | (Already listed above – used for both inference and GPU management) |

---

## Forgejo Git

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `FORGEJO_DB_PASSWORD` | PostgreSQL password for Forgejo | None | ✅ Yes | Forgejo |
| `FORGEJO_SECRET_KEY` | Secret key for Forgejo sessions | None | ✅ Yes | Forgejo |

---

## Bridge Service (Company‑Specific Overrides)

These variables are used by the `nettrades_bridge` module to route requests between local and remote brains. They are typically set in the Odoo admin interface rather than environment variables, but they can also be set in `.env`.

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `BRIDGE_MODE` | Override for a specific company: `local`, `remote`, `hybrid`, `global` | `global` | ⚠️ Optional | Bridge service |
| `BRIDGE_REMOTE_URL` | Company‑specific remote brain URL | None | ⚠️ Optional | Bridge service |
| `BRIDGE_REMOTE_API_KEY` | Company‑specific remote brain API key | None | ⚠️ Optional | Bridge service |

---

## Fine-Tuning Pipeline

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `FINETUNE_BACKEND` | Which fine‑tuning backend to use: `local` or `remote` | `local` | ⚠️ Optional | `ft.dataset` |
| `DATA_JUICER_ENABLED` | Whether to enable Data‑Juicer filtering | `false` | ⚠️ Optional | `ft.dataset` |
| `DEITA_ENABLED` | Whether to enable DEITA scoring | `false` | ⚠️ Optional | `ft.dataset` |

---

## Fairness & Bias Detection

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `OPENAI_API_KEY` | API key for OpenAI (used by fairness evaluator) | None | ⚠️ Optional | Fairness evaluator |
| `ANTHROPIC_API_KEY` | API key for Anthropic (used by fairness evaluator) | None | ⚠️ Optional | Fairness evaluator |
| `FAIRNESS_EVALUATION_MODEL` | Default fairness evaluation model | `gpt-4o-mini` | ⚠️ Optional | Fairness evaluator |
| `FAIRNESS_RATIONALITY_THRESHOLD` | Minimum rationality score | `7.0` | ⚠️ Optional | Fairness config |
| `FAIRNESS_BIAS_THRESHOLD` | Maximum bias score | `3.0` | ⚠️ Optional | Fairness config |

---

## Deployment & Installation

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `DOMAIN` | Main domain for the platform (e.g., `nettrades.ai`) | None | ✅ Yes | Traefik, Odoo, Forgejo |
| `ADMIN_EMAIL` | Email address for Let's Encrypt certificate registration | None | ✅ Yes | Traefik, cert‑manager |
| `PUBLIC_IP` | Public IP address of the server (auto‑detected if not set) | Auto‑detected | ⚠️ Optional | Installer scripts |

---

## Security Best Practices

1. **Never commit the `.env` file** to version control. Add it to `.gitignore`.
2. **Use strong random passwords** for all secrets. Use `openssl rand -base64 32` to generate them.
3. **Rotate API keys regularly** (especially `LANGGRAPH_API_KEY` and `ODOO_API_KEY`).
4. **In production, set `LOG_LEVEL=warn`** to reduce log noise and avoid leaking sensitive information.
5. **Store API keys securely** – use environment variables or a secrets manager, not hardcoded values.

---

## Next Steps

- [Glossary →](glossary.md)
- [Database Schema →](database-schema.md)
- [Back to Appendix →](index.md)