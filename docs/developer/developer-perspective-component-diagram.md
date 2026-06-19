# DEVELOPER PERSPECTIVE — Component Diagram

Purpose: Shows the high-level software components, their responsibilities, and how they communicate with each other.

---

## DEVELOPER PERSPECTIVE — Component Diagram

```mermaid
flowchart TB
    subgraph Presentation["??? Presentation Layer"]
        WebUI["Odoo Web UI<br>(Website / Forum / Shop)"]
        RESTAPI["JSON-RPC API<br>(/api/v1/*)"]
        FastAPI["FastAPI Service<br>(/invoke, /health, /metrics)"]
    end

    subgraph Orchestration["?? Orchestration Layer (LangGraph)"]
        Supervisor["Supervisor Graph<br>????????????????<br>• classify()<br>• medical_screening()<br>• route()"]
        
        subgraph Agents["Sub-Agents"]
            RecruitmentAgent["Recruitment Agent"]
            FreelanceAgent["Freelance Agent"]
            LeadGenAgent["Lead Gen Agent"]
            GPUManagementAgent["GPU Management Agent"]
            VisionAgent["Vision Agent"]
            ActionAgent["Action Agent"]
            GeneralLLM["General LLM Fallback"]
        end
    end

    subgraph Business["?? Business Logic Layer (Odoo Modules)"]
        Core["nettrades_core<br>????????????????<br>Fields, Qualification, Voting"]
        GoodAnswer["nettrades_good_answer<br>????????????????<br>Reputation, Fine-Tuning Dataset"]
        GPUAdmin["nettrades_gpu_admin<br>????????????????<br>Node Registry, Pool Management"]
        JobMatching["nettrades_job_matching<br>????????????????<br>CV Analysis, Match Scoring"]
        Proposals["nettrades_proposals<br>????????????????<br>Freelancer Matching"]
        LeadScoring["nettrades_lead_scoring<br>????????????????<br>Lead Generation & Scoring"]
        AskSomeone["nettrades_ask_someone<br>????????????????<br>Consultations, Stripe Escrow"]
        Chatbot["nettrades_chatbot<br>????????????????<br>Session Management"]
    end

    subgraph Data["?? Data Layer"]
        PostgreSQL["PostgreSQL + pgvector<br>????????????????<br>• Business Data<br>• Vector Embeddings<br>• Checkpoints"]
        Valkey["Valkey (Redis-compatible)<br>????????????????<br>• Session Cache<br>• Pub/Sub<br>• Rate Limiting"]
        Longhorn["Longhorn<br>????????????????<br>• File Storage<br>• Model Weights<br>• Datasets"]
    end

    subgraph Infrastructure["?? Infrastructure Layer"]
        GPUStack["GPUStack Manager<br>????????????????<br>• Inference Engine<br>• Token Metering<br>• Worker Pool"]
        GPUNode["GPU Node Agent<br>????????????????<br>• WireGuard<br>• Node Registration<br>• Worker Management"]
    end

    subgraph External["?? External Integrations"]
        Stripe["Stripe API<br>????????????????<br>Payments & Escrow"]
        LLMProviders["External LLM Providers<br>????????????????<br>OpenAI / Anthropic (Fallback)"]
    end

    %% Connections
    WebUI -->|"HTTP"| Core
    RESTAPI -->|"JSON-RPC"| Core
    FastAPI -->|"Executes"| Supervisor
    Supervisor -->|"Dispatches to"| Agents
    
    Agents -->|"Reads/Writes"| Business
    Agents -->|"Calls"| GPUStack
    Chatbot -->|"Async HTTP"| FastAPI
    
    Business -->|"SQL"| PostgreSQL
    Business -->|"Cache"| Valkey
    Business -->|"Files"| Longhorn
    
    FastAPI -->|"Checkpoints"| PostgreSQL
    
    GPUStack -->|"Manages"| GPUNode
    GPUNode -->|"Registers via"| RESTAPI
    
    AskSomeone -->|"Payments"| Stripe
    GeneralLLM -->|"Fallback"| LLMProviders

    classDef presentation fill:#e3f2fd,stroke:#1565c0;
    classDef orchestration fill:#f3e5f5,stroke:#6a1b9a;
    classDef business fill:#e8f5e9,stroke:#2e7d32;
    classDef data fill:#fff3e0,stroke:#e65100;
    classDef infrastructure fill:#fce4ec,stroke:#c62828;
    classDef external fill:#ede7f6,stroke:#4527a0;

    class Presentation presentation;
    class Orchestration,Agents orchestration;
    class Business business;
    class Data data;
    class Infrastructure infrastructure;
    class External external;