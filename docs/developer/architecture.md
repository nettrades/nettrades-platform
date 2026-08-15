# Architecture Overview

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## System Architecture Diagram

```mermaid

graph TB
    subgraph Frontend["Frontend Layer"]
        Web["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        NettradesUI["Nettrades-UI (Talks to Odoo for Authentication via Odoo-Proxy) / AI Chat"]
        Llamacpp["Llama.CPP-UI / AI Chat"]
        VSCode["VS Code Extension"]
        Launcher["NETTRADES Launcher (Electron)"]
    end

    subgraph Integration["Integration & Orchestration Layer"]
        Supervisor["LangGraph Supervisor Agent"]
        Agents["Specialised Sub-Agents"]
        MCP["Odoo-Proxy Bridge"]
        Bridge["nettrades_bridge"]
    end

    subgraph AI["AI Inference & Training Layer"]
        Router["Provider Router Logic"]
        Dynamo["NVIDIA Dynamo Server(s)"]
        vLLM["vLLM Workers (GPU)"]
        llama_cpp["llama.cpp (CPU)"]
        llama_cppfallback["llama.cpp (CPU Fallback)"]
        FineTune["Fine-Tuning Jobs (Unsloth/Axolotl)"]
        External["External LLM APIs (OpenAI, Anthropic)"]
    end

    subgraph Core["Core Odoo 19 CE Layer"]
        Odoo["Odoo 19 CE Instance"]
        Modules["Custom NETTRADES Modules"]
        Fairness["nettrades_fairness"]
        SelfImproving["Self-Improving Modules"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL 17 + pgvector"]
        Valkey["Valkey 8"]
        S3["MinIO / S3 (Models & Backups)"]
    end

    subgraph Security["Security & Network Layer"]
        WG["WireGuard Mesh/Hub-Spoke"]
        gVisor["gVisor Container Runtime (CPU Services)"]
        TEE["TEE / Confidential Computing"]
    end

    Frontend --> Core
    Frontend -->|Direct API Call| Integration
    Integration --> MCP --> Core
    Integration --> Router --> AI
    AI --> Dynamo --> vLLM
    AI --> Dynamo --> llama_cpp
    AI --> llama_cppfallback
    AI --> FineTune
    AI --> External
    Core --> Data
    Core -. Orchestrates .-> Security
    Security -. Secures .-> AI
    Fairness --> Data
    SelfImproving --> Data

```

## Bridge Architecture (Hub-and-Spoke)

```mermaid
graph TB
    subgraph Client["Client Company (nettrades.com)"]
        Odoo["Odoo 19 CE"]
        LocalAgents["Local LangGraph Agents"]
        Bridge["nettrades_bridge"]
    end

    subgraph Cloud["NETTRADES.AI (The Hub)"]
        CentralAgents["Global LangGraph Agents"]
        GPU["Global GPU Marketplace"]
        Talent["Global Talent Pool"]
    end

    Odoo --> Bridge
    Bridge -->|"Internal (default)"| LocalAgents
    Bridge -->|"Remote (when needed)"| CentralAgents
    CentralAgents --> Talent
    CentralAgents --> GPU

```


## Routing Decision Engine

The bridge module (`nettrades_bridge`) provides a configurable routing engine:

```mermaid

graph TD
    Request["Incoming Request"] --> GetRoute["get_route_for_request()"]
    
    GetRoute --> CheckMode["Check Routing Mode"]
    
    CheckMode -->|local_only| Local["Route to Local"]
    CheckMode -->|remote_only| Remote["Route to Remote"]
    CheckMode -->|hybrid| Hybrid["Try Local, Fallback Remote"]
    CheckMode -->|hybrid_remote_first| HybridRemote["Try Remote, Fallback Local"]
    CheckMode -->|auto| Auto["AI Agent Decides"]
    
    Local --> DynamoCheck["Is Dynamo Healthy?"]
    DynamoCheck -->|Yes| DynamoLB["Dynamo Load Balancing"]
    DynamoCheck -->|No| Llama["llama.cpp (CPU)"]
    
    DynamoLB --> RoundRobin["Round Robin"]
    DynamoLB --> Weighted["Weighted"]
    DynamoLB --> Random["Random"]
    DynamoLB --> Priority["Priority"]
    
    Remote --> Marketplace["GPU Marketplace"]
    Remote --> External["External API (OpenAI/Anthropic)"]
    
    Hybrid --> LocalCheck["Is Local Available?"]
    LocalCheck -->|Yes| Local
    LocalCheck -->|No| Remote
    
    HybridRemote --> RemoteCheck["Is Remote Available?"]
    RemoteCheck -->|Yes| Remote
    RemoteCheck -->|No| Local
    
    Auto --> AgentDecision["LangGraph Agent Decides"]
    AgentDecision --> Local
    AgentDecision --> Remote

```

