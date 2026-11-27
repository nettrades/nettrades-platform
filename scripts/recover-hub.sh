#!/bin/bash
# =============================================================================
# FILE: scripts/recover-hub.sh
# =============================================================================
# PURPOSE:
#   One-command recovery for a partially-deployed or wiped hub.
#
#   Unlike phase-deploy.sh, this script does NOT trust .phase-* marker
#   files. It inspects the actual state of the database, the containers,
#   and the installed modules on every run, and only performs the steps
#   that are missing. That makes it safe to run:
#     - after `docker volume rm` (fresh DB, empty schema)
#     - after a partial deploy (schema present, modules missing)
#     - after a full deploy (nothing to do, exits in ~3 s)
#
#   It is the equivalent of `phase-deploy.sh --force --auto` without the
#   expensive steps (model downloads, Docker rebuilds, Launcher builds).
#   Use it when you already have images built and just need a working
#   stack.
#
# USAGE:
#   ./scripts/recover-hub.sh                    # recover in place
#   ./scripts/recover-hub.sh --no-modules       # skip module install
#   ./scripts/recover-hub.sh --show-config      # just print token + secret
#
# WHAT IT DOES (each step skipped if already done):
#   1. Ensure postgres is healthy
#   2. Ensure the `odoo` database exists
#   3. Ensure the Odoo base schema exists (ir_module_module)
#   4. Apply extensions (pgcrypto, vector)
#   5. Apply the nettrades_infra + checkpoints schema (Phase 1a)
#   6. Install NETTRADES Odoo modules
#   7. Configure the Odoo admin user (configure-odoo-admin.sh)
#   8. Configure the hub for spokes (configure-hub-for-spokes.sh)
#   9. Write /tmp/hub-config.json with the values needed by install-spoke.sh
#  10. Print the token and heartbeat secret
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
ENV_FILE="$DEPLOY_DIR/.env"
HUB_CONFIG="${HUB_CONFIG:-/tmp/hub-config.json}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${BLUE}[recover]${NC} $*"; }
ok()   { echo -e "${GREEN}[recover]${NC} $*"; }
warn() { echo -e "${YELLOW}[recover]${NC} $*"; }
err()  { echo -e "${RED}[recover]${NC} $*" >&2; exit 1; }

SKIP_MODULES=false
SHOW_CONFIG_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --no-modules)     SKIP_MODULES=true ;;
        --show-config)    SHOW_CONFIG_ONLY=true ;;
        -h|--help)
            sed -n '3,45p' "$0"
            exit 0
            ;;
        *) err "Unknown argument: $arg" ;;
    esac
done

[[ -f "$ENV_FILE" ]] || err "$ENV_FILE not found — run phase-env.sh first"

# Load secrets (postgres password, heartbeat secret, proxy api key)
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$DEPLOY_DIR"

# -----------------------------------------------------------------------------
# --show-config: read-only mode
# -----------------------------------------------------------------------------
if [[ "$SHOW_CONFIG_ONLY" == "true" ]]; then
    if [[ -f "$HUB_CONFIG" ]]; then
        cat "$HUB_CONFIG"
        exit 0
    fi
    err "No $HUB_CONFIG — run ./scripts/recover-hub.sh first"
fi

# -----------------------------------------------------------------------------
# 1. Ensure the core stack is up (postgres, valkey, odoo)
# -----------------------------------------------------------------------------
# The previous version only started postgres. That is not enough: the
# module install in Step 6 calls `docker compose exec odoo ...`, which
# fails when odoo is not running. On a wiped or interrupted deployment,
# the caller should be able to run recover-hub.sh once and get a working
# stack, not two runs with a `docker compose up -d` in between.
# (Diagnosed 2026-11-16.)
log "Checking core stack (postgres, valkey, odoo)..."

# Bring up postgres first — odoo depends on its health.
if ! docker compose ps postgres --format json 2>/dev/null | grep -q '"Health":"healthy"'; then
    log "Starting postgres..."
    docker compose up -d postgres
    for i in $(seq 1 30); do
        docker compose ps postgres --format json 2>/dev/null \
            | grep -q '"Health":"healthy"' && break
        sleep 2
    done
    docker compose ps postgres --format json 2>/dev/null \
        | grep -q '"Health":"healthy"' \
        || err "postgres did not become healthy within 60s — check: docker compose logs postgres --tail 40"
fi
ok "postgres healthy"

# Bring up valkey and odoo now that postgres is healthy.
# `docker compose up -d valkey odoo` is idempotent: containers already
# running are left alone; stopped ones are started.
log "Ensuring valkey and odoo are up..."
docker compose up -d valkey odoo

