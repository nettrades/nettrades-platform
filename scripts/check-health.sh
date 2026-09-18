#!/bin/bash
# Quick health check
set -u
echo "Containers:"
docker compose -f deploy/docker/docker-compose.yaml ps --format "table {{.Name}}\t{{.Status}}"
echo ""
echo "Odoo:"; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/health
echo "LangGraph:"; curl -s http://localhost:8000/health
echo ""
echo "Modules:"
docker compose -f deploy/docker/docker-compose.yaml exec -T postgres \
    psql -U odoo -d odoo -c \
    "SELECT name, state FROM ir_module_module WHERE name LIKE 'nettrades_%' ORDER BY name;"