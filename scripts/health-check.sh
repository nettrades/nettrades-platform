#!/bin/bash
# =============================================================================
# FILE: scripts/health-check.sh
# PURPOSE:
#   Quick health check for the NETTRADES platform.
#   Checks container status, service endpoints, PostgreSQL, and installed modules.
# =============================================================================

echo "NETTRADES Platform Health Check"
echo "=================================="

# -----------------------------------------------------------------------------
# 1. Container status
# -----------------------------------------------------------------------------
docker ps --format "table {{.Names}}\t{{.Status}}"

# -----------------------------------------------------------------------------
# 2. Service endpoints
# -----------------------------------------------------------------------------
echo ""
echo "Service Health:"
curl -s -o /dev/null -w "Odoo: %{http_code}\n" http://localhost:8069
curl -s -o /dev/null -w "LangGraph: %{http_code}\n" http://localhost:8000/health

# -----------------------------------------------------------------------------
# 3. PostgreSQL
# -----------------------------------------------------------------------------
echo ""
if docker exec docker-postgres-1 pg_isready -U odoo &>/dev/null; then
    echo "PostgreSQL: OK"
else
    echo "PostgreSQL: FAILED"
fi

# -----------------------------------------------------------------------------
# 4. Installed NETTRADES modules (dynamic count)
# -----------------------------------------------------------------------------
echo ""
MODULE_COUNT=$(docker exec docker-postgres-1 psql -U odoo -d odoo -t -c "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades%' AND state='installed';" | tr -d ' ')
TOTAL_MODULES=$(docker exec docker-postgres-1 psql -U odoo -d odoo -t -c "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades%';" | tr -d ' ')

if [[ -n "$MODULE_COUNT" && -n "$TOTAL_MODULES" ]]; then
    echo "Modules: Installed ($MODULE_COUNT/$TOTAL_MODULES)"
else
    echo "Modules: Unable to determine (PostgreSQL may not be ready)"
fi