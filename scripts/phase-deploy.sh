#!/bin/bash
# =============================================================================
# FILE: scripts/phase-deploy.sh
# =============================================================================
# PURPOSE:
#   Phase 2: Single-VM Docker deployment.
#   This script deploys the entire NETTRADES stack using Docker Compose.
#   It is idempotent and safe to re-run.
#
#   It performs the following steps (in order):
#   1. Create required directories.
#   2. Download DeepSeek model (if not cached).
#   3. Build custom Docker images (Odoo, LangGraph) if missing.
#   4. Generate `init-db.sql` with all NETTRADES database tables.
#   5. Run security hardening (if Phase 0 not completed).
#   6. Start the Docker Compose stack (using `--no-recreate`).
#   7. Initialise PostgreSQL database with `init-db.sql`.
#   8. Install all NETTRADES Odoo modules.
#   9. Set up cron for daily backups.
#   10. Verify service health.
#   11. Display final status.
#
# USAGE:
#   ./phase-deploy.sh [--auto] [--force] [--upgrade]
# =============================================================================

set -euo pipefail

# Set PROJECT_ROOT if not already set (for standalone execution)
if [ -z "${PROJECT_ROOT:-}" ]; then
    PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    export PROJECT_ROOT
fi

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
UPGRADE="${UPGRADE:-false}"
export FORCE  # <-- FIX: Ensure FORCE is available to phase_completed()

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "2"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 2; then
    log_warning "Phase 2 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Prerequisites
# -----------------------------------------------------------------------------
if ! phase_completed 1; then
    log_info "Phase 1 not completed. Running Phase 1 first..."
    bash "$SCRIPT_DIR/phase-env.sh"
fi

check_docker || exit 1

# -----------------------------------------------------------------------------
# Set up paths
# -----------------------------------------------------------------------------
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
ENV_FILE="$PROJECT_ROOT/.env"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yaml"
DATA_DIR="$PROJECT_ROOT/data"
MODELS_DIR="$DATA_DIR/models"
ADDONS_DIR="$PROJECT_ROOT/addons"
LOGS_DIR="$PROJECT_ROOT/logs"

if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env not found. Please run Phase 1 first."
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "docker-compose.yaml not found at $COMPOSE_FILE"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Create required directories
# -----------------------------------------------------------------------------
log_step "Creating required directories..."
mkdir -p "$DATA_DIR/postgres"
mkdir -p "$DATA_DIR/odoo"
mkdir -p "$DATA_DIR/valkey"
mkdir -p "$DATA_DIR/forgejo"
mkdir -p "$DATA_DIR/prometheus"
mkdir -p "$DATA_DIR/grafana"
mkdir -p "$MODELS_DIR"
mkdir -p "$ADDONS_DIR"
mkdir -p "$LOGS_DIR"
mkdir -p "$DATA_DIR/backups"
log_success "Directories created"

# -----------------------------------------------------------------------------
# 2. Download DeepSeek model (if not cached)
# -----------------------------------------------------------------------------
log_step "Checking DeepSeek model cache..."
MODEL_FILE="$MODELS_DIR/deepseek-r1-distill-qwen-7b-q4_k_m.gguf"
if [[ ! -f "$MODEL_FILE" ]] || [[ "$FORCE" == true ]]; then
    log_info "Downloading DeepSeek model (this may take a while)..."
    if [[ -f "$DEPLOY_DIR/download-model.sh" ]]; then
        bash "$DEPLOY_DIR/download-model.sh" --output "$MODEL_FILE"
    else
        log_warning "No download-model.sh found. Please ensure the model is present at $MODEL_FILE."
        if [[ "$AUTO" != true ]]; then
            read -rp "Press Enter to continue or Ctrl+C to abort..."
        fi
    fi
else
    log_success "DeepSeek model already cached: $MODEL_FILE"
fi

# -----------------------------------------------------------------------------
# Prepare Odoo addons for Docker build
# -----------------------------------------------------------------------------
log_step "Preparing Odoo addons for build..."
if [[ -f "$SCRIPT_DIR/prepare-odoo-addons.sh" ]]; then
    if [[ "$FORCE" == true ]]; then
        bash "$SCRIPT_DIR/prepare-odoo-addons.sh" --force
    else
        bash "$SCRIPT_DIR/prepare-odoo-addons.sh"
    fi
