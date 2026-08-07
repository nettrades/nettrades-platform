#!/bin/bash
# =============================================================================
# FILE: scripts/phase-deploy.sh
# =============================================================================
# PURPOSE:
#   Phase 2: Single-VM Docker deployment with NVIDIA Dynamo as the primary inference
#   engine (includes vLLM), with automatic fallback to llama.cpp (CPU) if Dynamo
#   cannot be fully automated.
#   This script deploys the entire NETTRADES stack using Docker Compose.
#   It is idempotent and safe to re-run.
#
#   It performs the following steps (in order):
#   1. Create required directories.
#   2. Download a small model (e.g., Qwen2.5-1.5B) from a local server (no HF token).
#   3. Build custom Docker images (Odoo, LangGraph) if missing.
#   4. Generate `init-db.sql` with all NETTRADES database tables.
#   5. Run security hardening (if Phase 0 not completed).
#   6. Start PostgreSQL container and initialise the database (if empty).
#   7. Build and start the full Docker Compose stack.
#   8. Install all NETTRADES Odoo modules.
#   9. Set up cron for daily backups.
#   10. Verify service health.
#   11. Ensure Let's Encrypt certificate.
#   12. Display final status.
#
# USAGE:
#   ./phase-deploy.sh [--auto] [--force] [--upgrade]
#
# INFERENCE BACKEND LOGIC:
#   - Primary: NVIDIA Dynamo (GPU-accelerated)
#   - Fallback: llama.cpp (CPU)
#   - A background health check determines Dynamo availability.
#   - LangGraph (via inference_tools.py) selects the healthy backend.
#   - Odoo provides governance and model selection.
#
# UPDATES (2026-08):
#   - Removed any SQL that modifies core Odoo tables (res_partner, etc.).
#   - The init-db.sql now only creates nettrades_* tables.
#   - Added platform detection for macOS-specific Docker volume handling.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Network setup
# The web network is used by Traefik (the reverse proxy) to route incoming traffic to services like Odoo.
# -----------------------------------------------------------------------------
if ! docker network ls --format '{{.Name}}' | grep -q "^web$"; then
    docker network create web
fi

# Set PROJECT_ROOT if not already set
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
# Ensure VENV_DIR is available and activate the virtual environment
# This ensures that any Python commands (e.g., bcrypt) use the venv's Python
# and installed packages, not the system Python.
# -----------------------------------------------------------------------------
VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    log_info "Activated Python virtual environment: $VENV_DIR"
else
    log_warning "Virtual environment not found at $VENV_DIR – using system Python."
fi

# -----------------------------------------------------------------------------
# SAFE PASSWORD GENERATOR – only alphanumeric characters
# This prevents .env parsing errors caused by '+', '/', '=', "'", etc.
# -----------------------------------------------------------------------------
generate_safe_password() {
    # 24 alphanumeric characters (no special characters)
    openssl rand -base64 24 | tr -d '+/=' | tr -d '\n' | cut -c1-24
}

# -----------------------------------------------------------------------------
# Helper: Wait for PostgreSQL to be ready by attempting a SQL query
# This is more reliable than pg_isready because it confirms the database is
# fully initialised and accepting connections.
# -----------------------------------------------------------------------------
wait_for_postgres() {
    local retries=60
    local delay=2
    log_step "Waiting for PostgreSQL to become ready..."
    for i in $(seq 1 $retries); do
        # Use docker compose exec to avoid container name mismatches
        if docker compose exec -T postgres psql -U odoo -d odoo -c "SELECT 1" &>/dev/null; then
            log_success "PostgreSQL is ready"
            return 0
        fi
        if [ $((i % 10)) -eq 0 ]; then
            log_info "Still waiting for PostgreSQL... ($i/$retries attempts)"
        fi
        sleep $delay
    done
    log_error "PostgreSQL did not become ready within $((retries * delay)) seconds"
    log_info "Check PostgreSQL logs with: docker logs $(docker compose ps -q postgres) --tail 50"
    return 1
}

