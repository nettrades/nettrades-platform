# Logical Solution Architecture Diagram

## 1. Overview

The NETTRADES platform is a self-improving, agentic AI system built on Odoo 19 CE, LangGraph, and GPUStack. It connects companies, freelancers, job-seekers, researchers, partners, and customers through a hub-and-spoke architecture with a unique GPU marketplace and closed-loop self-improvement.

The platform is designed for **autonomous enterprise operations** where AI agents handle recruitment, freelancing, GPU management, and business operations, continuously learning and improving from user interactions.

```mermaid

flowchart TD
    %% ========================================================================
    %% 1. EXTERNAL CLIENTS & ACCESS LAYER
    %% ========================================================================
    subgraph AccessLayer["🌐 External Access & Clients"]
        Browser["Web Browser (PWA)
        ━━━━━━━━━━━━━━━
        • Odoo Website / Discuss / Chat
        • Service Worker (offline support)
        • Progressive Web App manifest"]
        APIClient["External API Client
        ━━━━━━━━━━━━━━━
        • REST / JSON-RPC consumers
        • Third-party job board scrapers
        • Partner integrations"]
        RoboticClient["Robotic / Edge Client
        ━━━━━━━━━━━━━━━
        • ROS 2 nodes
        • MCP-Robotics bridge
        • IoT sensor data ingestion"]
        MobileApp["Mobile App
        ━━━━━━━━━━━━━━━
        • React Native / Flutter
        • Push notifications
        • Offline-first sync"]
    end

    %% ========================================================================
    %% 2. API GATEWAY & EDGE SECURITY
    %% ========================================================================
    subgraph Gateway["🔒 API Gateway & Edge (Traefik)"]
        TLSTerm["TLS Termination
        ━━━━━━━━━━━━━━━
        • Let's Encrypt Auto-Cert
        • HTTP/2 & WebSocket support
        • mTLS for internal services"]
        AuthZ["Authentication / Authorization
        ━━━━━━━━━━━━━━━
        • JWT Bearer token validation
        • OAuth2 / OpenID Connect proxy
        • API key management"]
        RateLimit["Rate Limiting & Routing
        ━━━━━━━━━━━━━━━
        • Path-based routing
        • Request throttling per tenant
        • Circuit breaker patterns"]
        WAF["Web Application Firewall
        ━━━━━━━━━━━━━━━
        • SQL injection prevention
        • XSS protection
        • DDoS mitigation"]
    end

    %% ========================================================================
    %% 3. APPLICATION SERVICES LAYER (BACKEND LOGIC)
    %% ========================================================================
    subgraph ApplicationLayer["⚙️ Application Services Layer"]
        direction TB

        subgraph OdooServer["Odoo 19 CE Application Server (Python)"]
            WebController["Web Controllers
            ━━━━━━━━━━━━━━━
            • /website, /forum, /shop
            • /ask_someone, /jobs
            • /freelance, /research"]
            APIController["JSON-RPC API Controllers
            ━━━━━━━━━━━━━━━
            • /api/v1/gpu/register
            • /api/v1/dataset/export
            • /api/v1/chatbot/invoke
            • /api/v1/bridge/route"]
            subgraph OdooModels["Odoo ORM Models (Business Logic)"]
                CoreModel["nettrades.core
                ━━━━━━━━━━━━━━━
                • Field qualification rules
                • Voting weight config
                • Auto-qualification by karma
                • Worker agent configuration"]
                GoodAnswer["nettrades.good_answer
                ━━━━━━━━━━━━━━━
                • Vote collection
                • Reputation decay (1% daily)
                • FT dataset eligibility
                • Quality scoring"]
                GPUAdmin["nettrades.gpu_admin
                ━━━━━━━━━━━━━━━
                • GPU node registry
                • TEE/Edge device metadata
                • Pool assignment (public/internal)
                • Utilisation monitoring"]
                JobMatching["nettrades.job_matching
                ━━━━━━━━━━━━━━━
                • CV parsing & scoring
                • Candidate shortlist generation
                • Skill extraction"]
                Proposals["nettrades.proposals
                ━━━━━━━━━━━━━━━
                • Freelancer skills matching
                • Rate suggestions
                • Proposal lifecycle"]
                LeadScoring["nettrades.lead_scoring
                ━━━━━━━━━━━━━━━
                • Lead generation from external feeds
                • Quality scoring
                • Conversion tracking"]
                AskSomeone["nettrades.ask_someone
                ━━━━━━━━━━━━━━━
                • Expert consultation sessions
                • Stripe escrow management
                • Session billing"]
                Chatbot["nettrades.chatbot
                ━━━━━━━━━━━━━━━
                • Conversation session state
                • AI response generation
                • Context management"]
                BridgeModel["nettrades.bridge
                ━━━━━━━━━━━━━━━
                • Hub-and-spoke routing
                • Local ↔ Remote brain routing
                • GPU overflow detection
                • Intent-based routing
                • Usage logging"]
                DataCollectionModel["nettrades.data_collection
                ━━━━━━━━━━━━━━━
                • data.episode (interaction records)
                • data.annotation (human feedback)
                • data.dataset (training datasets)
                • Edge case detection"]
                TriggerModel["nettrades.trigger
                ━━━━━━━━━━━━━━━
                • trigger.config (conditions)
                • Quality score triggers
                • Data volume triggers
                • Cron evaluation"]
                LoopModel["nettrades.loop
                ━━━━━━━━━━━━━━━
                • self_improving.loop (cycles)
                • Training orchestration
                • Model deployment tracking
                • Performance metrics"]
                SelfImprovingConfigModel["nettrades.self_improving_config
                ━━━━━━━━━━━━━━━
                • Loop enable/disable
                • Quality threshold configuration
                • A/B testing settings
                • Auto-deploy/rollback settings"]
                FairnessModel["nettrades.fairness
                ━━━━━━━━━━━━━━━
                • AI fairness monitoring
                • Bias detection
                • Rationality checks"]
                NotificationsModel["nettrades.notifications
                ━━━━━━━━━━━━━━━
                • Real-time alerts
                • Email notifications
                • In-app notifications"]
            end
        end

        subgraph LangGraphLayer["🤖 LangGraph Agent Orchestration"]
            Supervisor["Supervisor Agent
            ━━━━━━━━━━━━━━━
            • Intent classification (LLM)
            • Medical/Legal screening (multi-turn)
            • Bridge integration (hub-and-spoke)
            • Self-improving loop integration
            • Error handling & retry"]
            subgraph SubAgents["Sub-Agents"]
                RecruitmentAgent["Recruitment Agent
                ━━━━━━━━━━━━━━━
                • fetch_job()
                • search_candidates()
                • rank_candidates()
                • create_leads()"]
                FreelanceAgent["Freelance Agent
                ━━━━━━━━━━━━━━━
                • fetch_project()
                • search_freelancers()
                • rank_freelancers()
                • create_matches()"]
                LeadGenAgent["Lead Generation Agent
                ━━━━━━━━━━━━━━━
                • fetch_source()
                • generate_leads()
                • create_leads()"]
                GPUManagementAgent["GPU Management Agent
                ━━━━━━━━━━━━━━━
                • fetch_cluster()
                • check_health()
                • generate_recommendations()"]
                VisionAgent["Vision Agent
                ━━━━━━━━━━━━━━━
                • load_image()
                • process_vlm()
                • detect_edge_case()
                • record_for_training()"]
                ActionAgent["Action Agent
                ━━━━━━━━━━━━━━━
                • plan_action()
                • dispatch_action()
                • ROS 2 integration"]
            end
            MCPBridge["MCP-Odoo Bridge
            ━━━━━━━━━━━━━━━
            • Tool execution
            • Data access
            • Odoo ORM integration
            • Authentication"]
        end
    end

    %% ========================================================================
    %% 4. SELF-IMPROVING SYSTEM LAYER
    %% ========================================================================
    subgraph SelfImprovingLayer["🔄 Self-Improving System Layer"]
        direction TB

        subgraph MonitorPhase["Monitor Phase (nettrades_data_collection)"]
            EpisodeCollector["Episode Collector
            ━━━━━━━━━━━━━━━
            • Collects LangGraph agent interactions
            • Stores input → output → feedback
            • Edge case detection"]
            FeedbackAggregator["Feedback Aggregator
            ━━━━━━━━━━━━━━━
            • Aggregates 'Good Answer' votes
            • Integrates expert annotations
            • Quality scoring"]
        end

        subgraph AnalyzePhase["Analyze Phase (nettrades_trigger)"]
            TriggerEvaluator["Trigger Evaluator
            ━━━━━━━━━━━━━━━
            • Evaluates quality thresholds
            • Detects performance degradation
            • Identifies data volume triggers"]
        end

        subgraph PlanExecutePhase["Plan + Execute Phases (nettrades_loop)"]
            TrainingOrchestrator["Training Orchestrator
            ━━━━━━━━━━━━━━━
            • Creates llm_training jobs
            • Submits to GPUStack
            • Monitors training progress"]
            DeploymentManager["Deployment Manager
            ━━━━━━━━━━━━━━━
            • Deploys fine-tuned models
            • A/B testing
            • Automatic rollback"]
        end

        subgraph ConfigLayer["Configuration Layer (nettrades_self_improving_config)"]
            AdminSettings["Administration Settings
            ━━━━━━━━━━━━━━━
            • Loop enable/disable
            • Quality thresholds
            • A/B traffic split
            • Auto-deploy settings"]
        end

        MonitorPhase --> AnalyzePhase --> PlanExecutePhase --> ConfigLayer
        ConfigLayer --> MonitorPhase
    end

    %% ========================================================================
    %% 5. AI INFERENCE & TRAINING LAYER
    %% ========================================================================
    subgraph TrainingLayer["🧠 AI Inference & Training Layer"]
        GPUStack["GPUStack Server
        ━━━━━━━━━━━━━━━
        • Cluster management
        • Resource scheduling
        • Health monitoring
        • OpenAI-compatible API"]
        Workers["GPU Workers
        ━━━━━━━━━━━━━━━
        • vLLM (high-throughput inference)
        • llama.cpp (local models)
        • SGLang (structured generation)
        • Ascend MindIE"]
        FineTune["Fine-Tuning Jobs
        ━━━━━━━━━━━━━━━
        • Unsloth (2x faster, 70% less memory)
        • Axolotl (configurable training)
        • Dataset management
        • Job orchestration"]
        External["External LLM APIs
        ━━━━━━━━━━━━━━━
        • OpenAI (GPT-4, GPT-4o)
        • Anthropic (Claude 3.5/3.7)
        • Ollama (Local deployment)
        • Replicate"]
        TrainingMgmt["llm_training
        ━━━━━━━━━━━━━━━
        • Dataset management
        • Training job orchestration
        • Model lifecycle
        • Cost tracking"]
    end

    %% ========================================================================
    %% 6. DATA LAYER
    %% ========================================================================
    subgraph DataLayer["💾 Data Layer"]
        PG["PostgreSQL 18 + pgvector
        ━━━━━━━━━━━━━━━
        • Structured data (Odoo ORM)
        • Vector embeddings (pgvector)
        • LangGraph checkpoints
        • Full-text search"]
        PGR["PostgreSQL Read Replicas
        ━━━━━━━━━━━━━━━
        • Reporting queries
        • Analytics workloads
        • Read scaling"]
        Valkey["Valkey 8 (Redis-compatible)
        ━━━━━━━━━━━━━━━
        • Session cache
        • Rate limiting
        • Pub/Sub (real-time events)
        • Job queue backend"]
        S3["MinIO / S3
        ━━━━━━━━━━━━━━━
        • File storage (attachments)
        • Dataset storage
        • Model artifacts
        • Training logs"]
    end

    %% ========================================================================
    %% 7. SECURITY LAYER
    %% ========================================================================
    subgraph SecurityLayer["🛡️ Security Layer"]
        WG["WireGuard VPN
        ━━━━━━━━━━━━━━━
        • Site-to-site encryption
        • Secure remote access"]
        gVisor["gVisor Sandbox
        ━━━━━━━━━━━━━━━
        • Container isolation
        • System call interception"]
        TEE["TEE / Confidential Computing
        ━━━━━━━━━━━━━━━
        • Intel SGX / AMD SEV
        • Encrypted memory
        • Attestation"]
        RBAC["RBAC / Access Control
        ━━━━━━━━━━━━━━━
        • Role-based permissions
        • Fine-grained policies
        • Audit logging"]
    end

    %% ========================================================================
    %% 8. CONNECTIONS & DATA FLOW
    %% ========================================================================
    AccessLayer --> Gateway
    Gateway --> ApplicationLayer
    Gateway --> TrainingLayer

    ApplicationLayer --> LangGraphLayer
    ApplicationLayer --> OdooServer
    ApplicationLayer --> SelfImprovingLayer

    LangGraphLayer --> TrainingLayer
    LangGraphLayer --> DataLayer

    SelfImprovingLayer --> TrainingLayer
    SelfImprovingLayer --> DataLayer

    TrainingLayer --> DataLayer

    OdooServer --> DataLayer

    SecurityLayer --> Gateway
    SecurityLayer --> ApplicationLayer
    SecurityLayer --> TrainingLayer
    SecurityLayer --> DataLayer

    %% ========================================================================
    %% 9. STYLING
    %% ========================================================================
    classDef access fill:#e3f2fd,stroke:#1565c0,color:#000;
    classDef gateway fill:#fff3e0,stroke:#e65100,color:#000;
    classDef app fill:#f3e5f5,stroke:#6a1b9a,color:#000;
    classDef selfimproving fill:#e8f5e9,stroke:#2e7d32,color:#000;
    classDef training fill:#fce4ec,stroke:#c62828,color:#000;
    classDef data fill:#ede7f6,stroke:#4527a0,color:#000;
    classDef security fill:#ffebee,stroke:#b71c1c,color:#000;

    class AccessLayer access;
    class Gateway gateway;
    class ApplicationLayer app;
    class SelfImprovingLayer selfimproving;
    class TrainingLayer training;
    class DataLayer data;
    class SecurityLayer security;
    
```

