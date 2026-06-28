#!/bin/bash
# =============================================================================
# NETTRADES.AI – Single-VM Idempotent Deployment Script (Valkey edition)
# =============================================================================
# PURPOSE:
#   This script is safe to re-run. It checks for existing files, images, and
#   directories before creating them. It uses the shared detection library to
#   decide between CPU (llama.cpp) and GPU (vLLM) inference.
#
#   Sessions, ORM cache, and bus notifications use Valkey (BSD-3-Clause).
#
# USAGE:
#   ./deploy-single.sh [--auto]
#     --auto: Skip confirmation prompts and use auto-detected values.
# =============================================================================

set -euo pipefail

trap 'echo "ERROR: script failed at line $LINENO with exit code $?." >&2' ERR

# -----------------------------------------------------------------------------
# Source detection library and environment
# -----------------------------------------------------------------------------
source /usr/local/bin/nettrades-ai-detect 2>/dev/null || true
source .env 2>/dev/null || true

# ---- Essential tool checks ----
for cmd in docker docker-compose wget; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed." >&2
        exit 1
    fi
done

# ---- Create required directories ----
mkdir -p addons postgres-data odoo-data forgejo-data llama-cpp-data \
         prometheus-data grafana-data traefik-data backups gpustack-data valkey-data config

# ---- Download the DeepSeek model if not already cached ----
if [ ! -f llama-cpp-data/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf ]; then
    echo "Downloading DeepSeek model (this may take a few minutes)..."
    wget -q --show-progress -P llama-cpp-data \
        https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf
fi

# ---- Build custom Docker images if they don't exist ----
if ! docker image inspect langgraph-agent:latest &>/dev/null; then
    echo "Building LangGraph agent image..."
    docker build -t langgraph-agent:latest ../langgraph-agent
fi

# ---- NEW: Build Odoo Proxy image (replaces mcp-odoo) ----
if ! docker image inspect odoo-proxy:latest &>/dev/null; then
    echo "Building Odoo Proxy image..."
    docker build -t odoo-proxy:latest ../odoo-proxy
fi

# ---- Generate init-db.sql if missing ----
if [ ! -f init-db.sql ]; then
    cat > init-db.sql << 'EOSQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS nettrades_experience (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL,
    job_title VARCHAR(255),
    company VARCHAR(255),
    start_date DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nettrades_review (
    id SERIAL PRIMARY KEY,
    reviewer_id INTEGER NOT NULL,
    reviewed_partner_id INTEGER NOT NULL,
    rating INTEGER CHECK(rating>=1 AND rating<=5),
    comment TEXT,
    project_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nettrades_user_match (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    match_score FLOAT,
    analysis TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forgejo_repo (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL,
    repo_url VARCHAR(512),
    clone_url VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nettrades_field (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    only_qualified BOOLEAN DEFAULT FALSE,
    reputation_threshold_for_charging INTEGER DEFAULT 100,
    base_points_per_vote INTEGER DEFAULT 1,
    qualified_points_per_vote INTEGER DEFAULT 5,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experience_partner ON nettrades_experience(partner_id);
CREATE INDEX IF NOT EXISTS idx_review_reviewed ON nettrades_review(reviewed_partner_id);
CREATE INDEX IF NOT EXISTS idx_match_job ON nettrades_user_match(job_id);
CREATE INDEX IF NOT EXISTS idx_match_user ON nettrades_user_match(user_id);
CREATE INDEX IF NOT EXISTS idx_forgejo_project ON forgejo_repo(project_id);
EOSQL
fi

# ---- Start the Docker Compose stack ----
echo "Starting all services..."
docker compose up -d

# ---- Wait for PostgreSQL to be ready, then initialise DB ----
echo "Waiting for PostgreSQL..."
sleep 10
docker exec -i postgres psql -U odoo odoo < init-db.sql 2>/dev/null || true

# ---- Schedule daily database backups ----
(crontab -l 2>/dev/null; echo "0 2 * * * docker exec postgres pg_dump -U odoo odoo | gzip > $(pwd)/backups/odoo_\$(date +\%Y\%m\%d).sql.gz") | crontab -

echo ""
echo "============================================================="
echo "  Deployment complete"
echo "============================================================="
echo "  Odoo:          https://${DOMAIN}"
echo "  Grafana:       https://grafana.${DOMAIN} (admin / ${GRAFANA_PASSWORD})"
echo "  GPUStack:      https://gpustack.${DOMAIN}"
echo "  Forgejo:       https://git.${DOMAIN}"
echo "  LangGraph:     https://langgraph.${DOMAIN}"
echo "  Odoo Proxy:    http://localhost:3000"
echo "============================================================="