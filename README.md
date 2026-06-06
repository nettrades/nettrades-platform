# NETTRADES.AI Platform — Codebase Summary

## 1. Project Overview

NETTRADES.AI is an open-source, autonomous enterprise platform that connects companies, freelancers, job-seekers, researchers, partners, and customers. It combines:

*    AI-powered job matching & freelancing – LangGraph agents analyse CVs, job postings, projects, and automatically create leads.

*    Distributed GPU marketplace – Companies and freelancers can share idle GPUs to run inference and fine-tuning, earning tokens.

*    Self-improving AI – A “Good Answer” voting system feeds a fine-tuning pipeline (Unsloth / Axolotl) that continuously improves field-specific models.

*    Expert marketplace (“Ask Someone”) – Users can request paid help from verified professionals with Stripe escrow.

*    Autonomous administration – GPU health watchdog, reputation decay, utilisation alerts, and automatic Karma-based qualification.

*    Multimodal & robotics support – Optional VLM, VLA, ROS 2, IoT/edge-device features, all controllable via admin toggles.

*    With transaction control and error handling

The platform is built on Odoo 19 Community Edition, orchestrated by LangGraph, with GPUStack as the GPU cluster manager, WireGuard for network isolation, and gVisor for container security.


## 2. Technology Stack (Final Versions)

Component			|Version		|License		|Purpose
________________________________|_______________________|_______________________|___________________________________________________________
Odoo				|19.0 CE		|LGPL-3.0		|ERP, marketplace, CRM, HR, Projects, Accounting

PostgreSQL + pgvector		|18.1 (via CNPG)	|PostgreSQL License	|Business data, vector embeddings, LangGraph checkpoints
Valkey				|8-alpine		|BSD-3-Clause		|Session storage, ORM cache, bus notifications
Forgejo				|15.0 LTS		|GPL-3.0+		|Self-hosted Git + CI/CD
Traefik				|v3.6.13		|MIT			|Reverse proxy, automatic Let's Encrypt TLS
LangGraph			|≥1.2.0			|MIT			|Multi-agent orchestration, durable execution
LangGraph Checkpoint Postgres	|≥3.0.3			|MIT			|Durable checkpoint storage in PostgreSQL
GPUStack			|v2.1.2			|Apache-2.0		|GPU cluster manager, inference engine, token metering
llama.cpp			|server-cpu/server-cuda	|MIT			|CPU inference fallback
Unsloth (core)			|2026.5.2		|Apache-2.0		|Single-GPU fine-tuning
Axolotl				|0.16.1+		|Apache-2.0		|Multi-GPU fine-tuning with FSDP2
WireGuard			|kernel module		|GPL-2.0		|Kernel-level network isolation
gVisor				|release-20260420.0	|Apache-2.0		|Syscall-level container isolation
OCA queue_job			|19.0 branch		|LGPL-3.0		|Background job processing
OCA payment_stripe		|19.0 branch		|LGPL-3.0		|Stripe payment acquirer
Talos Linux			|1.13.2			|MPL-2.0		|Immutable K8s OS
Kubernetes			|1.36 (via Talos)	|Apache-2.0		|Container orchestration
Cilium				|1.19.3			|Apache-2.0		|CNI with WireGuard encryption
Longhorn			|1.11.1			|Apache-2.0		|Distributed block storage
CloudNativePG			|1.29.0			|Apache-2.0		|PostgreSQL operator with HA & backups
cert-manager			|1.20.2			|Apache-2.0		|TLS certificate automation
MetalLB				|0.15.3			|Apache-2.0		|Bare-metal load balancer
Argo CD				|3.3.8			|Apache-2.0		|GitOps continuous delivery
NVIDIA GPU Operator		|v26.3.1		|Apache-2.0		|GPU support on Kubernetes
KubeRay				|1.6.1			|Apache-2.0		|Ray on Kubernetes for vLLM
Prometheus			|v3.8.0			|Apache-2.0		|Metrics collection
Grafana				|12.4.2			|AGPL-3.0 (unmodified)	|Dashboards

## 3. Licensing Strategy

NETTRADES uses a dual-licensing approach to protect the platform while keeping it open:

*    src/ (core orchestrator, agent, training scripts): AGPL-3.0 — strong copyleft; any modifications must be shared if offered as a network service. A commercial license is available for enterprises needing closed-source use.

