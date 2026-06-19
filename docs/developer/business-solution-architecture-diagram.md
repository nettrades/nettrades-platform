# Business Solution Architecture Diagram

## Detailed Narrative of the Business Solution Architecture
## 1. Access & Presentation Layer

The platform is accessed via a Web UI built on Odoo's website and portal, a Mobile PWA for on?the?go access, and an External API Gateway that exposes Odoo's JSON?RPC API and the LangGraph /invoke endpoint for programmatic integration.

## 2. AI Orchestration Layer (LangGraph)

This is the "brain" of the platform, handling all AI-driven workflows.

    Supervisor Agent (src/core/supervisor.py): The central orchestrator that:

        Classifies user intent using an LLM

        Screens medical/legal questions with up to 3 follow?up rounds

        Routes requests to the appropriate business sub?agent

    Business Sub?Agents (src/core/agents/):

        Recruitment Agent: Analyses CVs, matches candidates to jobs, and generates shortlists

        Freelance Agent: Matches freelancers to projects based on skills and availability

        Lead Gen Agent: Generates and scores leads from job postings and projects

        GPU Management Agent: Monitors GPU cluster health and manages node lifecycles

        Vision Agent: Processes image + text queries using a Vision-Language Model (VLM)

        Action Agent: Plans robotic actions and dispatches via ROS 2 / MCP

        General LLM: Fallback for general queries

    PostgresSaver Checkpointer: Saves state at every node to PostgreSQL, enabling crash recovery and workflow resumption.

## 3. Business Logic Layer (Odoo 19 CE)

The platform's business logic is encapsulated in Odoo 19 CE, with custom modules and third?party integrations.

Custom NETTRADES Modules (odoo-modules/):

    nettrades_core: Professional field configuration, qualification rules, voting weights, and karma management

    nettrades_good_answer: Good Answer voting, reputation management, and fine?tuning dataset pipeline

    nettrades_gpu_admin: GPU cluster dashboard, node registry, pool assignment, and token economics

    nettrades_gpustack_adapter: GPUStack API bridge for worker and token usage sync

    nettrades_ask_someone: Expert marketplace with Stripe escrow and live sessions

    nettrades_job_matching: AI-powered job search, matching, and one?click apply

    nettrades_proposals: Freelancer proposals and milestone payments

    nettrades_lead_scoring: AI-driven lead generation and CRM integration

    nettrades_chatbot: AI chatbot widget with Ask Someone integration

    nettrades_notifications: In?app notifications, reviews, and disputes

    nettrades_pwa: Progressive Web App manifest and service worker

Third-Party Modules (third-party/):

    Odoo 19 CE Core: CRM, Sales, Project, HR, Accounting, Website, eCommerce

    Apexive LLM Modules: llm, llm_pgvector, llm_knowledge, llm_assistant, llm_training

    MCP?Odoo Bridge: Enables AI agents to call Odoo functions and execute CRUD operations

## 4. Data & Persistence Layer

    PostgreSQL 18 + pgvector: Stores Odoo transactional data, vector embeddings for RAG, and LangGraph checkpoints.

    Valkey 8: Redis?compatible in?memory store for session caching, ORM cache, and bus notifications.

    Longhorn: Distributed block storage for Odoo filestore, fine?tuning datasets, and model weights.

## 5. Infrastructure & Security Layer

    Compute & Orchestration: Kubernetes on Talos Linux with Argo CD for GitOps.

    Networking & Security: Traefik reverse proxy with Let's Encrypt TLS, WireGuard for kernel?level network isolation, and gVisor for syscall?level container isolation of public GPU workloads.

    Monitoring & Observability: Prometheus for metrics collection and Grafana for dashboards.

## 6. Distributed GPU Infrastructure

    GPUStack Manager: Orchestrates GPU workers, provides an OpenAI?compatible inference engine, and meters token usage.

    GPU Pools:

        Internal Pool (Trusted): Docker runtime, multi?GPU vLLM, and Axolotl FSDP2 training over WireGuard mesh.

        Public Pool (Untrusted): gVisor runtime, single?GPU quantised inference, and hub?and?spoke WireGuard with hourly attestation.

## 7. Self-Improving AI Pipeline

The platform continuously improves its AI models through a closed?loop pipeline:

    Good Answer Vote: Users vote on helpful responses

    Export to JSONL: Feedback is exported from Odoo

    Data?Juicer: Quality filtering, deduplication, and PII removal

    DEITA Scorer: LLM?as?Judge scores complexity and quality

    Unsloth/Axolotl Training: LoRA/QLoRA fine?tuning with 4?bit quantization

    Model Registry: Versioned storage and registration with GPUStack

    LangGraph Agent: Uses the improved model for future inference

## 8. External Integrations

    Stripe API: Payment processing and escrow for consultations

    External LLM Providers: OpenAI / Anthropic fallback when GPUStack is unavailable

    Forgejo Git: Self?hosted Git for project collaboration and CI/CD

This architecture enables NETTRADES.AI to function as a self?improving, autonomous enterprise platform that connects companies, freelancers, job?seekers, researchers, partners, and customers through AI?powered matching, a distributed GPU marketplace, and a continuous fine?tuning pipeline.

---

## Business Solution Architecture Diagram

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        Web["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        ChatWidget["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
    end

    subgraph Integration["Integration & Orchestration Layer"]
        Supervisor["LangGraph Supervisor Agent"]
        Agents["Specialised Sub-Agents"]
        MCP["MCP-Odoo Bridge"]
    end

    subgraph AI["AI Inference & Training Layer"]
        Router["Provider Router Logic"]
        GPUStack["GPUStack Server(s)"]
        Workers["GPUStack Workers (vLLM, llama.cpp)"]
        FineTune["Fine-Tuning Jobs (Axolotl/Unsloth)"]
        External["External LLM APIs"]
    end

    subgraph Core["Core Odoo 19 CE Layer"]
        Odoo["Odoo 19 CE Instance"]
        Modules["Custom NETTRADES Modules"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL 18 + pgvector"]
        Valkey["Valkey 8"]
        S3["MinIO / S3 (Models & Backups)"]
    end

    subgraph Security["Security & Network Layer"]
        WG["WireGuard Mesh/Hub-Spoke"]
        gVisor["gVisor Container Runtime"]
        TEE["TEE / Confidential Computing"]
    end

    Frontend --> Core
    Frontend -->|Direct API Call| Integration
    Integration --> MCP --> Core
    Integration --> Router --> AI
    AI --> GPUStack --> Workers
    AI --> FineTune
    AI --> External
    Core --> Data
    Core -. Orchestrates .-> Security
    Security -. Secures .-> AI