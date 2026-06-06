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

Component			|    Version		|    License		|    Purpose


Odoo				|    19.0 CE		|    LGPL-3.0		|    ERP, marketplace, CRM, HR, Projects, Accounting

PostgreSQL + pgvector		|    18.1 (via CNPG)	|    PostgreSQL License	|    Business data, vector embeddings, LangGraph checkpoints

Valkey				|    8-alpine		|    BSD-3-Clause		|    Session storage, ORM cache, bus notifications

Forgejo				|    15.0 LTS		|    GPL-3.0+		|    Self-hosted Git + CI/CD

Traefik				|    v3.6.13		|    MIT			|    Reverse proxy, automatic Let's Encrypt TLS

LangGraph			|    ≥1.2.0			|    MIT			|    Multi-agent orchestration, durable execution

LangGraph Checkpoint Postgres	|    ≥3.0.3			|    MIT    |    Durable checkpoint storage in PostgreSQL

GPUStack			|    v2.1.2			|    Apache-2.0		|    GPU cluster manager, inference engine, token metering

llama.cpp			|    server-cpu/server-cuda	|    MIT			|    CPU inference fallback

Unsloth (core)			|    2026.5.2		|    Apache-2.0		|    Single-GPU fine-tuning

Axolotl				|    0.16.1+		|    Apache-2.0		|    Multi-GPU fine-tuning with FSDP2

WireGuard			|    kernel module		|    GPL-2.0		|    Kernel-level network isolation

gVisor				|    release-20260420.0	|    Apache-2.0		|    Syscall-level container isolation

OCA queue_job			|    19.0 branch		|    LGPL-3.0		|    Background job processing

OCA payment_stripe		|    19.0 branch		|    LGPL-3.0		|    Stripe payment acquirer

Talos Linux			|    1.13.2			|    MPL-2.0		|    Immutable K8s OS

Kubernetes			|    1.36 (via Talos)	|    Apache-2.0		|    Container orchestration

Cilium				|    1.19.3			|    Apache-2.0		|    CNI with WireGuard encryption

Longhorn			   |    1.11.1			|    Apache-2.0		|    Distributed block storage

CloudNativePG			|    1.29.0			|    Apache-2.0		|    PostgreSQL operator with HA & backups

cert-manager			|    1.20.2			|    Apache-2.0		|    TLS certificate automation

MetalLB				|    0.15.3			|    Apache-2.0		|    Bare-metal load balancer

Argo CD				|    3.3.8			|    Apache-2.0		|    GitOps continuous delivery

NVIDIA GPU Operator		|    v26.3.1		|    Apache-2.0		|    GPU support on Kubernetes

KubeRay				|    1.6.1			|    Apache-2.0		|    Ray on Kubernetes for vLLM

Prometheus			|    v3.8.0			|    Apache-2.0		|    Metrics collection

Grafana				|    12.4.2			|    AGPL-3.0 (unmodified)	|    Dashboards

## 3. Licensing 

NETTRADES uses a dual-licensing approach to protect the platform while keeping it open:

*    src/ (core orchestrator, agent, training scripts): AGPL-3.0 — strong copyleft; any modifications must be shared if offered as a network service. A commercial license is available for enterprises needing closed-source use.

*    odoo-modules/ (custom Odoo plugins): LGPL-3.0 — compatible with Odoo’s own license; plugins can be proprietary as long as they don’t copy Odoo core code.

*    third-party/: All third-party components retain their original licenses (LGPL, MIT, Apache-2.0, etc.).

*    deploy/: Deployment scripts and configurations are AGPL-3.0.

*    docs/: Documentation under Creative Commons Attribution 4.0.

*    scripts/: Build and setup scripts are MIT.

A Contributor License Agreement (CLA) is in CONTRIBUTING.md to ensure contributions can be re-licensed under the commercial license.

## 4. Transaction control and error handling notes

    • Odoo transaction control – all database writes inside a single request are automatically committed or rolled back by the framework. If the registration fails, the node record is not created.

    • LangGraph checkpointing – every node state is saved to PostgreSQL via PostgresSaver. If a machine crashes during training or inference, the workflow resumes from the last checkpoint without duplicating work.

    • Agent retry logic – the agent retries registration with exponential backoff and never gives up on transient failures. WireGuard and GPUStack workers are restarted automatically after a power‑cycle thanks to persistent config files and the DNS watchdog.

    • GPUStack worker recovery – GPUStack reschedules model instances onto other healthy workers within minutes of a node going offline.

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

The deployment scripts are in: 

nettrades-platform\scripts

The file

nettrades-platform\scripts\Readme.txt

Provided the instructions. The script “create-nettrades-projects.sh” has already been ran and many of the files were copied over from the previous deepseek context window into the file structure, so it could be ignored.

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