*    odoo-modules/ (custom Odoo plugins): LGPL-3.0 — compatible with Odoo’s own license; plugins can be proprietary as long as they don’t copy Odoo core code.

*    third-party/: All third-party components retain their original licenses (LGPL, MIT, Apache-2.0, etc.).

*    deploy/: Deployment scripts and configurations are AGPL-3.0.

*    docs/: Documentation under Creative Commons Attribution 4.0.

*    scripts/: Build and setup scripts are MIT.

A Contributor License Agreement (CLA) is in CONTRIBUTING.md to ensure contributions can be re-licensed under the commercial license.

## 4. Complete Directory Structure

text

nettrades-platform/
│
├── .vscode/
│   └── launch.json                         ← VS Code debug configuration for Odoo
│
├── LICENSE.txt                              ← Root license notice (points to per-dir licenses)
├── README.md                                ← Project overview and quick start
├── OPEN-SOURCE-NOTICES.txt                  ← Attribution for all bundled third-party components
├── CONTRIBUTING.md                          ← Contributor License Agreement (CLA)
├── .gitignore                               ← Files excluded from version control
│
├── src/                                     ★ AGPL-3.0 – Your original code
│   ├── LICENSE.txt                           ← Full AGPL-3.0 text
│   │
│   ├── core/                                 ← LangGraph orchestrator (the brain of NETTRADES)
│   │   ├── Dockerfile                        ← Container image for the LangGraph service
│   │   ├── requirements.txt                  ★ Python dependencies (added pillow, paho-mqtt)
│   │   ├── app.py                            ← FastAPI application with PostgresSaver & Prometheus
│   │   ├── supervisor.py                     ★ Supervisor agent – classifies intent and routes to sub-agents
│   │   │								updated (vision/action routing)	
│   │   ├── agents/                           ← Specialised business sub-agents
│   │   │   ├── __init__.py
│   │   │   ├── recruitment_agent.py          ← CV / job matching
│   │   │   ├── freelance_agent.py            ← Project ↔ freelancer matching
│   │   │   ├── lead_gen_agent.py             ← Lead scoring & creation
│   │   │   ├── gpu_management_agent.py       ← GPU cluster health & scaling
│   │   │   ├── vision_agent.py               ★ Multi-modal VLM agent (image + text)
│   │   │   └── action_agent.py               ★ VLA agent for robotic control
│   │   │
│   │   └── tools/                            ← Shared tool functions used by agents
│   │       ├── __init__.py
│   │       ├── inference_tools.py            ← Auto-detection of inference backend
│   │       ├── odoo_tools.py                 ← MCP-Odoo wrappers (search, create, etc.)
│   │       ├── ros2_tools.py                 ★ ROS 2 bridge (move_arm, navigate, get_sensor)
│   │       └── iot_tools.py                  ★ MQTT subscriber for IoT sensor data
│   │
│   ├── agent/                                ← Distributed GPU agent (runs on every GPU node)
│   │   ├── agent.py                          ★ Main daemon – registration, WireGuard, GPUStack worker
│   │   ├── wg_setup.py                       ← WireGuard key generation and config management
│   │   ├── isolate.py                        ← Container runtime selection (gVisor / Docker)
│   │   ├── wg_dns_watchdog.py                ← DNS re-resolution for dynamic IPs
│   │   ├── tee_detect.py                     ← Detects TEE/Confidential Computing capabilities
│   │   ├── edge_detect.py                    ★ Detects Jetson, Raspberry Pi, Coral TPU
│   │   ├── modes/
│   │   │   ├── __init__.py
│   │   │   ├── trusted_multi_gpu.py          ← WireGuard full-mesh for internal pools
│   │   │   └── untrusted_public.py           ← WireGuard hub-and-spoke for freelancer pools
│   │   ├── requirements.txt                  ← Python dependencies for the agent
│   │   ├── nettrades-agent.service           ← systemd unit file (Linux)
│   │   ├── install-agent.sh                  ← One-click Linux/macOS installer
│   │   └── client-wireguard-installer.ps1    ← Windows installer with WireGuard DNS watchdog
│   │
│   └── scripts/                              ← Training and data-quality scripts
│       ├── unsloth_single_gpu_training.py    ← Single-GPU fine-tuning with Unsloth
│       ├── axolotl_fsdp_config.yaml          ← Multi-GPU FSDP2 configuration for Axolotl
│       ├── axolotl_multi_node_launch.sh      ← Launcher for multi-node Axolotl training
│       ├── axolotl_vlm_fsdp_config.yaml      ← for Vision-Language Model fine-tuning 
│       ├── unsloth_requirements.txt          ← Pinned Unsloth dependencies
│       └── requirements-data-quality.txt     ★ Dependencies for Data-Juicer & DEITA
│
├── odoo-modules/                            ★ LGPL-3.0 – Your custom Odoo plugins
│   ├── LICENSE.txt                           ← Full LGPL-3.0 text
│   │
│   ├── nettrades_core/                       ← Core marketplace & AI integration
│   │   ├── __init__.py
│   │   ├── __manifest__.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── res_partner.py                ← Extended partner (skills, reputation, Good Answer)
│   │   │   ├── hr_job.py                     ← Job postings with AI matching
│   │   │   ├── project_project.py            ← Project ↔ Forgejo integration
│   │   │   ├── nettrades_user_match.py       ← AI match results
│   │   │   ├── nettrades_skill.py            ← Skill catalog
│   │   │   └── nettrades_field.py            ★ Professional field with quality, training & voting settings
│   │   ├── security/
│   │   │   ├── nettrades_security.xml        ← User groups (Job Seeker, Freelancer, etc.)
│   │   │   └── ir.model.access.csv           ← Access rights for all custom models
│   │   ├── views/
│   │   │   ├── res_partner_views.xml
│   │   │   ├── hr_job_views.xml
│   │   │   ├── project_views.xml
│   │   │   ├── nettrades_review_views.xml
│   │   │   └── nettrades_field_views.xml     ★ Field admin screens (qualification, training, quality)
│   │   └── data/
│   │       └── nettrades.skill.csv            ← Seed data for skills
│   │
│   ├── nettrades_ask_someone/                ← "Ask Someone" – expert help marketplace
│   │   ├── __init__.py
│   │   ├── __manifest__.py
│   │   ├── controllers/__init__.py, main.py               ← Session creation, matching, escrow
│   │   ├── models/ (expert_session, ask_someone_config, escrow_hold, expert_agreement)
│   │   ├── security/ir.model.access.csv
│   │   ├── views/ (ask_someone_config_views.xml, expert_session_views.xml)
│   │   └── data/expert_agreement_template.xml ← Updated agreement with AI training transparency
│   │
│   ├── nettrades_good_answer/                ← "Good Answer" voting & fine-tuning pipeline
│   │   ├── __init__.py
│   │   ├── __manifest__.py
│   │   ├── controllers/main.py               ← Vote recording
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── good_answer_vote.py
│   │   │   ├── user_field_reputation.py      ★ Reputation decay, auto-adjust weights
│   │   │   ├── qualified_professional.py
│   │   │   ├── llm_feedback.py               ← Training data extraction
│   │   │   ├── ft_dataset.py                 ★ Dataset export + quality pipeline trigger
│   │   │   ├── ft_training_job.py
│   │   │   ├── nettrades_field.py            ← Field model extension
│   │   │   └── ft_dataset_contribution.py    ← Indirect reputation tracking
│   │   ├── security/ir.model.access.csv
│   │   ├── views/ (qualified_professional_views.xml, good_answer_config_views.xml, ft_dataset_views.xml)
│   │   └── data/cron.xml                     ★ All scheduled jobs (feedback, decay, auto-qualify, auto-adjust)
│   │
│   ├── nettrades_gpu_admin/                  ← GPU cluster administration dashboard
│   │   ├── __init__.py
│   │   ├── __manifest__.py                   ★ Updated to include multimodal_config
│   │   ├── controllers/main.py               ← Agent registration, WireGuard peers, fine-tuning endpoints
│   │   ├── models/
│   │   │   ├── gpu_cluster.py                ★ Cluster model with utilisation alert & fine-tuning fields
│   │   │   ├── gpu_cluster_subnet.py
│   │   │   ├── gpu_node.py                   ★ Node model with TEE, edge-device, watchdog
│   │   │   ├── gpu_sharing_schedule.py
│   │   │   ├── gpu_token_economics.py
│   │   │   └── multimodal_config.py          ★ System-wide toggles for multi-modal, robotics, IoT, edge
│   │   ├── security/
│   │   │   ├── gpu_admin_security.xml
│   │   │   └── ir.model.access.csv
│   │   ├── views/
│   │   │   ├── gpu_cluster_views.xml         ★ Cluster config with "Next Steps" note
│   │   │   ├── gpu_node_views.xml            ★ Node detail with Edge Device, Checklist, TEE guidance
│   │   │   ├── gpu_schedule_views.xml
│   │   │   ├── gpu_token_economics_views.xml
│   │   │   ├── gpu_dashboard_templates.xml   ← Owl dashboard + fine-tuning panel
│   │   │   ├── menu_items.xml
│   │   │   └── multimodal_config_views.xml   ★ Admin screen for multi-modal & edge settings
│   │   ├── data/cron.xml                     ← Watchdog & utilisation alert cron jobs
│   │   └── static/src/
│   │       ├── js/ (dashboard.js, node_manager.js, network_scan.js, wireguard_manager.js)
│   │       └── scss/dashboard.scss
│   │
│   ├── nettrades_gpustack_adapter/           ← Bridge between GPUStack API and Odoo models
│   │   ├── __init__.py
│   │   ├── __manifest__.py
│   │   ├── controllers/gpustack_api.py
│   │   └── models/gpustack_sync.py           ← Worker & token usage sync with retry logic
│   │
│   ├── nettrades_queue/                      ← Meta-module to auto-load OCA queue_job
│   │   ├── __init__.py
│   │   └── __manifest__.py
│   │
│   ├── nettrades_onboarding/                 ← Smart onboarding wizard & CV parsing
│   ├── nettrades_job_matching/               ← Conversational job search & one-click apply
│   ├── nettrades_proposals/                  ← Freelancer proposals & milestone payments
│   ├── nettrades_lead_scoring/               ← Lead scoring from platform activity
│   ├── nettrades_research/                   ← Research project marketplace
│   ├── nettrades_chatbot/                    ← AI chatbot widget + "Ask Someone" / "Good Answer" buttons
│   ├── nettrades_notifications/              ← In-app notification centre, reviews, disputes
│   └── nettrades_pwa/                        ← Mobile PWA manifest & service worker
│
├── third-party/                             ★ UNMODIFIED – All third-party dependencies
│   ├── README.md                             ← "Do not modify any files in this directory."
│   ├── odoo/                                 ← Odoo 19 CE (LGPL-3.0) – clone
│   ├── website_sale_marketplace/             ← ERPGAP marketplace addon (LGPL-3.0) – clone
│   ├── odoo_llm/                             ← Apexive LLM modules (LGPL-3.0) – clone, merged 18.0→19.0
│   ├── odoo_llm_compat/                      ← Compatibility shim for Odoo 19
│   │   ├── __init__.py                 
│   │   └── __manifest__.py 
│   ├── payment_stripe_ce/                    ← OCA Stripe payment (LGPL-3.0) – clone
│   │   ├── __init__.py                 
│   │   └── __manifest__.py 
│   ├── queue_job/                            ← OCA Job Queue (LGPL-3.0) – clone
│   └── mcp-odoo/                             ← MCP-Odoo bridge (MIT) – clone
│
├── deploy/                                  ★ AGPL-3.0 – Deployment configurations
│   ├── LICENSE.txt
│   ├── docker/                               ← Single-VM Docker Compose deployment
│   │   ├── docker-compose.yml                ★ Full stack: Valkey, GPUStack, Forgejo, etc.
│   │   ├── .env.example                      ← Template for secrets
│   │   ├── .env.generator.sh                 ← One-command secret generator
│   │   ├── init-db.sql                       ← pgvector extension creation
│   │   ├── prometheus.yml                    ★ Scrape config (GPUStack ports corrected)
│   │   ├── alert-rules.yml
│   │   ├── alertmanager.yml
│   │   ├── config/
│   │   │   └── odoo.conf                     ★ Odoo configuration (Valkey sessions, addons path)
│   │   ├── deploy-single.sh                  ★ Idempotent deployment script
│   │   ├── install-nettrades.sh              ★ Interactive installation wizard
│   │   ├── nettrades-ai-detect               ← Shared hardware detection library
│   │   ├── migrate-to-gpu.sh                 ← CPU → GPU migration script
│   │   └── security-harden.sh                ← Ubuntu VM security hardening
│   │
│   └── kubernetes/                           ★ Kubernetes (Talos + Proxmox) manifests
│       ├── talos
│       │   ├── secrets.yaml.example
│       │   └── talos-proxmox/              ← Talos VM provisioning (main.tf, variables.tf, etc.)
│       │           ├── main.tf
│       │           ├── variables.tf
│       │           ├── outputs.tf
│       │           ├── terraform.tfvars.example
│       │           ├── deploy-infra.sh          (Cilium v1.19.3, Longhorn v1.11.1, Traefik v3.6.13)
│       │           └── patches/
│       │                 ├── controlplane.yaml.tpl
│       │                 └── worker.yaml.tpl
│       ├── apps/
│       │     ├── namespaces.yaml
│       │     ├── frontend/
│       │     │    ├── odoo-pvc.yaml
│       │     │    ├── odoo-deployment.yaml
│       │     │    └── kustomization.yaml               
│       │     ├── backend/
│       │     │    ├── postgres-cluster.yaml
│       │     │    ├── postgres-scheduled-backup.yaml
│       │     │    ├── redis-statefulset.yaml
│       │     │    └── kustomization.yaml
│       │     ├── ai/
│       │     │    ├── llama-cpp.yaml
│       │     │    ├── langgraph-deployment.yaml
│       │     │    ├── mcp-deployment.yaml
│       │     │    ├── vllm-deployment.yaml (optional)
│       │     │    └── kustomization.yaml
│       │     ├── forgejo/
│       │     │    ├── forgejo-internal.yaml
│       │     │    ├── forgejo-client.yaml
│       │     │    └── kustomization.yaml
│       │     ├── gpustack/
│       │     │    ├── gpustack-server.yaml
│       │     │    ├── wg-peer-manager.yaml
│       │     │    └── kustomization.yaml
│       │     ├── monitoring/
│       │     │    ├── kustomization.yaml
│       │     │    └── grafana-values.yaml
│       │     ├── registry/
│       │     │    ├── registry-deployment.yaml
│       │     │    └── kustomization.yaml
│       │     └── runners/
│       │           └── kustomization.yaml
│       ├── distributed-gpu/controller/ 
│       │     ├── gpustack-server.yaml
│       │     ├── gpustack-company-server.yaml
│       │     ├── wg-peer-manager
│       │     │     ├── main.go
│       │     │     ├── go.mod
│       │     │     ├── go.sum (generated by go mod tidy)
│       │     │     └── Dockerfile
│       │     ├── gvisor-runtime-class.yaml
│       │     ├── attestation-cron.yaml
│       │     ├── deploy-controller.sh
│       │     └── install-gpustack-company.sh
│       ├── ingress/ingress.yaml
│       ├── argocd/application.yaml
│       ├── kustomization.yaml
│       ├── deploy-k8s-base.sh                ★ K8s deployment script
│       ├── postgres-restore-guide.md
│       └── .env.example
│
├── docs/                                    ← Documentation & legal agreements
│   ├── README-QUICKSTART.md                  ★ One-page deployment cheat sheet
│   ├── README-LICENSING.md                   ★ Dual-licensing explanation
│   ├── TERMS-OF-SERVICE.md                   ★ Maximum legal protection for NETTRADES
│   ├── EXPERT-AGREEMENT.md                   ★ Professional agreement with indemnification
│   └── architecture/                         ← (future architecture diagrams)
│
├── scripts/                                 ← Build & setup orchestration (MIT)
│   ├── nettrades-setup.sh                    ★ Orchestrator – the only script the operator runs
│   ├── phase-dev-env.sh                      ★ Dev environment setup
│   ├── phase-deploy.sh                       ★ Single-VM deployment
│   ├── phase-add-gpu.sh                      ★ GPU addition
│   ├── phase-scale.sh                        ★ Kubernetes upgrade
│   └── create-nettrades-projects.sh          ★ Full scaffold & clone script
│
├── requirements-dev.txt                      ← Top-level Python dev dependencies
└── .gitignore