# -----------------------------------------------------------------------------
# Helper: Enable pgcrypto extension in PostgreSQL
# -----------------------------------------------------------------------------
enable_pgcrypto() {
    log_step "Enabling pgcrypto extension in PostgreSQL..."
    if docker compose exec -T postgres psql -U odoo -d odoo -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null; then
        log_success "pgcrypto extension enabled"
        return 0
    else
        log_warning "Could not enable pgcrypto – emergency user creation may fail"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Helper: Install bcrypt inside the venv if missing
# -----------------------------------------------------------------------------
ensure_bcrypt() {
    log_step "Ensuring bcrypt is available for Prometheus password hashing..."
    if python3 -c "import bcrypt" 2>/dev/null; then
        log_success "bcrypt already available"
        return 0
    else
        log_info "bcrypt not found – installing via pip in the virtual environment..."
        if pip install bcrypt 2>/dev/null; then
            log_success "bcrypt installed successfully"
            return 0
        else
            log_warning "Could not install bcrypt. Fallback to plain-text passwords."
            return 1
        fi
    fi
}

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
UPGRADE="${UPGRADE:-false}"
ENVIRONMENT="${ENVIRONMENT:-development}"
REGENERATE_SECRETS="${REGENERATE_SECRETS:-false}"
RESET_DATA="${RESET_DATA:-false}"
export FORCE

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
ENV_FILE="$DEPLOY_DIR/.env"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yaml"
DATA_DIR="$PROJECT_ROOT/data"
LOGS_DIR="$PROJECT_ROOT/logs"
DYNAMO_DATA_DIR="$DEPLOY_DIR/dynamo-data"
MODELS_DIR="$DYNAMO_DATA_DIR/models"

# Odoo data directory
ODOO_DATA_DIR="$DEPLOY_DIR/odoo-data"

if [[ ! -f "$ENV_FILE" ]]; then
    log_error ".env not found. Please run Phase 1 first."
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    log_error "docker-compose.yaml not found at $COMPOSE_FILE"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Create required directories (including redirector landing page)
# -----------------------------------------------------------------------------
log_step "Creating required directories..."
mkdir -p "$DATA_DIR/postgres" "$DATA_DIR/odoo" "$DATA_DIR/valkey" "$DATA_DIR/forgejo"
mkdir -p "$DATA_DIR/prometheus" "$DATA_DIR/grafana" "$DATA_DIR/backups"
mkdir -p "$DYNAMO_DATA_DIR" "$MODELS_DIR" "$LOGS_DIR" "$ODOO_DATA_DIR"
mkdir -p "redirector/landing-page"

# Create a default landing page if none exists
if [[ ! -f "redirector/landing-page/index.html" ]]; then
    cat > "redirector/landing-page/index.html" << 'EOF'
<!DOCTYPE html>
<html>
<head><title>NETTRADES Platform</title></head>
<body>
<h1>NETTRADES Platform</h1>
<p>Welcome to the NETTRADES AI Marketplace.</p>
<p><a href="/odoo">Odoo</a> | <a href="http://localhost:3002">AI Chat UI</a></p>
</body>
</html>
EOF
    log_success "Default landing page created"
fi
log_success "Directories created"

# =============================================================================
# EARLY: Download GGUF model for llama.cpp fallback from ModelScope mirror
# This ensures the CPU fallback engine has a model to load before the stack starts.
# ModelScope mirrors work without authentication.
# =============================================================================
if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
    log_step "Downloading GGUF model for llama.cpp fallback from ModelScope mirror..."

    # Ensure the models directory exists
    mkdir -p "$MODELS_DIR"

    # Run the download script with the correct model and format
    if bash "$SCRIPT_DIR/download-model.sh" --model deepseek-1.5b --format gguf --dir "$MODELS_DIR"; then
        log_success "GGUF model downloaded successfully to $MODELS_DIR"
    else
        log_warning "GGUF model download failed. Trying alternative source..."
        # Fallback: Try direct wget from ModelScope as a backup
        MODEL_FILE="$MODELS_DIR/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
        if wget -O "$MODEL_FILE" "https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf" --progress=dot:giga; then
            log_success "GGUF model downloaded via fallback to $MODEL_FILE"
        else
            log_warning "GGUF model download failed. You may need to manually place a model in $MODELS_DIR."
            log_info "The system will still work but llama.cpp fallback will not be available."
        fi
    fi

    # Validate the model file exists and is not corrupted (size check)
    MODEL_FILE="$MODELS_DIR/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"
    if [[ -f "$MODEL_FILE" ]]; then
        FILE_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
        if [[ "$FILE_SIZE" -lt 500000000 ]]; then
            log_warning "Model file exists but is too small ($FILE_SIZE bytes). It may be corrupted."
            log_info "Attempting to re-download the model..."
            rm -f "$MODEL_FILE"
            # Retry download with direct wget
            if wget -O "$MODEL_FILE" "https://www.modelscope.cn/models/unsloth/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/master/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf" --progress=dot:giga; then
                NEW_SIZE=$(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0)
                if [[ "$NEW_SIZE" -gt 500000000 ]]; then
                    log_success "Model re-downloaded successfully ($NEW_SIZE bytes)"
                else
                    log_error "Re-downloaded file still too small. Please check the URL and disk space."
                fi
            else
                log_error "Re-download failed. llama.cpp will not start."
            fi
        else
            log_success "Model file validated: $MODEL_FILE ($FILE_SIZE bytes)"
        fi
    else
        log_warning "Model file not found at $MODEL_FILE. llama.cpp will fail to start."
    fi
else
    log_warning "download-model.sh not found – skipping llama.cpp model download"
fi

# -----------------------------------------------------------------------------
# Prepare Odoo addons
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
# Build custom Docker images
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
# Query the Odoo user UID from the built image
# -----------------------------------------------------------------------------
ODOO_UID=""
if docker image inspect nettrades-odoo:latest &>/dev/null; then
    ODOO_UID=$(docker run --rm nettrades-odoo:latest id -u odoo 2>/dev/null || echo "")
fi
if [[ -z "$ODOO_UID" ]]; then
    log_warning "Could not determine Odoo UID from image. Falling back to UID 100."
    ODOO_UID="100"
fi
log_info "Odoo user UID: $ODOO_UID"

# -----------------------------------------------------------------------------
# Ensure Odoo data directory exists and set correct permissions
# -----------------------------------------------------------------------------
mkdir -p "$ODOO_DATA_DIR"
chown -R "$ODOO_UID:$ODOO_UID" "$ODOO_DATA_DIR" 2>/dev/null || true
log_success "Odoo data directory permissions set to UID $ODOO_UID"

# -----------------------------------------------------------------------------
# Generate init-db.sql with all NETTRADES tables
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

-- Enable pgcrypto for password hashing (used by Odoo emergency user)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
# 6. Start PostgreSQL and initialise the database (if empty)
# -----------------------------------------------------------------------------
cd "$DEPLOY_DIR"
log_step "Starting PostgreSQL container and initialising database..."

# Ensure .env has Unix line endings (fix Windows CRLF)
if command -v dos2unix &>/dev/null; then
    dos2unix "$ENV_FILE" 2>/dev/null || true
fi

# Source .env for environment variables
set -a
source "$ENV_FILE"
set +a

# Check PostgreSQL password consistency
check_postgres_password() {
    local pg_container
    pg_container=$(docker compose ps -q postgres 2>/dev/null)
    if [[ -n "$pg_container" ]] && docker inspect -f '{{.State.Running}}' "$pg_container" 2>/dev/null | grep -q true; then
        local actual_pass
        actual_pass=$(docker exec "$pg_container" env | grep POSTGRES_PASSWORD | cut -d= -f2)
        if [[ -n "$actual_pass" && "$actual_pass" != "$POSTGRES_PASSWORD" ]]; then
            log_warning "PostgreSQL password mismatch."
            log_warning "  .env password: $POSTGRES_PASSWORD"
            log_warning "  Container password: $actual_pass"
            if [[ "$FORCE" == true ]] || [[ "$AUTO" == true ]]; then
                log_info "Updating .env to match the container's password."
                safe_sed_replace "$ENV_FILE" "POSTGRES_PASSWORD" "$actual_pass"
                export POSTGRES_PASSWORD="$actual_pass"
            else
                log_error "Please either set the correct password in .env or use --force to update .env."
                exit 1
            fi
        fi
    fi
}

check_postgres_password

# Preserve PostgreSQL password if container already exists
POSTGRES_PRESERVED=false
PG_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null)
if [[ -n "$PG_CONTAINER" ]]; then
    if docker inspect -f '{{.State.Running}}' "$PG_CONTAINER" 2>/dev/null | grep -q true; then
        CURRENT_PG_PASS=$(docker exec "$PG_CONTAINER" env | grep POSTGRES_PASSWORD | cut -d= -f2)
        if [[ -n "$CURRENT_PG_PASS" ]]; then
            log_info "PostgreSQL container is running. Using its password: $CURRENT_PG_PASS"
            safe_sed_replace "$ENV_FILE" "POSTGRES_PASSWORD" "$CURRENT_PG_PASS"
            export POSTGRES_PASSWORD="$CURRENT_PG_PASS"
            POSTGRES_PRESERVED=true
        fi
    else
        log_info "PostgreSQL container exists but is not running. Skipping password preservation."
    fi
