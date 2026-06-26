<!--
=============================================================================
NETTRADES.AI – Autonomous Enterprise Platform
=============================================================================
FILE: README.md

PURPOSE:
  This is the main landing page for the NETTRADES platform on GitHub.
  It provides a comprehensive overview of the project, its architecture,
  technology stack, and links to all documentation.

  The README is designed to be:
  - Self-contained – gives a complete picture of the project
  - Navigable – clear sections with links to deeper documentation
  - Professional – follows the patterns of leading open-source projects
  - Up-to-date – reflects the latest architecture and modules

=============================================================================
-->

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/nettrades-banner-dark.png">
    <img src="logo.jpg" alt="NETTRADES.AI Banner" width="100%">
  </picture>
</p>

<h1 align="center">⚡ NETTRADES.AI</h1>
<p align="center">
  <strong>Autonomous Enterprise Platform · AI Agents · GPU Marketplace · Self-Improving AI</strong>
</p>

<p align="center">
  <!--
  ============================================================================
  BADGES – Social proof layer that increases perceived quality by 40%+.
  Follows the pattern used by Kubernetes, Argo CD, and Odoo.
  ============================================================================
  -->
  <a href="https://github.com/nettrades/nettrades-platform/blob/main/LICENSE.txt">
    <img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/releases">
    <img src="https://img.shields.io/github/v/release/nettrades/nettrades-platform?sort=semver" alt="GitHub release (latest SemVer)">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/actions">
    <img src="https://github.com/nettrades/nettrades-platform/actions/workflows/ci-cd.yml/badge.svg" alt="CI/CD">
  </a>
  <a href="https://codecov.io/gh/nettrades/nettrades-platform">
    <img src="https://codecov.io/gh/nettrades/nettrades-platform/branch/main/graph/badge.svg" alt="codecov">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/issues">
    <img src="https://goreportcard.com/badge/github.com/nettrades/nettrades-platform" alt="Go Report Card">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/stargazers">
    <img src="https://img.shields.io/github/stars/nettrades/nettrades-platform?style=social" alt="GitHub Stars">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/issues">
    <img src="https://img.shields.io/github/issues/nettrades/nettrades-platform" alt="GitHub Issues">
  </a>
  <a href="https://github.com/nettrades/nettrades-platform/pulls">
    <img src="https://img.shields.io/github/issues-pr/nettrades/nettrades-platform" alt="GitHub Pull Requests">
  </a>
</p>

<p align="center">
  <a href="#-what-is-nettrades">What is NETTRADES?</a> •
  <a href="#-key-features">Features</a> •
  <a href="#-architecture-overview">Architecture</a> •
  <a href="#-self-improving-ai-loop">Self-Improving Loop</a> •
  <a href="#-technology-stack">Tech Stack</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-documentation">Docs</a> •
  <a href="#-community--support">Community</a> •
  <a href="#-contributing">Contributing</a>
</p>

---

