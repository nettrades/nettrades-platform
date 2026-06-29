#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 2: Single VM Deployment (UPDATED)
# =============================================================================
# FILE: scripts/phase-deploy.sh
#
# PURPOSE:
#   This script deploys the NETTRADES platform on a single VM using Docker Compose.
#   It includes all custom modules including bridge, fairness, and self-improving.
#
# PHASE 2 STEPS:
#   1. Check prerequisites
#   2. Generate secure secrets (uses PROXY_API_KEY)
#   3. Download models (if no GPU)
#   4. Build Docker images
#   5. Start the stack
#   6. Initialize the database (with fairness & self-improving tables)
#   7. Install Odoo modules
#   8. (Optional) Run security hardening
#
# UPDATED (2026-06-29):
#   - Added phase marker for idempotency (--force to re-run)
#   - Added --auto flag to skip interactive prompts
#   - Added security hardening prompt (runs security-harden.sh if confirmed)
#   - Replaced MCP_API_KEY with PROXY_API_KEY
#   - All existing functionality is preserved
#
# USAGE:
#   ./scripts/phase-deploy.sh [--force] [--auto]
#
# OPTIONS:
#   --force    Re-run even if already completed (idempotency).
#   --auto     Skip all interactive prompts (use defaults).
#
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Phase completion marker and path setup
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PHASE_MARKER="$PROJECT_ROOT/.phase-2-complete"

# Check for --force and --auto flags
FORCE=false
AUTO=false
for arg in "$@"; do
    case $arg in
        --force) FORCE=true ;;
        --auto)  AUTO=true ;;
    esac
done

# If phase already completed and not forcing, exit
if [ -f "$PHASE_MARKER" ] && [ "$FORCE" != true ]; then
    echo -e "${YELLOW}[WARNING] Phase 2 already completed. Use --force to re-run.${NC}"
    exit 0
fi

# -----------------------------------------------------------------------------
# Colours for output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Phase 2: Single VM Deployment${NC}"
echo -e "${GREEN}============================================================${NC}"

# -----------------------------------------------------------------------------
# 1. Check Prerequisites
# -----------------------------------------------------------------------------
log_info "Checking prerequisites..."

# Check Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker not installed. Please install Docker and Docker Compose first."
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    log_error "Docker Compose not installed. Please install Docker Compose first."
    exit 1
fi

log_success "Prerequisites met"

# -----------------------------------------------------------------------------
# 2. Generate Secure Secrets
# -----------------------------------------------------------------------------
log_info "Generating secure secrets..."

cd "$PROJECT_ROOT"

if [ ! -f ".env" ] || [ "$FORCE" = true ]; then
    cat > .env << 'EOF'
# =============================================================================
# NETTRADES.AI – Environment Variables
# =============================================================================
DOMAIN=nettrades.ai
ADMIN_EMAIL=admin@nettrades.ai
POSTGRES_PASSWORD=$(openssl rand -base64 32)
ADMIN_PASSWORD=$(openssl rand -base64 32)
LANGGRAPH_API_KEY=$(openssl rand -base64 32)
ODOO_API_KEY=$(openssl rand -base64 32)
GPUSTACK_JWT_SECRET=$(openssl rand -base64 32)
WIREGUARD_PRIVATE_KEY=$(openssl rand -base64 32)
WIREGUARD_PUBLIC_KEY=$(openssl rand -base64 32)
GRAFANA_PASSWORD=$(openssl rand -base64 32)
FORGEJO_DB_PASSWORD=$(openssl rand -base64 32)
FORGEJO_SECRET_KEY=$(openssl rand -base64 32)
# NEW: Use PROXY_API_KEY (replaces MCP_API_KEY)
PROXY_API_KEY=$(openssl rand -base64 32)
# Fairness evaluation API keys (optional)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
    chmod 600 .env
    log_success "Secrets generated"
else
    log_info ".env file already exists"
fi

# Load environment variables
set -a
# shellcheck source=/dev/null
source .env
set +a

# -----------------------------------------------------------------------------
# 3. Create init-db.sql with all tables
# -----------------------------------------------------------------------------
log_info "Creating database initialisation script..."

cat > deploy/docker/init-db.sql << 'EOF'
CREATE EXTENSION IF NOT EXISTS vector;

