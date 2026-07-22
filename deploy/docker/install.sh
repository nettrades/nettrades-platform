#!/bin/bash
set -e

# ============================================================
# Sovereign AI in a Box - Installer v3 (Corrected Paths)
# ============================================================

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "=========================================="
echo " Sovereign AI in a Box - Installer v3"
echo "=========================================="

# 1. Navigate to the Docker deployment directory
cd deploy/docker

# 2. Detect Server IP
SERVER_IP=$(hostname -I | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    echo -e "${RED}ERROR: Could not detect server IP.${NC}"
    exit 1
fi
echo -e "${GREEN}[+] Detected IP: $SERVER_IP${NC}"

# 3. Prepare .env in the correct location (deploy/docker/.env)
if [ ! -f .env ]; then
    echo "[+] Creating .env from .env.example..."
    cp .env.example .env
    
    # Set the detected IP as the DOMAIN
    sed -i "s/DOMAIN='.*'/DOMAIN='$SERVER_IP'/" .env
    
    # Generate secure random passwords
    ADMIN_PW=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    POSTGRES_PW=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    GRAFANA_PW=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    PROMETHEUS_PW=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    GPUSTACK_PW=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    PROXY_KEY=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    JWT_SECRET=$(openssl rand -base64 32 | tr -d '\n' | tr -d '+/=')
    
    # Inject passwords into .env (using single quotes to preserve special chars)
    sed -i "s|ADMIN_PASSWORD='.*'|ADMIN_PASSWORD='$ADMIN_PW'|" .env
    sed -i "s|POSTGRES_PASSWORD='.*'|POSTGRES_PASSWORD='$POSTGRES_PW'|" .env
    sed -i "s|GRAFANA_PASSWORD='.*'|GRAFANA_PASSWORD='$GRAFANA_PW'|" .env
    sed -i "s|PROMETHEUS_PASSWORD='.*'|PROMETHEUS_PASSWORD='$PROMETHEUS_PW'|" .env
    sed -i "s|GPUSTACK_ADMIN_PASSWORD='.*'|GPUSTACK_ADMIN_PASSWORD='$GPUSTACK_PW'|" .env
    sed -i "s|PROXY_API_KEY='.*'|PROXY_API_KEY='$PROXY_KEY'|" .env
    sed -i "s|ODOO_API_KEY='.*'|ODOO_API_KEY='$PROXY_KEY'|" .env
    sed -i "s|JWT_SECRET='.*'|JWT_SECRET='$JWT_SECRET'|" .env

    echo -e "${GREEN}[+] .env created in deploy/docker/.env${NC}"
    echo "    Admin Password: $ADMIN_PW (save this)"
else
    echo "[+] .env already exists. Using existing."
    # Extract the admin password from the existing .env for the Odoo update
    ADMIN_PW=$(grep ADMIN_PASSWORD .env | cut -d '=' -f2 | tr -d "'")
fi

# 4. Start Docker Compose (from the deploy/docker directory)
echo "[+] Starting Docker stack..."
docker compose up -d

# 5. Wait for Odoo to be ready
echo "[+] Waiting for Odoo to be ready (up to 60s)..."
sleep 30

# 6. Enable pgcrypto & Force-set Odoo admin password (Kills admin/admin)
echo "[+] Securing Odoo admin password..."
docker exec odoo psql -U odoo -d odoo -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null || true
docker exec odoo psql -U odoo -d odoo -c "UPDATE res_users SET password = crypt('$ADMIN_PW', gen_salt('bf')) WHERE login='admin';"

# 7. Check if everything is running
echo "[+] Checking service status..."
docker compose ps

# 8. Print success
echo "=========================================="
echo -e "${GREEN} DEPLOYMENT COMPLETE!${NC}"
echo "=========================================="
echo " Access the platform at: http://$SERVER_IP"
echo " Odoo (Admin):         http://$SERVER_IP/odoo"
echo " GPUStack:             http://$SERVER_IP:8080"
echo " Grafana:              http://$SERVER_IP:3001"
echo " Prometheus:           http://$SERVER_IP:9090"
echo ""
echo " Admin Password:       $ADMIN_PW"
echo "=========================================="
echo -e "${RED} IMPORTANT: Save this password. It will NOT be shown again.${NC}"