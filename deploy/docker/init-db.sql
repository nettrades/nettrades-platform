-- =============================================================================
-- NETTRADES.AI – Database initialisation
-- =============================================================================
-- This file is executed ONCE by the deployment script (deploy-single.sh) after
-- the PostgreSQL container is ready and BEFORE Odoo starts.
--
-- It MUST be run by a superuser because it creates a PostgreSQL extension.
-- All other tables are created automatically by Odoo when the corresponding
-- custom modules are installed via the Apps menu.
-- =============================================================================

-- Enable the pgvector extension for RAG (retrieval-augmented generation).
-- This is required by the community LLM module (llm_pgvector) to store
-- text embeddings and perform similarity searches.
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- Custom tables for NETTRADES.AI
-- (These are NOT created by Odoo or its AI modules)
-- ============================================

-- User work experience (extended profile)
CREATE TABLE IF NOT EXISTS nettrades_experience (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL,
    job_title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    start_date DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- User reviews and ratings
CREATE TABLE IF NOT EXISTS nettrades_review (
    id SERIAL PRIMARY KEY,
    reviewer_id INTEGER NOT NULL,
    reviewed_partner_id INTEGER NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    project_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- AI match results between jobs and users (used by LangGraph)
CREATE TABLE IF NOT EXISTS nettrades_user_match (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    match_score FLOAT,
    analysis TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Links between Odoo projects and Forgejo repositories
CREATE TABLE IF NOT EXISTS forgejo_repo (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    repo_url VARCHAR(512),
    clone_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Professional fields for reputation and matching
CREATE TABLE IF NOT EXISTS nettrades_field (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    only_qualified BOOLEAN DEFAULT FALSE,
    reputation_threshold_for_charging INTEGER DEFAULT 100,
    base_points_per_vote INTEGER DEFAULT 1,
    qualified_points_per_vote INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_experience_partner ON nettrades_experience(partner_id);
CREATE INDEX IF NOT EXISTS idx_review_reviewed ON nettrades_review(reviewed_partner_id);
CREATE INDEX IF NOT EXISTS idx_match_job ON nettrades_user_match(job_id);
CREATE INDEX IF NOT EXISTS idx_match_user ON nettrades_user_match(user_id);
CREATE INDEX IF NOT EXISTS idx_forgejo_project ON forgejo_repo(project_id);

-- ============================================
-- For NETTRADES.AI
-- E3. Run these SQL statements when installing the nettrades_good_answer module.
-- ============================================


-- Extend res_partner with reputation fields
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS reputation_points INTEGER DEFAULT 0;
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS can_charge BOOLEAN DEFAULT FALSE;
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS charge_rate FLOAT DEFAULT 0.0;

-- Fields (already exist from Section A; ensure fine-tuning columns)
ALTER TABLE nettrades_field ADD COLUMN IF NOT EXISTS finetune_provider VARCHAR(50) DEFAULT 'unsloth';
ALTER TABLE nettrades_field ADD COLUMN IF NOT EXISTS base_model VARCHAR(255) DEFAULT 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B';
ALTER TABLE nettrades_field ADD COLUMN IF NOT EXISTS hyperparameters JSONB;

-- Qualified professionals per field
CREATE TABLE IF NOT EXISTS qualified_professional (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES nettrades_field(id) ON DELETE CASCADE,
    points_per_vote INTEGER,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_qualified_prof_field ON qualified_professional (partner_id, field_id);

-- User reputation per field
CREATE TABLE IF NOT EXISTS user_field_reputation (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES nettrades_field(id) ON DELETE CASCADE,
    reputation_points INTEGER DEFAULT 0,
    can_charge BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_field_reputation ON user_field_reputation (partner_id, field_id);

-- Good Answer votes
CREATE TABLE IF NOT EXISTS good_answer_vote (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    answer_id INTEGER NOT NULL,
    answer_model VARCHAR(255) NOT NULL,
    answerer_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES nettrades_field(id) ON DELETE CASCADE,
    points INTEGER NOT NULL,
    is_qualified_vote BOOLEAN DEFAULT FALSE,
    processed_for_ai BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_good_answer_vote_once ON good_answer_vote (user_id, answer_id, answer_model);
CREATE INDEX IF NOT EXISTS idx_good_answer_vote_answerer ON good_answer_vote (answerer_id, field_id);
CREATE INDEX IF NOT EXISTS idx_good_answer_vote_processed ON good_answer_vote (processed_for_ai) WHERE processed_for_ai = false;

-- Fine-tuning tables
CREATE TABLE IF NOT EXISTS ft_dataset (
    id SERIAL PRIMARY KEY,
    field_id INTEGER NOT NULL REFERENCES nettrades_field(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    file_uri VARCHAR(512),
    record_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ft_dataset_field ON ft_dataset(field_id);

CREATE TABLE IF NOT EXISTS ft_training_job (
    id SERIAL PRIMARY KEY,
    dataset_id INTEGER NOT NULL REFERENCES ft_dataset(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES nettrades_field(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,
    base_model VARCHAR(255),
    fine_tuned_model_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    hyperparameters JSONB,
    metrics JSONB,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_ft_job_field ON ft_training_job(field_id);
CREATE INDEX IF NOT EXISTS idx_ft_job_status ON ft_training_job(status);

-- ============================================
-- For NETTRADES.AI
-- D3. Run these SQL statements when installing the nettrades_ask_someone module.
-- ============================================


-- Extend res_partner with geolocation and presence
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS latitude FLOAT;
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS longitude FLOAT;
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP;
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS is_online BOOLEAN DEFAULT FALSE;

-- Expert session table
CREATE TABLE IF NOT EXISTS expert_session (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    requester_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    expert_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    field_id INTEGER REFERENCES nettrades_field(id) ON DELETE SET NULL,
    task_summary TEXT,
    ai_context_bundle JSONB,
    duration_minutes INTEGER,
    rate_per_minute FLOAT,
    total_charged FLOAT,
    escrow_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    rating_by_requester INTEGER,
    rating_by_expert INTEGER,
    forgejo_repo_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Escrow holds (optional, but recommended for audit)
CREATE TABLE IF NOT EXISTS escrow_hold (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES expert_session(id) ON DELETE CASCADE,
    amount FLOAT,
    currency VARCHAR(3) DEFAULT 'USD',
    provider VARCHAR(50) DEFAULT 'stripe',
    provider_hold_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'held',
    released_at TIMESTAMP
);

-- Admin configuration for Ask Someone
CREATE TABLE IF NOT EXISTS ask_someone_config (
    id SERIAL PRIMARY KEY,
    distance_weight FLOAT DEFAULT 0.4,
    reputation_weight FLOAT DEFAULT 0.5,
    online_bonus FLOAT DEFAULT 0.2,
    available_bonus FLOAT DEFAULT 0.1,
    max_distance_km INTEGER DEFAULT 100,
    reputation_threshold INTEGER DEFAULT 100,
    geocoding_provider VARCHAR(50) DEFAULT 'openstreetmap',
    geocoding_api_key VARCHAR(255),
    platform_fee_percent FLOAT DEFAULT 15.0,
    default_field_id INTEGER REFERENCES nettrades_field(id)
);

INSERT INTO ask_someone_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_expert_session_status ON expert_session(status, started_at);
CREATE INDEX IF NOT EXISTS idx_expert_session_expert ON expert_session(expert_id, status);
CREATE INDEX IF NOT EXISTS idx_expert_session_requester ON expert_session(requester_id, status);

-- ============================================
-- For NETTRADES.AI
-- F2. Add-on 1: Smart Onboarding & Profile Enhancement
-- Simplify registration; help users build complete profiles; allow import from LinkedIn/GitHub.
--  Role detection from email domain (e.g., @company.com → Company) or initial action (upload CV → Job Seeker).
--  Profile completeness wizard with step-by-step forms and progress indicator.
--  CV parsing using AI (via LangGraph) to extract skills, experience, and summary.
--  One-click import from LinkedIn, GitHub, Upwork (OAuth).
-- ============================================

ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS onboarding_step VARCHAR(50) DEFAULT 'new';
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS linkedin_uid VARCHAR(255);
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS github_username VARCHAR(255);
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS upwork_id VARCHAR(255);
ALTER TABLE res_partner ADD COLUMN IF NOT EXISTS profile_completeness INTEGER DEFAULT 0;

-- ============================================
-- For NETTRADES.AI
-- F3.2. Add-on 2: AI Job Matching & One-Click Apply
-- Purpose: Conversational job search, AI-powered job recommendations, and one-click application with generated cover letters.
-- Features
--    Natural language search bar (e.g., “Find remote Python jobs over $50k”).
--    AI-ranked job recommendations on the home page.
--    One-click apply with AI-generated cover letter (editable).
-- ============================================

ALTER TABLE hr_job ADD COLUMN IF NOT EXISTS ai_keywords TEXT;

-- ============================================
-- For NETTRADES.AI
-- F4. Add-on 3: Freelancer Proposal & Milestone Payments
-- 
--  AI-generated proposal draft from project description.
--  Milestone definition (client creates milestones with amounts).
--  Automatic escrow creation (uses Stripe from ask_someone module).
-- ============================================


CREATE TABLE IF NOT EXISTS project_milestone (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project_project(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    amount FLOAT,
    status VARCHAR(50) DEFAULT 'pending',
    due_date DATE,
    released BOOLEAN DEFAULT FALSE
);


-- ============================================
-- For NETTRADES.AI
-- F6. Add-on 5: Research Project Marketplace
-- 
-- Allow researchers to post projects and get matched with partners.
-- ============================================

CREATE TABLE IF NOT EXISTS research_project (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project_project(id),
    research_field VARCHAR(255),
    expected_publication TEXT,
    budget FLOAT
);




-- ============================================
-- For NETTRADES.AI
-- F8. Add-on 7: In-App Notifications, Reviews & Disputes
-- 
-- Centralised notification centre, streamlined review flow, and dispute resolution.
-- In-app notification centre (store notifications in database).
-- After project completion, both parties are prompted to leave a review.
-- Dispute workflow with a dedicated manager.
-- ============================================

CREATE TABLE IF NOT EXISTS user_notification (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id),
    notification_type VARCHAR(50),
    title VARCHAR(255),
    body TEXT,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispute (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES expert_session(id),
    project_id INTEGER REFERENCES project_project(id),
    raised_by INTEGER REFERENCES res_partner(id),
    description TEXT,
    status VARCHAR(50) DEFAULT 'open',
    resolved_at TIMESTAMP
);

-- ============================================
-- For NETTRADES.AI
-- F9.2 Custom Dashboard
-- 
-- Create a model user.dashboard.widget
-- ============================================

CREATE TABLE IF NOT EXISTS user_dashboard_widget (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id),
    widget_name VARCHAR(255),
    position INTEGER,
    config JSONB
);

-- ============================================
-- For NETTRADES.AI
-- H4. Odoo Add-on for Token Management and GPU Sharing
-- 
-- The add-on ai_gpu_network is installed alongside nettrades_core. It provides:
--     • User token balance (free tokens, configurable by admin)
 --    • GPU sharing toggle (user can enable sharing → unlimited tokens)
 --    • Client registration endpoint (/api/v1/clients/register)
--     • Administration configuration
--     • One-click client installer download
-- ============================================

-- User token balance
CREATE TABLE IF NOT EXISTS ai_gpu_user_token (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL UNIQUE REFERENCES res_partner(id) ON DELETE CASCADE,
    free_tokens_remaining INTEGER DEFAULT 100000,
    gpu_sharing_enabled BOOLEAN DEFAULT FALSE,
    extra_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Registered GPU nodes (from clients)
CREATE TABLE IF NOT EXISTS ai_gpu_node (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    node_id VARCHAR(255) UNIQUE NOT NULL,
    hostname VARCHAR(255),
    gpus JSONB,
    status VARCHAR(50) DEFAULT 'active',
    last_seen TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- API keys for clients
CREATE TABLE IF NOT EXISTS ai_gpu_api_key (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    api_key VARCHAR(255) UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Join token table (single-use, 10-minute expiry)
CREATE TABLE IF NOT EXISTS ai_gpu_join_token (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    token VARCHAR(255) UNIQUE NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Admin configuration (singleton)
CREATE TABLE IF NOT EXISTS ai_gpu_config (
    id SERIAL PRIMARY KEY,
    default_free_tokens INTEGER DEFAULT 100000,
    token_cost_per_1k_chars FLOAT DEFAULT 1.0,
    controller_ip VARCHAR(255),
    bootstrap_port INTEGER DEFAULT 51820,
    agent_download_url VARCHAR(512),
    agreement_version VARCHAR(10) DEFAULT '1.0'
);
INSERT INTO ai_gpu_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Signed GPU sharing agreements
CREATE TABLE IF NOT EXISTS ai_gpu_sharing_agreement (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES res_partner(id) ON DELETE CASCADE,
    version VARCHAR(10) NOT NULL,
    signed_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- Note: The following tables are created by Odoo's AI modules
-- and are NOT included here:
-- - llm_vector_store (RAG embeddings)
-- - llm_conversation_history
-- - llm_provider (LLM endpoint configuration)
-- - llm_training_job
-- - llm_dataset
-- These tables will be created automatically when you install 
-- the respective modules from the community odoo_llm package.
-- ============================================