## Self-Improving Loop (MAPE)

```mermaid
graph TB
    subgraph Monitor["Monitor Phase"]
        GA["Good Answer Votes"]
        ES["Expert Sessions"]
        LI["LangGraph Interactions"]
        ROS["ROS 2 / Robotics"]
        GM["GPU Metrics"]

        GA --> DC1["data.episode"]
        ES --> DC1
        LI --> DC1
        ROS --> DC1
        GM --> DC2["data.metric"]
    end

    subgraph Analyze["Analyze Phase"]
        DC1 --> QE["Quality Evaluation"]
        DC2 --> SE["Success Rate"]
        DC1 --> VE["Volume Evaluation"]
        DC1 --> EE["Edge Case Detection"]

        QE --> T["Trigger Fired?"]
        SE --> T
        VE --> T
        EE --> T
        Manual["Manual Trigger"] --> T
    end

    subgraph Plan["Plan Phase"]
        T -->|Yes| Dataset["Dataset Creation"]
        Dataset --> DJ["Data-Juicer"]
        DJ --> DEITA["DEITA Scoring"]
        DEITA --> Training["Unsloth/Axolotl"]
        Training --> Model["Fine-tuned Model"]
    end

    subgraph Execute["Execute Phase"]
        Model --> Deploy["NVIDIA Dynamo Deployment"]
        Deploy --> A["LangGraph Agents"]
        Deploy --> B["Odoo Assistants"]
        Deploy --> C["ROS 2 / Robotics"]

        A --> Monitor
        B --> Monitor
        C --> Monitor
    end

```

## Fairness Architecture

```mermaid
graph TB
    subgraph Evaluation["Evaluation Phase"]
        Response["AI Response"] --> Judge["LLM-as-Judge"]
        Judge --> Rationality["Rationality Score"]
        Judge --> Bias["Bias Score"]
        Rationality --> Threshold{"Threshold Check"}
        Bias --> Threshold
    end

    subgraph Action["Action Phase"]
        Threshold -->|Pass| Approve["Approve Response"]
        Threshold -->|Fail| Reject["Reject/Fallback Response"]
        Approve --> Log["Log to Database"]
        Reject --> Log
        Log --> Report["Generate Reports"]
    end

    subgraph Feedback["Feedback Loop"]
        Log --> Analytics["Analytics"]
        Analytics --> ModelUpdate["Update Thresholds"]
        ModelUpdate --> Judge
    end

```

## Good Answer -> Fine-Tuning Loop

```mermaid
graph LR
    Vote[(good_answer_vote)] --> Collector[Data Collector cron]
    Collector --> Exporter[Exporter to JSONL]
    Exporter --> Launcher[Direct LangGraph call]
    Launcher --> TrainingJob[Dynamo Training Job]
    TrainingJob --> Unsloth[Unsloth single GPU]
    TrainingJob --> Axolotl[Axolotl FSDP2 multi-GPU]
    Unsloth --> FineTuned[Fine-tuned model]
    Axolotl --> FineTuned
    FineTuned --> ProviderModel[llm.provider in Odoo]
    ProviderModel --> Field[(nettrades.field)]

```

## Inference Architecture


The platform uses a layered inference architecture with automatic fallback:

| Priority | Backend | Description |
|---------|-------------|---------|
| 1 | 	**NVIDIA Dynamo with vLLM** | Production-grade distributed inference, GPU-accelerated |
| 2 | 	**NVIDIA Dynamo (CPU mode)** | Runs on CPU when GPU unavailable |
| 3 | 	**NVIDIA Dynamo with llama.cpp** | Production-grade distributed inference, CPU-accelerated |
| 4 | 	**llama.cpp** | Zero-dependency CPU fallback, runs on port 8080 |


## Security Architecture

