#!/bin/bash
echo "🔍 NETTRADES Platform Health Check"
echo "=================================="
docker ps --format "table {{.Names}}\t{{.Status}}"
curl -s -o /dev/null -w "Odoo: %{http_code}\n" http://localhost:8069
curl -s -o /dev/null -w "LangGraph: %{http_code}\n" http://localhost:8000/health
docker exec docker-postgres-1 pg_isready -U odoo && echo "PostgreSQL: OK" || echo "PostgreSQL: FAILED"
docker exec odoo odoo -c /etc/odoo/odoo.conf --db_host=postgres --db_user=odoo --db_password=odoo123 -d odoo --list-modules 2>/dev/null | grep -q "nettrades_core" && echo "Modules: Installed" || echo "Modules: Not installed"