#!/usr/bin/env bash
# =============================================================================
# NETTRADES.AI – Phase Scale Script
# =============================================================================
# FILE: scripts/phase-scale.sh
#
# PURPOSE:
#   This script scales up or down the NETTRADES platform services.
#   It supports both:
#   1. Docker Compose scaling (local development)
#   2. Kubernetes scaling (production/staging)
#
# UPDATES (2026-07-29):
#   - Replaced GPUStack references with NVIDIA Dynamo.
#   - Updated K8S deployment file references to dynamo.
#   - Adjusted scaling commands.
#
# USAGE:
#   ./scripts/phase-scale.sh [command] [options]
#
# COMMANDS:
#   up      - Scale up services
#   down    - Scale down services
#   status  - Show current scale status
#   deploy  - Deploy Odoo modules
#   help    - Show this help message
#
# OPTIONS:
#   --kubernetes  - Use Kubernetes mode (default: Docker Compose)
#   --namespace   - Kubernetes namespace (default: frontend)
#   --context     - Kubernetes context (optional)
#
# =============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# -----------------------------------------------------------------------------
# 1. Configuration
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_DIR="$(dirname "$SCRIPT_DIR")"

# Default values
USE_KUBERNETES=false
K8S_NAMESPACE="frontend"
K8S_CONTEXT=""
DOCKER_COMPOSE_FILE="$PLATFORM_DIR/deploy/docker/docker-compose.yaml"
DOCKER_COMPOSE_OVERRIDE="$PLATFORM_DIR/deploy/docker/docker-compose.override.yml"
K8S_ODOO_DEPLOYMENT="deploy/kubernetes/apps/frontend/odoo-deployment.yaml"
K8S_LANGGRAPH_DEPLOYMENT="deploy/kubernetes/apps/frontend/langgraph-deployment.yaml"
K8S_DYNAMO_DEPLOYMENT="deploy/kubernetes/apps/frontend/dynamo-deployment.yaml"          # Replaced gpustack
K8S_SELF_IMPROVING_DEPLOYMENT="deploy/kubernetes/apps/frontend/self-improving-deployment.yaml"

# Scale values
ODOO_WORKERS=${ODOO_WORKERS:-2}
LANGGRAPH_WORKERS=${LANGGRAPH_WORKERS:-2}
GPU_WORKERS=${GPU_WORKERS:-1}
SELF_IMPROVING_WORKERS=${SELF_IMPROVING_WORKERS:-1}

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# -----------------------------------------------------------------------------
# 2. Helper Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
}

check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Kubernetes cluster is not accessible"
        exit 1
    fi
    if [ -n "$K8S_CONTEXT" ]; then
        kubectl config use-context "$K8S_CONTEXT"
    fi
}

check_files() {
    if [ "$USE_KUBERNETES" = true ]; then
        if [ ! -f "$PLATFORM_DIR/$K8S_ODOO_DEPLOYMENT" ]; then
            log_warning "Kubernetes Odoo deployment file not found: $K8S_ODOO_DEPLOYMENT"
            log_warning "Creating default deployment..."
            mkdir -p "$(dirname "$PLATFORM_DIR/$K8S_ODOO_DEPLOYMENT")"
        fi
    else
        if [ ! -f "$DOCKER_COMPOSE_FILE" ]; then
            log_error "Docker Compose file not found: $DOCKER_COMPOSE_FILE"
            exit 1
        fi
    fi
}

# -----------------------------------------------------------------------------
# 3. Kubernetes Scaling Functions
# -----------------------------------------------------------------------------

scale_kubernetes_up() {
    log_info "Scaling up services in Kubernetes (namespace: $K8S_NAMESPACE)..."
    
    check_kubectl
    check_files
    
    # Scale Odoo
    log_info "Scaling Odoo to $ODOO_WORKERS replicas..."
    if ! kubectl scale deployment/odoo --replicas="$ODOO_WORKERS" -n "$K8S_NAMESPACE"; then
        log_error "Failed to scale Odoo"
        exit 1
    fi
    log_success "Odoo scaled to $ODOO_WORKERS replicas"
    
    # Scale LangGraph
    log_info "Scaling LangGraph to $LANGGRAPH_WORKERS replicas..."
    if ! kubectl scale deployment/langgraph --replicas="$LANGGRAPH_WORKERS" -n "$K8S_NAMESPACE"; then
        log_error "Failed to scale LangGraph"
        exit 1
    fi
    log_success "LangGraph scaled to $LANGGRAPH_WORKERS replicas"
    
    # Scale GPU workers (NVIDIA Dynamo)
    if [ "$GPU_WORKERS" -gt 0 ]; then
        log_info "Scaling NVIDIA Dynamo to $GPU_WORKERS replicas..."
        if ! kubectl scale deployment/dynamo --replicas="$GPU_WORKERS" -n "$K8S_NAMESPACE"; then
            log_error "Failed to scale Dynamo"
            exit 1
        fi
        log_success "Dynamo scaled to $GPU_WORKERS replicas"
    fi
    
    # Scale self-improving services
    if [ "$SELF_IMPROVING_WORKERS" -gt 0 ]; then
        log_info "Scaling self-improving services to $SELF_IMPROVING_WORKERS replicas..."
        if ! kubectl scale deployment/self-improving --replicas="$SELF_IMPROVING_WORKERS" -n "$K8S_NAMESPACE"; then
            log_warning "Failed to scale self-improving services (deployment may not exist)"
        else
            log_success "Self-improving services scaled to $SELF_IMPROVING_WORKERS replicas"
        fi
    fi
    
    log_success "Kubernetes scaling completed successfully!"
    show_kubernetes_status
}

