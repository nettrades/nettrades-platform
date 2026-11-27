#!/bin/bash
# =============================================================================
# FILE: deploy/docker/postgres/01-create-databases.sh
# =============================================================================
# PURPOSE:
#   Creates the two databases that are NOT the primary Odoo database:
#     * nettrades_infra  — operational state (ADR-002)
#     * checkpoints      — LangGraph checkpoints (ADR-003)
#
#   Runs only on FIRST container start. On an existing deployment where
#   the postgres volume already has data, use scripts/migrate-phase1-databases.sh
#   instead.
#
#   The primary `odoo` database is created by POSTGRES_DB, so it already
#   exists by the time this script runs.
# =============================================================================

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE nettrades_infra;
    CREATE DATABASE checkpoints;
EOSQL

echo "[postgres-init] created nettrades_infra and checkpoints databases"