else
    log_info "PostgreSQL container does not exist. Will generate password if weak."
fi

# Auto-generate strong secrets for all services (if missing or weak)
generate_secret() {
    generate_safe_password
}

SECRET_VARS=(
    POSTGRES_PASSWORD
    ADMIN_PASSWORD
    FORGEJO_DB_PASSWORD
    FORGEJO_SECRET_KEY
    GRAFANA_PASSWORD
    PROMETHEUS_PASSWORD
    LANGGRAPH_API_KEY
    ODOO_API_KEY
    PROXY_API_KEY
)

if [[ ! -f "$ENV_FILE" ]] || [[ "$REGENERATE_SECRETS" == true ]]; then
    if [[ "$REGENERATE_SECRETS" == true ]]; then
        log_warning "Regenerating secrets in .env (this will break running services!)."
        BACKUP_ENV="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP_ENV"
        log_info "Backed up .env to $BACKUP_ENV"
    fi

    for VAR in "${SECRET_VARS[@]}"; do
        if [[ "$VAR" == "POSTGRES_PASSWORD" ]] && [[ "$POSTGRES_PRESERVED" == true ]]; then
            log_info "POSTGRES_PASSWORD preserved from container – skipping regeneration."
            continue
        fi

        if grep -q "^${VAR}=" "$ENV_FILE"; then
            CURRENT_VALUE=$(grep "^${VAR}=" "$ENV_FILE" | cut -d'=' -f2-)
            if [[ -z "$CURRENT_VALUE" || "$CURRENT_VALUE" == "changeit" ]]; then
                NEW_VALUE=$(generate_secret)
                safe_sed_replace "$ENV_FILE" "$VAR" "$NEW_VALUE"
                log_info "Regenerated ${VAR} (was weak)"
                export "${VAR}=${NEW_VALUE}"
            else
                export "${VAR}=${CURRENT_VALUE}"
            fi
        else
            NEW_VALUE=$(generate_secret)
            safe_sed_replace "$ENV_FILE" "$VAR" "$NEW_VALUE"
            log_info "Generated ${VAR}"
            export "${VAR}=${NEW_VALUE}"
        fi
    done

    # Ensure ODOO_API_KEY and PROXY_API_KEY are identical
    ODOO_API_KEY=$(grep "^ODOO_API_KEY=" "$ENV_FILE" | cut -d'=' -f2-)
    PROXY_API_KEY=$(grep "^PROXY_API_KEY=" "$ENV_FILE" | cut -d'=' -f2-)
    if [[ "$ODOO_API_KEY" != "$PROXY_API_KEY" ]]; then
        NEW_KEY=$(generate_secret)
        safe_sed_replace "$ENV_FILE" "ODOO_API_KEY" "$NEW_KEY"
        safe_sed_replace "$ENV_FILE" "PROXY_API_KEY" "$NEW_KEY"
        export ODOO_API_KEY="${NEW_KEY}"
        export PROXY_API_KEY="${NEW_KEY}"
        log_info "Synchronised ODOO_API_KEY and PROXY_API_KEY"
    fi
