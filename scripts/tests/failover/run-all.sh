#!/bin/bash
# =============================================================================
# FILE: scripts/tests/failover/run-all.sh
# PURPOSE:
#   Exercises each failover tier. Run from the sub-hub.
#   Exercise each failover tier of the supervisor's routing hierarchy.
#   Run from the sub-hub. Requires:
#     - LANGGRAPH_API_KEY set (source deploy/docker/.env)
#     - At least one spoke registered (for Tier 3)
#     - V100 reachable and allow_dynamo_fallback=True (for Tier 2)
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
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/deploy/docker/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Run from the sub-hub with the stack deployed."
    exit 1
fi

set -a; source "$ENV_FILE"; set +a

LANGGRAPH_URL="${LANGGRAPH_URL:-http://localhost:8000}"

call_invoke() {
    local thread_id="$1"
    curl -s -X POST "${LANGGRAPH_URL}/invoke" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: $LANGGRAPH_API_KEY" \
        -d "{\"input\":{\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]},\"config\":{\"configurable\":{\"thread_id\":\"$thread_id\"}}}"
}

get_active_track() {
    curl -s "${LANGGRAPH_URL}/routing/events?limit=1" \
        -H "X-API-Key: $LANGGRAPH_API_KEY" | \
        python3 -c "import sys, json; d=json.load(sys.stdin); print(d['events'][-1]['track'] if d['events'] else 'none')"
}

echo "════════════════════════════════════════════════════════════════════"
echo "  Failover Tier Tests"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# -----------------------------------------------------------------------------
# Tier 6 — Fail loud
# -----------------------------------------------------------------------------
echo "── Tier 6 — Fail loud ──"
echo "Instructions:"
echo "  1. On the AMD rig: sudo systemctl stop nettrades-spoke"
echo "  2. Ensure all allow_*_fallback=False in Odoo."
echo ""
read -rp "Press Enter when the spoke is stopped and the policy is set…"

TIER6_THREAD="test-tier6-$(date +%s)"
# Capture headers so we can verify BOTH the status and the Retry-After.
# An HTTP 503 without Retry-After is not the contract the demo claims.
TIER6_HEADERS=$(mktemp)
TIER6_HTTP=$(curl -s -o /dev/null -D "$TIER6_HEADERS" -w "%{http_code}" \
    -X POST "${LANGGRAPH_URL}/invoke" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $LANGGRAPH_API_KEY" \
    -d "{\"input\":{\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]},\"config\":{\"configurable\":{\"thread_id\":\"$TIER6_THREAD\"}}}")

TIER6_RETRY_AFTER=$(grep -i '^retry-after:' "$TIER6_HEADERS" | head -1 | sed 's/^[^:]*: *//' | tr -d '\r')
rm -f "$TIER6_HEADERS"

if [[ "$TIER6_HTTP" == "503" && "$TIER6_RETRY_AFTER" == "30" ]]; then
    echo "✅ Tier 6 PASS — HTTP 503 with Retry-After: 30"
elif [[ "$TIER6_HTTP" == "503" ]]; then
    echo "❌ Tier 6 FAIL — HTTP 503 but Retry-After is '${TIER6_RETRY_AFTER:-missing}' (expected 30)"
else
    echo "❌ Tier 6 FAIL — expected HTTP 503, got $TIER6_HTTP"
fi

# -----------------------------------------------------------------------------
# Tier 2 — Dynamo fallback
# -----------------------------------------------------------------------------
echo ""
echo "── Tier 2 — Dynamo fallback ──"
echo "Instructions:"
echo "  1. On the AMD rig: keep nettrades-spoke stopped"
echo "  2. In Odoo: set allow_dynamo_fallback=True, allow_rpc_partial_fallback=False"
echo "  3. Verify the V100 is reachable: curl http://<v100-ip>:8000/v1/models"
echo ""
read -rp "Press Enter when ready…"

TIER2_THREAD="test-tier2-$(date +%s)"
TIER2_BODY=$(call_invoke "$TIER2_THREAD")
TIER2_TRACK=$(get_active_track)

echo "Response: $TIER2_BODY" | head -c 300
echo ""
if [[ "$TIER2_TRACK" == "dynamo" ]]; then
    echo "✅ Tier 2 PASS — active track is dynamo"
else
    echo "❌ Tier 2 FAIL — active track is $TIER2_TRACK, expected dynamo"
fi

# -----------------------------------------------------------------------------
# Tier 3 — Partial RPC
# -----------------------------------------------------------------------------
echo ""
echo "── Tier 3 — Partial RPC ──"
echo "Instructions:"
echo "  1. On the AMD rig: sudo systemctl stop nettrades-spoke to bring down all 6 rpc-servers"
echo "  2. Start rpc-server manually on just 2 GPUs (e.g. HIP_VISIBLE_DEVICES=0,1)"
echo "  3. In Odoo: allow_rpc_partial_fallback=True, allow_dynamo_fallback=False"
echo ""
read -rp "Press Enter when ready (or skip with Ctrl+C)…"

TIER3_THREAD="test-tier3-$(date +%s)"
call_invoke "$TIER3_THREAD" >/dev/null
TIER3_TRACK=$(get_active_track)

if [[ "$TIER3_TRACK" == "rpc" ]]; then
    echo "✅ Tier 3 PASS — active track is rpc"
else
    echo "❌ Tier 3 FAIL — active track is $TIER3_TRACK, expected rpc"
fi

# -----------------------------------------------------------------------------
# Cleanup reminder
# -----------------------------------------------------------------------------
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Cleanup"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "  On the AMD rig:  sudo systemctl start nettrades-spoke"
echo "  In Odoo:         restore the desired failover policy"
echo ""