| Section | Components Included |
|-----------|----------|	
| `External Access & Clients` | Web Browser (PWA), External API Client, Robotic/Edge Client, Mobile App |
| `API Gateway & Edge Security` | TLS Termination, Authentication/Authorization, Rate Limiting & Routing, Web Application Firewall |
| `Application Services` | Odoo 19 CE (Web Controllers, API Controllers, Odoo ORM Models), LangGraph Agent Orchestration (Supervisor, Sub-Agents, MCP-Odoo Bridge) |
| `Self-Improving System` | Monitor Phase (Episode Collector, Feedback Aggregator), Analyze Phase (Trigger Evaluator), Plan + Execute Phases (Training Orchestrator, Deployment Manager), Configuration Layer (Administration Settings) |
| `AI Inference & Training` | GPUStack Server, GPU Workers, Fine-Tuning Jobs, External LLM APIs, llm_training |
| `Data Layer` | PostgreSQL 18 + pgvector, PostgreSQL Read Replicas, Valkey 8, MinIO / S3 |
| `Security Layer` | WireGuard VPN, gVisor Sandbox, TEE / Confidential Computing, RBAC / Access Control |




## 2. High-Level Architecture Diagram

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        Web["Odoo Website / Portal"]
        PWA["Mobile PWA"]
        ChatWidget["AI Chatbot Widget"]
        VSCode["VS Code Extension"]
        API["REST API / GraphQL"]
    end

    subgraph Integration["Orchestration Layer (LangGraph)"]
        Supervisor["Supervisor Agent\n━━━━━━━━━━━━━━━━\n• Intent classification\n• Medical/legal screening\n• Multi-agent coordination\n• State management"]
        Agents["Sub-Agents\n━━━━━━━━━━━━━━━━\n• Recruitment\n• Freelance\n• Lead Gen\n• GPU Management\n• Vision\n• Action"]
        MCP["MCP-Odoo Bridge\n━━━━━━━━━━━━━━━━\n• Tool execution\n• Data access\n• Odoo integration"]
        Bridge["nettrades_bridge\n━━━━━━━━━━━━━━━━\n• Hub-and-Spoke Router\n• Intent-based routing\n• GPU overflow detection\n• Local ↔ Remote decision"]
    end

    subgraph SelfImproving["Self-Improving System Layer"]
        DataCollection["nettrades_data_collection\nMonitor Phase\n━━━━━━━━━━━━━━━━\n• data.episode\n• data.annotation\n• data.dataset\n• Edge case detection"]
        Trigger["nettrades_trigger\nAnalyze Phase\n━━━━━━━━━━━━━━━━\n• trigger.config\n• Quality triggers\n• Data volume triggers\n• Cron evaluation"]
        Loop["nettrades_loop\nPlan + Execute Phases\n━━━━━━━━━━━━━━━━\n• self_improving.loop\n• Training orchestration\n• Model deployment\n• Performance metrics"]
        Config["nettrades_self_improving_config\nAdministration UI\n━━━━━━━━━━━━━━━━\n• Loop enable/disable\n• Quality thresholds\n• A/B testing\n• Auto-deploy settings"]
    end

    subgraph Training["AI Inference & Training Layer"]
        GPUStack["GPUStack Server\n━━━━━━━━━━━━━━━━\n• Cluster management\n• Resource scheduling\n• Health monitoring"]
        Workers["GPU Workers\n━━━━━━━━━━━━━━━━\n• vLLM\n• llama.cpp\n• SGLang\n• Ascend MindIE"]
        FineTune["Fine-Tuning Jobs\n━━━━━━━━━━━━━━━━\n• Unsloth/Axolotl\n• Dataset management\n• Job orchestration"]
        External["External LLM APIs\n━━━━━━━━━━━━━━━━\n• OpenAI\n• Anthropic\n• Ollama (Local)\n• Replicate"]
        TrainingMgmt["llm_training\n━━━━━━━━━━━━━━━━\n• Dataset management\n• Training job orchestration\n• Model lifecycle\n• Cost tracking"]
    end

    subgraph Core["Core Layer (Odoo 19 CE)"]
        Odoo["Odoo 19 CE\n━━━━━━━━━━━━━━━━\n• Business logic\n• ORM\n• Security\n• Multi-worker"]
        CoreModules["nettrades_core\n━━━━━━━━━━━━━━━━\n• Users & companies\n• Karma & reputation\n• Qualification rules\n• Worker agent config"]
        GPUAdmin["nettrades_gpu_admin\n━━━━━━━━━━━━━━━━\n• GPU node registry\n• Utilisation monitoring\n• Pool assignment"]
        GoodAnswer["nettrades_good_answer\n━━━━━━━━━━━━━━━━\n• Vote collection\n• Reputation decay\n• Dataset eligibility"]
        AskSomeone["nettrades_ask_someone\n━━━━━━━━━━━━━━━━\n• Expert sessions\n• Stripe escrow\n• Consultation management"]
        JobMatching["nettrades_job_matching\n━━━━━━━━━━━━━━━━\n• CV parsing\n• Candidate scoring\n• Shortlist generation"]
        LeadScoring["nettrades_lead_scoring\n━━━━━━━━━━━━━━━━\n• Lead generation\n• Quality scoring"]
        Chatbot["nettrades_chatbot\n━━━━━━━━━━━━━━━━\n• Conversation state\n• AI responses"]
        Notifications["nettrades_notifications\n━━━━━━━━━━━━━━━━\n• Real-time alerts\n• Email notifications"]
    end

    subgraph Data["Data Layer"]
        PG["PostgreSQL 18 + pgvector\n━━━━━━━━━━━━━━━━\n• Structured data\n• Vector embeddings\n• LangGraph checkpoints"]
        Valkey["Valkey 8\n━━━━━━━━━━━━━━━━\n• Session cache\n• Rate limiting\n• Pub/Sub"]
        S3["MinIO / S3\n━━━━━━━━━━━━━━━━\n• File storage\n• Dataset storage\n• Model artifacts"]
    end

    subgraph Security["Security Layer"]
        WG["WireGuard VPN"]
        gVisor["gVisor Sandbox"]
        TEE["TEE / Confidential Computing"]
        RBAC["RBAC / Access Control"]
    end

    Frontend --> Core
    Frontend --> Integration
    Integration --> Bridge --> SelfImproving
    Integration --> Supervisor --> Agents
    Integration --> MCP --> Core
    Integration --> Training
    Training --> GPUStack --> Workers
    Training --> FineTune
    Training --> External
    Training --> TrainingMgmt
    Core --> Data
    Core --> Security
    Security --> Training
    SelfImproving --> Training
    DataCollection --> Trigger --> Loop --> Config
    Loop --> TrainingMgmt
    
