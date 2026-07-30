#!/bin/bash
# =============================================================================
# FILE: scripts/phase-monitoring.sh
# =============================================================================
# PURPOSE:
#   Phase 5: Monitoring Setup – deploys Prometheus and Grafana.
#   This phase can be run on either Docker Compose or Kubernetes deployments.
#   It configures:
#   - Prometheus for metrics collection
#   - Grafana for visualisation
#   - Alertmanager for alerting
#   - Pre-configured dashboards for NETTRADES
#
# UPDATES (2026-07-29):
#   - Removed GPUStack scrape targets (replaced by Dynamo, no native metrics yet).
#   - Added a placeholder job for Dynamo (commented out) for future use.
#
# USAGE:
#   ./phase-monitoring.sh [--auto] [--force]
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Source shared libraries
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/common.sh"

# -----------------------------------------------------------------------------
# Parse arguments
# -----------------------------------------------------------------------------
AUTO="${AUTO:-false}"
FORCE="${FORCE:-false}"
export FORCE

# -----------------------------------------------------------------------------
# Production Safety Check
# -----------------------------------------------------------------------------
confirm_force_production "5"

# -----------------------------------------------------------------------------
# Phase marker
# -----------------------------------------------------------------------------
if phase_completed 5; then
    log_warning "Phase 5 already completed. Use --force to re-run."
    exit 0
fi

# -----------------------------------------------------------------------------
# Helper: Check if a Docker Compose service exists
# -----------------------------------------------------------------------------
compose_service_exists() {
    local service_name="$1"
    if docker compose ps -q "$service_name" 2>/dev/null | grep -q .; then
        return 0
    else
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Detect deployment type
# -----------------------------------------------------------------------------
DEPLOYMENT_TYPE="unknown"

if docker compose version &>/dev/null && [[ -f "$PROJECT_ROOT/deploy/docker/docker-compose.yaml" ]]; then
    if docker compose -f "$PROJECT_ROOT/deploy/docker/docker-compose.yaml" ps --services 2>/dev/null | grep -q prometheus; then
        DEPLOYMENT_TYPE="docker"
        log_info "Detected Docker Compose deployment"
    fi
fi

if command -v kubectl &>/dev/null && kubectl get namespace monitoring &>/dev/null; then
    DEPLOYMENT_TYPE="kubernetes"
    log_info "Detected Kubernetes deployment"
fi

if [[ "$DEPLOYMENT_TYPE" == "unknown" ]]; then
    log_error "No existing deployment detected. Please run Phase 2 (Docker) or Phase 4 (Kubernetes) first."
    exit 1
fi

# -----------------------------------------------------------------------------
# Deploy monitoring (Docker)
# -----------------------------------------------------------------------------
if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
    DEPLOY_DIR="$PROJECT_ROOT/deploy/docker"
    cd "$DEPLOY_DIR"

    log_step "Restarting Prometheus and Grafana (Docker)..."

    # Restart prometheus and grafana (always present)
    docker compose up -d prometheus grafana

    # Restart alertmanager only if it exists
    if compose_service_exists "alertmanager"; then
        log_step "Restarting alertmanager..."
        docker compose up -d alertmanager
    else
        log_info "alertmanager not defined in compose – skipping"
    fi

    log_step "Configuring Grafana datasource..."
    # Wait for Grafana to be ready (using port 3001 as exposed in docker-compose.yaml)
    sleep 10
    curl -X POST http://localhost:3001/api/datasources \
        -H "Content-Type: application/json" \
        -d '{"name":"Prometheus","type":"prometheus","url":"http://prometheus:9090","access":"proxy"}' \
        2>/dev/null || log_warning "Failed to configure Grafana datasource"

    cd "$PROJECT_ROOT"
fi

# -----------------------------------------------------------------------------
# Deploy monitoring (Kubernetes)
# -----------------------------------------------------------------------------
if [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
    log_step "Ensuring Prometheus & Grafana are running (Kubernetes)..."
    if ! kubectl get namespace monitoring &>/dev/null; then
        helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
        helm repo update
        helm install prometheus prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
    else
        log_success "Prometheus & Grafana already deployed"
    fi
fi

# -----------------------------------------------------------------------------
# Import NETTRADES dashboards
# -----------------------------------------------------------------------------
log_step "Importing NETTRADES dashboards..."
DASHBOARD_DIR="$PROJECT_ROOT/docs/operations/dashboards"

if [[ -d "$DASHBOARD_DIR" ]]; then
    for dashboard in "$DASHBOARD_DIR"/*.json; do
        if [[ -f "$dashboard" ]]; then
            log_info "Importing dashboard: $(basename "$dashboard")"

            # Import via Grafana API (using port 3001 for Docker)
            if [[ "$DEPLOYMENT_TYPE" == "docker" ]]; then
                curl -X POST http://localhost:3001/api/dashboards/db \
                    -H "Content-Type: application/json" \
                    -d @"$dashboard" 2>/dev/null || log_warning "Failed to import dashboard"
            elif [[ "$DEPLOYMENT_TYPE" == "kubernetes" ]]; then
                kubectl port-forward svc/grafana -n monitoring 3000:3000 &
                sleep 5
                curl -X POST http://localhost:3000/api/dashboards/db \
                    -H "Content-Type: application/json" \
                    -d @"$dashboard" 2>/dev/null || log_warning "Failed to import dashboard"
                kill %1 2>/dev/null || true
            fi
        fi
    done
    log_success "Dashboards imported"
else
    log_warning "Dashboard directory not found at $DASHBOARD_DIR – skipping import"
fi

# -----------------------------------------------------------------------------
# Mark phase complete
# -----------------------------------------------------------------------------
mark_phase_complete 5
log_success "Phase 5 completed – monitoring stack deployed"

echo ""
echo "Access monitoring:"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana: http://localhost:3001 (admin/admin)"
echo "  Alertmanager: http://localhost:9093"