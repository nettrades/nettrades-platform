## Technical Solution Architecture

```mermaid

flowchart TD
    %% ========================================================================
    %% 1. EXTERNAL ACCESS & EDGE (Single VM Entry Point)
    %% ========================================================================
    subgraph External[" External Access"]
        Internet["Internet / Public Network

        • End Users (Web Browsers)
        • API Clients
        • Robotic / Edge Clients"]
    end

    subgraph VM[" Single Virtual Machine (Host OS: Ubuntu 24.04 LTS)"]
        direction TB
        subgraph Edge[" Edge Layer (Container: traefik)"]
            Traefik["Traefik Reverse Proxy
            ━━━━━━━━━━━━━━━━
            • Port 443 (HTTPS) with Let's Encrypt
            • Port 80 (HTTP → HTTPS redirect)
            • Path-based routing:
              - / → Odoo Web UI
              - /api/v1/* → Odoo JSON-RPC API
              - /invoke → LangGraph FastAPI
            • JWT / OAuth2 Authentication Proxy
            • Rate Limiting"]
        end

        %% ========================================================================
        %% 2. APPLICATION & ORCHESTRATION SERVICES
        %% ========================================================================
        subgraph AppLayer[" Application Services Layer"]
            subgraph OdooContainer["Container: odoo-web (Port 8069 internal)"]
                Odoo["Odoo 19 CE Application Server
                ━━━━━━━━━━━━━━━━
                • Web Controllers (/website, /forum)
                • JSON-RPC API Controllers
                • Custom Odoo Modules:
                  - nettrades_core
                  - nettrades_good_answer
                  - nettrades_gpu_admin
                  - nettrades_job_matching
                  - nettrades_proposals
                  - nettrades_lead_scoring
                  - nettrades_ask_someone
                  - nettrades_chatbot
                • Scheduled Cron Jobs:
                  - _cron_decay_reputation()
                  - _cron_auto_qualify_by_karma()
                  - _cron_trigger_finetune()"]
            end

            subgraph LangGraphContainer["Container: langgraph-orchestrator (Port 8000 internal)"]
                FastAPI["FastAPI Application
                ━━━━━━━━━━━━━━━━
                • /invoke (async inference)
                • /health (liveness probe)
                • /metrics (Prometheus)"]
                Supervisor["Supervisor Graph
                ━━━━━━━━━━━━━━━━
                • classify Node
                • medical_screening Node
                • route Node"]
                SubAgents["Sub-Agents
                ━━━━━━━━━━━━━━━━
                • Recruitment Agent
                • Freelance Agent
                • Lead Gen Agent
                • GPU Management Agent
                • Vision Agent
                • Action Agent
                • General LLM Fallback"]
                Checkpointer["PostgresSaver Checkpointer
                ━━━━━━━━━━━━━━━━
                • Durable state snapshots"]
            end

            subgraph DynamoContainer["Container: nvidia-dynamo (Port 8001 internal)"]
                Dynamo["NVIDIA Dynamo
                ━━━━━━━━━━━━━━━━
                • Distributed Inference Engine
                • vLLM (GPU acceleration)
                • llama.cpp (CPU fallback)
                • OpenAI-compatible API
                • KV cache-aware routing"]
            end

            subgraph GPUNodeAgent["Container: gpu-node-agent (Privileged)"]
                GNA["GPU Node Agent
                ━━━━━━━━━━━━━━━━
                • ensure_wireguard()
                • get_or_create_node_id()
                • get_gpu_info() (nvidia-smi)
                • get_tee_summary()
                • node registration"]
            end
        end

        %% ========================================================================
        %% 3. DATA LAYER
        %% ========================================================================
        subgraph DataLayer[" Data Layer"]
            subgraph PostgresContainer["Container: postgres (Port 5432 internal)"]
                Postgres["PostgreSQL 17 + pgvector
                ━━━━━━━━━━━━━━━━
                • Business data (Odoo)
                • Vector embeddings (pgvector)
                • LangGraph checkpoints
                • Replication (primary/standby)"]
            end

            subgraph ValkeyContainer["Container: valkey (Port 6379 internal)"]
                Valkey["Valkey 8
                ━━━━━━━━━━━━━━━━
                • Session storage
                • ORM cache (Odoo)
                • Bus notifications
                • Pub/Sub messaging"]
            end

            subgraph Storage["Persistent Storage"]
                Models["Model Storage
                ━━━━━━━━━━━━━━━━
                • GGUF models (llama.cpp)
                • HF models (vLLM)
                • Fine-tuned models"]
                Backups["Backup Storage
                ━━━━━━━━━━━━━━━━
                • PostgreSQL dumps
                • Odoo filestore
                • Configuration backups"]
            end
        end

        %% ========================================================================
        %% 4. MONITORING
        %% ========================================================================
        subgraph Monitoring[" Monitoring"]
            Prometheus["Prometheus
            ━━━━━━━━━━━━━━━━
            • Metrics collection
            • Service discovery"]
            Grafana["Grafana
            ━━━━━━━━━━━━━━━━
            • Dashboards
            • Alerts"]
        end
    end

    %% ========================================================================
    %% 5. SECURITY
    %% ========================================================================
    subgraph Security[" Security"]
        gVisor["gVisor Container Runtime
        ━━━━━━━━━━━━━━━━
        • Strong isolation for CPU services
        • User-space kernel
        • Untrusted workloads"]
        WireGuard["WireGuard VPN
        ━━━━━━━━━━━━━━━━
        • Hub-and-spoke topology
        • AllowedIPs enforcement
        • Encrypted mesh"]
    end

    %% Connections
    Internet -->|"HTTPS:443"| Traefik
    Traefik -->|"/"| Odoo
    Traefik -->|"/invoke"| FastAPI
    Odoo -->|"SQL"| Postgres
    Odoo -->|"Cache"| Valkey
    FastAPI -->|"SQL"| Postgres
    FastAPI -->|"Inference"| Dynamo
    Dynamo -->|"GPU"| GNA
    Dynamo -->|"Fallback"| llama_cpp
    GNA -->|"Register"| Odoo
    Prometheus -->|"Scrape"| Odoo
    Prometheus -->|"Scrape"| FastAPI
    Prometheus -->|"Scrape"| Dynamo
    Grafana -->|"Query"| Prometheus
    gVisor -.->|"Isolates"| Odoo
    gVisor -.->|"Isolates"| LangGraph
    WireGuard -.->|"Secures"| GNA

```