scale_kubernetes_down() {
    log_info "Scaling down services in Kubernetes (namespace: $K8S_NAMESPACE)..."
    
    check_kubectl
    
    # Scale Odoo to 1
    log_info "Scaling Odoo to 1 replica..."
    kubectl scale deployment/odoo --replicas=1 -n "$K8S_NAMESPACE" || log_warning "Failed to scale Odoo"
    
    # Scale LangGraph to 1
    log_info "Scaling LangGraph to 1 replica..."
    kubectl scale deployment/langgraph --replicas=1 -n "$K8S_NAMESPACE" || log_warning "Failed to scale LangGraph"
    
    # Scale GPU to 0
    log_info "Scaling Dynamo to 0 replicas..."
    kubectl scale deployment/dynamo --replicas=0 -n "$K8S_NAMESPACE" || log_warning "Failed to scale Dynamo"
    
    log_success "Kubernetes scaling down completed!"
}

show_kubernetes_status() {
    log_info "Kubernetes service status:"
    kubectl get pods -n "$K8S_NAMESPACE" | grep -E "odoo|langgraph|dynamo|self-improving" || echo "No pods found"
}

# -----------------------------------------------------------------------------
# 4. Docker Compose Scaling Functions
# -----------------------------------------------------------------------------

scale_docker_up() {
    log_info "Scaling up services with Docker Compose..."
    
    check_docker
    check_files
    
    # Scale Odoo
    log_info "Scaling Odoo workers to $ODOO_WORKERS..."
    if ! docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale odoo="$ODOO_WORKERS" --no-recreate; then
        log_error "Failed to scale Odoo workers"
        exit 1
    fi
    log_success "Odoo workers scaled to $ODOO_WORKERS"
    
    # Scale LangGraph
    log_info "Scaling LangGraph workers to $LANGGRAPH_WORKERS..."
    if ! docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale langgraph="$LANGGRAPH_WORKERS" --no-recreate; then
        log_error "Failed to scale LangGraph workers"
        exit 1
    fi
    log_success "LangGraph workers scaled to $LANGGRAPH_WORKERS"
    
    # Scale GPU workers (NVIDIA Dynamo)
    if [ "$GPU_WORKERS" -gt 0 ]; then
        log_info "Scaling Dynamo workers to $GPU_WORKERS..."
        if ! docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale dynamo="$GPU_WORKERS" --no-recreate; then
            log_error "Failed to scale Dynamo workers"
            exit 1
        fi
        log_success "Dynamo workers scaled to $GPU_WORKERS"
    fi
    
    # Scale self-improving services
    if [ "$SELF_IMPROVING_WORKERS" -gt 0 ]; then
        log_info "Scaling self-improving workers to $SELF_IMPROVING_WORKERS..."
        if ! docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale self-improving="$SELF_IMPROVING_WORKERS" --no-recreate; then
            log_warning "Failed to scale self-improving workers (service may not exist)"
        else
            log_success "Self-improving workers scaled to $SELF_IMPROVING_WORKERS"
        fi
    fi
    
    log_success "All services scaled up successfully!"
    show_docker_status
}

scale_docker_down() {
    log_info "Scaling down services with Docker Compose..."
    
    check_docker
    check_files
    
    # Scale Odoo to 1
    log_info "Scaling Odoo workers to 1..."
    docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale odoo=1 --no-recreate || log_warning "Failed to scale Odoo"
    
    # Scale LangGraph to 1
    log_info "Scaling LangGraph workers to 1..."
    docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale langgraph=1 --no-recreate || log_warning "Failed to scale LangGraph"
    
    # Scale GPU to 0
    log_info "Scaling Dynamo workers to 0..."
    docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d --scale dynamo=0 --no-recreate || log_warning "Failed to scale GPU"
    
    log_success "Scaling down completed!"
}

