#!/bin/bash
# =============================================================================
# NETTRADES.AI – Kubernetes Base Deployment (Valkey edition)
# =============================================================================
# This script creates all namespaces, installs the CNPG operator,
# deploys the PostgreSQL cluster (with scheduled backups), Valkey,
# and all application manifests via Kustomize.  It also installs
# Prometheus/Grafana via the kube-prometheus-stack Helm chart.
# =============================================================================
set -euo pipefail
trap 'echo "ERROR: script failed at line $LINENO with exit code $?." >&2' ERR

# ---- Validate environment ----
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and fill in secrets." >&2
    exit 1
fi
source .env

required_vars=("POSTGRES_PASSWORD" "FORGEJO_INTERNAL_DB_PASSWORD" "FORGEJO_CLIENT_DB_PASSWORD"
               "LANGGRAPH_API_KEY" "ODOO_API_KEY" "MCP_API_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var:-}" ] || [ "${!var}" = "changeit" ]; then
        echo "ERROR: Environment variable $var is not set or still has the default value." >&2
        exit 1
    fi
done

# Verify required tools
for cmd in kubectl helm; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd is required but not installed." >&2
        exit 1
    fi
done

# ---- Namespaces & Pod Security ----
echo "=== 1. Namespaces ==="
kubectl apply -f apps/namespaces.yaml
kubectl label ns frontend gpustack pod-security.kubernetes.io/enforce=baseline --overwrite
kubectl label ns backend ai pod-security.kubernetes.io/enforce=baseline --overwrite
kubectl label ns runners pod-security.kubernetes.io/enforce=restricted --overwrite

# ---- CNPG Operator ----
echo "=== 2. CNPG Operator ==="
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm upgrade --install cnpg cnpg/cloudnative-pg --namespace cnpg-system --create-namespace --wait
# wait for CRD to be established
kubectl wait --for=condition=established crd/clusters.postgresql.cnpg.io --timeout=120s

# ---- PostgreSQL Cluster ----
echo "=== 3. PostgreSQL CNPG Cluster ==="
kubectl apply -f apps/backend/postgres-cluster.yaml
kubectl wait --for=condition=ready cluster/odoo-db -n backend --timeout=300s

# ---- Create Forgejo databases ----
echo "=== 4. Forgejo databases ==="
CNPG_PRIMARY=$(kubectl get pods -n backend -l cnpg.io/instanceRole=primary -o name | head -1)
if [ -z "$CNPG_PRIMARY" ]; then
    echo "ERROR: Could not find CNPG primary pod." >&2
    exit 1
fi
kubectl exec -n backend "$CNPG_PRIMARY" -- psql -U postgres -c \
    "CREATE USER forgejo_internal WITH PASSWORD '${FORGEJO_INTERNAL_DB_PASSWORD}';" || true
kubectl exec -n backend "$CNPG_PRIMARY" -- psql -U postgres -c \
    "CREATE DATABASE forgejo_internal OWNER forgejo_internal;" || true
kubectl exec -n backend "$CNPG_PRIMARY" -- psql -U postgres -c \
    "CREATE USER forgejo_client WITH PASSWORD '${FORGEJO_CLIENT_DB_PASSWORD}';" || true
kubectl exec -n backend "$CNPG_PRIMARY" -- psql -U postgres -c \
    "CREATE DATABASE forgejo_client OWNER forgejo_client;" || true

# ---- Valkey ----
echo "=== 5. Valkey ==="
kubectl apply -f apps/backend/valkey-statefulset.yaml

# ---- All applications via Kustomize ----
echo "=== 6. Applications ==="
kubectl apply -k .

# ---- Monitoring ----
echo "=== 7. Prometheus + Grafana ==="
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring --create-namespace --wait --version 84.5.0

# ---- Quick health-check ----
echo "=== 8. Health-check ==="
kubectl rollout status deployment/odoo -n frontend --timeout=120s || echo "WARNING: Odoo not ready yet"
kubectl rollout status deployment/gpustack -n gpustack --timeout=60s || echo "WARNING: GPUStack not ready yet"

echo ""
echo "============================================================="
echo " Kubernetes deployment complete"
echo "============================================================="
echo " Odoo:       https://nettrades.ai"
echo " Grafana:    https://grafana.nettrades.ai  (admin / <secret>)"
echo " Argo CD:    https://argo.nettrades.ai"
echo "============================================================="