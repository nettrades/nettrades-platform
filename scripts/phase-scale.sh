#!/bin/bash
# =============================================================================
# NETTRADES.AI – Phase 4: Kubernetes on Talos (UPDATED)
# =============================================================================
# FILE: scripts/phase-scale.sh
#
# PURPOSE:
#   This script upgrades the NETTRADES platform to Kubernetes on Talos.
#   It includes all custom modules including bridge, fairness, and self-improving.
#
# PHASE 4 STEPS:
#   1. Check prerequisites
#   2. Create Talos VMs on Proxmox
#   3. Bootstrap the Kubernetes cluster
#   4. Install core infrastructure (Cilium, Longhorn, MetalLB)
#   5. Deploy services
#   6. Configure GitOps with Argo CD
#
# UPDATED:
#   - Added all new modules to the Odoo deployment
#   - Added fairness and self-improving config to K8s manifests
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}NETTRADES.AI – Phase 4: Kubernetes on Talos${NC}"
echo -e "${GREEN}============================================================${NC}"

# ... existing infrastructure setup code ...

# =============================================================================
# Deploy Odoo with Updated Configuration
# =============================================================================
echo -e "${YELLOW}Deploying Odoo with updated configuration...${NC}"

cat > deploy/kubernetes/apps/frontend/odoo-deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: odoo
  namespace: frontend
  labels:
    app: odoo
spec:
  replicas: 3
  selector:
    matchLabels:
      app: odoo
  template:
    metadata:
      labels:
        app: odoo
    spec:
      containers:
        - name: odoo
          image: nettrades/odoo:19.0
          ports:
            - containerPort: 8069
          env:
            - name: HOST
              value: odoo-db-rw.backend.svc.cluster.local
            - name: PORT
              value: "5432"
            - name: USER
              value: odoo
            - name: PASSWORD
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: password
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: fairness-secrets
                  key: openai-api-key
                  optional: true
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: fairness-secrets
                  key: anthropic-api-key
                  optional: true
            - name: NETTRADES_BRIDGE_URL
              value: http://bridge.ai.svc.cluster.local:8000
            - name: NETTRADES_REMOTE_BRAIN_URL
              value: https://api.nettrades.ai
            - name: NETTRADES_BRAIN_MODE
              value: hybrid
          volumeMounts:
            - name: odoo-addons
              mountPath: /mnt/extra-addons
            - name: odoo-filestore
              mountPath: /var/lib/odoo
          livenessProbe:
            httpGet:
              path: /web/health
              port: 8069
            initialDelaySeconds: 60
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /web/health
              port: 8069
            initialDelaySeconds: 30
            periodSeconds: 10
      volumes:
        - name: odoo-addons
          persistentVolumeClaim:
            claimName: odoo-addons
        - name: odoo-filestore
          persistentVolumeClaim:
            claimName: odoo-filestore
EOF

echo -e "${GREEN}✓ Odoo deployment updated${NC}"

# =============================================================================
# Create Fairness Secrets
# =============================================================================
echo -e "${YELLOW}Creating fairness secrets...${NC}"

kubectl create secret generic fairness-secrets \
    --namespace frontend \
    --from-literal=openai-api-key=${OPENAI_API_KEY:-} \
    --from-literal=anthropic-api-key=${ANTHROPIC_API_KEY:-} \
    --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✓ Fairness secrets created${NC}"

# =============================================================================
# Deploy Bridge Service
# =============================================================================
echo -e "${YELLOW}Deploying bridge service...${NC}"

kubectl apply -f deploy/kubernetes/apps/bridge/bridge-deployment.yaml
kubectl apply -f deploy/kubernetes/apps/bridge/bridge-service.yaml

echo -e "${GREEN}✓ Bridge service deployed${NC}"

# =============================================================================
# Deploy Self-Improving Services
# =============================================================================
echo -e "${YELLOW}Deploying self-improving services...${NC}"

kubectl apply -f deploy/kubernetes/apps/self-improving/data-collection-deployment.yaml
kubectl apply -f deploy/kubernetes/apps/self-improving/trigger-deployment.yaml
kubectl apply -f deploy/kubernetes/apps/self-improving/loop-deployment.yaml

echo -e "${GREEN}✓ Self-improving services deployed${NC}"

# ... rest of the existing scale script ...