```
    
    
## 3. Odoo ORM Models (Detailed)

### Core Models

```mermaid
graph LR
    subgraph CoreModels["nettrades_core Models"]
        ResPartner["res.partner (Extended)\n━━━━━━━━━━━━━━━━\n• field_ids\n• skill_ids\n• experience_ids\n• karma\n• reputation_score\n• is_qualified\n• worker_agent\n• worker_context"]
        NettradesField["nettrades.field\n━━━━━━━━━━━━━━━━\n• name\n• description\n• qualification_rules"]
        NettradesSkill["nettrades.skill\n━━━━━━━━━━━━━━━━\n• name\n• category\n• proficiency_level"]
        NettradesExperience["nettrades.experience\n━━━━━━━━━━━━━━━━\n• partner_id\n• role\n• company\n• duration"]
        NettradesReview["nettrades.review\n━━━━━━━━━━━━━━━━\n• partner_id\n• rating\n• comment\n• reviewer_id"]
        UserMatch["nettrades.user_match\n━━━━━━━━━━━━━━━━\n• user_id\n• matched_user_id\n• score\n• status"]
    end
```

### Good Answer Models

```mermaid
graph LR
    subgraph GoodAnswerModels["nettrades_good_answer Models"]
        GoodAnswerVote["good.answer.vote\n━━━━━━━━━━━━━━━━\n• user_id\n• field_id\n• answer_text\n• score\n• points\n• processed_for_ai"]
        FieldReputation["user.field.reputation\n━━━━━━━━━━━━━━━━\n• user_id\n• field_id\n• reputation_score\n• vote_count"]
        FTDataset["ft.dataset\n━━━━━━━━━━━━━━━━\n• name\n• field_id\n• status\n• record_count"]
        FTContribution["ft.dataset.contribution\n━━━━━━━━━━━━━━━━\n• dataset_id\n• vote_id\n• included\n• weight"]
        FTTrainingJob["ft.training.job\n━━━━━━━━━━━━━━━━\n• dataset_id\n• status\n• started_at\n• completed_at"]
    end