## 5. Key Component Summaries & Critical Code

### 5.1 LangGraph Supervisor (src/core/supervisor.py)

The supervisor classifies user intents and routes to the correct business sub-agent. It also performs clinical screening for medical/legal questions.
python

class SupervisorState(dict):
    pass

def build_supervisor():
    backend = get_inference_backend()   # auto-detects GPUStack / vLLM / llama.cpp
    llm = ChatOpenAI(...)
    # compile sub-agents
    recruitment_agent = create_recruitment_agent()
    freelance_agent = create_freelance_agent()
    lead_gen_agent = create_lead_gen_agent()
    gpu_management_agent = create_gpu_management_agent()
    vision_agent = create_vision_agent()
    action_agent = create_action_agent()

    workflow = StateGraph(dict)
    workflow.add_node("classify", classify)
    workflow.add_node("medical_screening", medical_screening)
    workflow.add_node("route", route)
    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "medical_screening")
    workflow.add_edge("medical_screening", "route")
    workflow.add_edge("route", END)
    return workflow.compile()

Intent routing:

*    recruitment → recruitment_agent

*    freelance / project → freelance_agent

*    lead → lead_gen_agent

*    gpu / cluster → gpu_management_agent

*    vision (if image uploaded) → vision_agent

*    action (robotic command) → action_agent