fi

# Generate Grafana datasource provisioning file (using the Prometheus password)
log_step "Generating Grafana datasource provisioning..."
GRAFANA_DATASOURCES_DIR="$DEPLOY_DIR/grafana-datasources"
GRAFANA_DATASOURCES_FILE="$GRAFANA_DATASOURCES_DIR/datasources.yaml"
PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"

mkdir -p "$GRAFANA_DATASOURCES_DIR"

if [[ -f "$GRAFANA_DATASOURCES_FILE" ]]; then
    BACKUP_DS="${GRAFANA_DATASOURCES_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$GRAFANA_DATASOURCES_FILE" "$BACKUP_DS"
    log_info "Backed up existing datasources.yaml to $BACKUP_DS"
fi

cat > "$GRAFANA_DATASOURCES_FILE" << EOF
# =============================================================================
# Grafana Datasource Provisioning
# =============================================================================
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    basicAuth: true
    basicAuthUser: admin
    secureJsonData:
      basicAuthPassword: ${PROMETHEUS_PASSWORD}
    isDefault: true
    editable: false
EOF
log_success "Grafana datasource provisioning created"

# Generate Prometheus web.yml with basic auth (using the password from .env)
log_step "Generating Prometheus web.yml with basic auth..."
WEB_CONFIG_DIR="$DEPLOY_DIR/prometheus"
WEB_CONFIG_FILE="$WEB_CONFIG_DIR/web.yml"
PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"

if [[ -f "$WEB_CONFIG_FILE" ]]; then
    BACKUP_WEB="${WEB_CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$WEB_CONFIG_FILE" "$BACKUP_WEB"
    log_info "Backed up existing web.yml to $BACKUP_WEB"
fi

mkdir -p "$WEB_CONFIG_DIR"
if command -v python3 &>/dev/null && python3 -c "import bcrypt" 2>/dev/null; then
    HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw('$PROMETHEUS_PASSWORD'.encode(), bcrypt.gensalt()).decode())")
    cat > "$WEB_CONFIG_FILE" << EOF
basic_auth_users:
    admin: '$HASH'
EOF
    log_success "Prometheus web.yml generated with bcrypt hash"
else
    log_warning "bcrypt not available in Python – using plain-text password (INSECURE)."
    cat > "$WEB_CONFIG_FILE" << EOF
# WARNING: No bcrypt – basic auth uses plain text!
basic_auth_users:
    admin: '$PROMETHEUS_PASSWORD'
EOF
fi

# Determine if we should remove the Dynamo volume (only if --reset-data)
REMOVE_VOLUME=false
if [[ "$RESET_DATA" == true ]]; then
    if [[ "$AUTO" == true ]]; then
        REMOVE_VOLUME=true
        log_info "Auto mode: will remove dynamo_data volume without prompt."
    else
        echo ""
        echo -e "${YELLOW}WARNING: You are about to DELETE ALL Dynamo data (models, configurations).${NC}"
        echo "This action is irreversible."
        read -rp "Are you sure you want to remove the dynamo_data volume? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            REMOVE_VOLUME=true
        else
            log_info "Skipping volume removal."
        fi
    fi
fi

