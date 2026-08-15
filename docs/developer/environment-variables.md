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
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://odoo:password@postgres:5432/odoo` | ✅ Yes | Odoo, LangGraph |
| `POSTGRES_PASSWORD` | PostgreSQL password for the `odoo` user | None | ✅ Yes | Odoo, Postgres container |
| `DB_HOST` | PostgreSQL host (single-VM) | `localhost` | ⚠️ Optional | Odoo |
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

### NVIDIA Dynamo (Primary Inference Engine)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `DYNAMO_API_KEY` | API key for Dynamo authentication | None | ✅ **Critical** | Dynamo, LangGraph |
| `LLM_BASE_URL` | Dynamo API URL | `http://dynamo:8000/v1` | ⚠️ Optional | LangGraph, NETTRADES-UI |
| `MODEL_NAME` | Default model for inference | `Qwen2.5-1.5B-Instruct` | ⚠️ Optional | Dynamo, vLLM |

### vLLM (GPU Inference)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `VLLM_BASE_URL` | vLLM API URL | None | ⚠️ Optional | Inference tools |
| `VLLM_API_KEY` | vLLM API key | `dummy` | ⚠️ Optional | Inference tools |
| `VLLM_TARGET_DEVICE` | Target device (`cuda` or `cpu`) | `cuda` | ⚠️ Optional | vLLM |

### llama.cpp (CPU Fallback)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `LLAMA_API_KEY` | llama.cpp API key | `dummy` | ⚠️ Optional | Inference tools |
| `LLAMA_SERVER_MODEL` | Model path for llama.cpp | `/models/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf` | ⚠️ Optional | llama.cpp |
| `LLAMA_SERVER_PORT` | llama.cpp server port | `8080` | ⚠️ Optional | llama.cpp |

### LangGraph Service

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `LANGGRAPH_API_KEY` | API key for LangGraph authentication | None | ✅ **Critical** | FastAPI app |
| `LANGGRAPH_URL` | URL of the LangGraph service | `http://langgraph-server:8000` | ⚠️ Optional | NETTRADES-UI |
| `LANGGRAPH_API_URL` | External URL for LangGraph | `https://${DOMAIN}/api` | ⚠️ Optional | LangGraph |
| `LANGGRAPH_TRUST_X_FORWARDED_HEADERS` | Trust proxy headers | `true` | ⚠️ Optional | LangGraph |
| `DISABLE_AUTH` | Disable authentication (development only) | `false` | ⚠️ Optional | LangGraph |
| `LLM_MODEL` | Model for LangGraph agents | `deepseek-r1:1.5b` | ⚠️ Optional | LangGraph agents |


### Model Configuration

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `MODEL_NAME` | Default model for inference | `Qwen2.5-1.5B-Instruct` | ⚠️ Optional | Dynamo, vLLM |
| `LLM_MODEL` | Model for LangGraph agents | `deepseek-r1:1.5b` | ⚠️ Optional | LangGraph agents |
| `OPENAI_API_KEY` | OpenAI API key | None | ⚠️ Optional | Fairness evaluator, external API |
| `ANTHROPIC_API_KEY` | Anthropic API key | None | ⚠️ Optional | External API |

---

### Inference Backends (Auto-detection priority)

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
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

## Odoo

### Odoo Core

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `ODOO_URL` | Odoo instance URL | `http://odoo:8069` | ⚠️ Optional | Odoo Proxy, LangGraph |
| `ODOO_DB` | Odoo database name | `odoo` | ⚠️ Optional | Odoo Proxy |
| `ODOO_USER` | Odoo user ID for API calls | `1` | ⚠️ Optional | Odoo Proxy |
| `ODOO_PASSWORD` | Odoo admin password | `admin` | ✅ Yes | Odoo, Odoo Proxy |
| `ADMIN_PASSWORD` | Odoo admin password (alias) | None | ✅ Yes | Odoo |
| `ODOO_API_KEY` | API key for Odoo proxy authentication | None | ✅ **Critical** | Odoo Proxy, LangGraph |
| `PROXY_API_KEY` | API key for Odoo proxy (must match ODOO_API_KEY) | None | ✅ **Critical** | Odoo Proxy |

### Odoo Proxy

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `ODOO_PROXY_URL` | Odoo Proxy URL | `http://odoo-proxy:8080` | ⚠️ Optional | LangGraph, NETTRADES-UI |
| `USE_ODOO_PROXY` | Use Odoo Proxy for API calls | `true` | ⚠️ Optional | LangGraph |

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

---

## Forgejo Git

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `FORGEJO_DB_PASSWORD` | PostgreSQL password for Forgejo | None | ✅ Yes | Forgejo |
| `FORGEJO_SECRET_KEY` | Secret key for Forgejo sessions | None | ✅ Yes | Forgejo |