# Wait for odoo HTTP (not just container running — the app inside may
# still be starting).
log "Waiting for odoo HTTP /web/health (up to 90s)..."
for i in $(seq 1 45); do
    if curl -s --connect-timeout 2 --max-time 4 -f -o /dev/null \
        http://localhost:8069/web/health 2>/dev/null; then
        ok "odoo HTTP ready"
        break
    fi
    sleep 2
    if [[ $i -eq 45 ]]; then
        warn "odoo did not respond within 90s — continuing anyway"
        warn "check: docker compose logs odoo --tail 30"
    fi
done

# -----------------------------------------------------------------------------
# 2. Ensure the odoo database exists
# -----------------------------------------------------------------------------
ODOO_DB_EXISTS=$(docker compose exec -T postgres psql -U odoo -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname='odoo'" 2>/dev/null | tr -d '[:space:]')
if [[ "$ODOO_DB_EXISTS" != "1" ]]; then
    log "Creating odoo database..."
    docker compose exec -T postgres psql -U odoo -d postgres -c "CREATE DATABASE odoo;" >/dev/null
fi
ok "odoo database present"

# -----------------------------------------------------------------------------
# 3. Ensure the Odoo base schema exists
# -----------------------------------------------------------------------------
SCHEMA_OK=$(docker compose exec -T postgres psql -U odoo -d odoo -tAc \
    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ir_module_module'" \
    2>/dev/null | tr -d '[:space:]')

if [[ "$SCHEMA_OK" != "1" ]]; then
    log "Odoo schema missing — installing base modules (this takes ~90 s)..."
    docker compose run --rm \
        -e PGHOST=postgres -e PGUSER=odoo -e PGPASSWORD="$POSTGRES_PASSWORD" \
        -e PGDATABASE=odoo \
        odoo odoo -d odoo \
        --db_host=postgres --db_port=5432 \
        --db_user=odoo --db_password="$POSTGRES_PASSWORD" \
        -i base --stop-after-init --log-level=warn
    ok "Base modules installed"
else
    ok "Odoo base schema already present"
fi

# -----------------------------------------------------------------------------
# 4. Ensure extensions (idempotent)
# -----------------------------------------------------------------------------
log "Ensuring extensions (pgcrypto, vector)..."
docker compose exec -T postgres psql -U odoo -d odoo \
    -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" >/dev/null 2>&1 || true
docker compose exec -T postgres psql -U odoo -d odoo \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" >/dev/null 2>&1 || true
ok "Extensions present"

# -----------------------------------------------------------------------------
# 5. Apply Phase 1a schema (idempotent)
# -----------------------------------------------------------------------------
if [[ -x "$SCRIPT_DIR/migrate-phase1-databases.sh" ]]; then
    log "Applying Phase 1a databases..."
    bash "$SCRIPT_DIR/migrate-phase1-databases.sh"
    ok "Phase 1a applied"
else
    warn "migrate-phase1-databases.sh not found — skipping Phase 1a"
fi

# -----------------------------------------------------------------------------
# 6. Install NETTRADES modules (unless --no-modules)
# -----------------------------------------------------------------------------
if [[ "$SKIP_MODULES" != "true" ]]; then
    INSTALLED=$(docker compose exec -T postgres psql -U odoo -d odoo -tAc \
        "SELECT COUNT(*) FROM ir_module_module WHERE name LIKE 'nettrades_%' AND state='installed';" \
        2>/dev/null | tr -d '[:space:]')
    INSTALLED=${INSTALLED:-0}

    if [[ "$INSTALLED" -lt 5 ]]; then
        log "Installing NETTRADES modules (currently $INSTALLED installed)..."
        cd "$PROJECT_ROOT"
        bash "$SCRIPT_DIR/install-modules.sh" --auto
        cd "$DEPLOY_DIR"
        ok "NETTRADES modules installed"
    else
        ok "NETTRADES modules already installed ($INSTALLED modules)"
    fi
else
    log "--no-modules passed, skipping module install"
fi

# -----------------------------------------------------------------------------
# 7. Configure Odoo admin (idempotent)
# -----------------------------------------------------------------------------
if [[ -x "$SCRIPT_DIR/configure-odoo-admin.sh" ]] || [[ -f "$SCRIPT_DIR/configure-odoo-admin.sh" ]]; then
    log "Configuring Odoo admin user..."
    CONFIGURE_LOG=$(mktemp)
    docker compose exec -T \
        -e ODOO_ADMIN_PASSWORD="${ODOO_ADMIN_PASSWORD:-}" \
        -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
        -e NETTRADES_SERVICE_PASSWORD="${NETTRADES_SERVICE_PASSWORD:-}" \
        -e DYNAMO_API_KEY="${DYNAMO_API_KEY:-dummy}" \
        -e LLM_BASE_URL="${LLM_BASE_URL:-http://llama-cpp:8080/v1}" \
        odoo bash -c "$(cat "$SCRIPT_DIR/configure-odoo-admin.sh")" 2>&1 \
        | tee "$CONFIGURE_LOG" || warn "configure-odoo-admin had warnings"
    rm -f "$CONFIGURE_LOG"
    ok "Admin configured"
else
    warn "configure-odoo-admin.sh not found — skipping"
fi

# -----------------------------------------------------------------------------
# 8. Configure hub for spokes (generates token if not present)
# -----------------------------------------------------------------------------
log "Configuring hub for spokes..."
HUB_LOG=$(mktemp)
if bash "$SCRIPT_DIR/configure-hub-for-spokes.sh" 2>&1 | tee "$HUB_LOG"; then
    ok "Hub configured"
else
    warn "configure-hub-for-spokes.sh exited non-zero — see $HUB_LOG"
fi

# Extract the values we need
TOKEN=$(grep -E '^[[:space:]]+[A-Za-z0-9_-]{20,128}[[:space:]]*$' "$HUB_LOG" \
    | head -1 | tr -d '[:space:]')
CLUSTER_ID=$(grep -oE 'Cluster ID:[[:space:]]+[0-9]+' "$HUB_LOG" \
    | grep -oE '[0-9]+' | head -1)
HUB_IP=$(grep -oE 'Hub IP:[[:space:]]+[0-9.]+' "$HUB_LOG" \
    | grep -oE '[0-9.]+' | head -1)

# Fallback: try to read the heartbeat secret from .env
HEARTBEAT_SECRET=$(grep '^LANGGRAPH_HEARTBEAT_SECRET=' "$ENV_FILE" \
    | cut -d= -f2- | tr -d "\"'" | tr -d '[:space:]')

# Fallback: derive hub IP from .env or hostname
if [[ -z "$HUB_IP" ]]; then
    HUB_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

# -----------------------------------------------------------------------------
# 9. Write machine-readable config for install-spoke.sh
# -----------------------------------------------------------------------------
if [[ -n "$TOKEN" && -n "$CLUSTER_ID" ]]; then
# USE_WIREGUARD default: true on bare-metal Linux (the normal spoke OS).
# Override with USE_WIREGUARD=false in .env for a WSL/LAN-only setup.
HUB_USE_WG=$(grep '^SPOKE_USE_WIREGUARD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d "\"'" | tr -d '[:space:]')
HUB_USE_WG="${HUB_USE_WG:-true}"

cat > "$HUB_CONFIG" <<EOF
{
  "hub_url": "http://${HUB_IP}:8069",
  "hub_ip": "${HUB_IP}",
  "cluster_id": ${CLUSTER_ID},
  "registration_token": "${TOKEN}",
  "heartbeat_secret": "${HEARTBEAT_SECRET}",
  "use_wireguard": ${HUB_USE_WG},
  "generated_at": "$(date -Iseconds)"
}
EOF
    chmod 600 "$HUB_CONFIG"
    ok "Hub config written to $HUB_CONFIG"
else
    warn "Could not extract token/cluster from configure-hub-for-spokes.sh output"
    warn "You may need to inspect $HUB_LOG and generate manually"
fi

# -----------------------------------------------------------------------------
# 10. Print summary
# -----------------------------------------------------------------------------
echo
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  Hub ready"
echo "═══════════════════════════════════════════════════════════════════════════"
echo
echo "  Hub IP:              ${HUB_IP:-<unknown>}"
echo "  Cluster ID:          ${CLUSTER_ID:-<unknown>}"
echo "  Registration token:  ${TOKEN:-<not extracted — see $HUB_LOG>}"
echo "  Heartbeat secret:    ${HEARTBEAT_SECRET:0:12}...${HEARTBEAT_SECRET: -4}"
echo
echo "  Full config:         $HUB_CONFIG"
echo
if [[ -n "${SPOKE_HOST:-}" ]]; then
    echo "  Next: install spoke on $SPOKE_HOST"
    echo "    scp $HUB_CONFIG root@${SPOKE_HOST}:/tmp/hub-config.json"
    echo "    ssh root@${SPOKE_HOST} 'cd ~/nettrades-platform && sudo ./scripts/install-spoke.sh --config-file=/tmp/hub-config.json'"
else
    echo "  Next: install a spoke"
    echo "    scp $HUB_CONFIG root@<spoke-host>:/tmp/hub-config.json"
    echo "    ssh root@<spoke-host> 'cd ~/nettrades-platform && sudo ./scripts/install-spoke.sh --config-file=/tmp/hub-config.json'"
fi
echo
echo "  Re-run this script at any time to re-verify. It is idempotent."
echo "═══════════════════════════════════════════════════════════════════════════"