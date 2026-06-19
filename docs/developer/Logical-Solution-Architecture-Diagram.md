# Logical Solution Architecture Diagram

This is an extremely detailed, up-to-date Logical Solution Architecture diagram.

This diagram moves beyond business domains to focus on the software components, service interactions, APIs, data flows, and processing pipelines that make up the system.

# Detailed Narrative of the Logical Architecture
# 1. Access & Edge Layer

Clients (Browser, External API, Robotics) communicate via HTTPS/WebSockets.

Traefik acts as the single entry point, handling TLS termination, JWT/OAuth2 authentication, and path-based routing (/ for Odoo, /invoke for the LangGraph FastAPI service).

# 2. Application Services (The "Brain" & "Bones")

Odoo 19 CE serves as the System of Record. It houses all business logic in ORM models:

Manages professional fields, reputation, and voting weights.

Handles GPU node registration and inventory.

Executes scheduled cron jobs for reputation decay, auto-qualification, and triggering fine-tuning.

The nettrades.chatbot model acts as the bridge, dispatching user messages to LangGraph via an internal HTTP call.

LangGraph Orchestrator (FastAPI) is the System of Intelligence.

The Supervisor Graph runs the classify ? medical_screening ? route pipeline.

Sub-agents execute specialized tasks. They read/write back to Odoo models (e.g., Recruitment agent writes to nettrades.job_matching) and call inference engines.

GPUStack Manager provides the Inference Fabric. It exposes an OpenAI-compatible API, metering tokens per request, and managing worker pools with strict isolation (gVisor for public workloads).

# 3. Data & Persistence Layer (The "Memory")

PostgreSQL + pgvector: Stores transactional business data, vector embeddings for semantic search, and the LangGraph checkpointing blobs (allowing full workflow resumption).

Valkey: Handles high-speed caching, ORM session storage, and the Odoo bus (real-time Pub/Sub for notifications).

Longhorn: Provides persistent block storage for unstructured data like uploaded CVs, fine-tuning datasets (JSONL), and model weight files (GGUF).

# 4. AI/ML Pipeline (The "Self-Improvement Loop")

Triggered by Odoo cron jobs based on new "Good Answer" votes:

Export : ft.dataset.export_to_jsonl() extracts eligible Q&A pairs.

Data-Juicer : Applies quality filtering and deduplication.

DEITA : Uses an LLM-as-Judge to score the complexity and quality of responses.

Unsloth/Axolotl : Runs QLoRA fine-tuning on the curated dataset.

Model Registry : The new adapter weights are saved to Longhorn and registered with the GPUStack inference engine, making the improved model available for future inference.

# 5. Security & Network Fabric (The "Nerve System")

WireGuard creates an encrypted mesh VPN between the control plane and all GPU worker nodes, ensuring secure internal communication (e.g., GPU health checks, model transfers).

gVisor provides an additional layer of syscall-level isolation specifically for public GPU worker pools, preventing tenant workloads from affecting the host kernel.

RBAC is enforced via Odoo's native security groups and Cilium's eBPF network policies.

# 6. Foundation & Orchestration

Kubernetes (Talos OS) orchestrates all containers, providing high availability, self-healing, and scaling.

Argo CD implements GitOps, ensuring the entire logical architecture (deployments, services, configmaps) is declared in Git and automatically synchronized.

Cilium provides high-performance eBPF networking and deep observability (Hubble) across all services.
        
---

## Logical Solution Architecture Diagram