```

### GPU Admin Models

```mermaid
graph LR
    subgraph GPUAdminModels["nettrades_gpu_admin Models"]
        GPUNode["gpu.node\n━━━━━━━━━━━━━━━━\n• name\n• partner_id\n• cluster_id\n• gpu_count\n• gpu_model\n• vram_gb\n• status\n• gpu_utilisation"]
        GPUCluster["gpu.cluster\n━━━━━━━━━━━━━━━━\n• name\n• partner_id\n• available_vram_gb\n• total_vram_gb"]
        GPUTest["gpu.test\n━━━━━━━━━━━━━━━━\n• node_id\n• status\n• results"]
        GPStackSync["gpustack.sync\n━━━━━━━━━━━━━━━━\n• last_sync\n• status\n• sync_log"]
    end
```

### Self-Improving System Models

```mermaid
graph LR
    subgraph DataCollectionModels["nettrades_data_collection Models"]
        DataEpisode["data.episode\n━━━━━━━━━━━━━━━━\n• partner_id\n• field_id\n• input_text\n• output_text\n• quality_score\n• vote_count\n• is_qualified\n• processed"]
        DataAnnotation["data.annotation\n━━━━━━━━━━━━━━━━\n• episode_id\n• annotator_id\n• labels\n• quality_score\n• source"]
        SimulationDataset["simulation.dataset\n━━━━━━━━━━━━━━━━\n• name\n• version\n• parent_id\n• num_episodes\n• num_frames\n• data_format\n• storage_path"]
    end

    subgraph TriggerModels["nettrades_trigger Models"]
        TriggerConfig["self_improving.trigger\n━━━━━━━━━━━━━━━━\n• name\n• trigger_type\n• threshold_value\n• comparison_operator\n• time_window_hours\n• field_id\n• action_template"]
    end

    subgraph LoopModels["nettrades_loop Models"]
        SelfImprovingLoop["self_improving.loop\n━━━━━━━━━━━━━━━━\n• name\n• trigger_id\n• status\n• dataset_id\n• training_job_id\n• model_version\n• metrics\n• quality_before\n• quality_after"]
    end

    subgraph ConfigModels["nettrades_self_improving_config Models"]
        SelfImprovingConfig["self_improving.config\n━━━━━━━━━━━━━━━━\n• loop_enabled\n• loop_interval\n• min_quality_score\n• min_votes_for_training\n• max_samples_per_dataset\n• ab_testing_enabled\n• ab_traffic_split\n• promotion_threshold\n• auto_deploy\n• auto_rollback"]
    end

    DataEpisode --> DataAnnotation
    DataEpisode --> SimulationDataset
    TriggerConfig --> SelfImprovingLoop
    SelfImprovingLoop --> SimulationDataset
    SelfImprovingLoop --> ConfigModels