# Handle orphans (only if --force)
if [[ "$FORCE" == true ]]; then
    log_info "Force mode – recreating containers..."

    REMOVE_ORPHANS=""
    if [[ "$AUTO" == true ]]; then
        REMOVE_ORPHANS="--remove-orphans"
        log_info "Auto mode: removing orphans without prompt."
    else
        echo ""
        echo -e "${YELLOW}Do you want to remove orphan containers (containers that were part of this NETTRADES stack but are no longer defined in the compose file)?${NC}"
        echo "This will NOT affect other containers running on this server from different projects."
        read -rp "Remove orphans? (y/N): " confirm_orphans
        if [[ "$confirm_orphans" =~ ^[Yy]$ ]]; then
            REMOVE_ORPHANS="--remove-orphans"
        else
            REMOVE_ORPHANS=""
        fi
    fi

    if [[ "$RESET_DATA" == true ]]; then
        docker compose down $REMOVE_ORPHANS -v
        log_info "Removed all containers and volumes (--reset-data)"
    else
        docker compose down $REMOVE_ORPHANS
        log_info "Removed containers (data preserved)"
    fi

    if [[ "$REMOVE_VOLUME" == true ]] && [[ "$RESET_DATA" != true ]]; then
        if docker volume ls -q | grep -q "dynamo_data"; then
            docker volume rm dynamo_data 2>/dev/null || true
            log_info "Removed dynamo_data volume"
        else
            log_info "dynamo_data volume not found"
        fi
    fi
fi

# --- Start PostgreSQL only and initialise database ---
log_info "Starting PostgreSQL..."
docker compose up -d postgres

wait_for_postgres || {
    log_error "PostgreSQL failed to become ready. Cannot initialise database."
    exit 1
}

# Check if database is already initialised
if docker compose exec -T postgres psql -U odoo -d odoo -c "\dt" 2>/dev/null | grep -q "ir_module_module"; then
    log_success "Database already initialised – skipping init."
else
    log_info "Database seems empty – initialising with init-db.sql and base module..."
    if [[ -f "$INIT_SQL" ]]; then
        docker compose exec -T postgres psql -U odoo odoo < "$INIT_SQL" || {
            log_warning "Database initialisation may have already been done."
        }
    else
        log_error "init-db.sql not found!"
        exit 1
    fi

    # Install base module
    log_info "Initialising database with base modules..."
    docker compose run --rm odoo odoo -d odoo \
      --db_host=postgres \
      --db_port=5432 \
      --db_user=odoo \
      --db_password="$POSTGRES_PASSWORD" \
      -i base --stop-after-init --log-level=info
    log_success "Base modules installed"
fi

enable_pgcrypto || true

# -----------------------------------------------------------------------------
# 7. Build and start the full Docker Compose stack (with retry)
# -----------------------------------------------------------------------------
log_step "Building and starting Docker Compose stack (with retries)..."

max_attempts=3
attempt=1
while [ $attempt -le $max_attempts ]; do
    if docker compose up -d --build; then
        log_success "Docker Compose stack started successfully"
        break
    fi
    log_warning "Docker Compose up failed (attempt $attempt/$max_attempts). Retrying in 10s..."
    sleep 10
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    log_error "Failed to start Docker Compose stack after $max_attempts attempts."
    exit 1
fi

log_success "Docker Compose stack started"

# -----------------------------------------------------------------------------
# 8. Validate deployment
# -----------------------------------------------------------------------------
validate_deployment() {
    local max_retries=120                   # 120 * 2 = 240 seconds (4 minutes)
    local attempt=1
    local odoo_ready=false
    local langgraph_ready=false

    log_step "Validating deployment health..."

    # Wait for Odoo with improved logging of HTTP status
    log_info "Waiting for Odoo to become ready (this may take 2-3 minutes on first install)..."
    for i in {1..90}; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:8069 2>/dev/null)
        if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "302" || "$HTTP_CODE" == "303" ]]; then
            odoo_ready=true
            log_success "Odoo is ready (HTTP $HTTP_CODE)"
            break
        fi
        if [ $((i % 10)) -eq 0 ]; then
            log_info "Still waiting for Odoo... ($i/90 attempts) - HTTP $HTTP_CODE"
        fi
        sleep 2
    done

    if [ "$odoo_ready" != true ]; then
        log_error "Odoo failed to become ready within 3 minutes."
        log_info "Check Odoo logs with: docker logs odoo --tail 50"
        return 1
    fi

    # Wait for LangGraph
    log_info "Waiting for LangGraph to become ready..."
    while [[ $attempt -le $max_retries ]]; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null | grep -q "200"; then
            langgraph_ready=true
            log_success "LangGraph is healthy"
            break
        else
            if [ $((attempt % 10)) -eq 0 ]; then
                log_info "Still waiting for LangGraph... ($attempt/$max_retries attempts)"
            fi
        fi
        log_info "Waiting for services to be ready... ($attempt/$max_retries)"
        sleep 2
        attempt=$((attempt + 1))
    done

    if [ "$langgraph_ready" != true ]; then
        log_error "LangGraph failed to become ready within $((max_retries * 2)) seconds."
        log_info "Check LangGraph logs with: docker logs langgraph-server --tail 50"
        return 1
    fi

    # Wait for NETTRADES UI (on port 3002)
    log_info "Waiting for NETTRADES UI to become ready..."
    local ui_ready=false
    for i in {1..60}; do
        if curl -s -o /dev/null -w "%{http_code}" http://localhost:3002/ 2>/dev/null | grep -q "200"; then
            ui_ready=true
            log_success "NETTRADES UI is ready"
            break
        fi
        sleep 2
    done
    if [ "$ui_ready" != true ]; then
        log_warning "NETTRADES UI did not become ready within 2 minutes. Check logs."
    else
        log_success "NETTRADES UI is healthy"
    fi

    log_success "All services are healthy"
    return 0
}