---

## Bridge Service (Company-Specific Overrides)

These variables are used by the `nettrades_bridge` module to route requests between local and remote brains. They are typically set in the Odoo admin interface rather than environment variables, but they can also be set in `.env`.

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `BRIDGE_MODE` | Override for a specific company: `local`, `remote`, `hybrid`, `global` | `global` | ⚠️ Optional | Bridge service |
| `BRIDGE_REMOTE_URL` | Company-specific remote brain URL | None | ⚠️ Optional | Bridge service |
| `BRIDGE_REMOTE_API_KEY` | Company-specific remote brain API key | None | ⚠️ Optional | Bridge service |

---

## Self-Improving Service

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `THRESHOLD_EPISODES` | Number of episodes to trigger training | `50` | ⚠️ Optional | Self-Improving |
| `THRESHOLD_QUALITY` | Minimum quality score for training (0-10) | `7.0` | ⚠️ Optional | Self-Improving |
| `FINE_TUNE_MODEL` | Model to fine-tune | `deepseek-1.5b` | ⚠️ Optional | Self-Improving |
| `FINE_TUNE_METHOD` | Fine-tuning method (`unsloth`, `axolotl`) | `unsloth` | ⚠️ Optional | Self-Improving |
| `DATA_CLASSIFICATION_DEFAULT` | Default data classification | `public` | ⚠️ Optional | Self-Improving |

## Fine-Tuning Pipeline

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `FINETUNE_BACKEND` | Which fine-tuning backend to use: `local` or `remote` | `local` | ⚠️ Optional | `ft.dataset` |
| `DATA_JUICER_ENABLED` | Whether to enable Data-Juicer filtering | `false` | ⚠️ Optional | `ft.dataset` |
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
| `ADMIN_EMAIL` | Email address for Let's Encrypt certificate registration | None | ✅ Yes | Traefik, cert-manager |
| `PUBLIC_IP` | Public IP address of the server (auto-detected if not set) | Auto-detected | ⚠️ Optional | Installer scripts |

---

## Security Best Practices

1. **Never commit the `.env` file** to version control. Add it to `.gitignore`.
2. **Use strong random passwords** for all secrets. Use `openssl rand -base64 32` to generate them.
3. **Rotate API keys regularly** (especially `LANGGRAPH_API_KEY` and `ODOO_API_KEY`).
4. **In production, set `LOG_LEVEL=warn`** to reduce log noise and avoid leaking sensitive information.
5. **Store API keys securely** – use environment variables or a secrets manager, not hardcoded values.

---

## External APIs

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `OPENAI_API_KEY` | OpenAI API key | None | ⚠️ Optional | Fairness evaluator, external API |
| `ANTHROPIC_API_KEY` | Anthropic API key | None | ⚠️ Optional | External API |

## Feature Flags

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `FEATURE_CORE` | Enable core features | `true` | ✅ Yes | All |
| `FEATURE_GPU_MARKETPLACE` | Enable GPU marketplace | `true` | ⚠️ Optional | GPU Admin |
| `FEATURE_GPU_ADMIN` | Enable GPU administration | `true` | ⚠️ Optional | GPU Admin |
| `FEATURE_BRIDGE` | Enable bridge routing | `true` | ⚠️ Optional | Bridge |
| `FEATURE_ROUTER` | Enable routing engine | `true` | ⚠️ Optional | Bridge |
| `FEATURE_GOOD_ANSWER` | Enable Good Answer system | `true` | ⚠️ Optional | Self-Improving |
| `FEATURE_SELF_IMPROVING` | Enable self-improving AI | `true` | ⚠️ Optional | Self-Improving |
| `FEATURE_TRAINING` | Enable training | `true` | ⚠️ Optional | Training |
| `FEATURE_ASK_SOMEONE` | Enable Ask Someone | `false` | ⚠️ Optional | Ask Someone |
| `FEATURE_JOB_MATCHING` | Enable job matching (coming soon) | `false` | ⚠️ Optional | Job Matching |
| `FEATURE_DATA_COLLECTION` | Enable data collection (coming soon) | `false` | ⚠️ Optional | Data Collection |


