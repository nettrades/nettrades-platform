# ARCHITECT PERSPECTIVE — Logical Architecture Diagram

Purpose: Shows the logical layers, components, and data flows across the entire platform, including all major subsystems.

---

## ARCHITECT PERSPECTIVE — Logical Architecture Diagram

```mermaid
flowchart TB
    subgraph External["?? External World"]
        Users["End Users<br>(Web Browsers)"]
        APIClients["API Clients<br>(Third-party)"]
        Robots["Robotic Clients<br>(ROS 2 / MCP)"]
        JobBoards["External Job Boards<br>(LinkedIn, Indeed, Upwork)"]
    end

    subgraph Gateway["?? API Gateway Layer"]
        Traefik["Traefik<br>????????????????<br>• TLS Termination<br>• JWT / OAuth2 Auth<br>• Rate Limiting<br>• Path-based Routing"]
    end

    subgraph Application["?? Application Layer"]
        direction TB
        
        subgraph Odoo["Odoo 19 CE Application Server"]
            WebControllers["Web Controllers<br>(/website, /forum, /shop)"]
            APIControllers["JSON-RPC API Controllers<br>(/api/v1/*)"]
            
            subgraph Modules["Custom Odoo Modules"]
                CoreModule["nettrades_core<br>????????????????<br>Fields • Qualification • Voting"]
                GoodAnswerModule["nettrades_good_answer<br>????????????????<br>Reputation • Fine-Tuning • Datasets"]
                GPUAdminModule["nettrades_gpu_admin<br>????????????????<br>GPU Registry • Pools • TEE"]
                JobMatchingModule["nettrades_job_matching<br>????????????????<br>CV Analysis • Match Scoring"]
                ProposalsModule["nettrades_proposals<br>????????????????<br>Freelancer Matching • Rates"]
                LeadScoringModule["nettrades_lead_scoring<br>????????????????<br>Lead Generation • Scoring"]
                AskSomeoneModule["nettrades_ask_someone<br>????????????????<br>Consultations • Stripe Escrow"]
                ChatbotModule["nettrades_chatbot<br>????????????????<br>Session Management • Context"]
            end
            
            CronJobs["Scheduled Cron Jobs<br>????????????????<br>• Reputation Decay (Daily)<br>• Auto-Qualification (Hourly)<br>• Fine-Tuning Trigger"]
        end
        
        subgraph LangGraph["LangGraph Orchestrator (FastAPI)"]
            SupervisorGraph["Supervisor Graph<br>????????????????<br>classify ? medical_screening ? route"]
            
            subgraph Agents["Sub-Agents"]
                RecruitmentAgent["Recruitment Agent"]
                FreelanceAgent["Freelance Agent"]
                LeadGenAgent["Lead Gen Agent"]
                GPUManagementAgent["GPU Management Agent"]
                VisionAgent["Vision Agent"]
                ActionAgent["Action Agent"]
                GeneralLLM["General LLM"]
            end
            
            Checkpointer["PostgresSaver Checkpointer"]
        end
        
        subgraph GPUStack["GPUStack Manager"]
            InferenceEngine["Inference Engine<br>(OpenAI-compatible API)"]
            TokenMeter["Token Metering"]
            WorkerPool["Worker Pool Manager<br>• gVisor (Public)<br>• Docker (Internal)"]
        end
    end

    subgraph Data["?? Data & Persistence Layer"]
        PostgreSQL["PostgreSQL + pgvector<br>????????????????<br>• Odoo Business Data<br>• Vector Embeddings<br>• LangGraph Checkpoints"]
        Valkey["Valkey (Redis-compatible)<br>????????????????<br>• Session Cache<br>• Pub/Sub Notifications<br>• Rate Limiting Counters"]
        Longhorn["Longhorn Storage<br>????????????????<br>• CVs & Attachments<br>• Fine-Tuning Datasets<br>• Model Weights"]
    end

    subgraph ML["?? ML Pipeline (Cron-Triggered)"]
        DataJuicer["Data-Juicer<br>????????????????<br>Quality Filtering • Dedup"]
        DEITA["DEITA Scorer<br>????????????????<br>LLM-as-Judge • Complexity"]
        Unsloth["Unsloth/Axolotl<br>????????????????<br>LoRA/QLoRA Fine-Tuning"]
        ModelRegistry["Model Registry<br>????????????????<br>Versioning • Metadata"]
    end

    subgraph Security["??? Security & Network Fabric"]
        WireGuard["WireGuard VPN Mesh<br>????????????????<br>Encrypted Node Communication"]
        gVisor["gVisor Sandbox<br>????????????????<br>Syscall-level Isolation"]
        RBAC["RBAC & Policy Engine<br>????????????????<br>Odoo Security Groups"]
    end

    %% Connections
    Users -->|HTTPS| Traefik
    APIClients -->|HTTPS| Traefik
    Robots -->|HTTPS/WebSocket| Traefik
    JobBoards -->|RSS/API| LeadScoringModule

    Traefik -->|"/"| WebControllers
    Traefik -->|"/api/v1/*"| APIControllers
    Traefik -->|"/invoke"| LangGraph

    WebControllers --> Modules
    APIControllers --> Modules
    ChatbotModule -->|Async HTTP| LangGraph

    LangGraph --> SupervisorGraph
    SupervisorGraph --> Agents
    Agents -->|Reads/Writes| Modules
    Agents -->|Inference| InferenceEngine
    
    Modules -->|SQL| PostgreSQL
    Modules -->|Cache| Valkey
    Modules -->|Files| Longhorn
    
    LangGraph -->|Checkpoints| PostgreSQL
    
    CronJobs -->|Trigger| GoodAnswerModule
    GoodAnswerModule -->|Export| DataJuicer
    DataJuicer --> DEITA
    DEITA --> Unsloth
    Unsloth --> ModelRegistry
    ModelRegistry -->|Register| InferenceEngine
    ModelRegistry -->|Store| Longhorn

    InferenceEngine -->|Manages| WorkerPool
    WorkerPool -->|Isolates| gVisor
    GPUManagementAgent -->|Registers| APIControllers
    GPUManagementAgent -->|Encrypted Tunnel| WireGuard

    classDef external fill:#e3f2fd,stroke:#1565c0;
    classDef gateway fill:#fff3e0,stroke:#e65100;
    classDef app fill:#f3e5f5,stroke:#6a1b9a;
    classDef data fill:#e8f5e9,stroke:#2e7d32;
    classDef ml fill:#fce4ec,stroke:#c62828;
    classDef security fill:#ffebee,stroke:#b71c1c;

    class External external;
    class Gateway gateway;
    class Application,Odoo,LangGraph,GPUStack app;
    class Data data;
    class ML ml;
    class Security security;