if validate_deployment; then
    log_success "Deployment validation passed"
else
    log_error "Deployment validation failed. Check logs."
    exit 1
fi

# -----------------------------------------------------------------------------
# 9. Wait for Dynamo to be ready and download models
# -----------------------------------------------------------------------------
log_step "Waiting for Dynamo to be ready..."
for i in {1..60}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models | grep -q "200"; then
        log_success "Dynamo is ready"
        break
    fi
    sleep 2
done

# -----------------------------------------------------------------------------
# Download a small model for Dynamo (if not already present)
# -----------------------------------------------------------------------------
log_step "Downloading a small model for Dynamo (if not already present)..."
MODEL_NAME="${MODEL_NAME:-Qwen2.5-1.5B-Instruct}"
MODEL_URL="${MODEL_URL:-https://your-model-repo/models}"  # Replace with your actual model server

if [[ ! -d "$MODELS_DIR/$MODEL_NAME" ]]; then
    log_info "Downloading $MODEL_NAME from local server..."
    mkdir -p "$MODELS_DIR"
    if curl -sL "$MODEL_URL/$MODEL_NAME.tar.gz" -o "$MODELS_DIR/$MODEL_NAME.tar.gz"; then
        tar -xzf "$MODELS_DIR/$MODEL_NAME.tar.gz" -C "$MODELS_DIR"
        rm "$MODELS_DIR/$MODEL_NAME.tar.gz"
        echo "$MODEL_NAME" > "$MODELS_DIR/model_name.txt"
        log_success "Model downloaded and extracted."
    else
        log_warning "Model download failed. You may need to manually place a model in $MODELS_DIR."
    fi
else
    log_success "Model already present."
fi

# =============================================================================
# 10. DYNAMO SETUP – Fully Automated, No Login Required
# =============================================================================
log_step "Configuring NVIDIA Dynamo..."

if [[ -z "${DYNAMO_API_KEY:-}" ]]; then
    DYNAMO_API_KEY=$(generate_safe_password)
    safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"
    export DYNAMO_API_KEY
    log_info "Generated DYNAMO_API_KEY and updated .env"
fi

log_step "Waiting for Dynamo to be ready..."
DYNAMO_HEALTHY=false
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models \
        -H "Authorization: Bearer $DYNAMO_API_KEY" | grep -q "200"; then
        DYNAMO_HEALTHY=true
        log_success "Dynamo is ready"
        break
    fi
    sleep 2
done

log_step "Downloading a small model for Dynamo..."
MODEL_NAME="${MODEL_NAME:-Qwen2.5-1.5B-Instruct}"
MODEL_URL="${MODEL_URL:-https://your-model-repo/models}"  # Replace with your actual model server URL

if [[ ! -d "$MODELS_DIR/$MODEL_NAME" ]]; then
    log_info "Downloading $MODEL_NAME from $MODEL_URL..."
    mkdir -p "$MODELS_DIR"
    if curl -sL "$MODEL_URL/$MODEL_NAME.tar.gz" -o "$MODELS_DIR/$MODEL_NAME.tar.gz"; then
        tar -xzf "$MODELS_DIR/$MODEL_NAME.tar.gz" -C "$MODELS_DIR"
        rm "$MODELS_DIR/$MODEL_NAME.tar.gz"
        echo "$MODEL_NAME" > "$MODELS_DIR/model_name.txt"
        log_success "Model downloaded and extracted."
    else
        log_warning "Model download failed. You may need to manually place a model in $MODELS_DIR."
        log_info "The system will use llama.cpp as fallback."
    fi
else
    log_success "Model already present: $MODEL_NAME"
fi

# NOTE: The GGUF model for llama.cpp was downloaded earlier (before building images).
# The container will use that model if available.

# -----------------------------------------------------------------------------
# Determine inference backend
# -----------------------------------------------------------------------------
log_step "Determining inference backend..."

if [[ "$DYNAMO_HEALTHY" == true ]]; then
    log_success "Dynamo is healthy. Using Dynamo as the primary inference backend."
    LLM_BASE_URL="http://dynamo:8000/v1"
    OPENAI_API_KEY="$DYNAMO_API_KEY"
