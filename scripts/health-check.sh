#!/bin/bash
# =============================================================================
# FILE: scripts/health-check.sh
# PURPOSE:
#   Quick health check for the NETTRADES platform.
#   Checks container status, service endpoints, PostgreSQL, and installed modules.
# =============================================================================

echo "🔍 NETTRADES Platform Health Check"
echo "=================================="

# -----------------------------------------------------------------------------
# 1. Container status
# -----------------------------------------------------------------------------
docker ps --format "table {{.Names}}\t{{.Status}}"

# -----------------------------------------------------------------------------
# 2. Service endpoints
# -----------------------------------------------------------------------------
curl -s -o /dev/null -w "Odoo: %{http_code}\n" http://localhost:8069
curl -s -o /dev/null -w "LangGraph: %{http_code}\n" http://localhost:8000/health

# -----------------------------------------------------------------------------
# 3. PostgreSQL
# -----------------------------------------------------------------------------
docker exec docker-postgres-1 pg_isready -U odoo && echo "PostgreSQL: OK" || echo "PostgreSQL: FAILED"

# -----------------------------------------------------------------------------
# 4. Installed NETTRADES modules (count)
# -----------------------------------------------------------------------------
MODULE_COUNT=$(docker exec docker-postgres-1 psql -U odoo -d odoo -t -c "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades%' AND state='installed';" | tr -d ' ')
if [ "$MODULE_COUNT" -eq 20 ]; then
    echo "Modules: Installed ($MODULE_COUNT/20)"
else
    echo "Modules: Not installed ($MODULE_COUNT/20)"
fi