show_docker_status() {
    log_info "Docker Compose service status:"
    docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" ps
}

# -----------------------------------------------------------------------------
# 5. Deploy Odoo Modules
# -----------------------------------------------------------------------------

deploy_odoo_modules() {
    log_info "Deploying Odoo modules..."
    
    if [ "$USE_KUBERNETES" = true ]; then
        deploy_odoo_modules_kubernetes
    else
        deploy_odoo_modules_docker
    fi
}

deploy_odoo_modules_docker() {
    check_docker
    
    ODOO_CONTAINER=$(docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" ps -q odoo 2>/dev/null)
    
    if [ -z "$ODOO_CONTAINER" ]; then
        log_warning "Odoo container not running. Starting it..."
        docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" up -d odoo
        sleep 10
        ODOO_CONTAINER=$(docker compose -f "$DOCKER_COMPOSE_FILE" -f "$DOCKER_COMPOSE_OVERRIDE" ps -q odoo)
    fi
    
    if [ -z "$ODOO_CONTAINER" ]; then
        log_error "Failed to start Odoo container"
        exit 1
    fi
    
    MODULES="nettrades_core,nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config"
    
    log_info "Installing modules: $MODULES"
    if ! docker exec "$ODOO_CONTAINER" python /usr/lib/python3/dist-packages/odoo/odoo-bin \
        -c /etc/odoo/odoo.conf \
        -i "$MODULES" \
        --stop-after-init 2>&1; then
        log_error "Failed to install modules"
        exit 1
    fi
    
    log_success "Modules installed successfully!"
}

deploy_odoo_modules_kubernetes() {
    check_kubectl
    
    ODOO_POD=$(kubectl get pods -n "$K8S_NAMESPACE" -l app=odoo -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$ODOO_POD" ]; then
        log_error "No Odoo pod found in namespace $K8S_NAMESPACE"
        exit 1
    fi
    
    MODULES="nettrades_core,nettrades_bridge,nettrades_data_collection,nettrades_trigger,nettrades_loop,nettrades_self_improving_config"
    
    log_info "Installing modules in pod $ODOO_POD: $MODULES"
    if ! kubectl exec "$ODOO_POD" -n "$K8S_NAMESPACE" -- \
        python /usr/lib/python3/dist-packages/odoo/odoo-bin \
        -c /etc/odoo/odoo.conf \
        -i "$MODULES" \
        --stop-after-init; then
        log_error "Failed to install modules"
        exit 1
    fi
    
    log_success "Modules installed successfully!"
}

# -----------------------------------------------------------------------------
# 6. Command Handling
# -----------------------------------------------------------------------------

usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  up              Scale up services"
    echo "  down            Scale down services"
    echo "  status          Show current scale status"
    echo "  deploy          Deploy Odoo modules"
    echo "  help            Show this help message"
    echo ""
    echo "Options:"
    echo "  --kubernetes    Use Kubernetes mode (default: Docker Compose)"
    echo "  --namespace     Kubernetes namespace (default: frontend)"
    echo "  --context       Kubernetes context (optional)"
    echo ""
    echo "Environment Variables:"
    echo "  ODOO_WORKERS       Number of Odoo workers (default: 2)"
    echo "  LANGGRAPH_WORKERS  Number of LangGraph workers (default: 2)"
    echo "  GPU_WORKERS        Number of GPU workers (NVIDIA Dynamo) (default: 1)"
    echo "  SELF_IMPROVING_WORKERS  Number of self-improving workers (default: 1)"
}

# Parse command line arguments
COMMAND=""
while [[ $# -gt 0 ]]; do
    case $1 in
        up|down|status|deploy|help)
            COMMAND="$1"
            shift
            ;;
        --kubernetes)
            USE_KUBERNETES=true
            shift
            ;;
        --namespace)
            K8S_NAMESPACE="$2"
            shift 2
            ;;
        --context)
            K8S_CONTEXT="$2"
            shift 2
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Default command
if [ -z "$COMMAND" ]; then
    COMMAND="status"
fi

# Execute command
case $COMMAND in
    up)
        if [ "$USE_KUBERNETES" = true ]; then
            scale_kubernetes_up
        else
            scale_docker_up
        fi
        ;;
    down)
        if [ "$USE_KUBERNETES" = true ]; then
            scale_kubernetes_down
        else
            scale_docker_down
        fi
        ;;
    status)
        if [ "$USE_KUBERNETES" = true ]; then
            show_kubernetes_status
        else
            show_docker_status
        fi
        ;;
    deploy)
        deploy_odoo_modules
        ;;
    help)
        usage
        ;;
esac

echo ""
log_success "Operation completed successfully!"