else
    log_warning "Dynamo not available or not ready. Falling back to llama.cpp (CPU)."
    LLM_BASE_URL="http://llama-cpp:8080/v1"
    OPENAI_API_KEY="dummy"
fi

safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
safe_sed_replace "$ENV_FILE" "DYNAMO_API_KEY" "$DYNAMO_API_KEY"
log_success ".env updated with inference backend settings"

log_step "Restarting LangGraph to apply new inference settings..."
docker compose restart langgraph-server

if curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/v1/models \
       -H "Authorization: Bearer $DYNAMO_API_KEY" | grep -q "200"; then
    log_success "Dynamo is healthy. Using Dynamo as the primary inference backend."
    LLM_BASE_URL="http://dynamo:8000/v1"
    OPENAI_API_KEY="$DYNAMO_API_KEY"
else
    log_warning "Dynamo not available or not ready. Falling back to llama.cpp (CPU)."
    LLM_BASE_URL="http://llama-cpp:8080/v1"
    OPENAI_API_KEY="dummy"
fi

log_step "Updating .env with inference backend settings..."
safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_BASE_URL"
safe_sed_replace "$ENV_FILE" "OPENAI_API_KEY" "$OPENAI_API_KEY"
log_success ".env updated"

log_step "Restarting LangGraph..."
docker compose restart langgraph-server

# -----------------------------------------------------------------------------
# 11. Install NETTRADES Odoo modules
# -----------------------------------------------------------------------------
log_step "Installing NETTRADES Odoo modules..."

log_info "Waiting for Odoo to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
        log_success "Odoo is ready"
        break
    fi
    sleep 2
done

log_info "Testing database connection..."
if ! docker compose exec -T odoo odoo -d odoo --db_host=postgres --db_port=5432 --db_user=odoo --db_password="$POSTGRES_PASSWORD" --stop-after-init --log-level=error 2>/dev/null; then
    log_error "Odoo cannot connect to PostgreSQL. Please check the password."
    log_error "Current .env password: $POSTGRES_PASSWORD"
    log_error "Try: docker compose exec odoo odoo -d odoo --db_host=postgres --db_user=odoo --db_password=... --stop-after-init"
    exit 1
fi

if [[ -f "$SCRIPT_DIR/install-modules.sh" ]]; then
    log_step "Installing NETTRADES Odoo modules..."
    ARGS=""
    [[ "$FORCE" == true ]] && ARGS="$ARGS --force"
    [[ "$UPGRADE" == true ]] && ARGS="$ARGS --upgrade"
    [[ "$AUTO" == true ]] && ARGS="$ARGS --auto"
    bash "$SCRIPT_DIR/install-modules.sh" $ARGS
else
    log_warning "install-modules.sh not found – skipping module installation"
fi

# -----------------------------------------------------------------------------
# 12. Create emergency Odoo user
# -----------------------------------------------------------------------------
log_step "Creating emergency Odoo user..."
EMERGENCY_PASSWORD=$(openssl rand -base64 24 | tr -d '+/=' | cut -c1-24)
docker compose exec -T postgres psql -U odoo -d odoo <<EOF
INSERT INTO res_users (login, password, active, create_date, write_date)
VALUES ('emergency', crypt('$EMERGENCY_PASSWORD', gen_salt('bf')), true, NOW(), NOW())
ON CONFLICT (login) DO NOTHING;
EOF
echo "$EMERGENCY_PASSWORD" > /root/emergency_password.txt
chmod 600 /root/emergency_password.txt
log_success "Emergency user created: login='emergency', password in /root/emergency_password.txt"

# -----------------------------------------------------------------------------
# 13. Set up cron for daily backups
# -----------------------------------------------------------------------------
log_step "Setting up cron for daily backups..."

BACKUP_SCRIPT="$DEPLOY_DIR/backup.sh"
if [[ -f "$BACKUP_SCRIPT" ]]; then
    if command -v crontab &>/dev/null; then
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
# 14. Final health checks
# -----------------------------------------------------------------------------
log_step "Verifying service health..."
sleep 10

if curl -s -o /dev/null -w "%{http_code}" http://localhost:8069 | grep -q "200\|302"; then
    log_success "Odoo is healthy"
else
    log_warning "Odoo health check failed – please check logs"
fi

if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
    log_success "LangGraph is healthy"
else
    log_warning "LangGraph health check failed – please check logs"
fi

if docker compose exec -T postgres pg_isready -U odoo &>/dev/null; then
    log_success "PostgreSQL is healthy"
else
    log_warning "PostgreSQL health check failed – please check logs"
fi

log_step "Waiting for LangGraph Server to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
        log_success "LangGraph Server is ready"
        break
    fi
    sleep 2
done

# NOTE: agent-chat-ui and copilotkit-frontend have been replaced by NETTRADES-UI.
# The health check for the frontend is now handled inside validate_deployment.

