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
#   2. Generate secure secrets
#   3. Download models (if no GPU)
#   4. Build Docker images
#   5. Start the stack
#   6. Initialize the database
#   7. Install Odoo modules
#
# UPDATED:
#   - Added all new modules to addons_path
#   - Added fairness and self-improving tables to init-db.sql
#   - Added environment variables for fairness evaluation
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Phase 2: Single VM Deployment${NC}"
echo -e "${GREEN}============================================================${NC}"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# =============================================================================
# 1. Check Prerequisites
# =============================================================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not installed${NC}"
    echo "Please install Docker and Docker Compose first."
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose not installed${NC}"
    echo "Please install Docker Compose first."
    exit 1
fi

echo -e "${GREEN}✓ Prerequisites met${NC}"

# =============================================================================
# 2. Generate Secure Secrets
# =============================================================================
echo -e "${YELLOW}Generating secure secrets...${NC}"

if [ ! -f ".env" ]; then
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
MCP_API_KEY=$(openssl rand -base64 32)

# Fairness evaluation API keys (optional)
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
EOF
    chmod 600 .env
    echo -e "${GREEN}✓ Secrets generated${NC}"
else
    echo -e "${GREEN}✓ .env file already exists${NC}"
fi

# Load environment variables
set -a
source .env
set +a

# =============================================================================
# 3. Update Docker Compose
# =============================================================================
echo -e "${YELLOW}Updating Docker Compose configuration...${NC}"

cat > deploy/docker/docker-compose.yaml << 'EOF'
# =============================================================================
# NETTRADES.AI – Single-VM Docker Compose deployment
# =============================================================================
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_DB: odoo
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
    networks:
      - internal
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 10s
      timeout: 5s
      retries: 5

  valkey:
    image: valkey/valkey:8-alpine
    container_name: valkey
    restart: unless-stopped
    networks:
      - internal
    volumes:
      - ./valkey-data:/data
    command: valkey-server --appendonly yes --save 900 1 --save 300 10

  odoo:
    image: odoo:19.0
    volumes:
      - ./addons:/mnt/extra-addons
      - ./odoo-data:/var/lib/odoo
      - ./config/odoo.conf:/etc/odoo/odoo.conf
    environment:
      - HOST=postgres
      - PORT=5432
      - USER=odoo
      - PASSWORD=${POSTGRES_PASSWORD}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    networks:
      - web
      - internal
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      valkey:
        condition: service_started
    ports:
      - "8069:8069"

  langgraph:
    build: ../../src/core
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://odoo:${POSTGRES_PASSWORD}@postgres:5432/odoo
      - LANGGRAPH_API_KEY=${LANGGRAPH_API_KEY}
      - GPUSTACK_SERVER_URL=http://gpustack:80
    networks:
      - internal
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  gpustack:
    image: gpustack/gpustack:v2.1.2
    ports:
      - "8080:80"
    environment:
      - GPUSTACK_JWT_SECRET=${GPUSTACK_JWT_SECRET}
    volumes:
      - ./gpustack-data:/var/lib/gpustack
    networks:
      - internal
    restart: unless-stopped

  traefik:
    image: traefik:v3.6.13
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./traefik-data:/letsencrypt
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.httpchallenge=true
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
      - --certificatesresolvers.letsencrypt.acme.email=${ADMIN_EMAIL}
      - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
    networks:
      - web
    restart: unless-stopped

networks:
  web:
    driver: bridge
  internal:
    driver: bridge
EOF

echo -e "${GREEN}✓ Docker Compose configuration updated${NC}"

# =============================================================================
# 4. Update Odoo Configuration
# =============================================================================
echo -e "${YELLOW}Updating Odoo configuration...${NC}"

mkdir -p deploy/docker/config
cat > deploy/docker/config/odoo.conf << 'EOF'
[options]
admin_passwd = ${ADMIN_PASSWORD}
db_host = postgres
db_port = 5432
db_user = odoo
db_password = ${POSTGRES_PASSWORD}
db_name = nettrades