```

### Bridge Models

```mermaid
graph LR
    subgraph BridgeModels["nettrades_bridge Models"]
        BridgeConfig["nettrades.bridge.config\n━━━━━━━━━━━━━━━━\n• bridge_mode\n• remote_brain_url\n• remote_brain_api_key\n• enable_remote_recruitment\n• enable_remote_freelance\n• enable_remote_gpu\n• gpu_overflow_enabled\n• gpu_overflow_threshold\n• request_timeout\n• max_retries\n• fallback_to_local"]
        BridgeCompanyConfig["nettrades.bridge.company.config\n━━━━━━━━━━━━━━━━\n• company_id\n• override_bridge_mode\n• bridge_mode\n• override_features\n• enable_remote_*\n• override_gpu_overflow\n• gpu_overflow_enabled\n• gpu_overflow_threshold\n• override_remote_url\n• remote_brain_url"]
        BridgeUsageLog["nettrades.bridge.usage.log\n━━━━━━━━━━━━━━━━\n• company_id\n• intent\n• source\n• success\n• request_data\n• response_data\n• response_time_ms\n• tokens_used"]
        BridgeRouting["nettrades.bridge.routing\n━━━━━━━━━━━━━━━━\n• (Transient Service)\n• route_request()\n• _should_route_remote()\n• _check_gpu_overflow()\n• _call_remote_brain()\n• _call_local_brain()\n• _log_usage()"]
    end