```mermaid

graph TB
    subgraph Layer1["Layer 1: Launcher Security"]
        L1A["contextIsolation enabled"]
        L1B["preload.js exposes safe APIs"]
        L1C["Auto-update with signature verification"]
    end
    
    subgraph Layer2["Layer 2: Network Security"]
        L2A["WireGuard VPN Mesh/Hub-Spoke"]
        L2B["Traefik with Let's Encrypt SSL"]
        L2C["mDNS only within trusted network"]
        L2D["STUN/TURN for NAT traversal (optional)"]
    end
    
    subgraph Layer3["Layer 3: Container Security"]
        L3A["gVisor runtime for strong isolation"]
        L3B["no-new-privileges:true on all containers"]
        L3C["seccomp profiles"]
    end
    
    subgraph Layer4["Layer 4: Application Security"]
        L4A["Odoo RBAC (roles, groups, permissions)"]
        L4B["API key authentication"]
        L4C["Audit logging"]
        L4D["Rate limiting"]
    end
    
    Layer1 --> Layer2 --> Layer3 --> Layer4
    
```

## Technology Stack

		
| Component | Version | Purpose |
|---------|-------------|---------|
| **Odoo** | 19.0 CE | ERP, marketplace, CRM, HR, Projects, Accounting |
| **PostgreSQL + pgvector** | 17 | Business data, vector embeddings, LangGraph checkpoints |
| **Valkey** | 8 | Session storage, ORM cache, bus notifications |
| **LangGraph** | >=1.2.0 | Multi-agent orchestration, durable execution |
| **NVIDIA Dynamo** | 1.2.1 | Distributed inference engine with vLLM and llama.cpp |
| **vLLM** | Latest | GPU-accelerated inference |
| **llama.cpp** | Latest | CPU inference fallback |
| **Traefik** | v3.6.13 | Reverse proxy with Let's Encrypt SSL |
| **WireGuard** | kernel | VPN mesh for secure node-to-node communication |
| **gVisor** | Latest | Container isolation for CPU services |
| **Prometheus** | Latest | Metrics collection and monitoring |
| **Grafana** | Latest | Visualisation and dashboards |
| **mDNS/Avahi** | Latest | Automatic node discovery on local networks |


## Security Architecture