# =============================================================================
# 15. Ensure Let's Encrypt certificate
# =============================================================================
ensure_letsencrypt_certificate() {
    local domain="${DOMAIN:-nettrades.ai}"
    local acme_file="$DEPLOY_DIR/traefik-data/acme.json"
    local max_attempts=6
    local attempt=1

    log_step "Ensuring Let's Encrypt certificate for domain: $domain"

    if [[ "$domain" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_warning "DOMAIN is an IP address – Let's Encrypt cannot issue certificates for IPs. Skipping."
        return 0
    fi

    if [[ -f "$acme_file" ]] && grep -q '"Certificate"' "$acme_file"; then
        log_success "Certificate already exists in $acme_file"
        expire_date=$(grep -o '"notAfter":"[^"]*"' "$acme_file" | head -1 | cut -d'"' -f4 | cut -d'T' -f1)
        if [[ -n "$expire_date" ]]; then
            log_info "Certificate expires on: $expire_date"
        fi
        return 0
    fi

    log_info "Certificate not found or invalid. Triggering certificate request..."
    mkdir -p "$DEPLOY_DIR/traefik-data"
    chmod 755 "$DEPLOY_DIR/traefik-data"

    if [[ -f "$acme_file" ]]; then
        sudo rm -f "$acme_file"
        log_info "Removed old acme.json"
    fi

    docker compose restart traefik

    while [[ $attempt -le $max_attempts ]]; do
        log_info "Checking for certificate (attempt $attempt/$max_attempts)..."
        sleep 15

        if [[ -f "$acme_file" ]] && grep -q '"Certificate"' "$acme_file"; then
            log_success "Certificate successfully obtained!"
            docker compose restart traefik
            return 0
        fi

        if docker compose logs traefik 2>/dev/null | grep -q "acme: error"; then
            log_error "ACME error detected. Check Traefik logs for details."
            log_info "Common issues: domain not resolving, port 80 blocked, rate limiting."
            log_info "You may need to accept the self-signed certificate in your browser for now."
            break
        fi

        attempt=$((attempt + 1))
    done

    log_warning "Certificate could not be obtained after $max_attempts attempts."
    log_warning "The site will still work with the self-signed certificate, but your browser will show a warning."
    log_info "You can manually force a renewal by running:"
    echo "  cd $DEPLOY_DIR && sudo rm -f traefik-data/acme.json && docker compose restart traefik"
}

ensure_letsencrypt_certificate

# -----------------------------------------------------------------------------
# 16. Reset Grafana admin password (using correct syntax)
# -----------------------------------------------------------------------------
log_step "Resetting Grafana admin password..."
if [[ -n "${GRAFANA_PASSWORD:-}" ]]; then
    # Try the new 'grafana cli' command (preferred)
    if docker exec grafana grafana cli admin reset-admin-password "$GRAFANA_PASSWORD" &>/dev/null; then
        log_success "Grafana password reset successfully using 'grafana cli'"
    else
        # Fallback to old 'grafana-cli' (deprecated but may still work)
        if docker exec grafana grafana-cli admin reset-admin-password "$GRAFANA_PASSWORD" &>/dev/null; then
            log_success "Grafana password reset successfully using 'grafana-cli'"
        else
            log_warning "Could not reset Grafana password automatically."
            log_info "Try: docker exec grafana grafana cli admin reset-admin-password $GRAFANA_PASSWORD"
        fi
    fi
else
    log_warning "GRAFANA_PASSWORD not set – skipping password reset"
fi

# -----------------------------------------------------------------------------
# 17. Display final status
# -----------------------------------------------------------------------------
cd "$PROJECT_ROOT"
mark_phase_complete 2
touch /tmp/nettrades-phase2-completed

log_success "Phase 2 completed – Docker stack deployed with all modules"
echo ""
echo "============================================================"
echo " NETTRADES Platform is now running!"
echo "============================================================"
echo ""
docker compose -f "$DEPLOY_DIR/docker-compose.yaml" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Access the services:"
echo "  Frontend (UI): http://localhost:3002 (or http://nettrades.ai:3002)"
echo "  Odoo:      http://localhost:8069  (admin / password in .env ADMIN_PASSWORD)"
echo "  Forgejo:   http://localhost:3000"
echo "  Grafana:   http://localhost:3001  (admin / password in .env GRAFANA_PASSWORD)"
echo "  Prometheus: http://localhost:9090 (admin / password in .env PROMETHEUS_PASSWORD)"
echo "  Dynamo:    http://localhost:8001  (primary inference, API key in .env DYNAMO_API_KEY)"
echo "  llama.cpp: http://localhost:8080  (fallback inference, includes built-in UI)"
echo ""
echo "Emergency Odoo user: emergency (password in /root/emergency_password.txt)"
echo "Use this if you get locked out of admin."
if [[ "$ENVIRONMENT" == "production" ]]; then
    echo ""
    echo "Production mode: SSH is key-only on port 22. Use port 2222 for password auth."
    echo "SSH keys are stored in: $PROJECT_ROOT/ssh-keys/"
fi