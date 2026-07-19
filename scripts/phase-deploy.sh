#!/bin/bash
# =============================================================================
# FILE: scripts/phase-deploy.sh
# =============================================================================
# PURPOSE:
#   Phase 2: Single-VM Docker deployment with GPUStack as the inference engine.
#   This script deploys the entire NETTRADES stack using Docker Compose.
#   It is idempotent and safe to re-run.
#
#   It performs the following steps (in order):
#   1. Create required directories.
#   2. Download DeepSeek model (if not cached).
#   3. Build custom Docker images (Odoo, LangGraph) if missing.
#   4. Generate `init-db.sql` with all NETTRADES database tables.
#   5. Run security hardening (if Phase 0 not completed).
#   6. Start the Docker Compose stack (idempotent).
#   7. Initialise PostgreSQL database (only if empty).
#   8. Install all NETTRADES Odoo modules.
#   9. Set up cron for daily backups.
#   10. Verify service health.
#   11. Display final status.
#
# USAGE:
#   ./phase-deploy.sh [--auto] [--force] [--upgrade]
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
# SAFE PASSWORD GENERATOR – only alphanumeric characters
# This prevents .env parsing errors caused by '+', '/', '=', "'", etc.
# -----------------------------------------------------------------------------
generate_safe_password() {
    # 24 alphanumeric characters (no special characters)
    openssl rand -base64 24 | tr -d '+/=' | tr -d '\n' | cut -c1-24
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
GPUSTACK_DATA_DIR="$DEPLOY_DIR/gpustack-data"
MODELS_DIR="$GPUSTACK_DATA_DIR/models"

# [FIX] Define Odoo data directory early
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
# 1. Create required directories
# -----------------------------------------------------------------------------
log_step "Creating required directories..."
mkdir -p "$DATA_DIR/postgres" "$DATA_DIR/odoo" "$DATA_DIR/valkey" "$DATA_DIR/forgejo"
mkdir -p "$DATA_DIR/prometheus" "$DATA_DIR/grafana" "$DATA_DIR/backups"
mkdir -p "$GPUSTACK_DATA_DIR" "$MODELS_DIR" "$LOGS_DIR" "$ODOO_DATA_DIR"
log_success "Directories created"

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
    # [The full init-db.sql content is here – omitted for brevity, but it's the same as before]
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

# Ensure .env has Unix line endings (fix Windows CRLF)
if command -v dos2unix &>/dev/null; then
    dos2unix "$ENV_FILE" 2>/dev/null || true
fi

# Source .env for environment variables
set -a
source "$ENV_FILE"
set +a

# -----------------------------------------------------------------------------
# Check PostgreSQL password consistency
# -----------------------------------------------------------------------------
check_postgres_password() {
    local pg_container=$(docker compose ps -q postgres 2>/dev/null)
    if [[ -n "$pg_container" ]] && docker inspect -f '{{.State.Running}}' "$pg_container" 2>/dev/null | grep -q true; then
        local actual_pass=$(docker exec "$pg_container" env | grep POSTGRES_PASSWORD | cut -d= -f2)
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

# -----------------------------------------------------------------------------
# Preserve PostgreSQL password if container already exists
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Auto-generate strong secrets for all services (if missing or weak)
# -----------------------------------------------------------------------------
# We use the safe password generator that avoids special characters
generate_secret() {
    generate_safe_password
}

# List of variables to ensure strong values
SECRET_VARS=(
    POSTGRES_PASSWORD
    ADMIN_PASSWORD
    FORGEJO_DB_PASSWORD
    FORGEJO_SECRET_KEY
    GRAFANA_PASSWORD
    PROMETHEUS_PASSWORD
    LANGGRAPH_API_KEY
    GPUSTACK_ADMIN_PASSWORD
    GPUSTACK_JWT_SECRET
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

# -----------------------------------------------------------------------------
# Generate Prometheus web.yml with basic auth (using the password from .env)
# -----------------------------------------------------------------------------
log_step "Generating Prometheus web.yml with basic auth..."
WEB_CONFIG_DIR="$DEPLOY_DIR/prometheus"
WEB_CONFIG_FILE="$WEB_CONFIG_DIR/web.yml"
PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"

# Backup existing web.yml if present
if [[ -f "$WEB_CONFIG_FILE" ]]; then
    BACKUP_WEB="${WEB_CONFIG_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$WEB_CONFIG_FILE" "$BACKUP_WEB"
    log_info "Backed up existing web.yml to $BACKUP_WEB"
fi

# -----------------------------------------------------------------------------
# [FIX] Use the dedicated Python script for bcrypt hashing
# -----------------------------------------------------------------------------
if command -v python3 &>/dev/null && python3 -c "import bcrypt" 2>/dev/null; then
    chmod +x "$SCRIPT_DIR/generate-bcrypt-hash.py" 2>/dev/null || true
    if [[ -f "$SCRIPT_DIR/generate-bcrypt-hash.py" ]]; then
        PROMETHEUS_HASH=$(python3 "$SCRIPT_DIR/generate-bcrypt-hash.py" <<< "$PROMETHEUS_PASSWORD")
        mkdir -p "$WEB_CONFIG_DIR"
        cat > "$WEB_CONFIG_FILE" << EOF
basic_auth_users:
    admin: $PROMETHEUS_HASH
EOF
        log_success "Prometheus web.yml generated with basic auth"
    else
        log_warning "generate-bcrypt-hash.py not found – skipping web.yml generation"
    fi
else
    log_warning "python3-bcrypt not installed. Skipping automatic web.yml generation."
    mkdir -p "$WEB_CONFIG_DIR"
    cat > "$WEB_CONFIG_FILE" << EOF
# WARNING: No authentication configured. Install python3-bcrypt and re-run.
EOF
fi

# -----------------------------------------------------------------------------
# Generate Grafana datasource provisioning file (using the Prometheus password)
# -----------------------------------------------------------------------------
log_step "Generating Grafana datasource provisioning..."
GRAFANA_DATASOURCES_DIR="$DEPLOY_DIR/grafana-datasources"
GRAFANA_DATASOURCES_FILE="$GRAFANA_DATASOURCES_DIR/datasources.yaml"
PROMETHEUS_PASSWORD="${PROMETHEUS_PASSWORD:-admin}"

mkdir -p "$GRAFANA_DATASOURCES_DIR"

# Backup existing datasources.yaml if present
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

# -----------------------------------------------------------------------------
# Determine if we should remove the GPUStack volume (only if --reset-data)
# -----------------------------------------------------------------------------
REMOVE_VOLUME=false
if [[ "$RESET_DATA" == true ]]; then
    if [[ "$AUTO" == true ]]; then
        REMOVE_VOLUME=true
        log_info "Auto mode: will remove gpustack_data volume without prompt."
    else
        echo ""
        echo -e "${YELLOW}WARNING: You are about to DELETE ALL GPUStack data (models, configurations, statistics).${NC}"
        echo "This action is irreversible."
        read -rp "Are you sure you want to remove the gpustack_data volume? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            REMOVE_VOLUME=true
        else
            log_info "Skipping volume removal."
        fi
    fi
fi

# -----------------------------------------------------------------------------
# Handle orphans (only if --force)
# -----------------------------------------------------------------------------
if [[ "$FORCE" == true ]]; then
    log_info "Force mode – recreating containers..."

    # Ask about removing orphans (unless auto)
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
        if docker volume ls -q | grep -q "gpustack_data"; then
            docker volume rm gpustack_data 2>/dev/null || true
            log_info "Removed gpustack_data volume"
        else
            log_info "gpustack_data volume not found"
        fi
    fi
fi

# -----------------------------------------------------------------------------
# Build and start the stack (with retry)
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
# Capture GPUStack initial admin password
# -----------------------------------------------------------------------------
log_step "Capturing initial admin password immediately..."
INITIAL_PASS_FILE="/var/lib/gpustack/initial_admin_password"
if docker exec gpustack test -f "$INITIAL_PASS_FILE" 2>/dev/null; then
    INITIAL_PASS=$(docker exec gpustack cat "$INITIAL_PASS_FILE" | tr -d '\n')
    if [[ -n "$INITIAL_PASS" ]]; then
        log_info "Initial admin password captured: $INITIAL_PASS"
        safe_sed_replace "$ENV_FILE" "GPUSTACK_ADMIN_PASSWORD" "$INITIAL_PASS"
        export GPUSTACK_ADMIN_PASSWORD="${INITIAL_PASS}"
        log_success "Updated .env with the initial admin password"
    fi
else
    log_info "Initial password file not found – will generate a new one."
fi

# -----------------------------------------------------------------------------
# Wait for GPUStack to be ready
# -----------------------------------------------------------------------------
log_step "Waiting for GPUStack to be ready..."
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/v1/models | grep -q "200\|401"; then
        log_success "GPUStack is ready"
        break
    fi
    sleep 2
done

# -----------------------------------------------------------------------------
# Generate a new GPUStack admin password
# -----------------------------------------------------------------------------
log_step "Generating new GPUStack admin password..."
# Use the safe password generator
SAFE_GPUSTACK_PASS=$(generate_safe_password)
safe_sed_replace "$ENV_FILE" "GPUSTACK_ADMIN_PASSWORD" "$SAFE_GPUSTACK_PASS"
export GPUSTACK_ADMIN_PASSWORD="$SAFE_GPUSTACK_PASS"
log_success "Generated safe password: $SAFE_GPUSTACK_PASS"

log_info "Waiting 10 seconds for password propagation..."
sleep 10

# -----------------------------------------------------------------------------
# Download GGUF model
# -----------------------------------------------------------------------------
log_step "Downloading GGUF model into GPUStack's model directory..."
MODEL_NAME="deepseek-1.5b"
if [[ -f "$SCRIPT_DIR/download-model.sh" ]]; then
    if ! bash "$SCRIPT_DIR/download-model.sh" --model "$MODEL_NAME" --format gguf --dir "$MODELS_DIR"; then
        log_warning "GGUF model download failed. You can manually add models via GPUStack UI."
    else
        log_success "GGUF model downloaded to $MODELS_DIR"
    fi
else
    log_warning "download-model.sh not found – skipping model download"
fi

# -----------------------------------------------------------------------------
# Authenticate with GPUStack API and register the model
# -----------------------------------------------------------------------------
log_step "Authenticating with GPUStack API and registering model..."

TOKEN=""
if [[ -z "${GPUSTACK_ADMIN_PASSWORD:-}" ]]; then
    log_warning "GPUSTACK_ADMIN_PASSWORD not set – skipping API automation."
else
    # Wait longer for password propagation
    log_info "Waiting 30 seconds for GPUStack password propagation..."
    sleep 30

    # Retry login with exponential backoff (more attempts)
    for attempt in {1..10}; do
        log_info "Login attempt $attempt/10..."

        # Wait for the auth endpoint to be ready (with progressive delay)
        for i in {1..10}; do
            if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/auth/login | grep -q "405\|200\|401"; then
                break
            fi
            sleep 2
        done

        # Use jq to build the JSON payload safely
        LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8080/auth/login \
            -H "Content-Type: application/json" \
            -d "$(jq -n --arg pass "$GPUSTACK_ADMIN_PASSWORD" '{username:"admin", password:$pass}')")

        TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.token // empty')

        if [[ -n "$TOKEN" ]]; then
            log_success "GPUStack authentication successful"
            break
        else
            wait_time=$((attempt * 2))
            log_warning "Login attempt $attempt failed. Waiting ${wait_time} seconds before retry..."
            sleep $wait_time
        fi
    done

    if [[ -n "$TOKEN" ]]; then
        # Register the downloaded GGUF file using the correct v2 endpoint
        GGUF_FILE=$(find "$MODELS_DIR" -name "*.gguf" -type f | head -1)
        if [[ -n "$GGUF_FILE" ]]; then
            MODEL_PATH="/models/$(basename "$GGUF_FILE")"
            log_info "Registering model file via API: $MODEL_PATH"
            curl -X POST http://localhost:8080/v2/model-files \
                -H "Authorization: Bearer $TOKEN" \
                -H "Content-Type: application/json" \
                -d "{\"path\": \"$MODEL_PATH\"}" 2>/dev/null && \
                log_success "Model registered successfully" || \
                log_warning "Model registration failed – you can register manually via GPUStack UI"
        else
            log_warning "No GGUF file found – skipping registration"
        fi
    else
        log_warning "Failed to get GPUStack token after multiple attempts."
        log_info "You can register the model manually via GPUStack UI at http://localhost:8080"
        log_info "Username: admin, Password: $GPUSTACK_ADMIN_PASSWORD"
    fi
fi

# -----------------------------------------------------------------------------
# Reset Grafana admin password to match .env
# -----------------------------------------------------------------------------
log_step "Resetting Grafana admin password..."
# Wait for Grafana to be ready
for i in {1..30}; do
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/api/health | grep -q "200"; then
        log_success "Grafana is ready"
        break
    fi
    sleep 2
done

if [[ -n "${GRAFANA_PASSWORD:-}" ]]; then
    RESET_SUCCESS=false

    # -------------------------------------------------------------------------
    # Step 1: Check if the password from .env already works
    # -------------------------------------------------------------------------
    if curl -s -o /dev/null -w "%{http_code}" -u "admin:$GRAFANA_PASSWORD" http://localhost:3001/api/org | grep -q "200"; then
        log_success "Grafana password from .env is already correct – no action needed"
        RESET_SUCCESS=true
    fi

    # -------------------------------------------------------------------------
    # Step 2: Try API login with default admin/admin (for fresh installs)
    # -------------------------------------------------------------------------
    if [[ "$RESET_SUCCESS" != true ]]; then
        if curl -s -o /dev/null -w "%{http_code}" -u "admin:admin" http://localhost:3001/api/org | grep -q "200"; then
            log_info "Logged in with default admin/admin. Changing password via API..."
            COOKIE_JAR=$(mktemp)
            curl -s -X POST http://localhost:3001/login \
                -H "Content-Type: application/json" \
                -d '{"user":"admin","password":"admin"}' \
                -c "$COOKIE_JAR" > /dev/null

            if curl -s -X PUT http://localhost:3001/api/user/password \
                -H "Content-Type: application/json" \
                -H "X-Grafana-Org-Id: 1" \
                -b "$COOKIE_JAR" \
                -d "{\"oldPassword\":\"admin\",\"newPassword\":\"$GRAFANA_PASSWORD\",\"confirmNew\":\"$GRAFANA_PASSWORD\"}" \
                | grep -q "message.*Password changed"; then
                log_success "Grafana password changed successfully via API"
                RESET_SUCCESS=true
            else
                log_warning "API password change failed"
            fi
            rm -f "$COOKIE_JAR"
        fi
    fi

    # -------------------------------------------------------------------------
    # Step 3: Fall back to CLI methods (for existing installations)
    # -------------------------------------------------------------------------
    if [[ "$RESET_SUCCESS" != true ]]; then
        log_info "API methods failed; trying CLI..."
        
        # Try grafana-cli
        if docker exec grafana grafana-cli admin reset-admin-password "$GRAFANA_PASSWORD" &>/dev/null; then
            log_success "Grafana password reset successfully using grafana-cli"
            RESET_SUCCESS=true
        fi
        # Try unified grafana admin
        if [[ "$RESET_SUCCESS" != true ]]; then
            if docker exec grafana grafana admin reset-admin-password "$GRAFANA_PASSWORD" &>/dev/null; then
                log_success "Grafana password reset successfully using grafana admin"
                RESET_SUCCESS=true
            fi
        fi
    fi

    if [[ "$RESET_SUCCESS" != true ]]; then
        log_warning "Could not reset Grafana password automatically."
        log_info "Try: docker exec -it grafana grafana-cli admin reset-admin-password $GRAFANA_PASSWORD"
    fi
else
    log_warning "GRAFANA_PASSWORD not set – skipping password reset"
fi

# -----------------------------------------------------------------------------
# Update .env with LLM_BASE_URL
# LangGraph runs inside the Docker network and communicates with the gpustack service by its container name gpustack hence LLM_BASE_URL=http://gpustack:8080/v1
# -----------------------------------------------------------------------------
log_step "Updating .env to use GPUStack..."
LLM_URL="LLM_BASE_URL=http://gpustack:8080/v1"
if grep -q "^LLM_BASE_URL=" "$ENV_FILE"; then
    safe_sed_replace "$ENV_FILE" "LLM_BASE_URL" "$LLM_URL"
else
    echo "" >> "$ENV_FILE"
    echo "${LLM_URL}" >> "$ENV_FILE"
fi
log_success ".env updated"

# -----------------------------------------------------------------------------
# Restart LangGraph to pick up new URL
# -----------------------------------------------------------------------------
log_step "Restarting LangGraph..."
docker compose restart langgraph

# -----------------------------------------------------------------------------
# Initialise PostgreSQL database (only if empty)
# -----------------------------------------------------------------------------
log_step "Initialising PostgreSQL database..."

# Wait for PostgreSQL to be ready
log_info "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker compose -f "$DEPLOY_DIR/docker-compose.yaml" exec postgres pg_isready -U odoo &>/dev/null; then
        log_success "PostgreSQL is ready"
        break
    fi
    sleep 2
done

# Check if database is already initialised
if docker compose exec -T postgres psql -U odoo -d odoo -c "SELECT 1 FROM ir_module_module LIMIT 1" &>/dev/null; then
    log_success "Database already initialised – skipping init."
else
    log_info "Database seems empty – initialising with base modules..."
    if [[ -f "$INIT_SQL" ]]; then
        docker exec -i postgres psql -U odoo odoo < "$INIT_SQL" 2>/dev/null || {
            log_warning "Database initialisation may have already been done."
        }
    else
        log_error "init-db.sql not found!"
        exit 1
    fi

    # Install base module
    # Install base module with explicit database connection parameters
    log_info "Initialising database with base modules..."
    docker compose exec -T odoo odoo -d odoo \
      --db_host=postgres \
      --db_port=5432 \
      --db_user=odoo \
      --db_password="$POSTGRES_PASSWORD" \
      -i base --stop-after-init --log-level=info
    log_success "Base modules installed"
fi

# -----------------------------------------------------------------------------
# Install NETTRADES Odoo modules
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

# Test database connection from Odoo container
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
# Create emergency Odoo user
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
# Set up cron for daily backups
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
# Verify service health
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

if docker exec postgres pg_isready -U odoo &>/dev/null; then
    log_success "PostgreSQL is healthy"
else
    log_warning "PostgreSQL health check failed – please check logs"
fi

# -----------------------------------------------------------------------------
# Display final status
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
echo "  Odoo:      http://localhost:8069  (admin / password in .env ADMIN_PASSWORD)"
echo "  Forgejo:   http://localhost:3000"
echo "  Grafana:   http://localhost:3001  (admin / password in .env GRAFANA_PASSWORD)"
echo "  Prometheus: http://localhost:9090 (admin / password in .env PROMETHEUS_PASSWORD)"
echo "  GPUStack:  http://localhost:8080  (admin / password in .env GPUSTACK_ADMIN_PASSWORD)"
echo ""
echo "Emergency Odoo user: emergency (password in /root/emergency_password.txt)"
echo "Use this if you get locked out of admin."
if [[ "$ENVIRONMENT" == "production" ]]; then
    echo ""
    echo "Production mode: SSH is $(if [[ "$KEEP_PASSWORD_AUTH" == true ]]; then echo "password + key"; else echo "key-only"; fi) on port 22."
    echo "Rescue SSH (password auth) is available on port 2222."
    echo "SSH keys are stored in: $PROJECT_ROOT/ssh-keys/"
fi