else
    log_warning "prepare-odoo-addons.sh not found – skipping addon preparation"
fi

# -----------------------------------------------------------------------------
# 3. Build custom Docker images
# -----------------------------------------------------------------------------
log_step "Building custom Docker images..."

# Odoo image
ODOO_DOCKERFILE="$DEPLOY_DIR/Dockerfile.odoo"
if [[ -f "$ODOO_DOCKERFILE" ]]; then
    if ! docker image inspect nettrades-odoo:latest &>/dev/null || [[ "$FORCE" == true ]]; then
        log_info "Building Odoo image..."
        docker build -f "$ODOO_DOCKERFILE" -t nettrades-odoo:latest "$DEPLOY_DIR"
        log_success "Odoo image built"
    else
        log_success "Odoo image already exists"
    fi
else
    log_warning "Dockerfile.odoo not found – skipping Odoo image build"
fi

# LangGraph image
LANGGRAPH_DOCKERFILE="$PROJECT_ROOT/src/core/Dockerfile"
if [[ -f "$LANGGRAPH_DOCKERFILE" ]]; then
    if ! docker image inspect nettrades-langgraph:latest &>/dev/null || [[ "$FORCE" == true ]]; then
        log_info "Building LangGraph image..."
        docker build -f "$LANGGRAPH_DOCKERFILE" -t nettrades-langgraph:latest "$PROJECT_ROOT/src/core"
        log_success "LangGraph image built"
    else
        log_success "LangGraph image already exists"
    fi
else
    log_warning "Dockerfile for LangGraph not found – skipping build"
fi

# -----------------------------------------------------------------------------
# 4. Generate init-db.sql with all NETTRADES tables
# -----------------------------------------------------------------------------
log_step "Generating init-db.sql with all NETTRADES tables..."
INIT_SQL="$DEPLOY_DIR/init-db.sql"
if [[ ! -f "$INIT_SQL" ]] || [[ "$FORCE" == true ]]; then
    cat > "$INIT_SQL" << 'EOF'
-- =============================================================================
-- NETTRADES Database Initialisation Script
-- =============================================================================
-- This script creates all required PostgreSQL tables for the NETTRADES platform.
-- It is idempotent – tables are created only if they do not already exist.
-- =============================================================================

-- Enable pgvector extension for AI embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- Core Platform Tables
-- =============================================================================

