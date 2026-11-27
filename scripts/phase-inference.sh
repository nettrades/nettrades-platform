#!/bin/bash
# =============================================================================
# FILE: scripts/phase-inference.sh
# =============================================================================
# PURPOSE:
#   Phase 6: Hardware-aware inference backend deployment.
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
export PROJECT_ROOT

source "$SCRIPT_DIR/lib/colors.sh"
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/gpu_detect.sh"

ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"
[[ -f "$ENV_FILE" ]] || { log_error ".env not found. Run Phase 1."; exit 1; }

V100_IP=$(detect_primary_ip)
BACKEND=$(select_inference_backend)

log_step "Hardware-aware Inference Backend Selection"
log_info "Primary LAN IP: $V100_IP"
log_info "Selected backend: $BACKEND"

# Persist to .env
if grep -q "^INFERENCE_BACKEND=" "$ENV_FILE"; then
    sed -i "s#^INFERENCE_BACKEND=.*#INFERENCE_BACKEND=$BACKEND#" "$ENV_FILE"
else
    echo "INFERENCE_BACKEND=$BACKEND" >> "$ENV_FILE"
fi

case "$BACKEND" in
    vllm)
        log_step "Deploying vLLM (Volta SM70 path)"
        VLLM_PORT=8001 DYNAMO_API_KEY="$(grep '^DYNAMO_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)" \
            bash "$SCRIPT_DIR/deploy-v100-vllm.sh"
        
        # Update .env with the real LAN IP
        sed -i "s#^LLM_BASE_URL=.*#LLM_BASE_URL=http://${V100_IP}:8001/v1#" "$ENV_FILE"

        # Wait for vLLM to actually serve /v1/models before we point the
        # consumers at it. The model load takes 2-5 minutes for a 7B on
        # four V100s; without this wait, configure-hub-for-spokes.sh
        # probes an endpoint that is still loading and marks the
        # dynamo_worker unreachable, which disables Tier 2.
        log_step "Waiting for vLLM to become healthy on port 8001..."
        _api_key=$(grep '^DYNAMO_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)
        _ready=false
        for _i in $(seq 1 60); do
            if curl -sf -o /dev/null -H "Authorization: Bearer ${_api_key}" \
                    "http://${V100_IP}:8001/v1/models"; then
                _ready=true
                break
            fi
            sleep 5
        done
        if [[ "$_ready" != "true" ]]; then
            log_error "vLLM did not become healthy within 5 minutes."
            log_error "Check: docker logs vllm-demo --tail 50"
            exit 1
        fi
        log_success "vLLM is serving on http://${V100_IP}:8001/v1"

        # Recreate the containers that read LLM_BASE_URL from .env.
        # Without this, langgraph-server keeps the old endpoint baked
        # into its environment and every chat goes to CPU.
        log_step "Recreating langgraph-server and nettrades-ui with new LLM_BASE_URL..."
        docker compose -f "$PROJECT_ROOT/deploy/docker/docker-compose.yaml" \
            up -d --force-recreate langgraph-server nettrades-ui
        log_success "Consumers recreated"
        ;;
    dynamo)
        log_step "Deploying NVIDIA Dynamo (Ampere+ path)"
        # Placeholder for future Dynamo deployment
        log_warning "Dynamo deployment script not yet implemented. Falling back to vLLM."
        ;;
    llamacpp)
        log_step "Deploying llama.cpp (CPU fallback)"
        # llama.cpp is part of the standard docker stack, already started in Phase 2.
        sed -i "s#^LLM_BASE_URL=.*#LLM_BASE_URL=http://llama-cpp:8080/v1#" "$ENV_FILE"
        ;;
esac

# Trigger the hub configuration to register the dynamo_worker with the correct IP
log_step "Registering inference endpoint with Odoo..."
if ! bash "$SCRIPT_DIR/configure-hub-for-spokes.sh"; then
    log_error "configure-hub-for-spokes.sh failed. The dynamo_worker may not be registered."
    log_error "Without it, Tier 2 failover (V100 vLLM fallback) will not fire."
    exit 1
fi

log_success "Phase 6 (Inference) completed. Backend: $BACKEND"