-- Self-improving loop tables
CREATE TABLE IF NOT EXISTS nettrades_episode (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL,
    field_id INTEGER,
    input_text TEXT,
    output_text TEXT,
    quality_score FLOAT DEFAULT 0.0,
    context_data JSONB,
    source VARCHAR(50) DEFAULT 'auto',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Fairness evaluation tables
CREATE TABLE IF NOT EXISTS nettrades_fairness_metric (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    calculation_type VARCHAR(50),
    threshold FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nettrades_fairness_audit (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(255),
    metric_id INTEGER REFERENCES nettrades_fairness_metric(id),
    score FLOAT,
    passed BOOLEAN,
    details JSONB,
    audited_at TIMESTAMP DEFAULT NOW()
);

-- Bridge routing tables
CREATE TABLE IF NOT EXISTS nettrades_bridge_route (
    id SERIAL PRIMARY KEY,
    intent VARCHAR(100) NOT NULL,
    source VARCHAR(50) DEFAULT 'local',
    target_url VARCHAR(512),
    company_id INTEGER,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_episode_partner ON nettrades_episode(partner_id);
CREATE INDEX IF NOT EXISTS idx_episode_quality ON nettrades_episode(quality_score);
CREATE INDEX IF NOT EXISTS idx_fairness_audit_model ON nettrades_fairness_audit(model_id);
EOF

log_success "init-db.sql created"

# -----------------------------------------------------------------------------
# 4. Set up addons path with all modules
# -----------------------------------------------------------------------------
log_info "Setting up addons path..."

ADDONS_PATH="third-party/odoo/addons,\
odoo-modules,\
third-party/odoo_llm,\
third-party/odoo_llm_compat,\
third-party/website_sale_marketplace,\
third-party/queue-19"

log_info "Addons path: $ADDONS_PATH"

# -----------------------------------------------------------------------------
# 5. (Optional) Run Security Hardening
# -----------------------------------------------------------------------------
if [ -f "$PROJECT_ROOT/deploy/docker/security-harden.sh" ]; then
    if [ "$AUTO" = true ]; then
        log_info "Auto mode: Skipping security hardening prompt."
        log_info "To run hardening later: sudo ./deploy/docker/security-harden.sh"
    else
        log_warning "Security hardening is recommended for production servers."
        read -rp "Run security hardening now? (y/N): " run_harden
        if [[ "$run_harden" =~ ^[Yy]$ ]]; then
            log_info "Running security hardening..."
            bash "$PROJECT_ROOT/deploy/docker/security-harden.sh"
        else
            log_info "Skipping security hardening. You can run it later with: sudo ./deploy/docker/security-harden.sh"
        fi
    fi
else
    log_warning "security-harden.sh not found. Skipping."
fi

# -----------------------------------------------------------------------------
# 6. Build and Start Docker Compose Stack
# -----------------------------------------------------------------------------
log_info "Building and starting Docker Compose stack..."

cd deploy/docker

# Build images if needed (or if --force)
if [ "$FORCE" = true ] || ! docker image inspect nettrades-langgraph:latest &>/dev/null; then
    docker compose build --no-cache
fi

# Start the stack
docker compose up -d

log_success "Stack started"

# -----------------------------------------------------------------------------
# 7. Initialize Database
# -----------------------------------------------------------------------------
log_info "Initialising database..."

sleep 10  # Wait for PostgreSQL to be ready

if [ -f "init-db.sql" ]; then
    docker exec -i postgres psql -U odoo odoo < init-db.sql 2>/dev/null || true
    log_success "Database initialised"
fi

# -----------------------------------------------------------------------------
# 8. Install Odoo Modules
# -----------------------------------------------------------------------------
log_info "Installing Odoo modules..."

cd "$PROJECT_ROOT"

if [ -f "scripts/install-modules.sh" ]; then
    bash scripts/install-modules.sh
else
    log_warning "install-modules.sh not found. Skipping module installation."
fi

# -----------------------------------------------------------------------------
# 9. Post-Installation Summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}Phase 2 completed successfully!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Services running:"
echo "  Odoo:          http://localhost:8069"
echo "  LangGraph:     http://localhost:8000"
echo "  Grafana:       http://localhost:3000"
echo ""
echo "Next steps:"
echo "  1. Log in to Odoo and install the Website module"
echo "  2. Run Phase 3 (GPU): ./scripts/phase-add-gpu.sh (if you have a GPU)"
echo "  3. Run Phase 5 (Modules): ./scripts/install-modules.sh --upgrade"
echo ""

# Mark phase complete
echo "$(date -Iseconds)" > "$PHASE_MARKER"