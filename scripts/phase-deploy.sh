#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 2: Single-VM Production Deployment
# =============================================================================
# Deploys the full production stack on a single Ubuntu 24.04 VM.
# No GPU is required — the platform uses llama.cpp for CPU inference.
#
# Checks:
#   • Phase 1 (dev-env) has been run — if not, runs it automatically.
#   • Docker and Docker Compose are installed.
#   • Ports 80 and 443 are not already in use.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$PLATFORM_DIR/deploy/docker"

# Ensure Phase 1 is done
if [ ! -d "$PLATFORM_DIR/third-party/odoo/.git" ]; then
    echo "Phase 1 (development environment) has not been run yet."
    echo "Running it now automatically..."
    bash "$SCRIPT_DIR/phase-dev-env.sh"
fi

# Pre-flight: Docker must be installed
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed." >&2
    echo "Install Docker: https://docs.docker.com/engine/install/" >&2
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo "ERROR: Docker Compose plugin is not installed." >&2
    exit 1
fi

# Pre-flight: check for port conflicts
for port in 80 443; do
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        echo "WARNING: Port $port is already in use." >&2
        echo "Traefik needs ports 80 and 443 for HTTP/HTTPS." >&2
        echo "Stop the service using port $port or change the Traefik ports in docker-compose.yml." >&2
    fi
done

cd "$DEPLOY_DIR"

echo "=== Step 1: Security hardening ==="
if [ -f "$DEPLOY_DIR/security-harden.sh" ]; then
    sudo bash "$DEPLOY_DIR/security-harden.sh"
fi

echo ""
echo "=== Step 2: Generate secrets and deploy ==="
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    if [ -f "$DEPLOY_DIR/.env.generator.sh" ]; then
        bash "$DEPLOY_DIR/.env.generator.sh" > "$DEPLOY_DIR/.env"
        chmod 600 "$DEPLOY_DIR/.env"
    else
        echo "ERROR: .env.generator.sh not found." >&2
        exit 1
    fi
fi

sudo bash "$DEPLOY_DIR/install-nettrades.sh" --auto

echo ""
echo "============================================================="
echo " Deployment complete!"
echo "============================================================="
echo ""
echo "Odoo:       https://nettrades.ai"
echo "Grafana:    https://grafana.nettrades.ai"
echo "GPUStack:   https://gpustack.nettrades.ai"
echo "Forgejo:    https://git.nettrades.ai"