*    medical / legal → first screened, then general LLM

*    general → general inference

### 5.2 FastAPI Application (src/core/app.py)

The main entry point for the LangGraph service. Provides /invoke (authenticated inference), /health (liveness probe), and /metrics (Prometheus).

python

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(DB_URI) as checkpointer:
        await checkpointer.setup()
        graph = build_supervisor()
        graph.checkpointer = checkpointer
        ml_models["graph"] = graph
        yield

Environment: DATABASE_URL, LLM_BASE_URL, LANGGRAPH_API_KEY, GPUSTACK_SERVER_URL, etc.

### 5.3 Distributed GPU Agent (src/agent/agent.py)

The agent runs on every GPU node. Key responsibilities:

*    Auto-install WireGuard (Linux)

*    Generate hardware-bound node ID (TPM EK or MAC hash)

*    Detect GPUs via nvidia-smi

*    Detect TEE capabilities (NVIDIA CC, Intel SGX, AMD SEV, etc.)

*    Detect edge devices (Jetson, Raspberry Pi, Coral TPU)

*    Register with Odoo (/api/v1/gpu/register) with all hardware info

*    Bring up WireGuard with hub-and-spoke or mesh configuration

*    Start GPUStack worker inside gVisor (public pool) or Docker (internal)

*    Start WireGuard DNS watchdog (daemon thread)