[![License](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://opensource.org/licenses/AGPL-3.0)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-brightgreen.svg)](https://nettrades.github.io/nettrades-platform/)
[![GitHub Stars](https://img.shields.io/github/stars/nettrades/nettrades-platform)](https://github.com/nettrades/nettrades-platform/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/nettrades/nettrades-platform)](https://github.com/nettrades/nettrades-platform/issues)

## What is NETTRADES?

**NETTRADES is an open-source, autonomous enterprise platform** that connects companies, freelancers, job-seekers, researchers, partners and customers. It combines:

- **AI-powered job matching & freelancing** – LangGraph agents analyse CVs, job postings, and projects, automatically creating leads. It combines the functionalities of LinkedIn, Fiverr, Upwork, and Freelancer with AI Matching and Git Collaboration.
- **Distributed GPU marketplace** – Companies and freelancers can share idle GPUs to run inference and fine-tuning, earning tokens.
- **Expert marketplace “Ask Someone”** – Users can request paid help from verified professionals with Stripe escrow.
- **Self-improving AI – A “Good Answer”** voting system feeds a fine-tuning pipeline (Unsloth / Axolotl) that continuously improves field-specific models.
- **Autonomous administration** – GPU health watchdog, reputation decay, utilisation alerts, and automatic Karma-based qualification.
- **Multimodal & robotics support** – Optional VLM, VLA, ROS 2, IoT/edge-device features, all controllable via admin toggles.
- **Transaction control and error handling** – Odoo ACID transactions + LangGraph checkpointing.

🌐 Hub-and-Spoke Architecture** – Companies run the open-source client software locally for internal operations which seamlessly calls `NETTRADES.AI` for external recruitment, GPU overflow and global services.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **🤖 Agentic AI** | [LangGraph-based](docs/developer/LangGraph-Agent-State-Machine-Diagram.md) multi-agent system for recruitment, freelancing, lead generation, GPU management, vision, and action. |
| **🖥️ [GPU Marketplace](docs/developer/distributed-gpu-network-trusted-vs-untrusted.md)** | Distributed GPU sharing with token-based economy. Earn tokens by sharing idle GPUs; spend tokens on inference and fine-tuning. |
| **🔄 [Self-Improving AI](docs/developer/self-improving.md)** | “Good Answer” voting + Unsloth/Axolotl fine-tuning pipeline. Models continuously improve from user feedback. |
| **🧠 Vision-Language-Action** | VLM (Vision-Language Models) and VLA (Vision-Language-Action) support for multimodal and robotics applications. |
| **🔌 [Hub-and-Spoke Routing](docs/developer/bridge-architecture.md)** | `nettrades_bridge` module routes requests between local and remote brains based on intent, company policy, and GPU capacity. |
| **📊 Autonomous Administration** | GPU health watchdog, reputation decay, utilisation alerts, automatic Karma-based qualification. |
| **💬 Expert Marketplace** | “Ask Someone” – paid expert consultations with Stripe escrow. |
| **🔐 Secure & Sovereign** | WireGuard VPN, gVisor isolation, and full on-premise deployment options. |
| **📱 Mobile PWA** | Progressive Web App with offline support. |
| **🔗 [Git Collaboration](docs/operations/deployment-perspective-CICD-pipeline-diagram.md)** | Forgejo Git integration for project collaboration. |

---

## 🏗️ Architecture Overview

### 1. High-Level System Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        Web["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        ChatWidget["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
    end

    subgraph Ingress["Ingress / Reverse Proxy"]
        Traefik["Traefik"]
    end

    subgraph Integration["Orchestration Layer (LangGraph)"]
        Supervisor["Supervisor Agent"]
        Agents["Sub-Agents"]
        MCP["MCP-Odoo Bridge"]
        Bridge["nettrades_bridge"]
    end

    subgraph SelfImproving["Self-Improving System Layer"]
        DataCollection["nettrades_data_collection\nMonitor Phase"]
        Trigger["nettrades_trigger\nAnalyze Phase"]
        Loop["nettrades_loop\nPlan + Execute Phases"]
        Config["nettrades_self_improving_config\nAdministration UI"]
    end

    subgraph Training["AI Inference & Training Layer"]
        GPUStack["GPUStack"]
        Workers["GPU Workers\n(vLLM, llama.cpp)"]
        FineTune["Fine-Tuning Jobs\n(Unsloth / Axolotl)"]
        External["External LLM APIs"]
    end

    subgraph Core["Core Layer (Odoo 19 CE)"]
        Odoo["Odoo 19 CE"]
        Modules["Custom Odoo Modules"]
        Queue["OCA queue_job"]
        Payments["OCA payment_stripe"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL + pgvector"]
        Valkey["Valkey 8"]
        S3["MinIO / S3"]
    end

    subgraph K8s["Kubernetes Cluster (Talos Linux)"]
        Cilium["Cilium CNI"]
        Longhorn["Longhorn Storage"]
        MetalLB["MetalLB"]
        certmgr["cert-manager"]
        CloudNativePG["CloudNativePG"]
        GPUOp["NVIDIA GPU Operator"]
    end

    subgraph GitOps["GitOps"]
        Forgejo["Forgejo"]
        ArgoCD["Argo CD"]
    end

    subgraph Monitoring["Monitoring"]
        Prometheus["Prometheus"]
        Grafana["Grafana"]
    end

    Frontend --> Traefik --> Core
    Integration --> SelfImproving --> Training
    Training --> GPUStack --> Workers
    Training --> FineTune
    Core --> Data
    K8s --> Core
    K8s --> Data
    GitOps --> K8s
    Monitoring --> K8s
    
```


Detailed architecture diagrams are available in the [docs/developer/](docs/developer/index.md) folder.

### 2. The Hub-and-Spoke Model

NETTRADES uses a hub-and-spoke architecture to distribute load, preserve data sovereignty, and enable seamless scaling. Each spoke (company) runs its own client instance of the software for internal operations, while the hub (NETTRADES.AI) provides global services like talent discovery, GPU overflow, and the self-improving loop.

Companies can use `Local Internal Shell` internally for their operations and connect to `NETTRADES.AI` when they need external talent, researchers, partners, or additional GPU capacity.

`Local Internal Shell (Self-hosted, LGPL-3.0) `
                                                
• Internal job adverts and collaboration 
• CRM, ERP, eCommerce   
• Local GPU inferencing on your own hardware 
• Agentic AI for internal operations  
• Fine-tune AI on your internal data 


`NETTRADES.AI (The Brain) (Cloud-based, Commercial)`
                                      
• Global talent pool (external recruitment)
• Global GPU marketplace    
• Central inference and fine-tuning  
• Self-improving AI pipeline    

```mermaid

graph TB
    subgraph Hub["🌐 NETTRADES.AI (The Hub)"]
        GlobalTalent["Global Talent Pool"]
        GlobalGPU["Global GPU Marketplace"]
        GlobalModels["Global Self-Improving Models"]
        CentralBridge["Central Bridge Router"]
    end

    subgraph Spoke1["🏢 Company A (Spoke)"]
        LocalOdoo1["Local Odoo 19 CE"]
        LocalLangGraph1["Local LangGraph Agents"]
        LocalGPU1["Local GPUStack"]
        LocalBridge1["nettrades_bridge (Local Router)"]
        LocalData1["Local PostgreSQL + pgvector"]
        LocalValkey1["Local Valkey"]
    end

    subgraph Spoke2["🏢 Company B (Spoke)"]
        LocalOdoo2["Local Odoo 19 CE"]
        LocalLangGraph2["Local LangGraph Agents"]
        LocalGPU2["Local GPUStack"]
        LocalBridge2["nettrades_bridge (Local Router)"]
        LocalData2["Local PostgreSQL + pgvector"]
        LocalValkey2["Local Valkey"]
    end

    subgraph SpokeN["🏢 Company N (Spoke)"]
        LocalOdooN["Local Odoo 19 CE"]
        LocalLangGraphN["Local LangGraph Agents"]
        LocalGPUN["Local GPUStack"]
        LocalBridgeN["nettrades_bridge (Local Router)"]
        LocalDataN["Local PostgreSQL + pgvector"]
        LocalValkeyN["Local Valkey"]
    end

    LocalBridge1 -->|"Internal Ops"| LocalLangGraph1
    LocalBridge1 -->|"External Talent / GPU"| CentralBridge
    LocalBridge2 -->|"Internal Ops"| LocalLangGraph2
    LocalBridge2 -->|"External Talent / GPU"| CentralBridge
    LocalBridgeN -->|"Internal Ops"| LocalLangGraphN
    LocalBridgeN -->|"External Talent / GPU"| CentralBridge

    CentralBridge --> GlobalTalent
    CentralBridge --> GlobalGPU
    CentralBridge --> GlobalModels

    GlobalModels -->|"Pushes model updates"| LocalBridge1
    GlobalModels -->|"Pushes model updates"| LocalBridge2
    GlobalModels -->|"Pushes model updates"| LocalBridgeN

```

### Routing Logic:

```mermaid

flowchart TD
    A[Incoming Request] --> B{Intent?}
    B -->|Recruitment / Freelance| C{Local Talent Available?}
    C -->|Yes| D[Process Locally]
    C -->|No| E[Route to Hub]
    B -->|GPU| F{Local GPU < Threshold?}
    F -->|Yes| G[Process Locally]
    F -->|No| H[Route to Hub for Overflow]
    B -->|Vision / Action| I{Feature Flag?}
    I -->|Local| J[Process Locally]
    I -->|Remote| K[Route to Hub]
    D --> L[Return Response]
    E --> L
    G --> L
    H --> L
    J --> L
    K --> L

```

### 3. Self-Improving AI Loop

The platform continuously learns from user interactions and improves its models. This closed-loop system is the engine of NETTRADES’ self-improvement capability.

```mermaid

graph TD
    subgraph Monitor["1. MONITOR (nettrades_data_collection)"]
        A1["User Interactions"] --> A2["LangGraph Agents"]
        A2 --> A3["data.episode"]
        A3 --> A4["Quality Score"]
        A3 --> A5["Edge Case Detection"]
    end

    subgraph Analyze["2. ANALYZE (nettrades_trigger)"]
        B1["Trigger Evaluation"] --> B2{"Quality Drop?"}
        B2 -->|Yes| B3["Trigger Fired"]
        B2 -->|No| B4{"Data Volume?"}
        B4 -->|Yes| B3
        B4 -->|No| B5["Wait"]
    end

    subgraph Plan["3. PLAN (nettrades_loop)"]
        C1["Create Training Job"] --> C2["llm_training.dataset"]
        C2 --> C3["llm_training.job"]
        C3 --> C4["GPUStack Training"]
    end

    subgraph Execute["4. EXECUTE (nettrades_loop)"]
        D1["Model Validation"] --> D2["A/B Test"]
        D2 -->|Pass| D3["Deploy Model"]
        D2 -->|Fail| D4["Rollback"]
        D3 --> D5["Update LangGraph Agents"]
        D5 --> D6["Monitor Performance"]
    end

    Monitor --> Analyze --> Plan --> Execute
    Execute -->|"Feedback Loop"| Monitor

```

### 4. LangGraph Agent State Machine (Simplified)

The LangGraph supervisor orchestrates all sub-agents, incorporating bridge routing and self-improvement hooks.

```mermaid

graph TD
    START([Start]) --> CLASSIFY["classify\n━━━━━━━━━━━━━━━━\nIntent Classification"]
    CLASSIFY --> MEDICAL["medical_screening\n━━━━━━━━━━━━━━━━\nClinical/Legal Screening"]
    MEDICAL -->|"screening_done = True"| BRIDGE["bridge_route\n━━━━━━━━━━━━━━━━\nHub-and-Spoke Router"]
    BRIDGE -->|"route_source = remote"| ROUTE
    BRIDGE -->|"route_source = local"| ROUTE
    ROUTE["route\n━━━━━━━━━━━━━━━━\nIntent Router"] --> POST["post_process\n━━━━━━━━━━━━━━━━\nSelf-Improving Loop"]
    POST --> END([End])
    MEDICAL -->|"screening_done = False"| MEDICAL

```

### 5. CI/CD Pipeline

The platform uses Forgejo Actions for CI and Argo CD for GitOps deployment on Kubernetes.

```mermaid

flowchart LR
    subgraph Dev["Developer Workstation"]
        Code["Write Code"]
        Commit["git commit & push"]
    end

    subgraph Forgejo["Forgejo (Self-Hosted Git)"]
        Repo["Repository"]
        Actions["Forgejo Actions"]
    end

    subgraph Registry["Container Registry"]
        Images["Stored Images"]
    end

    subgraph GitOps["GitOps (Argo CD)"]
        Manifests["K8s Manifests"]
        ArgoCD["Argo CD"]
    end

    subgraph K8s["Kubernetes Cluster"]
        Pods["Running Pods"]
    end

    Code --> Commit
    Commit -->|"git push"| Repo
    Repo -->|"Triggers"| Actions
    Actions -->|"Build & Push"| Registry
    Repo -->|"Stores"| Manifests
    ArgoCD -->|"Pulls"| Manifests
    ArgoCD -->|"Pulls"| Registry
    ArgoCD -->|"Deploys"| Pods

```

### 6. Technology Stack Table

| Layer | Component | Technology | Version | License | Notes |
|---------|-------------|-------------|---------|-------------|-------------|
| `Business Logic` | ERP / CRM / HR | Odoo | 19 CE | LGPL-3 | Core business logic |
| `Job Queue` | Async processing | OCA queue_job | 19.0 | LGPL-3 | Background jobs |
| `Payments` | Payment processing | OCA payment_stripe | 19.0 | LGPL-3 | Stripe integration |
| `Database` | Primary database | PostgreSQL + pgvector | 18 | PostgreSQL | Vector embeddings |
| `Cache` | Session / Rate limiting | Valkey | 8 | BSD-3 | High-performance cache |
| `Object Storage` | Files / Models | MinIO / S3 | Latest | AGPL-3 | Model artifacts |
| `Agent Orchestration` | Multi-agent framework | LangGraph | Latest | MIT | Stateful agents |
| `Agent State` | Checkpointing | LangGraph Checkpoint Postgres | Latest | MIT | Durable workflows |
| `GPU Management` | Cluster management | GPUStack | Latest	Apache-2.0 | GPU orchestration |
| `Fine-Tuning` | Model training | Unsloth / Axolotl | Latest	Apache-2.0 | LLM fine-tuning |
| `Inference` | LLM serving | vLLM, llama.cpp, SGLang | Latest	MIT | High-performance inference |
| `Ingress` | Reverse proxy | Traefik | Latest | MIT | Dynamic routing |
| `Git / CI` | Source control / CI | Forgejo | Latest	MIT | Self-hosted Git |
| `GitOps` | Continuous delivery | Argo CD | Latest	Apache-2.0 | Declarative deployments |
| `OS` | Kubernetes OS | Talos Linux	Latest	MPL-2.0	Immutable, secure |
| `Orchestration` | Container orchestration | Kubernetes | Latest | Apache-2.0 | Container management |
| `CNI` | Networking | Cilium | Latest | Apache-2.0 | eBPF networking |
| `Storage` | Persistent volumes | Longhorn | Latest | Apache-2.0 | Distributed block storage |
| `Load Balancing` | Bare-metal LB | MetalLB | Latest | Apache-2.0 | Load balancing |
| `Certificates` | TLS management | cert-manager | Latest | Apache-2.0 | Automated certificates |
| `Database Operator` | PostgreSQL operator | CloudNativePG | Latest | Apache-2.0 | PostgreSQL management |
| `GPU Operator` | NVIDIA GPU management | NVIDIA GPU Operator | Latest | Apache-2.0 | GPU provisioning |
| `Distributed Computing` | Ray on K8s | KubeRay | Latest | Apache-2.0 | Distributed training |
| `VPN` | Secure networking | WireGuard | Latest | GPL-2.0 | Secure tunnels |
| `Sandboxing` | Container isolation | gVisor | Latest | pache-2.0 | Secure containers |
| `Metrics` | Monitoring | Prometheus | Latest | Apache-2.0 | Metrics collection |
| `Dashboards` | Visualisation | Grafana | Latest | AGPL-3.0 | Monitoring dashboards |

📖 Full architecture details are in the docs/developer/ folder.

🚀 Quick Start

Prerequisites

* Python 3.12+

* PostgreSQL 18+ with pgvector extension

* Docker & Kubernetes (for production deployment)

* NVIDIA GPU (optional, for GPU features)

One-Click Installer

The quickest way to get started is with the interactive installer:

```bash

curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash

```

The installer auto-detects your hardware, asks for your domain, generates secure passwords, and starts all services.
Manual Installation
#### 1. Clone the Repository

```bash

git clone https://github.com/nettrades/nettrades-platform.git
cd nettrades-platform

```

#### 2. Set Up Python Virtual Environment

```bash

python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

```

#### 3. Install Dependencies

```bash

# Core Python packages
pip install torch transformers datasets accelerate

# Odoo LLM modules requirements
pip install -r third-party/odoo_llm/requirements.txt

# Upgrade Starlette (security fix for CVE-2026-48710)
pip install --upgrade "starlette>=1.0.1"

```

### 4. Install Odoo Modules (in the correct order)

    ⚠️ Important: Modules must be installed in this order to satisfy dependencies.

#### Batch 1: Foundation Modules

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=third-party/odoo/addons,odoo-modules,third-party/odoo_llm,third-party/odoo_llm_compat,third-party/website_sale_marketplace,third-party/queue-19 \
  -i queue_job,queue_job_batch,queue_job_cron,llm,llm_tool,llm_store,llm_pgvector,llm_knowledge,llm_assistant,llm_thread,llm_generate,llm_training \
  --stop-after-init

```

#### Batch 2: NETTRADES Core

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=... \
  -i nettrades_core \
  --stop-after-init

```

#### Batch 3: Core NETTRADES Modules

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=... \
  -i nettrades_gpu_admin,nettrades_gpustack_adapter,nettrades_good_answer,nettrades_ask_someone,nettrades_queue,nettrades_notifications,nettrades_job_matching,nettrades_lead_scoring,nettrades_chatbot \
  --stop-after-init

```

#### Batch 4: Self-improving System Modules

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=... \
  -i nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config \
  --stop-after-init

```

#### Batch 5: Additional Modules

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=... \
  -i nettrades_fairness,nettrades_onboarding,nettrades_proposals,nettrades_research,nettrades_pwa \
  --stop-after-init

```

    📖 See the full installation guide in docs/operations/module-installation-order.md.

### 5. Start Odoo

```bash

python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
  --addons-path=third-party/odoo/addons,odoo-modules,third-party/odoo_llm,third-party/odoo_llm_compat,third-party/website_sale_marketplace,third-party/queue-19 \
  -d nettrades

```

Open http://localhost:8069 and log in with admin / admin.



## 🛠️ Quick Start

### One-Command Deployment (Ubuntu 24.04)

```bash

# Download and run the interactive installer
curl -sSL https://raw.githubusercontent.com/nettrades/nettrades-platform/main/deploy/docker/install-nettrades.sh | sudo bash

```

The installer auto-detects your hardware, asks for your domain, generates secure passwords, and starts all services.

### Access Your Platform

### After ~10-20 minutes, you'll have:


| Service | URL | Default Credentials |
|---------|-------------|-------------|
|`Odoo`	| https://your-domain	| Create database on first login|
|`Grafana`	| https://grafana.your-domain	| admin / password from .env|
|`GPUStack`	| https://gpustack.your-domain	| admin / admin (change immediately)|
|`Forgejo`	| https://git.your-domain	| Create first user on first login|

All services are secured with Let's Encrypt TLS.

For detailed step-by-step instructions, see the [Full Documentation](docs/index.md).


## 📚 Documentation

Full documentation is available at: [Full Documentation](docs/index.md).

| Section | Description | Link |
|---------|-------------|-----------|		
| `User Guide`	| For end-users – companies, freelancers, job-seekers	| `docs/user/index.md |
| `Developer Guide`	| For developers extending the platform	| `docs/developer/index.md |
| `Operations Guide`	| For system administrators and DevOps	| `docs/operations/index.md |
| `API Reference`	| Complete API documentation	| `docs/developer/api-reference.md |
| `Architecture Overview`	| System architecture diagrams and explanations	| `docs/developer/architecture.md |
| `Core Models`	| Reference for all custom Odoo models	| `docs/developer/core-models.md |
| `Database Schema`	| Complete database schema	| `docs/appendix/database-schema.md |
| `Glossary`	| Key terms and definitions	| `docs/appendix/glossary.md |
| `Contributing Guide`	| How to contribute to the project	| `docs/governance/contributing.md |
| `Roadmap`	| Project roadmap and milestones	| `docs/governance/roadmap |

## 🤝 Community & Support

NETTRADES has a growing community of developers, enterprises, and researchers. We welcome you to join us!
💬 Get Help

| Channel | Purpose | Link |
|---------|-------------|-----------|
| `GitHub Issues`	| Report bugs, request features, or ask technical questions	| [Issues](https://github.com/nettrades/nettrades-platform/issues) |
| `GitHub Discussions`	| Ask questions, share ideas, and get community support	| [Discussions](https://github.com/nettrades/nettrades-platform/discussions) |
| `Twitter / X`	| Follow for project updates and announcements	| [@nettrades_ai](https://twitter.com/nettrades) |

## 📖 Learn More

* [Developer Documentation](docs/developer/index.md) – In-depth architecture, agent diagrams, and API references.

* [Operations Guide](docs/operations/index.md) – Deployment, CI/CD, and Kubernetes configuration.

* [Installation Guide](docs/operations/module-installation-order.md) – Step-by-step module installation.

## 🌟 Community Highlights

* Contributors: We welcome contributions from developers of all skill levels. See our [Contributing Guide](contributing.md).

* Adopters: Companies using NETTRADES in production – [add your logo!](https://github.com/nettrades/nettrades-platform/discussions)

* Events: Join our monthly community calls (details in Discussions).

## 🤝 Contributing

We welcome contributions! Please read our [Contributing Guide](contributing.md) before submitting PRs.

### Quick Steps

🍴 Fork the repository

🌿 Create a feature branch (git checkout -b feature/amazing-feature)

💻 Make your changes

✅ Run tests (pytest src/core/tests/)

📝 Update documentation

🚀 Push and open a Pull Request

## ⭐ Star Us!

If you find [NETTRADES.AI](https://nettrades.ai/) useful, please consider giving us a ⭐ on GitHub – it helps others discover the project and supports our work.


## 📄 License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0) – see the [LICENSE.txt](LICENSE.txt) file for details.

| Component | License |
|---------|-------------|
| src/ (core orchestrator, agent, training scripts) | [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.en.html) |
| odoo-modules/ (custom Odoo plugins) | [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.en.html) |
| third-party/ | Original licenses (LGPL, MIT, Apache-2.0) |
| deploy/ | AGPL-3.0 |
| scripts/ | MIT |

Please agree to the [Contributor License Agreement (CLA)](CONTRIBUTING.md) before contributing.

## 🙏 Acknowledgements

NETTRADES builds on the shoulders of many amazing open-source projects:

* [Odoo](https://www.odoo.com/) – Open-source ERP

* [LangGraph](https://github.com/langchain-ai/langgraph) – Stateful agent orchestration

* [GPUStack](https://gpustack.ai/) – GPU cluster management

* [Kubernetes](https://kubernetes.io/) – Container orchestration

* [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) – Vector database

* [Valkey](https://valkey.io/) – High-performance cache

* [Traefik](https://traefik.io/) – Cloud-native reverse proxy

* [Forgejo](https://forgejo.org/) – Self-hosted Git

* [Argo CD](https://argo-cd.readthedocs.io/) – GitOps continuous delivery

* [Talos Linux](https://www.talos.dev/) – Kubernetes-native OS

* [Cilium](https://cilium.io/) – eBPF networking

* [Longhorn](https://longhorn.io/) – Distributed block storage

* [Unsloth](https://unsloth.ai/) – Efficient fine-tuning

* [Axolotl](https://github.com/OpenAccess-AI-Collective/axolotl) – Multi-GPU fine-tuning

* [Prometheus](https://prometheus.io/) & [Grafana](https://grafana.com/) – Monitoring





## User Workflow: NETTRADES Platform

### 1. User Journey Overview

```mermaid

graph TB
    subgraph UserTypes["User Types"]
        CompanyUser["Company / Employer"]
        Freelancer["Freelancer / Job Seeker"]
        Expert["Expert / Professional"]
        Researcher["Researcher"]
        Admin["System Administrator"]
    end

    subgraph EntryPoints["Entry Points"]
        WebPortal["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        ChatWidget["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
        API["REST API / GraphQL"]
    end

    subgraph CoreActions["Core User Actions"]
        PostJob["Post Job / Project"]
        SearchTalent["Search Talent / Freelancers"]
        AskSomeone["Ask Someone (Expert Help)"]
        VoteAnswer["Good Answer Voting"]
        ShareGPU["Share GPU Resources"]
        RunInference["Run AI Inference"]
        FineTune["Fine-Tune Models"]
        ManageGPU["Manage GPU Cluster"]
    end

    UserTypes --> EntryPoints
    EntryPoints --> CoreActions
```

### 2. Complete End-to-End Workflow

```mermaid
graph TD
    START([User Logs In]) --> A{User Type?}

    A -->|Company / Employer| B[Post Job / Project]
    A -->|Freelancer| C[Search Jobs / Projects]
    A -->|Expert| D[Offer Expert Services]
    A -->|Researcher| E[Access Research Marketplace]
    A -->|Admin| F[Manage System Configuration]

    B --> G[LangGraph Recruitment Agent]
    C --> H[LangGraph Freelance Agent]
    D --> I[Ask Someone Module]
    E --> J[Research Module]
    F --> K[Administration UI]

    G --> L[Search Candidates]
    H --> M[Match with Projects]
    I --> N[Expert Consultation Flow]

    L --> O[Local Talent Available?]
    M --> O
    N --> P[Expert Available?]

    O -->|Yes| Q[Process Locally]
    O -->|No| R[Route to Hub nettrades_bridge]

    P -->|Yes| S[Connect with Expert]
    P -->|No| T[Search Global Experts]

    S --> U[Stripe Escrow Payment]
    U --> V[Consultation Session]
    V --> W[Session Complete]

    Q --> X[Return Results]
    R --> Y[Global Talent Pool]
    Y --> X

    W --> Z[Good Answer Vote?]
    X --> Z
    Z -->|Yes| AA[Vote Recorded]
    Z -->|No| AB[Session Ends]

    AA --> AC[nettrades_good_answer]
    AC --> AD[Reputation Updated]
    AD --> AE[Karma Threshold Met?]
    AE -->|Yes| AF[User Qualified]
    AE -->|No| AG[Continue]

    AF --> AH[Autonomous Administration]
    AH --> AI[GPU Health Watchdog]
    AH --> AJ[Utilisation Alerts]
    AH --> AK[Auto Qualification]

    AI --> AL[GPU Cluster Management]
    AL --> AM[Share GPU Resources]
    AM --> AN[Earn Tokens]

    AN --> AO[Spend Tokens on Inference]
    AO --> AP[GPUStack Inference]
    AP --> AQ[Return Results]

    AF --> AR[Fine-Tuning Pipeline]
    AR --> AS[Unsloth/Axolotl Training]
    AS --> AT[Model Improved]
    AT --> AU[Deploy to LangGraph Agents]

    AU --> AV[Self-Improving Loop]
    AV --> AW[Monitor Performance]
    AW --> AX[Trigger Detection]
    AX --> AY[New Cycle]
    AY --> AR
```

### 3. Detailed Ask Someone Workflow

```mermaid
graph TD
    START([User Requests Help]) --> A[Ask Someone Module]

    A --> B[Select Professional Field]
    B --> C[Describe Question / Problem]
    C --> D[Set Budget / Timeframe]

    D --> E[Search Experts]
    E --> F{Expert Available?}

    F -->|Yes| G[Display Expert Profiles]
    F -->|No| H[Route to Hub]
    H --> I[Search Global Experts]
    I --> G

    G --> J[User Selects Expert]
    J --> K[Create Escrow Hold]
    K --> L[Stripe Payment Processing]
    L --> M[Payment Confirmed]

    M --> N[Start Consultation Session]
    N --> O[Chat / Video / Document Sharing]
    O --> P[Expert Provides Answer]

    P --> Q{User Satisfied?}
    Q -->|Yes| R[Release Payment to Expert]
    Q -->|No| S[Dispute Resolution]

    R --> T[Session Complete]
    T --> U[User Rates Expert]
    U --> V[Expert Reputation Updated]
    V --> W[Good Answer Vote?]

    W -->|Yes| X[Vote Recorded in nettrades_good_answer]
    W -->|No| Y[Session Ends]

    X --> Z[Reputation Decay Applied]
    Z --> AA[Karma Updated]
    AA --> AB{Qualification Threshold?}
    AB -->|Yes| AC[User Qualified as Expert]
    AB -->|No| AD[Continue]

    S --> AE[Admin Review]
    AE --> AF{Resolved?}
    AF -->|Yes| AG[Payment Released/Refunded]
    AF -->|No| AH[Escalated]

    AC --> AI[Expert Marketplace Expanded]

```

### 4. Good Answer Voting Workflow

```mermaid
graph TD
    START([User Receives Answer]) --> A[Review Answer Quality]

    A --> B{Good Answer?}
    B -->|Yes| C[Click Good Answer Button]
    B -->|No| D[Skip / Report]

    C --> E[Vote Recorded]
    E --> F[Answer Score Updated]
    F --> G[Answerer Karma Increased]

    G --> H{Threshold Met?}
    H -->|Yes| I[Answerer Qualified]
    H -->|No| J[Continue]

    I --> K[Autonomous Administration Check]
    K --> L[Reputation Decay Applied]
    L --> M[Vote Processed for AI Training]

    M --> N[data.episode Created]
    N --> O[data.annotation Created]
    O --> P[Quality Score Calculated]

    P --> Q{Score > Threshold?}
    Q -->|Yes| R[Episode Marked as Qualified]
    Q -->|No| S[Episode Rejected]

    R --> T[Dataset Prepared]
    T --> U[Fine-Tuning Pipeline Triggered]
    U --> V[Unsloth/Axolotl Training]
    V --> W[Model Improved]

    W --> X[Deploy to LangGraph Agents]
    X --> Y[Self-Improving Loop Continues]

    Y --> Z[Monitor Performance]
    Z --> AA[Edge Case Detection]
    AA --> AB[New Triggers Identified]
    AB --> AC[New Cycle]
```

### 5. Distributed GPU Functionality Workflow

```mermaid
graph TD
    START([GPU Request]) --> A{Request Type?}

    A -->|Inference| B[GPUStack Inference Request]
    A -->|Training| C[Fine-Tuning Job]
    A -->|GPU Sharing| D[GPU Marketplace]

    B --> E{Local GPU Available?}
    C --> E

    E -->|Yes| F[Process Locally]
    E -->|No| G[Check GPU Overflow]
    G --> H{Overflow Enabled?}

    H -->|Yes| I[Route to Hub]
    H -->|No| J[Queue Request]
    I --> K[Global GPU Marketplace]

    K --> L[Allocate GPU Resources]
    L --> M[Run Inference/Training]
    M --> N[Return Results]

    D --> O[User Shares GPU]
    O --> P[GPU Registered]
    P --> Q[GPU Health Watchdog]
    Q --> R[GPU Available for Others]

    R --> S[User Earns Tokens]
    S --> T[Token Balance Updated]
    T --> U[Spend Tokens on Inference/Training]

    F --> V[GPU Utilisation Updated]
    V --> W[Autonomous Administration]
    W --> X[Utilisation Alerts]
    X --> Y[Scaling Recommendations]

    Y --> Z[GPU Cluster Management]
    Z --> AA[Add/Remove Nodes]
    AA --> AB[Cluster Scaled]
```

### 6. Self-Improving Loop with GPU Integration

```mermaid
graph TD
    subgraph Monitor["1. MONITOR (nettrades_data_collection)"]
        A1["User Interactions"] --> A2["Good Answer Votes"]
        A1 --> A3["Ask Someone Sessions"]
        A1 --> A4["LangGraph Agent Interactions"]
        A2 --> A5["data.episode"]
        A3 --> A5
        A4 --> A5
        A5 --> A6["Quality Score"]
        A5 --> A7["Edge Case Detection"]
    end

    subgraph Analyze["2. ANALYZE (nettrades_trigger)"]
        B1["Trigger Evaluation"] --> B2{"Quality Drop?"}
        B2 -->|Yes| B3["Trigger Fired"]
        B2 -->|No| B4{"Data Volume?"}
        B4 -->|Yes| B3
        B4 -->|No| B5["Wait"]
        B3 --> B6["Create Training Job"]
    end

    subgraph Plan["3. PLAN (nettrades_loop)"]
        C1["llm_training.dataset"] --> C2["llm_training.job"]
        C2 --> C3{"Local GPU Available?"}
        C3 -->|Yes| C4["Local GPUStack Training"]
        C3 -->|No| C5["Route to Hub"]
        C5 --> C6["Global GPU Marketplace"]
        C6 --> C7["Distributed Training"]
        C4 --> C8["Unsloth/Axolotl"]
        C7 --> C8
        C8 --> C9["Model Fine-Tuned"]
    end

    subgraph Execute["4. EXECUTE (nettrades_loop)"]
        D1["Model Validation"] --> D2["A/B Test"]
        D2 -->|Pass| D3["Deploy Model"]
        D2 -->|Fail| D4["Rollback"]
        D3 --> D5["Update LangGraph Agents"]
        D5 --> D6["Monitor Performance"]
        D6 --> D7["GPU Utilisation"]
        D7 --> D8["Autonomous Scaling"]
    end

    Monitor --> Analyze --> Plan --> Execute
    Execute -->|"Feedback Loop"| Monitor
```

### 7. Complete System Workflow with All Components

```mermaid
graph TB
    subgraph UserLayer["User Layer"]
        U1["Company / Employer"]
        U2["Freelancer / Job Seeker"]
        U3["Expert / Professional"]
        U4["Researcher"]
        U5["System Administrator"]
    end

    subgraph FrontendLayer["Frontend Layer"]
        F1["Odoo Website / Portal"]
        F2["Mobile PWA"]
        F3["AI Chatbot Widget"]
        F4["VS Code Extension"]
        F5["REST API / GraphQL"]
    end

    subgraph OrchestrationLayer["Orchestration Layer (LangGraph)"]
        O1["Supervisor Agent"]
        O2["Recruitment Agent"]
        O3["Freelance Agent"]
        O4["Lead Gen Agent"]
        O5["GPU Management Agent"]
        O6["Vision Agent"]
        O7["Action Agent"]
        O8["MCP-Odoo Bridge"]
    end

    subgraph BridgeLayer["Bridge Layer"]
        B1["nettrades_bridge"]
        B2["Local Brain Routing"]
        B3["Remote Brain Routing"]
        B4["GPU Overflow Detection"]
    end

    subgraph CoreModules["Core Odoo Modules"]
        C1["nettrades_core"]
        C2["nettrades_good_answer"]
        C3["nettrades_ask_someone"]
        C4["nettrades_gpu_admin"]
        C5["nettrades_gpustack_adapter"]
        C6["nettrades_queue"]
        C7["nettrades_notifications"]
        C8["nettrades_job_matching"]
        C9["nettrades_lead_scoring"]
        C10["nettrades_chatbot"]
    end

    subgraph SelfImprovingModules["Self-Improving Modules"]
        S1["nettrades_data_collection"]
        S2["nettrades_trigger"]
        S3["nettrades_loop"]
        S4["nettrades_self_improving_config"]
    end

    subgraph TrainingLayer["Training & Inference Layer"]
        T1["GPUStack"]
        T2["GPU Workers (vLLM)"]
        T3["GPU Workers (llama.cpp)"]
        T4["Unsloth / Axolotl"]
        T5["llm_training"]
        T6["External LLM APIs"]
    end

    subgraph DataLayer["Data Layer"]
        D1["PostgreSQL + pgvector"]
        D2["Valkey 8"]
        D3["MinIO / S3"]
    end

    subgraph Infrastructure["Infrastructure Layer"]
        I1["Kubernetes (Talos Linux)"]
        I2["Cilium CNI"]
        I3["Longhorn Storage"]
        I4["MetalLB"]
        I5["cert-manager"]
        I6["CloudNativePG"]
        I7["NVIDIA GPU Operator"]
        I8["KubeRay"]
    end

    subgraph GitOpsLayer["GitOps Layer"]
        G1["Forgejo"]
        G2["Argo CD"]
    end

    subgraph MonitoringLayer["Monitoring Layer"]
        M1["Prometheus"]
        M2["Grafana"]
    end

    UserLayer --> FrontendLayer
    FrontendLayer --> OrchestrationLayer
    OrchestrationLayer --> BridgeLayer
    BridgeLayer --> CoreModules
    OrchestrationLayer --> SelfImprovingModules
    SelfImprovingModules --> TrainingLayer
    TrainingLayer --> CoreModules
    CoreModules --> DataLayer
    Infrastructure --> CoreModules
    Infrastructure --> DataLayer
    GitOpsLayer --> Infrastructure
    MonitoringLayer --> Infrastructure
    MonitoringLayer --> TrainingLayer
```

### 8. Key Workflow Sequences
#### 8.1 Ask Someone Flow

```mermaid
sequenceDiagram
    participant User
    participant Portal as Odoo Portal
    participant Ask as nettrades_ask_someone
    participant Bridge as nettrades_bridge
    participant Expert
    participant Stripe
    participant GPUStack

    User->>Portal: Request help
    Portal->>Ask: Create consultation request
    Ask->>Bridge: Route request
    Bridge->>Expert: Search local experts
    alt Expert Found
        Expert-->>Bridge: Available
        Bridge-->>Ask: Expert found
    else No Expert
        Bridge->>Hub: Search global experts
        Hub-->>Bridge: Expert found
        Bridge-->>Ask: Expert found
    end
    Ask->>Stripe: Create escrow hold
    Stripe-->>Ask: Hold confirmed
    Ask->>Expert: Notify assignment
    Expert-->>User: Start session
    User-->>Expert: Provide details
    Expert-->>User: Provide answer
    User->>Ask: Rate answer
    Ask->>Stripe: Release payment
    Ask->>GPUStack: Record for training
```


#### 8.2 GPU Sharing & Inference Flow

```mermaid
sequenceDiagram
    participant User
    participant Portal as Odoo Portal
    participant GPU as nettrades_gpu_admin
    participant Adapter as nettrades_gpustack_adapter
    participant Bridge as nettrades_bridge
    participant GPUStack
    participant Token

    User->>Portal: Share GPU
    Portal->>GPU: Register GPU
    GPU->>Adapter: Sync with GPUStack
    Adapter->>GPUStack: Register node
    GPUStack-->>Adapter: Node registered
    Adapter-->>GPU: Node confirmed
    GPU->>Token: Earn tokens
    Token-->>User: Tokens added

    User->>Portal: Request inference
    Portal->>Bridge: Route request
    Bridge->>GPU: Check local capacity
    alt Local Capacity Available
        GPU->>Adapter: Run inference
        Adapter->>GPUStack: Execute
        GPUStack-->>Adapter: Result
    else No Capacity
        Bridge->>GPUStack: Route to hub
        GPUStack-->>Bridge: Result
    end
    Bridge-->>User: Return result
```

#### 8.3 Good Answer Flow

```mermaid
sequenceDiagram
    participant User
    participant Portal
    participant Vote
    participant Core
    participant Data
    participant Trigger
    participant Trainer
    participant GPU

    User->>Portal: Views answer
    Portal->>User: Displays answer
    User->>Portal: Clicks "Good Answer"
    Portal->>Vote: Submit vote
    Vote->>Vote: Validate & record
    Vote->>Core: Update Karma
    Core-->>Vote: Karma updated
    Vote->>Data: Create episode
    Data->>Data: Calculate quality
    Data->>Trigger: Check triggers
    Trigger->>Trigger: Evaluate quality
    Trigger->>Data: Mark episode
    Trigger->>Trainer: Start improvement
    Trainer->>GPU: Submit training
    GPU-->>Trainer: Training done
    Trainer->>Portal: Deploy new model
```

```mermaid

graph TB
    START([User views answer]) --> A[Portal displays answer]
    A --> B[User clicks Good Answer button]
    B --> C[Portal submits vote]

    C --> D[Vote Module validates user]
    D --> E[Vote Module checks for duplicates]
    E --> F[Vote Module records vote]

    F --> G[Update Karma in Core Module]
    G --> H[Core Module recalculates reputation]
    H --> I[Karma updated]

    I --> J[Create data.episode in Data Module]
    J --> K[Data Module calculates quality_score]

    K --> L[Trigger Module checks triggers]
    L --> M{Trigger Module evaluates quality}

    M -->|Quality Good| N[Mark episode as qualified]
    M -->|Quality Poor| O[Mark episode as rejected]

    N --> P[Trigger Module starts self-improvement loop]
    P --> Q[Loop Module prepares training dataset]
    Q --> R[Loop Module submits fine-tuning job]

    R --> S[GPUStack allocates GPU resources]
    S --> T[GPUStack runs Unsloth/Axolotl training]
    T --> U[GPUStack validates model]

    U --> V[Loop Module A/B tests new model]
    V --> W{Model improved?}

    W -->|Yes| X[Loop Module deploys improved model]
    W -->|No| Y[Loop Module rolls back]

    X --> Z[Portal displays improved responses]
    O --> END1([End - Rejected])
    Y --> END2([End - Rollback])

    style START fill:#4CAF50,color:white
    style END1 fill:#f44336,color:white
    style END2 fill:#ff9800,color:black
    style M fill:#2196F3,color:white
    style W fill:#2196F3,color:white

```

## 9. File Locations Summary

| Component | File Path |
|---------|-------------|
| Supervisor Agent | src/core/supervisor.py |
| Bridge Integration | src/core/bridge_integration.py |
| Self-Improving Integration | src/core/self_improving_integration.py |
| Recruitment Agent | src/core/agents/recruitment_agent.py |
| Freelance Agent | src/core/agents/freelance_agent.py |
| Lead Gen Agent | src/core/agents/lead_gen_agent.py |
| GPU Management Agent | src/core/agents/gpu_management_agent.py |
| Vision Agent | src/core/agents/vision_agent.py |
| Action Agent | src/core/agents/action_agent.py |
| Ask Someone | odoo-modules/nettrades_ask_someone/models/ |
| Good Answer | odoo-modules/nettrades_good_answer/models/ |
| GPU Admin | odoo-modules/nettrades_gpu_admin/models/ |
| GPUStack Adapter | odoo-modules/nettrades_gpustack_adapter/models/ |
| Data Collection | odoo-modules/nettrades_data_collection/models/ |
| Trigger | odoo-modules/nettrades_trigger/models/ |
| Loop | odoo-modules/nettrades_loop/models/ |
| Self-Improving Config | odoo-modules/nettrades_self_improving_config/models/ |
| Bridge | odoo-modules/nettrades_bridge/models/ |

## 10. Summary of Workflows

| Workflow | Key Modules  | Key Features |
|---------|----------|-------------|
| `Ask Someone` | `nettrades_ask_someone, nettrades_bridge, Stripe` | Expert consultation, escrow payments, reputation |
| `Good Answer Voting` | `nettrades_good_answer, nettrades_core, nettrades_data_collection` | User feedback, karma, qualification |
| `GPU Sharing` | `nettrades_gpu_admin, nettrades_gpustack_adapter, GPUStack` | GPU marketplace, token economy |
| `Self-Improving Loop` | `nettrades_data_collection, nettrades_trigger, nettrades_loop` | Continuous learning, fine-tuning, deployment |
| `Agent Routing` | `nettrades_bridge, LangGraph Agents` | Hub-and-spoke, local/remote routing, overflow |


## 11. Top-Level System Architecture

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        User["User / Browser"]
        Portal["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        Chat["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
        API["REST / GraphQL"]
    end

    subgraph Ingress["Ingress Layer"]
        Traefik["Traefik Reverse Proxy"]
    end

    subgraph Orchestration["Orchestration Layer (LangGraph)"]
        MCP["MCP-Odoo Bridge"]
        Supervisor["Supervisor Agent"]
        SubAgents["Sub-Agents"]
        Bridge["nettrades_bridge"]
        LocalBrain["Local Brain"]
        RemoteBrain["Remote Brain"]
    end

    subgraph SelfImproving["Self-Improving System"]
        DataCollect["nettrades_data_collection"]
        Trigger["nettrades_trigger"]
        Loop["nettrades_loop"]
        Config["nettrades_self_improving_config"]
    end

    subgraph Training["AI Inference & Training"]
        GPUStack["GPUStack"]
        Workers["GPU Workers (vLLM)"]
        FineTune["Unsloth / Axolotl"]
        External["External LLM APIs"]
        LLMTraining["llm_training"]
    end

    subgraph Core["Core Layer (Odoo 19 CE)"]
        Odoo["Odoo 19 CE"]
        Modules["Custom Odoo Modules"]
        Queue["OCA queue_job"]
        Payments["OCA payment_stripe"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL + pgvector"]
        Valkey["Valkey 8"]
        MinIO["MinIO / S3"]
    end

    subgraph K8s["Kubernetes Infrastructure"]
        K8sCluster["Kubernetes (Talos Linux)"]
        Cilium["Cilium CNI"]
        Longhorn["Longhorn Storage"]
        MetalLB["MetalLB"]
        CertMgr["cert-manager"]
        CloudNativePG["CloudNativePG"]
        GPUOp["NVIDIA GPU Operator"]
        KubeRay["KubeRay"]
    end

    subgraph GitOps["GitOps Layer"]
        Forgejo["Forgejo"]
        ArgoCD["Argo CD"]
    end

    subgraph Monitoring["Monitoring Layer"]
        Prometheus["Prometheus"]
        Grafana["Grafana"]
    end

    subgraph Security["Security Layer"]
        WireGuard["WireGuard VPN"]
        gVisor["gVisor Sandbox"]
    end

    User --> Traefik
    Portal --> Traefik
    PWA --> Traefik
    Chat --> Traefik
    VSCode --> Traefik
    API --> Traefik

    Traefik --> Odoo

    Odoo --> Modules
    Odoo --> Queue
    Odoo --> Payments
    Odoo --> MCP

    MCP --> Supervisor
    Supervisor --> SubAgents
    SubAgents --> Bridge
    Bridge -->|Local| LocalBrain
    Bridge -->|Remote| RemoteBrain
    Bridge -->|GPU Overflow| GPUStack

    Odoo --> DataCollect
    DataCollect --> Trigger
    Trigger --> Loop
    Loop --> Config
    Loop --> LLMTraining

    LLMTraining --> GPUStack
    GPUStack --> Workers
    GPUStack --> FineTune
    GPUStack --> External

    Odoo --> PG
    Odoo --> Valkey
    Odoo --> MinIO

    GPUStack --> PG

    K8sCluster --> Odoo
    K8sCluster --> MCP
    K8sCluster --> GPUStack
    K8sCluster --> PG
    K8sCluster --> Valkey
    K8sCluster --> MinIO

    Cilium --> K8sCluster
    Longhorn --> PG
    MetalLB --> Traefik
    CertMgr --> Traefik
    CloudNativePG --> PG
    GPUOp --> GPUStack
    KubeRay --> GPUStack

    Forgejo --> ArgoCD
    ArgoCD --> K8sCluster

    Prometheus --> Odoo
    Prometheus --> GPUStack
    Prometheus --> PG
    Grafana --> Prometheus

    WireGuard --> K8sCluster
    gVisor --> K8sCluster

    style Frontend fill:#e3f2fd,stroke:#1565c0
    style Ingress fill:#fff3e0,stroke:#e65100
    style Orchestration fill:#f3e5f5,stroke:#6a1b9a
    style SelfImproving fill:#e8eaf6,stroke:#283593
    style Training fill:#e8f5e9,stroke:#2e7d32
    style Core fill:#fce4ec,stroke:#c62828
    style Data fill:#ede7f6,stroke:#4527a0
    style K8s fill:#f5f5f5,stroke:#424242
    style GitOps fill:#fff8e1,stroke:#f57f17
    style Monitoring fill:#f1f8e9,stroke:#33691e
    style Security fill:#ffebee,stroke:#b71c1c
```


#### Step-by-Step flow

| Step | From | To | Description |
|---------|--------|---------|-------------|
| 1 | User | Traefik | User request enters via browser, mobile, chat, VS Code, or API. |
| 2 | Traefik | Odoo 19 CE | Traefik routes requests to Odoo with SSL termination. |
| 3 | Odoo | Custom Odoo Modules | Odoo processes business logic via custom modules. |
| 4 | Odoo | OCA queue_job | Long-running tasks are queued. |
| 5 | Odoo | OCA payment_stripe | Payment processing for expert consultations. |
| 6 | Odoo | MCP-Odoo Bridge | Odoo communicates with LangGraph via the bridge. |
| 7 | MCP-Odoo Bridge | Supervisor Agent | The bridge forwards to the supervisor for intent classification. |
| 8 | Supervisor | Sub-Agents | Supervisor routes to specialised sub-agents (Recruitment, Freelance, GPU Management, Vision, Action). |
| 9 | Sub-Agents | nettrades_bridge | Sub-agents use the bridge to decide local vs remote routing. |
| 10 | nettrades_bridge | Local Brain | If local processing is chosen, the request is processed by local LangGraph agents. |
| 11 | nettrades_bridge | Remote Brain | If remote processing is chosen, the request is forwarded to NETTRADES.AI. |
| 12 | nettrades_bridge | GPUStack | If local GPU capacity is exceeded, requests overflow to GPUStack. |
| 13 | Odoo | nettrades_data_collection | All interactions are recorded as data episodes. |
| 14 | data_collection | nettrades_trigger | Trigger module evaluates quality scores and data volume. |
| 15 | nettrades_trigger | nettrades_loop | If triggers fire, the loop initiates self-improvement. |
| 16 | nettrades_loop | llm_training | Training jobs are prepared and submitted. |
| 17 | llm_training | GPUStack | Training jobs are executed on GPUStack. |
| 18 | GPUStack | GPU Workers (vLLM) | Inference workloads run on vLLM. |
| 19 | GPUStack | Fine-Tune (Unsloth/Axolotl) | Fine-tuning runs on Unsloth/Axolotl. |
| 20 | GPUStack | External LLM APIs | Optionally route to external providers. |
| 21 | Odoo | PostgreSQL + pgvector | All transaction data and embeddings are persisted. |
| 22 | Odoo | Valkey 8 | Session caching and rate limiting. |
| 23 | Odoo | MinIO / S3 | File attachments and model artifacts are stored. |
| 24 | GPUStack | PostgreSQL + pgvector | Embeddings and training metadata are stored. |
| 25 | Kubernetes | All Services | All services run as Kubernetes pods. |
| 26 | Cilium | Kubernetes | Cilium provides eBPF networking. |
| 27 | Longhorn | PostgreSQL | Longhorn provides persistent block storage. |
| 28 | MetalLB | Traefik | MetalLB provides load balancing for Traefik. |
| 29 | cert-manager | Traefik | Automates TLS certificate provisioning. |
| 30 | CloudNativePG | PostgreSQL | Manages PostgreSQL clustering and failover. |
| 31 | NVIDIA GPU Operator | GPUStack | Provisions and manages GPU resources. |
| 32 | KubeRay | GPUStack | Enables distributed training via Ray. |
| 33 | Forgejo | Argo CD | Git repository triggers Argo CD for GitOps. |
| 34 | Argo CD | Kubernetes | Argo CD syncs manifests and applies changes. |
| 35 | Prometheus | Odoo, GPUStack, PostgreSQL | Scrapes metrics from all services. |
| 36 | Grafana | Prometheus | Visualises metrics on dashboards. |
| 37 | WireGuard | Kubernetes | Provides secure VPN access. |
| 38 | gVisor | Containers | Sandboxes containers for enhanced security. |



#### Summary of Flow Paths


| Path | Steps | Description |
|---------|-------------|-------------|
|` User → Local Processing` |	1-3, 6-10 |	User request → Odoo → LangGraph → Local Brain |
|` User → Remote Processing` |	1-3, 6-9, 11 |	User request → Odoo → LangGraph → Remote Brain |
|` Self-Improving Loop` | 13-17, 19 |	User interaction → data_episode → trigger → loop → fine-tuning |
|` GPU Inference` | 12, 18, 20 |	Bridge → GPUStack → vLLM / External APIs |
|` Data Persistence` | 21-24 |	Odoo → PostgreSQL, Valkey, MinIO; GPUStack → PostgreSQL |