```

## 4. Data Flow: Self-Improving Loop

```mermaid
graph TD
    subgraph Monitor["1. MONITOR (nettrades_data_collection)"]
        A1["User Interactions"] --> A2["LangGraph Agents"]
        A2 --> A3["data.episode"]
        A3 --> A4["Quality Score"]
        A3 --> A5["Edge Case Detection"]
    end

    subgraph Analyze["2. ANALYZE (nettrades_trigger)"]
        B1["Trigger Evaluation"] --> B2["Quality Drop?"]
        B2 -->|Yes| B3["Trigger Fired"]
        B2 -->|No| B4["Data Volume?"]
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
    Execute -->|Feedback Loop| Monitor
```

## 5. Application Services Layer

```mermaid
graph TB
    subgraph ApplicationServices["Application Services"]
        direction TB

        subgraph RecruitmentServices["Recruitment Services"]
            RecruitmentAgent["recruitment_agent\n━━━━━━━━━━━━━━━━\n• fetch_job()\n• search_candidates()\n• rank_candidates()\n• create_leads()"]
            JobMatching["nettrades_job_matching\n━━━━━━━━━━━━━━━━\n• CV parsing\n• Skill extraction\n• Match scoring\n• Candidate ranking"]
        end

        subgraph FreelanceServices["Freelance Services"]
            FreelanceAgent["freelance_agent\n━━━━━━━━━━━━━━━━\n• fetch_project()\n• search_freelancers()\n• rank_freelancers()\n• create_matches()"]
            Proposals["nettrades_proposals\n━━━━━━━━━━━━━━━━\n• Proposal creation\n• Rate suggestions\n• Skills matching"]
        end

        subgraph GPUServices["GPU Services"]
            GPUAgent["gpu_management_agent\n━━━━━━━━━━━━━━━━\n• fetch_cluster()\n• check_health()\n• generate_recommendations()"]
            GPUAdmin["nettrades_gpu_admin\n━━━━━━━━━━━━━━━━\n• Node management\n• Utilisation monitoring\n• Overflow detection"]
            GPStackAdapter["nettrades_gpustack_adapter\n━━━━━━━━━━━━━━━━\n• GPUStack sync\n• Inference scheduling\n• Training orchestration"]
        end

        subgraph SelfImprovingServices["Self-Improving Services"]
            DataCollection["nettrades_data_collection\n━━━━━━━━━━━━━━━━\n• Episode collection\n• Feedback aggregation\n• Dataset management"]
            Trigger["nettrades_trigger\n━━━━━━━━━━━━━━━━\n• Trigger evaluation\n• Cron jobs\n• Quality monitoring"]
            Loop["nettrades_loop\n━━━━━━━━━━━━━━━━\n• Training orchestration\n• Deployment management\n• A/B testing"]
            Config["nettrades_self_improving_config\n━━━━━━━━━━━━━━━━\n• Admin settings\n• Feature flags\n• Threshold configuration"]
        end

        subgraph BridgeServices["Bridge Services"]
            Bridge["nettrades_bridge\n━━━━━━━━━━━━━━━━\n• Hub-and-spoke routing\n• Intent classification\n• GPU overflow\n• Usage logging"]
        end
    end
