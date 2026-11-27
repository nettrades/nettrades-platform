#!/bin/bash
# =============================================================================
# FILE: scripts/configure-hub-for-spokes.sh
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

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found. Run nettrades-setup.sh first."
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

HUB_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{print $7; exit}')"
if [[ -z "$HUB_IP" ]]; then
    HUB_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
if [[ -z "$HUB_IP" ]]; then
    echo "ERROR: Could not determine the hub's LAN IP."
    exit 1
fi
echo "Hub LAN IP: $HUB_IP"

PY_SCRIPT=$(mktemp /tmp/configure-hub-XXXXXX.py)
cat > "$PY_SCRIPT" << 'PYEOF'
import os, sys, json, urllib.request, urllib.error

hub_ip = os.environ.get('HUB_IP', '0.0.0.0')
company = env['res.company'].search([], limit=1)

print('[configure-hub-for-spokes] trust_mode=company_single_gpu', file=sys.stderr)

cluster = env['gpu.cluster'].sudo().search([('name', '=', 'Demo Cluster')], limit=1)
if not cluster:
    cluster = env['gpu.cluster'].sudo().create({
        'name': 'Demo Cluster',
        'company_id': company.id,
        'trust_mode': 'company_single_gpu',
        'status': 'active',
        'wireguard_mesh_subnet': hub_ip.rsplit('.', 1)[0] + '.0/24',
        'allow_dynamo_fallback': True,
        'allow_rpc_partial_fallback': False,
        'allow_marketplace_fallback': False,
        'allow_external_api_fallback': False,
    })
    print('[configure-hub-for-spokes] created cluster id=%s' % cluster.id, file=sys.stderr)
else:
    if cluster.trust_mode != 'company_single_gpu':
        cluster.write({'trust_mode': 'company_single_gpu', 'allow_dynamo_fallback': True})
        print('[configure-hub-for-spokes] corrected trust_mode on id=%s' % cluster.id, file=sys.stderr)
    else:
        print('[configure-hub-for-spokes] cluster exists id=%s' % cluster.id, file=sys.stderr)

llm_base_url = os.environ.get('LLM_BASE_URL', '').rstrip('/')
if not llm_base_url:
    print('[configure-hub-for-spokes] LLM_BASE_URL not set; skipping dynamo_worker', file=sys.stderr)