*    Periodically refresh GPUStack token

Registration payload example:

python

payload = {
    "node_id": node_id,
    "hostname": socket.gethostname(),
    "gpus": gpus,
    "wireguard_public_key": get_wireguard_pubkey(),
    "os": platform.system().lower(),
    "tee_capabilities": tee_caps,
    "edge_device_info": edge_info,
}

### 5.4 Odoo Core Models



nettrades.field (odoo-modules/nettrades_core/models/nettrades_field.py)

Central model for configuring every aspect of a professional field:

*    Qualification rules (only_qualified, auto_karma_qualify)

*    Voting weights (base_points_per_vote, qualified_points_per_vote, auto_adjust_weights)

*    Expert answer usage (expert_answers_trainable, indirect_reputation_points)

*    Fine-tuning backend (finetune_provider, base_model, hyperparameters)

*    Data-Juicer quality filter (enable_data_juicer, data_juicer_min_quality_score, etc.)

*    DEITA LLM-as-Judge (enable_deita_scoring, deita_min_complexity, etc.)

*    Advanced training (A/B testing, GRPO, benchmark evaluation, vote thresholds)

All settings have detailed help strings for the administrator.



gpu.node (odoo-modules/nettrades_gpu_admin/models/gpu_node.py)

Represents a registered GPU/edge machine:

*    WireGuard identity

*    GPU inventory (JSON)

*    Pool assignment (internal / public)

*    Container runtime (gvisor / docker)

*    OS auto-detected (linux / windows / darwin)

*    TEE capabilities (JSON)

*    Edge device info (JSON) – Jetson, Raspberry Pi, Coral TPU

*    GPUStack worker ID

*    Status, token accounting, reputation, attestation

*    Methods: action_remove_node, action_reassign_pool, _cron_health_watchdog



ft.dataset (odoo-modules/nettrades_good_answer/models/ft_dataset.py)

Fine-tuning dataset with built-in quality pipeline:

*    export_to_jsonl() – exports eligible feedback, applying vote thresholds

*    _run_data_juicer_pipeline() – runs Alibaba Data-Juicer for quality scoring, dedup, PII

*    _run_deita_scoring() – runs DEITA (LLM-as-Judge) via distilabel

*    action_trigger_finetune() – full pipeline: export → Data-Juicer → DEITA → record contributions → create training job → call LangGraph



user_field_reputation (odoo-modules/nettrades_good_answer/models/user_field_reputation.py)

    _cron_decay_reputation() – daily 1% decay for inactive experts

    _cron_auto_qualify_by_karma() – hourly promotion of high-reputation users

    _cron_auto_adjust_weights() – auto-adjusts qualified_points_per_vote based on community composition