## Inference Architecture


```mermaid

graph TB
    subgraph Inference["Inference Pipeline"]
        Request["Request"] --> Router["Provider Router Logic"]

        Router -->|"Priority 1"| Dynamo["NVIDIA Dynamo"]
        Router -->|"Priority 2"| vLLM["vLLM (GPU)"]
        Router -->|"Priority 3"| llama_cpp["llama.cpp (CPU)"]

        Dynamo --> vLLM
        Dynamo --> llama_cpp

        vLLM --> Response["Response"]
        llama_cpp --> Response
    end

```


### Inference Backend Priority


| Priority | Backend | Condition |
|---------|-------------|---------|
| 1	| **NVIDIA Dynamo with vLLM** |  GPU available and healthy |
| 2	| **NVIDIA Dynamo (CPU mode)** |  GPU unavailable but Dynamo running |
| 3	| **NVIDIA Dynamo with llama.cpp** |  CPU available and healthy |
| 4	| **llama.cpp** |  Dynamo unavailable (fallback) |


## Security Architecture


| Layer | Technology | Description |
|---------|-------------|---------|
| **Edge** |  Traefik + Let's Encrypt | TLS termination, rate limiting, path routing |
| **Network** | WireGuard | Encrypted VPN mesh, AllowedIPs enforcement |
| **Container** |  gVisor (CPU), default (GPU) | User-space kernel for CPU services; default for GPU |
| **Application** |  Odoo RBAC | Role-based access control, audit logging |
| **Secrets** |  Kubernetes Secrets / .env | Encrypted secrets management |


## Scaling Architecture (Future)


The platform is designed to scale from a single VM to a full Kubernetes cluster:

| Scale | Deployment | Services |
|---------|-------------|---------|
| **Small** |  Single VM (Docker Compose) | All services on one host |
| **Medium** |  Kubernetes (3 nodes) | Odoo, LangGraph, Dynamo, PostgreSQL |
| **Large** |  Kubernetes (10+ nodes) | All services + GPU workers |
| **Enterprise** |  Kubernetes (100+ nodes) | Multi-region, active-active |