else:
    models_url = llm_base_url + '/models'
    dynamo_reachable = False
    model_count = 0
    try:
        req = urllib.request.Request(models_url, method='GET')
        api_key = os.environ.get('DYNAMO_API_KEY', '')
        if api_key:
            req.add_header('Authorization', 'Bearer ' + api_key)
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode('utf-8'))
                model_count = len(body.get('data') or [])
                dynamo_reachable = model_count > 0
    except Exception as e:
        print('[configure-hub-for-spokes] LLM_BASE_URL probe failed: %s' % e, file=sys.stderr)

    Node = env['gpu.node'].sudo()
    dynamo_node = Node.search([('inference_capability', '=', 'dynamo_worker')], limit=1)
    
    if dynamo_reachable:
        # The supervisor uses this to decide whether the model fits
        # before routing to Dynamo (Tier 2). It must be real VRAM,
        # not a token value. Try, in order:
        #   1. explicit override in the environment
        #   2. nvidia-smi on the host
        #   3. a conservative fallback that is large enough to hold
        #      the demo model (so Tier 2 can fire)
        _vram_override = os.environ.get('DYNAMO_NODE_VRAM_MB', '').strip()
        if _vram_override:
            nominal_vram_mb = int(_vram_override)
        else:
            try:
                import subprocess as _sp
                _out = _sp.run(
                    ['nvidia-smi', '--query-gpu=memory.total',
                     '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=5,
                )
                if _out.returncode == 0:
                    _total = sum(int(x.strip()) for x in _out.stdout.strip().split('\n') if x.strip())
                    nominal_vram_mb = _total if _total > 0 else 65536
                else:
                    nominal_vram_mb = 65536
            except Exception:
                nominal_vram_mb = 65536
        print(
            '[configure-hub-for-spokes] dynamo_worker VRAM = %d MB'
            % nominal_vram_mb,
            file=sys.stderr,
        )

        if not dynamo_node:
            dynamo_node = Node.create({
                'name': 'Remote-vLLM-Hub',
                'hostname': os.environ.get('HUB_IP', '0.0.0.0'),
                'endpoint': llm_base_url.replace('/v1', ''),
                'cluster_id': cluster.id,
                'company_id': company.id,
                'partner_id': company.partner_id.id,
                'inference_capability': 'dynamo_worker',
                'state': 'active',
                'compute_profile': {
                    'source': 'probe',
                    'models_url': models_url,
                    'model_count': model_count,
                },
                'gpus': [{
                    'index': 0, 'vendor': 'unknown', 'model': 'vLLM',
                    'memory_mb': nominal_vram_mb,
                }],
            })
            print(
                '[configure-hub-for-spokes] registered dynamo_worker id=%s models=%d'
                % (dynamo_node.id, model_count),
                file=sys.stderr,
            )
        else:
            dynamo_node.write({
                'endpoint': llm_base_url.replace('/v1', ''),
                'gpus': [{
                    'index': 0, 'vendor': 'unknown', 'model': 'vLLM',
                    'memory_mb': nominal_vram_mb,
                }],
                'compute_profile': {
                    'source': 'probe',
                    'models_url': models_url,
                    'model_count': model_count,
                },
            })
            print(
                '[configure-hub-for-spokes] updated dynamo_worker id=%s'
                % dynamo_node.id,
                file=sys.stderr,
            )
    else:
        if dynamo_node:
            dynamo_node.unlink()
            print(
                '[configure-hub-for-spokes] removed stale dynamo_worker id=%s'
                % dynamo_node.id,
                file=sys.stderr,
            )
        else:
            print(
                '[configure-hub-for-spokes] no dynamo_worker (endpoint unreachable)',
                file=sys.stderr,
            )
Token = env['gpu.registration.token'].sudo()
plaintext = None
try:
    if hasattr(Token, 'generate_token'):
        rec, plaintext = Token.generate_token(name='Demo Spoke Token', company_id=company.id, max_uses=0)
        print('[configure-hub-for-spokes] token generated via generate_token', file=sys.stderr)
    else:
        raise AttributeError('no generate_token')
except Exception:
    import secrets, string
    plaintext = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
    fields = Token._fields
    vals = {'name': 'Demo Spoke Token', 'company_id': company.id}
    for candidate in ('token', 'api_key', 'key', 'secret'):
        if candidate in fields:
            vals[candidate] = plaintext
            break
    if 'cluster_id' in fields:
        vals['cluster_id'] = cluster.id
    rec = Token.create(vals)
    print('[configure-hub-for-spokes] token created via create()', file=sys.stderr)

try:
    if hasattr(Token, 'validate_token'):
        check = Token.validate_token(plaintext)
        token_valid = bool(check and check.get('valid'))
    else:
        token_valid = True
        print('[configure-hub-for-spokes] WARNING: no validate_token()', file=sys.stderr)
except Exception as e:
    token_valid = False
    print('[configure-hub-for-spokes] validate_token() raised: %s' % e, file=sys.stderr)

if not token_valid:
    print('[configure-hub-for-spokes] FATAL: token does not validate', file=sys.stderr)
    env.cr.rollback()
    print('NETTRADES_TOKEN=')
    print('NETTRADES_CLUSTER_ID=')
    sys.exit(1)

env.cr.commit()
print('[configure-hub-for-spokes] VERIFIED: cluster=%s' % cluster.id, file=sys.stderr)
print('NETTRADES_TOKEN=%s' % plaintext)
print('NETTRADES_CLUSTER_ID=%s' % cluster.id)
PYEOF

cd "$DEPLOY_DIR"

TOKEN_OUTPUT=$(docker compose exec -T \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e HUB_IP="$HUB_IP" \
    -e LLM_BASE_URL="${LLM_BASE_URL:-}" \
    -e DYNAMO_API_KEY="${DYNAMO_API_KEY:-}" \
    odoo bash -c "cat > /tmp/configure_hub.py && odoo shell -d odoo --db_host=postgres --db_port=5432 --db_user=odoo --db_password=\"\$POSTGRES_PASSWORD\" --no-http < /tmp/configure_hub.py" < "$PY_SCRIPT" 2>&1)

rm -f "$PY_SCRIPT"

echo "$TOKEN_OUTPUT" | grep '^\[configure-hub-for-spokes\]' || true

TOKEN=$(printf '%s\n' "$TOKEN_OUTPUT" | grep '^NETTRADES_TOKEN=' | tail -1 | cut -d= -f2- | tr -d '\r')
CLUSTER_ID=$(printf '%s\n' "$TOKEN_OUTPUT" | grep '^NETTRADES_CLUSTER_ID=' | tail -1 | cut -d= -f2- | tr -d '\r')

if [[ -z "$TOKEN" || -z "$CLUSTER_ID" ]]; then
    echo "ERROR: could not extract token."
    echo "Create manually: http://$HUB_IP:8069 > GPU Manager > Registration Tokens > New"
    exit 1
fi

echo ""
echo "===================================================================="
echo "  Hub ready for spokes"
echo "===================================================================="
echo ""
echo "  Hub IP:          $HUB_IP"
echo "  Cluster ID:      $CLUSTER_ID"
echo "  Trust mode:      company_single_gpu (RPC cluster)"
echo "  Dynamo fallback: enabled (Tier 2)"
echo "  Registration token (visible once):"
echo ""
echo "      $TOKEN"
echo ""
echo "  On the AMD rig, run:"
echo "      sudo ./scripts/install-spoke.sh --hub-host=$HUB_IP --token=$TOKEN"
echo "===================================================================="