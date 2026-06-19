# LangGraph Agent State Machine Diagram

The diagram covers the main Supervisor graph, all sub-agents, their internal states, and the overall flow.

##  Detailed Explanation of the State Machine
## 1. Supervisor Graph (The Orchestrator)
    
The supervisor is the core entry point for all user requests. It is built in src/core/supervisor.py and compiled in src/core/app.py with a durable PostgresSaver checkpointer.
Node	Function	Key Logic
classify	Intent Classification	Extracts the last user message, checks for an uploaded image (image_base64), and calls an LLM to classify the intent into one of: recruitment, freelance, lead_gen, gpu_management, medical, legal, action, vision, or general.
medical_screening	Clinical/Legal Screening	Only triggered for medical or legal intents. Uses a follow-up counter (MAX_FOLLOWUP_ROUNDS = 3) to ask clarifying questions about comorbidities or medication interactions before deciding if enough information is present to answer safely.
route	Intent Router	Dispatches to the appropriate sub-agent based on state['intent']. If screening_done is False, it loops back. Otherwise, it routes to the matching agent or falls back to a general LLM.
    
State Object (SupervisorState): A Python dict that carries:
    
messages: List of conversation messages
    
intent: Classified intent string
    
followup_count: Number of screening follow-ups
    
screening_done: Boolean flag
    
image_base64: Base64-encoded image (if any)
    
Results from sub-agents (e.g., analysis, action_plan)
    
## 2. Sub-Agents (Business Logic)
    
Each sub-agent is a LangGraph sub-graph that handles a specific domain.
Agent	File	Purpose
Recruitment Agent	src/core/agents/recruitment_agent.py	Analyzes CVs against job postings, computes match scores, and generates candidate shortlists.
Freelance Agent	src/core/agents/freelance_agent.py	Matches freelancers to projects based on skills, availability, and rates.
Lead Gen Agent	src/core/agents/lead_gen_agent.py	Scans job postings and projects to automatically create and score lead records.
GPU Management Agent	src/core/agents/gpu_management_agent.py	Manages GPU cluster health, node registration, pool assignments, and token economics.
Vision Agent	src/core/agents/vision_agent.py	Handles image + text queries via a Vision-Language Model (VLM) like Qwen2-VL or LLaVA. Requires "Multi-Modal Inferencing" to be enabled in admin. Sends the image as a base64 data URL and returns analysis in state['analysis'].
Action Agent	src/core/agents/action_agent.py	Translates natural language commands into robotic actions. Uses a Vision-Language-Action (VLA) model to generate a JSON action plan (move_arm, navigate, grasp, release, speak) and dispatches via ROS 2 or an MCP-Robotics bridge. Two nodes: plan_action ? dispatch.

## 3. GPU Node Agent (Per-Node Daemon)
    
The GPU Node Agent runs on every GPU machine in the cluster. It is a standalone script (src/agent/agent.py) that performs the following steps:
    
ensure_wireguard() – Auto-installs WireGuard if missing (supports Ubuntu/Debian/CentOS/RHEL).
    
get_or_create_node_id() – Generates a hardware-bound node ID, preferring TPM Endorsement Key (EK) hash, falling back to MAC address hash.
    
get_gpu_info() – Detects NVIDIA GPUs via nvidia-smi.
    
get_tee_summary() – Detects TEE capabilities (NVIDIA CC, Intel SGX, AMD SEV).
    
get_edge_device_info() – Detects edge devices (Jetson, Raspberry Pi, Coral TPU).
    
register_with_odoo() – Registers with Odoo via POST /api/v1/gpu/register with retries and exponential backoff.
    
apply_wireguard_config() – Writes wg0.conf and brings up the WireGuard interface.
    
start_gpustack_worker() – Launches the GPUStack worker: uses gVisor for public pools (syscall-level isolation) and Docker directly for internal pools.
    
start_dns_watchdog() – Starts a daemon thread that keeps the WireGuard tunnel alive when the ISP changes the IP.
    
Token Refresh Loop – Every 600 seconds, refreshes the GPUStack worker token and restarts the worker.
    
## 4. Inference Backend Auto-Detection
    
The get_inference_backend() function in src/core/tools/inference_tools.py auto-detects the available inference backend with the following priority:
Priority	Backend	Environment Variable	Endpoint
1	GPUStack	GPUSTACK_SERVER_URL	{url}/v1-openai
2	vLLM	VLLM_BASE_URL	{url}/v1
3	llama.cpp (fallback)	LLM_BASE_URL	http://llama-cpp:8080/v1
    
All backends expose an OpenAI-compatible API, allowing LangChain's ChatOpenAI to work seamlessly.
## 5. Infrastructure & Persistence
    
FastAPI Application (src/core/app.py): Exposes /invoke (authenticated inference), /health (liveness probe), and /metrics (Prometheus) endpoints.
    
PostgresSaver: Provides durable checkpointing. Every node state is saved to PostgreSQL, so if a machine crashes during training or inference, the workflow resumes from the last checkpoint without duplicating work.
    
Prometheus Metrics: Tracks langgraph_requests_total (by intent) and langgraph_request_duration_seconds.
    
## 6. Odoo Integration
    
The platform is built on Odoo 19 Community Edition. Key Odoo models include:
Model	File	Purpose
nettrades.field	odoo-modules/nettrades_core/models/nettrades_field.py	Configures professional fields: qualification rules, voting weights, fine-tuning hyperparameters, Data-Juicer quality filters, DEITA LLM-as-Judge scoring.
gpu.node	odoo-modules/nettrades_gpu_admin/models/gpu_node.py	Represents registered GPU/edge machines: WireGuard identity, GPU inventory, pool assignment, TEE capabilities, edge device info, status, token accounting.
ft.dataset	odoo-modules/nettrades_good_answer/models/ft_dataset.py	Fine-tuning dataset with quality pipeline: export_to_jsonl(), Data-Juicer, DEITA scoring, and action_trigger_finetune().
user_field_reputation	odoo-modules/nettrades_good_answer/models/user_field_reputation.py	Cron jobs: daily 1% reputation decay for inactive experts, hourly auto-qualification by karma, auto-adjustment of voting weights.

## 7. Complete Request Flow
    
User sends a message (optionally with an image) to /invoke.
    
FastAPI receives the request, tracks metrics, and passes it to the compiled Supervisor graph.
    
The classify node determines the intent.
    
If the intent is medical or legal, the medical_screening node engages in a multi-turn dialogue (up to 3 rounds) to gather sufficient context.
    
The route node dispatches to the appropriate sub-agent:
    
recruitment ? Recruitment Agent
    
freelance ? Freelance Agent
    
lead_gen ? Lead Gen Agent
    
gpu ? GPU Management Agent
    
vision (if image present) ? Vision Agent
    
action ? Action Agent
    
medical/legal (after screening) ? General LLM
    
general ? General LLM
    
The sub-agent processes the request and returns a result.
    
The response is sent back to the user.
    
All state transitions are checkpointed to PostgreSQL for durability.

---

##  LangGraph Agent State Machine Diagram

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
    
    
    