```mermaid
flowchart TD
    %% ========================================================================
    %% 1. EXTERNAL CLIENTS & ACCESS LAYER
    %% ========================================================================
    subgraph AccessLayer["?? External Access & Clients"]
        Browser["Web Browser (PWA)<br>????????????????<br>• Odoo Website / Discuss / Chat<br>• Service Worker (offline support)"]
        APIClient["External API Client<br>????????????????<br>• REST / JSON-RPC consumers<br>• Third-party job board scrapers"]
        RoboticClient["Robotic / Edge Client<br>????????????????<br>• ROS 2 nodes<br>• MCP-Robotics bridge"]
    end

    %% ========================================================================
    %% 2. API GATEWAY & EDGE SECURITY
    %% ========================================================================
    subgraph Gateway["?? API Gateway & Edge (Traefik)"]
        direction TB
        TLSTerm["TLS Termination<br>????????????????<br>• Let's Encrypt Auto-Cert<br>• HTTP/2 & WebSocket support"]
        AuthZ["Authentication / Authorization<br>????????????????<br>• JWT Bearer token validation<br>• OAuth2 / OpenID Connect proxy"]
        RateLimit["Rate Limiting & Routing<br>????????????????<br>• Path-based routing (/ ? Odoo, /invoke ? FastAPI)<br>• Request throttling per tenant"]
    end

    %% ========================================================================
    %% 3. APPLICATION SERVICES LAYER (BACKEND LOGIC)
    %% ========================================================================
    subgraph ApplicationLayer["?? Application Services Layer"]
        direction TB

        subgraph OdooServer["Odoo 19 CE Application Server (Python)"]
            direction TB
            WebController["Web Controllers<br>????????????????<br>• /website, /forum, /shop<br>• /ask_someone, /jobs"]
            APIController["JSON-RPC API Controllers<br>????????????????<br>• /api/v1/gpu/register<br>• /api/v1/dataset/export<br>• /api/v1/chatbot/invoke"]
            
            subgraph OdooModels["Odoo ORM Models (Business Logic)"]
                CoreModel["nettrades.core<br>????????????????<br>• Field qualification rules<br>• Voting weight config<br>• Auto-qualification by karma"]
                GoodAnswer["nettrades.good_answer<br>????????????????<br>• Vote collection<br>• Reputation decay (1% daily)<br>• FT dataset eligibility"]
                GPUAdmin["nettrades.gpu_admin<br>????????????????<br>• GPU node registry<br>• TEE/Edge device metadata<br>• Pool assignment (public/internal)"]
                JobMatching["nettrades.job_matching<br>????????????????<br>• CV parsing & scoring<br>• Candidate shortlist generation"]
                Proposals["nettrades.proposals<br>????????????????<br>• Freelancer skills matching<br>• Rate suggestions"]
                LeadScoring["nettrades.lead_scoring<br>????????????????<br>• Lead generation from external feeds<br>• Quality scoring"]
                AskSomeone["nettrades.ask_someone<br>????????????????<br>• Expert consultation sessions<br>• Stripe escrow management"]
                Chatbot["nettrades.chatbot<br>????????????????<br>• Conversation session state<br>• LangGraph request dispatcher"]
            end

            OdooCron["Scheduled Cron Jobs<br>????????????????<br>• _cron_decay_reputation()<br>• _cron_auto_qualify_by_karma()<br>• _cron_auto_adjust_weights()<br>• _cron_trigger_finetune()"]
        end

        subgraph LangGraphOrchestrator["LangGraph Orchestrator (FastAPI - Python)"]
            direction TB
            FastAPIApp["FastAPI Application<br>????????????????<br>• /invoke (async inference)<br>• /health (liveness)<br>• /metrics (Prometheus)"]
            
            subgraph SupervisorGraph["Supervisor Graph (src/core/supervisor.py)"]
                Classify["classify Node<br>????????????????<br>• Extracts last user message<br>• Detects image_base64<br>• LLM intent classification"]
                MedicalScreening["medical_screening Node<br>????????????????<br>• MAX_FOLLOWUP=3<br>• Asks clarifying medical/legal Qs"]
                Router["route Node<br>????????????????<br>• Dispatches intent to sub-agent<br>• Fallback to general LLM"]
            end

            subgraph SubAgents["Sub-Agents (src/core/agents/)"]
                RecruitmentAgent["Recruitment Agent<br>????????????????<br>• process_cv_match()"]
                FreelanceAgent["Freelance Agent<br>????????????????<br>• match_freelance_project()"]
                LeadGenAgent["Lead Gen Agent<br>????????????????<br>• generate_leads()"]
                GPUAgent["GPU Management Agent<br>????????????????<br>• manage_gpu_cluster()"]
                VisionAgent["Vision Agent<br>????????????????<br>• analyse(image_base64 + text)<br>• Calls VLM (Qwen2-VL/LLaVA)"]
                ActionAgent["Action Agent<br>????????????????<br>• plan_action() ? JSON plan<br>• dispatch() ? ROS 2 / MCP"]
                GeneralLLM["General LLM Fallback<br>????????????????<br>• Direct chat completion"]
            end

            Checkpointer["Durable Checkpointer<br>????????????????<br>• PostgresSaver<br>• Stores state snapshots on every node"]
        end

        subgraph GPUStackManager["GPUStack Manager (Go/Python)"]
            direction TB
            InferenceEngine["Inference Engine<br>????????????????<br>• OpenAI-compatible /v1 endpoint<br>• Dynamic model loading"]
            TokenMeter["Token Metering<br>????????????????<br>• Per-request token counting<br>• Usage billing integration"]
            WorkerPool["Worker Pool Manager<br>????????????????<br>• gVisor (public) / Docker (internal)<br>• Node lifecycle management"]
        end
    end

    %% ========================================================================
    %% 4. DATA & PERSISTENCE LAYER
    %% ========================================================================
    subgraph DataLayer["?? Data & Persistence Layer"]
        direction TB
        
        PostgreSQL["PostgreSQL 17 + pgvector (CNPG)<br>?????????????????????????????<br>• Odoo transactional data (business records)<br>• Vector embeddings (pgvector)<br>• LangGraph checkpoint blobs<br>• Full-text search indexes"]
        
        Valkey["Valkey 8.0 (Redis-compatible)<br>?????????????????????????????<br>• Odoo ORM session cache<br>• Odoo bus notifications (Pub/Sub)<br>• Rate limiting counters<br>• Temporary job locks"]
        
        Longhorn["Longhorn Distributed Storage<br>?????????????????????????????<br>• Fine-tuning datasets (JSONL)<br>• Trained model weights (GGUF/Safetensors)<br>• Data-Juicer intermediate artifacts<br>• Odoo filestore (CVs, images)"]
    end

    %% ========================================================================
    %% 5. AI/ML PIPELINE LAYER (FINE-TUNING & DATA OPS)
    %% ========================================================================
    subgraph MLPipeline["?? AI/ML Pipeline & Model Registry"]
        direction TB
        
        DataJuicer["Data-Juicer Pipeline<br>????????????????<br>• Quality filtering<br>• Deduplication<br>• Format transformation"]
        
        DEITA["DEITA Scorer<br>????????????????<br>• LLM-as-Judge scoring<br>• Response quality ranking<br>• Complexity assessment"]
        
        Unsloth["Unsloth/Axolotl Trainer<br>????????????????<br>• LoRA/QLoRA fine-tuning<br>• GRPO / DPO preference tuning<br>• 4-bit quantization (QLoRA)"]
        
        ModelRegistry["Model Registry<br>????????????????<br>• Versioned model storage<br>• Metadata tags (domain, score)<br>• Rollback capabilities"]
    end

    %% ========================================================================
    %% 6. EXTERNAL INTEGRATIONS
    %% ========================================================================
    subgraph External["?? External Integrations & Data Sources"]
        Stripe["Stripe API<br>????????????????<br>• Payment intents<br>• Escrow settlements<br>• Webhook callbacks"]
        LLMProviders["External LLM Providers<br>????????????????<br>• OpenAI / Anthropic / Cohere<br>• (Fallback when GPUStack is down)"]
        JobFeeds["External Job Boards<br>????????????????<br>• RSS / API feeds<br>• LinkedIn / Indeed / Upwork"]
    end

    %% ========================================================================
    %% 7. SECURITY & NETWORK FABRIC (LOGICAL OVERLAY)
    %% ========================================================================
    subgraph SecurityFabric["??? Security & Isolation Fabric"]
        WireGuard["WireGuard VPN Mesh<br>????????????????<br>• Hub-and-spoke topology<br>• Encrypted node-to-node traffic<br>• Dynamic IP endpoint handling"]
        gVisor["gVisor Sandbox<br>????????????????<br>• Syscall-level isolation<br>• Applied to public GPU worker pools"]
        RBAC["RBAC & Policy Engine<br>????????????????<br>• Odoo security groups<br>• Cilium Network Policies"]
    end

    %% ========================================================================
    %% 8. ORCHESTRATION & FOUNDATION
    %% ========================================================================
    subgraph Foundation["?? Orchestration & Foundation (Kubernetes Talos)"]
        K8s["Kubernetes Control Plane<br>????????????????<br>• Pod scheduling<br>• Service discovery (DNS)<br>• Horizontal Pod Autoscaling"]
        ArgoCD["Argo CD (GitOps)<br>????????????????<br>• Declarative manifests<br>• Auto-sync from Forgejo Git"]
        Cilium["Cilium CNI & Hubble<br>????????????????<br>• eBPF networking<br>• Network observability<br>• Security policies"]
    end

    %% ========================================================================
    %% 9. CONNECTIVITY & DATA FLOW ARROWS (LABELED)
    %% ========================================================================
    
    %% Access to Gateway
    Browser -->|"HTTPS / WebSocket"| Gateway
    APIClient -->|"HTTPS / JSON-RPC"| Gateway
    RoboticClient -->|"HTTPS / ROS 2 WebBridge"| Gateway

    %% Gateway to Services
    Gateway -->|"Routes / ? Odoo UI"| WebController
    Gateway -->|"Routes /api/v1/* ? Odoo API"| APIController
    Gateway -->|"Routes /invoke ? FastAPI"| FastAPIApp

    %% Odoo internal flow
    WebController -->|"Calls"| OdooModels
    APIController -->|"Calls"| OdooModels
    OdooModels -->|"Async HTTP Request"| Chatbot
    Chatbot -->|"POST /invoke with context"| FastAPIApp

    %% LangGraph Orchestration Flow
    FastAPIApp -->|"Executes"| SupervisorGraph
    SupervisorGraph --> Classify --> MedicalScreening --> Router
    Router -->|"intent: recruitment"| RecruitmentAgent
    Router -->|"intent: freelance"| FreelanceAgent
    Router -->|"intent: lead_gen"| LeadGenAgent
    Router -->|"intent: gpu_management"| GPUAgent
    Router -->|"intent: vision (has image)"| VisionAgent
    Router -->|"intent: action"| ActionAgent
    Router -->|"intent: general"| GeneralLLM

    %% Sub-agent dependencies
    RecruitmentAgent -->|"Reads/Updates"| JobMatching
    FreelanceAgent -->|"Reads/Updates"| Proposals
    LeadGenAgent -->|"Creates"| LeadScoring
    GPUAgent -->|"Reads/Updates"| GPUAdmin
    VisionAgent -->|"Calls"| InferenceEngine
    ActionAgent -->|"Sends JSON plan"| RoboticClient

    %% Inference flow
    GeneralLLM -->|"OpenAI-compatible API"| InferenceEngine
    VisionAgent -->|"OpenAI-compatible API + base64 image"| InferenceEngine
    GPUAgent -->|"Manages worker pool"| WorkerPool

    %% Data Persistence
    OdooModels -->|"SQL (psycopg2)"| PostgreSQL
    OdooModels -->|"Set/Get (redis-py)"| Valkey
    FastAPIApp -->|"Checkpoint (asyncpg)"| Checkpointer
    Checkpointer -->|"Read/Write blobs"| PostgreSQL
    GPUAdmin -->|"Node registration metadata"| PostgreSQL

    %% ML Pipeline Flow (Triggered by Odoo Cron)
    OdooCron -->|"export_to_jsonl()"| GoodAnswer
    GoodAnswer -->|"Writes dataset"| Longhorn
    Longhorn -->|"Reads dataset"| DataJuicer
    DataJuicer -->|"Cleaned data"| DEITA
    DEITA -->|"Scored data"| Unsloth
    Unsloth -->|"Produces adapter weights"| ModelRegistry
    ModelRegistry -->|"Stores final model"| Longhorn
    ModelRegistry -->|"Registers new model version"| InferenceEngine

    %% External Integrations Flow
    AskSomeone -->|"Stripe API (create payment/escrow)"| Stripe
    Stripe -->|"Webhook (payment.confirmed)"| APIController
    LeadScoring -->|"Periodic fetch"| JobFeeds
    GeneralLLM -->|"Fallback (if GPUStack unavailable)"| LLMProviders

    %% Security & Foundation Dependencies
    WorkerPool -->|"Runs inside"| gVisor
    GPUAgent -->|"Node-to-node encrypted tunnel"| WireGuard
    Cilium -->|"Enforces"| RBAC
    K8s -->|"Orchestrates"| OdooServer
    K8s -->|"Orchestrates"| LangGraphOrchestrator
    K8s -->|"Orchestrates"| GPUStackManager
    ArgoCD -->|"Deploys manifests to"| K8s

    %% ========================================================================
    %% 10. STYLE DEFINITIONS
    %% ========================================================================
    classDef access fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef gateway fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef app fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px;
    classDef data fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef ml fill:#fce4ec,stroke:#c62828,stroke-width:2px;
    classDef ext fill:#ede7f6,stroke:#4527a0,stroke-width:2px;
    classDef security fill:#ffebee,stroke:#b71c1c,stroke-width:2px;
    classDef foundation fill:#eceff1,stroke:#37474f,stroke-width:2px;

    class AccessLayer access;
    class Gateway gateway;
    class ApplicationLayer,OdooServer,LangGraphOrchestrator,GPUStackManager app;
    class DataLayer,PostgreSQL,Valkey,Longhorn data;
    class MLPipeline,DataJuicer,DEITA,Unsloth,ModelRegistry ml;
    class External,Stripe,LLMProviders,JobFeeds ext;
    class SecurityFabric,WireGuard,gVisor,RBAC security;
    class Foundation,K8s,ArgoCD,Cilium foundation;