```

## 6. Technology Stack Summary

| Layer | Technology | Version | Purpose |
|-----------|----------|-------------|-------------|
| `Frontend` | Odoo Website | 19 CE | Business portal |
| `Mobile` | Odoo PWA | 19 CE | Mobile access |
| `Agent Orchestration` | LangGraph | Latest | Multi-agent workflows |
| `Agent Framework` | LangChain | Latest | Agent tools and memory |
| `Business Logic` | Odoo 19 CE | 19.0 | ERP, CRM, HR, Accounting |
| `Database` | PostgreSQL | 18 | Primary database |
| `Vector Storage` | pgvector | Latest | Embedding storage |
| `Cache` | Valkey | 8 | Session management |
| `Object Storage` | MinIO / S3 | Latest | File and model storage |
| `GPU Management` | GPUStack | Latest | GPU cluster management |
| `Fine-Tuning` | Unsloth / Axolotl | Latest | Model fine-tuning |
| `Inference` | vLLM / llama.cpp | Latest | LLM inference |
| `Container` | Docker / Kubernetes | Latest | Container orchestration |
| `Security` | WireGuard / gVisor | Latest | Network and sandbox |
| `LLM Providers` | OpenAI, Anthropic, Ollama | Various	LLM access |
| `LLM Integration` | Apexive odoo-llm | 19.0 | LLM modules |

## 7. Self-Improving System Data Flow (Detailed)

```mermaid
graph LR
    subgraph MonitorPhase["Monitor Phase"]
        A[User Interaction] --> B[data.episode]
        B --> C[data.annotation]
        B --> D[quality_score]
    end

    subgraph AnalyzePhase["Analyze Phase"]
        E[Trigger Cron] --> F{Evaluate Triggers}
        F -->|quality_drop| G[Trigger Fired]
        F -->|data_volume| G
        F -->|manual| G
    end

    subgraph PlanPhase["Plan Phase"]
        G --> H[Create llm_training.job]
        H --> I[Prepare Dataset]
        I --> J[Submit to GPUStack]
    end

    subgraph ExecutePhase["Execute Phase"]
        J --> K[Train Model]
        K --> L[A/B Test]
        L -->|Pass| M[Deploy to LangGraph]
        L -->|Fail| N[Rollback]
        M --> O[Update Agents]
    end

    O -->|Feedback| A
