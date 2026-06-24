# Architecture Overview

This document provides a comprehensive overview of the NETTRADES.AI platform architecture.

---

## System Architecture Diagram

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
        Bridge["nettrades_bridge"]
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
        Fairness["nettrades_fairness"]
        SelfImproving["Self-Improving Modules"]
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
        Model --> Deploy["GPUStack Deployment"]
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
    end

    subgraph Thresholds["Threshold Check"]
        Rationality --> RCheck{"Score >= 7?"}
        Bias --> BCheck{"Score <= 3?"}
        RCheck -->|No| Flag["Flag for Review"]
        BCheck -->|No| Flag
        RCheck -->|Yes| Pass["Pass"]
        BCheck -->|Yes| Pass
    end

    subgraph Actions["Automated Actions"]
        Pass --> Training["Include in Training"]
        Flag --> Review["Human Review"]
        Review -->|Accepted| Training
        Review -->|Rejected| Discard["Discard"]
    end

    Training --> FT["Fine-Tuning Pipeline"]

```

## Component Descriptions
### 1. LangGraph Supervisor (src/core/supervisor.py)

The supervisor is the central orchestrator that classifies user intents and routes them to the correct sub-agent.

#### Key Functions:


| Function | Purpose | Status |
|----------|---------|--------|
| `build_supervisor()` | 	Constructs the complete LangGraph workflow |	? Complete |
| `classify()` | 	Classifies user intent (recruitment, freelance, lead_gen, gpu_management, medical, legal, action, vision, general) |	? Complete |
| `medical_screening()` | 	Conducts multi-round screening for medical/legal questions |	?? Needs Fix: No conditional edge to loop back |
| `route()` | 	Dispatches to the appropriate sub-agent |	? Complete |

### 2. FastAPI Application (src/core/app.py)

The FastAPI application is the main entry point for the LangGraph service.

#### Endpoints:


| Endpoint | Method | Purpose | Authentication |
|----------|---------|--------|--------|
| `/health` | 	GET |	Liveness/readiness probe | None |
| `/metrics` | 	GET |	Prometheus metrics | None |
| `/invoke` | 	POST |	Main inference endpoint	| API Key (header) |

### 3. Sub-Agents (src/core/agents/)

The sub-agents are LangGraph sub-graphs that handle specific business domains.

| Agent | Status | Location |
|----------|---------|--------|
| Recruitment Agent | ?? PLACEHOLDER | `src/agent/recruitment_agent.py` (real code) |
| Freelance Agent | ?? PLACEHOLDER | `src/agent/freelance_agent.py` (real code) |
| Lead Gen Agent | ?? PLACEHOLDER | `src/agent/lead_gen_agent.py` (real code) |
| GPU Management Agent | ?? PLACEHOLDER| `src/agent/gpu_management_agent.py` (real code) |
| Vision Agent | ?? PLACEHOLDER	| Not implemented |
| Action Agent | ?? PLACEHOLDER	| Not implemented |

### 4. Distributed GPU Agent (src/agent/agent.py)

The GPU agent runs on every GPU node in the cluster.

#### Responsibilities:

* Auto-install WireGuard

* Generate hardware-bound node ID (TPM EK or MAC hash)

* Detect GPUs via nvidia-smi

* Detect TEE capabilities

* Detect edge devices (Jetson, Raspberry Pi, Coral TPU)

* Register with Odoo

* Bring up WireGuard

* Start GPUStack worker

* Start DNS watchdog

* Periodically refresh GPUStack token

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
| `GPUStack` | v2.1.2 | Apache-2.0 | GPU cluster manager, inference engine, token metering |
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
