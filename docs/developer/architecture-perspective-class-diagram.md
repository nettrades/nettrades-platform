# Architect Perspective — Class Diagram (Core Domain Models) 

Below is the Architect Perspective — Class Diagram (Core Domain Models) for NETTRADES.AI, showing the primary Odoo models, their attributes, key methods, and relationships. This diagram is based on the actual code in odoo-modules/ and the database schema described in the documentation.

# Explanation of Key Models
# User & Professional Models

    res_partner: Extended Odoo partner with fields for freelancer, skills, reputation, location, and social links. The central user entity.

    nettrades_field: Professional fields (e.g., Cardiology, Python Development). Contains all configuration for qualification, voting, and fine?tuning.

    user_field_reputation: Per?field reputation points for each user, with cron jobs for decay and auto?qualification.

    qualified_professional: Explicitly verified experts for restricted fields (e.g., medical).

# Good Answer & Fine?Tuning

    good_answer_vote: Stores user votes on answers. Points are weighted based on voter qualification.

    llm_feedback: Feedback data (question + answer) extracted from votes, used for training.

    ft_dataset: Collection of feedback records for a field, with export to JSONL and quality pipeline.

    ft_training_job: Tracks training jobs submitted to GPUStack.

    ft_dataset_contribution: Indirect reputation earned by professionals whose answers contributed to training.

# Expert Help (Ask Someone)

    expert_session: Represents a live consultation session between requester and expert, with escrow and ratings.

    escrow_hold: Audit trail for Stripe escrow holds.

    ask_someone_config: Admin?configurable matching weights and fees.

    expert_agreement: Signed legal agreement for experts.

# GPU Administration

    gpu_cluster: Represents a GPU cluster (company internal or public), with WireGuard configuration and GPUStack server details.

    gpu_node: Individual GPU node, with hardware inventory, WireGuard keys, pool assignment, and runtime.

    gpu_sharing_schedule: Schedule for public sharing (e.g., only at night).

    gpu_token_economics: Token earning/spending rates and payout schedule.

# Job Matching & Freelance

    hr_job: Job posting with AI match criteria.

    hr_applicant: Applicant linked to a job, with AI match score.

    candidate_match: Explicit match record between job and candidate.

    project_project: Project with Forgejo Git integration.

    project_milestone: Milestone?based payments.

# Lead Scoring & CRM

    crm_lead: Extended CRM lead with AI?generated scores and recommendations.

# Research & Collaboration

    research_project: Research?specific project with matching logic.

    forgejo_repo: Git repository details linked to a project.

# Notifications & Reviews

    user_notification: In?app notification store.

    nettrades_review: User reviews with ratings.

    dispute: Dispute resolution for sessions or projects.

This class diagram provides an architect?level view of the core domain models, enabling a clear understanding of the data model, relationships, and business logic encapsulated in each entity. It is directly derived from the Odoo custom modules and the database schema described in the documentation.

---

## Architect Perspective — Class Diagram (Core Domain Models) 

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