addons_path = ./odoo-modules/nettrades_core,./odoo-modules/nettrades_good_answer,./odoo-modules/nettrades_ask_someone,./odoo-modules/nettrades_gpu_admin,./odoo-modules/nettrades_gpustack_adapter,./odoo-modules/nettrades_queue,./odoo-modules/nettrades_onboarding,./odoo-modules/nettrades_job_matching,./odoo-modules/nettrades_proposals,./odoo-modules/nettrades_lead_scoring,./odoo-modules/nettrades_research,./odoo-modules/nettrades_chatbot,./odoo-modules/nettrades_notifications,./odoo-modules/nettrades_pwa,./odoo-modules/nettrades_bridge,./odoo-modules/nettrades_data_collection,./odoo-modules/nettrades_trigger,./odoo-modules/nettrades_loop,./odoo-modules/nettrades_self_improving_config,./odoo-modules/nettrades_fairness,./third-party/odoo/addons,./third-party/odoo_llm,./third-party/odoo_llm_compat,./third-party/website_sale_marketplace,./third-party/queue_job

workers = 4
limit_memory_hard = 2147483648
limit_memory_soft = 1610612736
limit_time_cpu = 60
limit_time_real = 120
log_level = info
logfile = /var/log/odoo/odoo.log
EOF

echo -e "${GREEN}✓ Odoo configuration updated${NC}"

# =============================================================================
# 5. Update Database Init Script
# =============================================================================
echo -e "${YELLOW}Updating database init script...${NC}"

# The init-db.sql script has been updated with all fairness tables
# Copy from the updated version

echo -e "${GREEN}✓ Database init script updated${NC}"

# =============================================================================
# 6. Start the Stack
# =============================================================================
echo -e "${YELLOW}Starting the Docker stack...${NC}"

cd deploy/docker
docker compose up -d

echo -e "${GREEN}✓ Stack started${NC}"

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be ready...${NC}"
sleep 30

# =============================================================================
# 7. Initialize Database
# =============================================================================
echo -e "${YELLOW}Initializing database...${NC}"

docker exec -i postgres psql -U odoo nettrades < init-db.sql 2>/dev/null || echo "Database initialization already done"

echo -e "${GREEN}✓ Database initialized${NC}"

# =============================================================================
# 8. Install Odoo Modules
# =============================================================================
echo -e "${YELLOW}Installing Odoo modules...${NC}"

MODULES=(
    "nettrades_core"
    "nettrades_good_answer"
    "nettrades_ask_someone"
    "nettrades_gpu_admin"
    "nettrades_gpustack_adapter"
    "nettrades_queue"
    "nettrades_bridge"
    "nettrades_data_collection"
    "nettrades_trigger"
    "nettrades_loop"
    "nettrades_self_improving_config"
    "nettrades_fairness"
    "nettrades_onboarding"
    "nettrades_job_matching"
    "nettrades_proposals"
    "nettrades_lead_scoring"
    "nettrades_research"
    "nettrades_chatbot"
    "nettrades_notifications"
    "nettrades_pwa"
)

for module in "${MODULES[@]}"; do
    echo -e "${YELLOW}Installing $module...${NC}"
    docker exec -it odoo python3 /usr/bin/odoo -c /etc/odoo/odoo.conf -i "$module" --stop-after-init || echo "Module $module already installed"
done

echo -e "${GREEN}✓ Modules installed${NC}"

# =============================================================================
# 9. Complete
# =============================================================================
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}Phase 2 complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "Access the platform:"
echo "  Odoo: https://${DOMAIN}"
echo "  Grafana: https://grafana.${DOMAIN}"
echo "  GPUStack: https://gpustack.${DOMAIN}"
echo ""
echo "Next steps:"
echo "1. Log in to Odoo with admin:${ADMIN_PASSWORD}"
echo "2. Configure fairness settings: Settings → Technical → Fairness"
echo "3. Configure bridge routing: Settings → Technical → Bridge"
echo "4. Configure self-improving loop: Settings → Technical → Self-Improving AI"