-- nettrades_core – Core platform tables
CREATE TABLE IF NOT EXISTS nettrades_users (
    id SERIAL PRIMARY KEY,
    odoo_user_id INTEGER UNIQUE,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    wallet_address VARCHAR(42),
    karma_score INTEGER DEFAULT 0,
    reputation_score DECIMAL(5,2) DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    website VARCHAR(255),
    industry VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_projects (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES nettrades_companies(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    budget DECIMAL(15,2),
    status VARCHAR(50) DEFAULT 'open',
    required_skills TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Good Answer / Self-Improving AI
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_good_answers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model_used VARCHAR(100),
    votes_positive INTEGER DEFAULT 0,
    votes_negative INTEGER DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_votes (
    id SERIAL PRIMARY KEY,
    answer_id INTEGER REFERENCES nettrades_good_answers(id),
    user_id INTEGER REFERENCES nettrades_users(id),
    vote_type VARCHAR(10) CHECK (vote_type IN ('positive', 'negative')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(answer_id, user_id)
);

-- =============================================================================
-- Ask Someone – Expert Marketplace
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_ask_someone_requests (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    budget DECIMAL(15,2),
    category VARCHAR(100),
    status VARCHAR(50) DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_ask_someone_offers (
    id SERIAL PRIMARY KEY,
    request_id INTEGER REFERENCES nettrades_ask_someone_requests(id),
    expert_id INTEGER REFERENCES nettrades_users(id),
    price DECIMAL(15,2),
    proposal TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- GPU Marketplace
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_gpu_nodes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    gpu_model VARCHAR(100),
    vram_gb INTEGER,
    compute_capability VARCHAR(20),
    ip_address VARCHAR(45),
    port INTEGER,
    status VARCHAR(50) DEFAULT 'available',
    owner_id INTEGER REFERENCES nettrades_users(id),
    price_per_hour DECIMAL(10,4),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_gpu_bookings (
    id SERIAL PRIMARY KEY,
    node_id INTEGER REFERENCES nettrades_gpu_nodes(id),
    user_id INTEGER REFERENCES nettrades_users(id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    total_cost DECIMAL(15,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_gpu_usage_logs (
    id SERIAL PRIMARY KEY,
    booking_id INTEGER REFERENCES nettrades_gpu_bookings(id),
    node_id INTEGER REFERENCES nettrades_gpu_nodes(id),
    usage_type VARCHAR(50),
    duration_seconds INTEGER,
    tokens_used INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Bridge / Hub-and-Spoke Routing
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_bridge_routes (
    id SERIAL PRIMARY KEY,
    source_node VARCHAR(255),
    target_node VARCHAR(255),
    route_type VARCHAR(50),
    config JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Job Matching & Proposals
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_job_matches (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES nettrades_projects(id),
    freelancer_id INTEGER REFERENCES nettrades_users(id),
    match_score DECIMAL(5,2),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nettrades_proposals (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES nettrades_projects(id),
    freelancer_id INTEGER REFERENCES nettrades_users(id),
    cover_letter TEXT,
    bid_amount DECIMAL(15,2),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Fairness & Reputation
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_fairness_scores (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    fairness_score DECIMAL(5,2) DEFAULT 0,
    trust_score DECIMAL(5,2) DEFAULT 0,
    last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Notifications
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    type VARCHAR(50),
    title VARCHAR(255),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Research Module
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_research_projects (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    researcher_id INTEGER REFERENCES nettrades_users(id),
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Queue / Task Management
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_queue_tasks (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(100),
    payload JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,
    scheduled_at TIMESTAMP,
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Self-Improving Config
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_self_improving_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(255) UNIQUE NOT NULL,
    value JSONB,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Lead Scoring
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_leads (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES nettrades_companies(id),
    score INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'new',
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Chatbot
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_chatbot_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    session_id VARCHAR(255),
    messages JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- PWA / Offline
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_pwa_cache (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES nettrades_users(id),
    cache_key VARCHAR(255),
    cache_data JSONB,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Indexes for Performance
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_good_answers_user_id ON nettrades_good_answers(user_id);
CREATE INDEX IF NOT EXISTS idx_gpu_nodes_status ON nettrades_gpu_nodes(status);
CREATE INDEX IF NOT EXISTS idx_gpu_bookings_user_id ON nettrades_gpu_bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_job_matches_project_id ON nettrades_job_matches(project_id);
CREATE INDEX IF NOT EXISTS idx_proposals_project_id ON nettrades_proposals(project_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON nettrades_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_queue_tasks_status ON nettrades_queue_tasks(status);

EOF
    log_success "init-db.sql generated with all NETTRADES tables"
else
    log_success "init-db.sql already exists"
fi

# -----------------------------------------------------------------------------
# 5. Run security hardening (if Phase 0 not completed)
# -----------------------------------------------------------------------------
if ! phase_completed 0; then
    log_step "Phase 0 not completed – running security hardening..."
    if [[ -f "$SCRIPT_DIR/phase-system.sh" ]]; then
        bash "$SCRIPT_DIR/phase-system.sh"
    else
        log_warning "phase-system.sh not found – skipping hardening"
    fi
else
    log_success "Security hardening already applied (Phase 0)"
fi

# -----------------------------------------------------------------------------
# 6. Start Docker Compose stack
# -----------------------------------------------------------------------------
cd "$DEPLOY_DIR"
log_step "Starting Docker Compose stack..."

# Source .env for environment variables
set -a
source "$ENV_FILE"
set +a

if [[ "$FORCE" == true ]]; then
    log_info "Force mode – recreating containers..."
    docker compose down --remove-orphans
    docker compose up -d --build
else
    docker compose up -d --no-recreate
fi

log_success "Docker Compose stack started"

# -----------------------------------------------------------------------------
# 7. Initialise PostgreSQL database
# -----------------------------------------------------------------------------
log_step "Initialising PostgreSQL database..."

# Wait for PostgreSQL to be ready
log_info "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec postgres pg_isready -U odoo &>/dev/null; then
        log_success "PostgreSQL is ready"
        break
    fi
    sleep 2
done

if [[ -f "$INIT_SQL" ]]; then
    docker exec -i postgres psql -U odoo odoo < "$INIT_SQL" 2>/dev/null || {
        log_warning "Database initialisation may have already been done."
    }
else
    log_error "init-db.sql not found!"
    exit 1
fi

# -----------------------------------------------------------------------------
# 8. Install all NETTRADES Odoo modules
# -----------------------------------------------------------------------------
log_step "Installing NETTRADES Odoo modules..."

# Wait for Odoo to be fully ready
log_info "Waiting for Odoo to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
        log_success "Odoo is ready"
        break
    fi
    sleep 2
done

if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
    # -----------------------------------------------------------------------------
    # 8a. Install required Odoo base modules (website, portal, etc.)
    # -----------------------------------------------------------------------------
    log_step "Installing Odoo base modules required by NETTRADES..."
    for base_module in website portal mail auth_signup; do
        log_info "Installing module: $base_module"
        docker exec odoo odoo -c /etc/odoo/odoo.conf -d odoo -i "$base_module" --stop-after-init --log-level=info 2>&1 | grep -i "error\|warning" || true
    done
    log_success "Base modules installed"
    
    # -----------------------------------------------------------------------------
    # 8b. Install NETTRADES Odoo modules (existing step)
    # -----------------------------------------------------------------------------
    log_step "Installing NETTRADES Odoo modules..."
    
    log_info "Running install-modules.sh..."
    ARGS=""
    [[ "$FORCE" == true ]] && ARGS="$ARGS --force"
    [[ "$UPGRADE" == true ]] && ARGS="$ARGS --upgrade"
    bash "$SCRIPT_DIR/install-modules.sh" $ARGS
else
    log_warning "install-modules.sh not found – skipping module installation"
fi

# -----------------------------------------------------------------------------
# 9. Set up cron for daily backups
# -----------------------------------------------------------------------------
log_step "Setting up cron for daily backups..."

BACKUP_SCRIPT="$DEPLOY_DIR/backup.sh"
if [[ -f "$BACKUP_SCRIPT" ]]; then
    if command -v crontab &>/dev/null; then
        # Remove any existing entry for backup.sh
        (crontab -l 2>/dev/null | grep -v "$BACKUP_SCRIPT" || echo "") > /tmp/cron.tmp
        echo "0 2 * * * $BACKUP_SCRIPT >> $LOGS_DIR/backup.log 2>&1" >> /tmp/cron.tmp
        crontab /tmp/cron.tmp
        rm /tmp/cron.tmp
        log_success "Cron backup scheduled at 2 AM daily"
    else
        log_warning "crontab not found – skipping cron setup"
    fi
else
    log_warning "backup.sh not found – skipping cron setup"
fi

# -----------------------------------------------------------------------------
# 10. Verify service health
# -----------------------------------------------------------------------------
log_step "Verifying service health..."
sleep 10  # Allow services to settle

# Check Odoo
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
    log_success "Odoo is healthy"
else
    log_warning "Odoo health check failed – please check logs"
fi

# Check LangGraph
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
    log_success "LangGraph is healthy"
else
    log_warning "LangGraph health check failed – please check logs"
fi

# Check PostgreSQL
if docker exec postgres pg_isready -U odoo &>/dev/null; then
    log_success "PostgreSQL is healthy"
else
    log_warning "PostgreSQL health check failed – please check logs"
fi

# -----------------------------------------------------------------------------
# 11. Display final status
# -----------------------------------------------------------------------------
cd "$PROJECT_ROOT"
mark_phase_complete 2

log_success "Phase 2 completed – Docker stack deployed with all modules"
echo ""
echo "============================================================"
echo " NETTRADES Platform is now running!"
echo "============================================================"
echo ""
docker compose -f "$DEPLOY_DIR/docker-compose.yaml" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Access the services:"
echo "  Odoo:      http://localhost:8069"
echo "  Forgejo:   http://localhost:3000"
echo "  Grafana:   http://localhost:3001"
echo "  Prometheus: http://localhost:9090"
echo ""
echo "Default Odoo credentials: admin / admin"
echo "(Change immediately after first login)"