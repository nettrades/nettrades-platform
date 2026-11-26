#!/bin/bash
# =============================================================================
# FILE: scripts/ensure-session-secret.sh
# =============================================================================
# PURPOSE:
#   Backfill a strong SESSION_SECRET into deploy/docker/.env on existing
#   deployments that were created before phase-env.sh auto-generated it.
#
#   Idempotent. If SESSION_SECRET is already strong, the script does nothing.
#   If it is empty or 'changeit', the script generates a new one and
#   restarts the nettrades-ui container so it picks up the new key.
#
# USAGE:
#   ./scripts/ensure-session-secret.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found."
    exit 1
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

CURRENT=$(grep -E '^SESSION_SECRET=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\"\r" || true)

if [[ -n "$CURRENT" && "$CURRENT" != "changeit" && ${#CURRENT} -ge 40 ]]; then
    echo "SESSION_SECRET already set (${#CURRENT} chars). Nothing to do."
    exit 0
fi

NEW=$(generate_session_secret)
safe_sed_replace "$ENV_FILE" "SESSION_SECRET" "$NEW"
echo "Generated a new SESSION_SECRET (${#NEW} chars)."
echo "Restarting nettrades-ui to pick it up..."
docker compose -f "$PROJECT_ROOT/deploy/docker/docker-compose.yaml" \
    up -d --force-recreate nettrades-ui
echo "Done. Existing admin sessions are invalidated; re-login at /admin/login."