### 5.5 Administration Views (Key Screens)

#### GPU Node Detail (gpu_node_views.xml)

Tabs: Hardware, Pool & Isolation, Hardware Security (TEE), Edge Device (new), Network (WireGuard), Earnings & Reputation, Administrator Checklist.

Checklist guides the admin through required steps (agent installed, WireGuard active, GPUStack registered, runtime set, etc.).


#### GPU Cluster Configuration (gpu_cluster_views.xml)

Tabs: Configuration, WireGuard, Registered Subnets, GPU Nodes, Token Economics, Fine-Tuning.

“Next Steps” note links to Multi-Modal & Edge Settings.


#### Multi-Modal & Edge Settings (multimodal_config_views.xml)

Toggles for:

    Multi-Modal Inferencing (requires VLM deployed in GPUStack)

    Robotics Integration (requires ROS 2 bridge + VLA model)

    IoT Integration (requires MQTT broker)

    Edge Device Support (auto-detected by agent)

Each section includes a “Before enabling” checklist with exact steps.


#### Professional Field Form (nettrades_field_views.xml)

Tabs: General, Qualification & Karma, Training & AI Learning, Data-Juicer Quality, LLM-as-Judge (DEITA), Advanced Training.

Every field has help text; dependency notes remind admins to install libraries.

## 6. Deployment Scripts

The project ships with a phase-based orchestrator (scripts/nettrades-setup.sh):
text

Phase 1 – dev-env    : scaffold + clone repos + install dependencies
Phase 2 – deploy     : single-VM production stack (no GPU required)
Phase 3 – add-gpu    : migrate CPU→GPU (installs vLLM)
Phase 4 – scale      : upgrade to Kubernetes (Talos + K8s)

All phase scripts auto-detect missing prerequisites and run earlier phases if needed.

### Key deployment files:

*    deploy/docker/docker-compose.yml – full stack with Valkey, GPUStack, Forgejo, LangGraph, llama.cpp, Prometheus/Grafana.

*    deploy/docker/config/odoo.conf – Valkey sessions, correct addons_path.

*    deploy/kubernetes/ – all K8s manifests for production HA deployment.

## 7. Environment Variables (.env.example)

text

DOMAIN=nettrades.ai
POSTGRES_PASSWORD=...  ADMIN_PASSWORD=...
FORGEJO_DB_PASSWORD=...  FORGEJO_SECRET_KEY=...  JWT_SECRET=...
GRAFANA_PASSWORD=...
LLAMA_API_KEY=dummy  LANGGRAPH_API_KEY=...
ODOO_API_KEY=...  MCP_API_KEY=...
GPUSTACK_JWT_SECRET=...
WIREGUARD_PRIVATE_KEY=...  WIREGUARD_PUBLIC_KEY=...
DATABASE_URL=postgresql://odoo:...@postgres:5432/odoo

## 8. Quickstart Guide (Development)

A.    Run scripts/create-nettrades-projects.sh to scaffold and clone repos.

B.    Run ./scripts/nettrades-setup.sh → select Phase 1.

C.    Start Odoo:
    bash

    python third-party/odoo/odoo-bin -c deploy/docker/config/odoo.conf \
        --addons-path=third-party/odoo/addons,odoo-modules

D.    Install Odoo modules in order: standard (CRM, Project, etc.) → community (llm, llm_pgvector, etc.) → NETTRADES custom modules (nettrades_core first, then the rest).

## 9. Future Development Notes

*    Data-Juicer & DEITA are optional; install dependencies only when enabled in the admin UI.

*    Multimodal features (vision, robotics, IoT) are off by default; they require separate hardware/dependencies.

*    Edge device support auto-detects Jetson, Raspberry Pi, Coral TPU; the agent reports device info to Odoo.

*    The project uses dual licensing – AGPL-3.0 for original code, LGPL-3.0 for Odoo plugins.

*    All external APIs are called with timeouts and retry logic; LangGraph uses PostgresSaver for crash recovery.