| Layer | Technology | Purpose |
|---------|-------------|---------|
| **Launcher Security** | contextIsolation, preload.js | Secure IPC, auto-update with verification |
| **Network Security** | WireGuard, Traefik (Let's Encrypt), mDNS | VPN mesh, SSL, trusted network discovery |
| **Container Security** | gVisor (CPU services), no-new-privileges, seccomp | Strong isolation, reduced attack surface |
| **Application Security** | Odoo RBAC, API keys, audit logging | Access control, authentication, compliance |


## Component Descriptions


### 1. LangGraph Supervisor (src/core/supervisor.py)


The supervisor is the central orchestrator that classifies user intents and routes them to the correct sub-agent.


#### Key Functions:


| Function | Purpose |
|----------|---------|
| `build_supervisor()` | 	Constructs the complete LangGraph workflow |
| `classify()` | 	Classifies user intent (recruitment, freelance, lead_gen, gpu_management, medical, legal, action, vision, general) |
| `medical_screening()` | 	Conducts multi-round screening for medical/legal questions |
| `route()` | 	Dispatches to the appropriate sub-agent |


### 2. FastAPI Application (src/core/app.py)


The FastAPI application is the main entry point for the LangGraph service.


#### Endpoints:


| Endpoint | Method | Purpose | Authentication |
|----------|---------|--------|--------|
| `/health` | 	GET |	liveness probe for container orchestration | None |
| `/metrics` | 	GET |	Prometheus metrics endpoint | None |
| `/invoke` | 	POST |	Main inference endpoint	| API Key (header) (authenticated)|
| `/assistants` |  |		list available assistants (for agent-chat-ui) |	 |
| `/threads` | 	 |	create a new conversation thread (for agent-chat-ui) |	 |
| `/threads/{thread_id}/state` |  |		get thread state (for agent-chat-ui) |	 |
| `/threads/{thread_id}/runs` |  |		run a thread (for agent-chat-ui) |	 |
| `/runs   ` | 	 |	create a new run and return assistant response |	 |



### 3. Sub-Agents (src/core/agents/)

The sub-agents are LangGraph sub-graphs that handle specific business domains.

| Agent | Location |
|----------|--------|
| Action Agent |  `src/core/agents/action_agent.py` |
| Ask Someone Agent |  `src/core/agents/ask_someone_agent.py` |
| Freelance Agent | `src/agent/freelance_agent.py` |
| Good Answer Agent |  `src/core/agents/good_answer_agent.py` |
| GPU Management Agent | `src/core/agents/gpu_management_agent.py` |
| GPU Marketplace Agent | `src/core/agents/gpu_marketplace_agent.py` |
| Inference Tools Agent |  `src/core/agents/inference_tools.py` |
| Lead Gen Agent | `src/agent/lead_gen_agent.py` |
| Recruitment Agent | `src/agent/recruitment_agent.py` |
| Vision Agent |  `src/core/agents/` |


### 4. Distributed GPU Agent (src/agent/gpu_agent.py)


The GPU agent runs on every GPU node in the cluster.


#### Responsibilities:

* Auto-install WireGuard

* Generate hardware-bound node ID (TPM EK or MAC hash)

* Detect GPUs via nvidia-smi

* Detect TEE capabilities

* Detect edge devices (Jetson, Raspberry Pi, Coral TPU)

* Register with Odoo

* Bring up WireGuard

* Start NVIDIA Dynamo worker

* Start DNS watchdog

* Periodically refresh NVIDIA Dynamo token


### 5. Fairness Module (odoo-modules/nettrades_fairness/)


The fairness module provides comprehensive bias detection and rationality evaluation.


#### Key Components:

| Component | Purpose |
|----------|---------|
| `nettrades.fairness.config` | Global and field-specific configuration |
| `nettrades.fairness.evaluator` | LLM-as-Judge evaluation service |
| `nettrades.fairness.audit` | Audit log for all evaluations |
| `nettrades.fairness.flag` | Human review workflow for flagged responses |
| `nettrades.fairness.metrics` | Fairness metrics calculator |


##### Configuration:
		

| Setting | Default | Description |
|----------|---------|------------|
| `rationality_evaluation_enabled` | True	Enable rationality evaluation |
| `bias_detection_enabled` | True	Enable bias detection |
| `auto_flag_for_review` | True | Auto-flag low-quality responses |
| `auto_filter_training` | True | Filter training data |
| `rationality_threshold` | 7.0 | Minimum rationality score |
| `bias_threshold` | 3.0 | Maximum bias score |
| `evaluation_model` | gpt-4o-mini | LLM judge model |


#### Technology Stack
			
| Component | Version | License | Purpose |
|----------|---------|--------|--------|
| `Odoo` | 19.0 CE` | LGPL-3.0 | 	ERP, marketplace, CRM, HR, Projects, Accounting |
| `PostgreSQL + pgvector` | 18.1 (via CNPG) | PostgreSQL License | Business data, vector embeddings, LangGraph checkpoints |
| `Valkey` | 	8-alpine | BSD-3-Clause | Session storage, ORM cache, bus notifications |
| `LangGraph` | ?1.2.0 | MIT | 	Multi-agent orchestration, durable execution |
| `LangGraph Checkpoint Postgres` | ?3.0.3 | MIT | Durable checkpoint storage in PostgreSQL |
| `NVIDIA Dynamo` | 1.3.1 | Apache-2.0 | GPU manager, inference engine |
| `llama.cpp` | server-cpu/server-cuda | MIT | 	CPU inference fallback |
| `Unsloth (core)` | 2026.5.2 | Apache-2.0 | Single-GPU fine-tuning |
| `Axolotl` | 0.16.1+ | Apache-2.0 | Multi-GPU fine-tuning with FSDP2 |
| `WireGuard` | kernel module | GPL-2.0 | Kernel-level network isolation |
| `gVisor` | release-20260420.0 | Apache-2.0 | 	Syscall-level container isolation |


### Next Steps


[Building LangGraph Agents](building-agents.md)

[Building Odoo Modules](building-odoo-modules.md)

[API Reference](api-reference.md)

[Roadmap](roadmap.md)

[NVIDIA Dynamo Integration](nvidia-dynamo-integration.md) – Dynamo integration guide

[Bridge Architecture](bridge-architecture.md) – Understanding the bridge

[Building Agents](building-agents.md) – Create custom LangGraph agents

[API Reference](api-reference.md) – API documentation

[Troubleshooting](troubleshooting.md) – Common issues and solutions