```

## 8. Deployment Architecture

```mermaid
graph TB
    subgraph LoadBalancer["Load Balancer (Nginx/HAProxy)"]
        LB["SSL Termination\nLoad Balancing\nRate Limiting"]
    end

    subgraph FrontendServices["Frontend Services"]
        Web["Odoo Web\n(Port 8069)"]
        API["REST API\n(Port 8069)"]
        Websocket["WebSocket\n(Port 8069)"]
    end

    subgraph OdooWorkers["Odoo Workers (Multi-Worker)"]
        Worker1["Worker 1\n(HTTP)"]
        Worker2["Worker 2\n(HTTP)"]
        WorkerN["Worker N\n(HTTP)"]
        Cron["Cron Worker"]
        Queue["Queue Worker"]
    end

    subgraph AgentServices["Agent Services"]
        LangGraph["LangGraph Supervisor"]
        SubAgents["LangGraph Sub-Agents"]
        MCP["MCP-Odoo Bridge"]
    end

    subgraph GPUCluster["GPU Cluster (GPUStack)"]
        GPU1["GPU Worker 1\n(NVIDIA RTX)"]
        GPU2["GPU Worker 2\n(NVIDIA RTX)"]
        GPUN["GPU Worker N\n(NVIDIA RTX)"]
    end

    subgraph Storage["Storage"]
        PG["PostgreSQL\n(Read/Write)"]
        PGR["PostgreSQL\n(Read Replicas)"]
        Valkey["Valkey Cache"]
        S3["MinIO/S3"]
    end

    LB --> Web
    Web --> Worker1
    Web --> Worker2
    Web --> WorkerN
    Web --> Cron
    Web --> Queue
    Worker1 --> LangGraph
    LangGraph --> SubAgents
    SubAgents --> MCP
    MCP --> Worker1
    LangGraph --> GPU1
    GPU1 --> PG
    GPU1 --> S3
    Worker1 --> PG
    Worker1 --> Valkey
    PG --> PGR
```

## 9. Key Integration Points

| Integration | Source | Target | Purpose |
|-----------|----------|-------------|-------------|
| `LangGraph ↔ Odoo` | LangGraph Agents | Odoo ORM | Data access via MCP-Odoo Bridge |
| `LangGraph ↔ GPUStack` | LangGraph Agents | GPUStack API | LLM inference and training |
| `Odoo ↔ GPUStack` | Odoo Modules | GPUStack API | GPU resource management |
| `Odoo ↔ PostgreSQL` | Odoo ORM | PostgreSQL | Data persistence |
| `Odoo ↔ pgvector` | Odoo ORM | pgvector | Vector embeddings |
| `LangGraph ↔ PostgreSQL` | LangGraph Checkpointer | PostgreSQL | State persistence |
| `nettrades_bridge ↔ LangGraph` | Bridge Service | Supervisor Agent | Hub-and-spoke routing |

## 10. Security Architecture

```mermaid
graph TB
    subgraph External["External Access"]
        User["User (Browser)"]
        API["API Client"]
    end

    subgraph SecurityControls["Security Controls"]
        Firewall["Firewall\n(IP Filtering)"]
        WAF["WAF\n(Web Application Firewall)"]
        Auth["Authentication\n(OAuth 2.0 / JWT)"]
        RBAC["RBAC\n(Role-Based Access)"]
    end

    subgraph Encryption["Encryption"]
        TLS["TLS 1.3\n(Transport)"]
        Enc["Encryption at Rest\n(AES-256)"]
        TEE["TEE\n(Confidential Computing)"]
    end

    subgraph Internal["Internal Security"]
        VPN["WireGuard VPN"]
        gVisor["gVisor Sandbox"]
        Isolation["Network Isolation\n(Kubernetes Namespaces)"]
        Audit["Audit Logging"]
    end

    User --> Firewall --> WAF --> Auth --> RBAC --> Web
    API --> TLS --> Auth --> RBAC --> API
    Web --> VPN --> Internal
    Internal --> gVisor --> Isolation
    Isolation --> Audit
    Enc --> TEE
```

## 11. Monitoring & Observability

| Component | Monitoring Tool | Metrics |
|-----------|----------|-------------|
| `Odoo` | Odoo Logging, Prometheus | Request rate, error rate, response time |
| `LangGraph` | LangSmith, OpenTelemetry | Agent traces, step duration, success rate |
| `GPUStack` | Grafana, Prometheus | GPU utilisation, inference latency, throughput |
| `PostgreSQL` | pg_stat_statements, Prometheus | Query performance, connection count, replication lag |
| `Kubernetes` | Prometheus, Grafana | Pod status, CPU/Memory usage, network I/O |

## 12. Scaling Recommendations

| Component | Scaling Strategy | Max Instances |
|-----------|----------|-------------|
| `Odoo Workers` | Horizontal (multi-worker) | 8-12 workers |
| `LangGraph Agents` | Horizontal (Kubernetes HPA) | 5-10 pods |
| `GPUStack Workers` | Horizontal (add nodes) | 10-20 nodes |
| `PostgreSQL` | Read replicas | 2-3 replicas |
| `Valkey` | Cluster mode | 3-6 nodes |