## NETTRADES-UI

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `AUTH_ENABLED` | Enable authentication | `false` | ⚠️ Optional | NETTRADES-UI |
| `UI_API_KEY` | API key for NETTRADES-UI | None | ⚠️ Optional | NETTRADES-UI |
| `SESSION_SECRET` | Session encryption secret | None | ✅ **Critical** | NETTRADES-UI |
| `ODOO_OAUTH_CLIENT_ID` | Odoo OAuth client ID | None | ⚠️ Optional | NETTRADES-UI |
| `ODOO_OAUTH_CLIENT_SECRET` | Odoo OAuth client secret | None | ⚠️ Optional | NETTRADES-UI |
| `ODOO_OAUTH_REDIRECT_URI` | Odoo OAuth redirect URI | `https://${DOMAIN}/api/auth/callback/odoo` | ⚠️ Optional | NETTRADES-UI |
| `ODOO_OAUTH_AUTHORIZE_URL` | Odoo OAuth authorize URL | `${ODOO_URL}/restapi/1.0/common/oauth2/authorize` | ⚠️ Optional | NETTRADES-UI |
| `ODOO_OAUTH_TOKEN_URL` | Odoo OAuth token URL | `${ODOO_URL}/restapi/1.0/common/oauth2/access_token` | ⚠️ Optional | NETTRADES-UI |
| `ODOO_OAUTH_USERINFO_URL` | Odoo OAuth user info URL | `${ODOO_URL}/restapi/1.0/common/oauth2/userinfo` | ⚠️ Optional | NETTRADES-UI |

## WireGuard

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `WIREGUARD_PRIVATE_KEY` | WireGuard private key | None | ✅ Yes | WireGuard |
| `WIREGUARD_PUBLIC_KEY` | WireGuard public key | None | ✅ Yes | WireGuard |
| `WG_ADMIN_PORT` | WireGuard admin VPN port | `51821` | ⚠️ Optional | WireGuard |
| `WG_ADMIN_SUBNET` | WireGuard admin VPN subnet | `10.10.10.0/24` | ⚠️ Optional | WireGuard |
| `WG_ADMIN_SERVER_IP` | WireGuard admin VPN server IP | `10.10.10.1` | ⚠️ Optional | WireGuard |

## Domain & Admin

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `DOMAIN` | Domain name or IP address | `changeit` | ✅ Yes | All services |
| `ADMIN_EMAIL` | Admin email for Let's Encrypt | `changeit` | ✅ Yes (for SSL) | Traefik |
| `ENVIRONMENT` | Environment (`development` or `production`) | `development` | ⚠️ Optional | All |
| `DEFAULT_LANDING_PAGE` | Default landing page (`odoo`, `ui`, `custom`) | `odoo` | ⚠️ Optional | Redirector |

## UV Package Installer

| Variable | Purpose | Default | Required | Used By |
|----------|---------|---------|----------|---------|
| `USE_UV` | Use UV instead of pip for Python packages | `true` | ⚠️ Optional | Setup scripts |

## How to Generate Secure Secrets

```bash
# Generate a secure PostgreSQL password
openssl rand -base64 24 | tr -d '+/=' | tr -d '\n' | cut -c1-24

# Generate a secure API key (48 characters)
openssl rand -base64 48 | tr -d '+/=' | tr -d '\n' | cut -c1-48

# Generate a WireGuard private key
wg genkey

# Generate a WireGuard public key
wg pubkey < privatekey

```

## Environment File Location

The .env file is located at:

```text

/root/nettrades-platform/deploy/docker/.env
```

## Example .env File

```bash

# Domain & Admin
DOMAIN=nettrades.ai
ADMIN_EMAIL=admin@nettrades.ai
ENVIRONMENT=production

# PostgreSQL
POSTGRES_PASSWORD=your_secure_password

# Odoo
ADMIN_PASSWORD=your_secure_password
ODOO_API_KEY=your_secure_api_key
PROXY_API_KEY=your_secure_api_key

# LangGraph
LANGGRAPH_API_KEY=your_secure_api_key
DISABLE_AUTH=false

# NVIDIA Dynamo
DYNAMO_API_KEY=your_secure_api_key
LLM_BASE_URL=http://dynamo:8000/v1
MODEL_NAME=Qwen2.5-1.5B-Instruct

# Grafana
GRAFANA_PASSWORD=your_secure_password

# Prometheus
PROMETHEUS_PASSWORD=your_secure_password

# WireGuard
WIREGUARD_PRIVATE_KEY=your_wireguard_private_key
WIREGUARD_PUBLIC_KEY=your_wireguard_public_key

# Feature Flags
FEATURE_CORE=true
FEATURE_GPU_MARKETPLACE=true
FEATURE_GPU_ADMIN=true
FEATURE_BRIDGE=true
FEATURE_ROUTER=true
FEATURE_GOOD_ANSWER=true
FEATURE_SELF_IMPROVING=true
FEATURE_TRAINING=true
FEATURE_ASK_SOMEONE=false

```

## Next Steps

[Glossary →](glossary.md) – Key terms and definitions

[Database Schema →](database-schema.md) – Database schema reference

[API Reference](../developer/api-reference.md) – API documentation
