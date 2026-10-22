#!/bin/bash
# =============================================================================
# FILE: scripts/check-health.sh
# =============================================================================
set -u

COMPOSE="docker compose -f deploy/docker/docker-compose.yaml"

echo "Containers:"
$COMPOSE ps --format "table {{.Name}}\t{{.Status}}"

echo ""
echo "Service health:"
printf "Odoo:      "; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8069/web/health
printf "LangGraph: "; curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health

echo ""
echo "Modules:"
$COMPOSE exec -T postgres psql -U odoo -d odoo -c \
    "SELECT name, state FROM ir_module_module WHERE name LIKE 'nettrades_%' ORDER BY name;"

INSTALLED=$($COMPOSE exec -T postgres psql -U odoo -d odoo -t -c \
    "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades_%' AND state='installed';" | tr -d ' ')
TOTAL=$($COMPOSE exec -T postgres psql -U odoo -d odoo -t -c \
    "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades_%';" | tr -d ' ')
echo "Summary: $INSTALLED / $TOTAL installed"