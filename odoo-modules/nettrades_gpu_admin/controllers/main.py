#!/usr/bin/env python3
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/controllers/main.py
# =============================================================================
# DESCRIPTION:
#   GPU Admin Controller - handles GPU node registration, cluster management,
#   WireGuard configuration, and administrative tasks for the distributed GPU
#   network.
#
#   This controller implements a secure token-based authentication system for
#   node registration (modeled after Tailscale, Wiredoor, and DockNimbus) while
#   preserving all original admin and peer-management functionality.
#
#
#   It also handles:
#     - Network scanning for GPU-equipped machines
#     - Remote installation of GPU agents
#     - Fine-tuning job submission, status checking, and deployment
#
# ENDPOINTS:
#   ----------------------------------------------------------------------------
#   PUBLIC (token-authenticated)
#   ----------------------------------------------------------------------------
#   POST /api/v1/gpu/register          - Register a new GPU node using a
#                                        registration token. (REPLACED the old
#                                        insecure bearer-check with real token
#                                        validation.)
#
#   ----------------------------------------------------------------------------
#   INTERNAL (Odoo user authenticated)
#   ----------------------------------------------------------------------------
#   GET  /api/v1/gpu/peers             - List all active WireGuard peers.
#   POST /api/v1/admin/scan_network    - Scan network for GPU machines.
#   POST /api/v1/admin/install_node    - Install GPU agent on remote host.
#   POST /api/v1/admin/remove_node     - Remove a GPU node from cluster.
#   POST /api/v1/admin/finetune/start  - Start a fine-tuning job.
#   GET  /api/v1/admin/finetune/status - Check fine-tuning job status.
#   POST /api/v1/admin/finetune/deploy - Deploy a fine-tuned model.
#
# SECURITY IMPROVEMENTS:
#   1. Registration uses SHA-256 hashed tokens stored in gpu.registration.token.
#   2. Tokens are one-time use, time-limited, revocable, and scoped by company.
#   3. Node provides its own WireGuard public key (private key never transmitted).
#   4. Controller private key is NEVER generated or exposed.
#   5. All admin endpoints enforce group permissions (group_gpu_administrator).
#   6. All endpoints log detailed audit information.
# =============================================================================

import os
import logging
import ipaddress
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================
# The registration endpoint is enabled by default with token-based auth.
# Set ENABLE_GPU_REGISTRATION=false to disable it entirely (emergency kill-switch).
_ENABLE_GPU_REGISTRATION = os.getenv('ENABLE_GPU_REGISTRATION', 'true').lower() == 'true'
_DEFAULT_SUBNET = os.getenv('WIREGUARD_SUBNET', '10.0.0.0/8')


class GpuAdminController(http.Controller):

    # =========================================================================
    # 1. GPU NODE REGISTRATION (Token-Authenticated)
    # =========================================================================

    def _validate_token(self, auth_header):
        """
        Extract and validate the Bearer token from the Authorization header.

        This method:
        1. Extracts the token from the "Authorization: Bearer <token>" header.
        2. Validates the token against the gpu.registration.token model.
        3. Returns the validated token record or raises an exception.

        Args:
            auth_header (str): The Authorization header value.

        Returns:
            gpu.registration.token: The validated token record.

        Raises:
            Exception: With appropriate error message if validation fails.
        """
        if not auth_header:
            _logger.warning("GPU registration: missing Authorization header")
            raise Exception("Missing Authorization header")

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            _logger.warning("GPU registration: malformed Authorization header")
            raise Exception("Invalid Authorization header format. Expected: Bearer <token>")

        plaintext_token = parts[1]

        # Validate the token using the model
        token_model = request.env['gpu.registration.token'].sudo()
        result = token_model.validate_token(plaintext_token)

        if not result['valid']:
            _logger.warning("GPU registration: token validation failed: %s", result.get('error'))
            raise Exception(result.get('error', 'Token validation failed'))

        return result['token']

    def _allocate_ip(self, cluster, node_name=None):
        """
        Allocate a unique IP address for a new node from the cluster's subnet.

        Args:
            cluster (gpu.cluster): The GPU cluster record.
            node_name (str, optional): Name of the node for logging.

        Returns:
            str: The allocated IP address.

        Raises:
            Exception: If no IP addresses are available.
        """
        subnet_str = cluster.wireguard_subnet or _DEFAULT_SUBNET
        try:
            subnet = ipaddress.ip_network(subnet_str, strict=False)
        except ValueError as e:
            _logger.error("Invalid subnet configuration: %s", subnet_str)
            raise Exception(f"Invalid subnet configuration: {subnet_str}")

        Node = request.env['gpu.node'].sudo()
        existing_nodes = Node.search([('cluster_id', '=', cluster.id)])
        existing_ips = set()
        for node in existing_nodes:
            if node.wireguard_ip:
                try:
                    existing_ips.add(ipaddress.ip_address(node.wireguard_ip))
                except ValueError:
                    pass

        all_ips = list(subnet.hosts())
        for ip in all_ips:
            if ip not in existing_ips:
                _logger.info(
                    "Allocated IP %s for node %s in cluster %s",
                    str(ip), node_name or 'unnamed', cluster.name
                )
                return str(ip)

        _logger.error("No available IPs in subnet %s for cluster %s", subnet_str, cluster.name)
        raise Exception(f"No available IPs in subnet {subnet_str}")

    def _generate_node_wireguard_config(self, cluster, node_name, node_public_key, node_ip):
        """
        Generate a WireGuard configuration for a specific node.

        This method returns the server-side details that the node needs to
        establish a tunnel. The node's private key is NEVER stored or returned.

        Args:
            cluster (gpu.cluster): The GPU cluster record.
            node_name (str): Name of the node.
            node_public_key (str): The node's WireGuard public key.
            node_ip (str): The allocated IP address for the node.

        Returns:
            dict: WireGuard configuration with keys:
                - server_public_key: The server's public key.
                - server_endpoint: The server's endpoint (IP or domain:port).
                - address: The node's IP address.
                - allowed_ips: The allowed IP ranges.
                - persistent_keepalive: Keepalive interval.
                - dns_servers: DNS servers for the node.
        """
        server_public_key = cluster.wireguard_server_public_key
        server_endpoint = cluster.wireguard_server_endpoint
        listen_port = cluster.wireguard_listen_port or 51820

        if not server_public_key or not server_endpoint:
            _logger.error(
                "Cluster %s missing WireGuard server configuration. "
                "Please configure wireguard_server_public_key and wireguard_server_endpoint.",
                cluster.name
            )
            raise Exception("Cluster WireGuard configuration incomplete")

        allowed_ips = cluster.wireguard_subnet or _DEFAULT_SUBNET

        config = {
            'server_public_key': server_public_key,
            'server_endpoint': server_endpoint,
            'server_port': listen_port,
            'address': node_ip,
            'allowed_ips': allowed_ips,
            'persistent_keepalive': 25,
            'node_name': node_name,
            'dns_servers': '8.8.8.8, 1.1.1.1',
        }

        _logger.info(
            "Generated WireGuard config for node %s with IP %s in cluster %s",
            node_name, node_ip, cluster.name
        )

        return config

    @http.route(
        '/api/v1/gpu/register',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        csrf=False,
        cors='*'
    )
    def register_node(self, **kwargs):
        """
        Register a new GPU node into the cluster.

        Two modes are supported:

        * WireGuard mode (use_wireguard: true, default for legacy
          clients): the spoke generates a WireGuard keypair, the hub
          allocates an IP from the cluster's WireGuard subnet, and the
          hub returns a peer config. The spoke brings up the tunnel.

        * LAN mode (use_wireguard: false, default for the demo): the
          spoke sends its LAN IP in `subnet_ip`. The hub stores that IP
          in `wireguard_ip`. The hub does not generate a WireGuard
          config. The RPC master connects to the LAN IP directly over
          plain TCP.

        Both modes create the same `gpu.node` record with `state='active'`.
        Only the IP assignment and the optional WireGuard block differ.
        """
        if not _ENABLE_GPU_REGISTRATION:
            _logger.warning("GPU registration endpoint called but is disabled.")
            return {
                "status": "error",
                "error": "GPU registration is disabled by administrator configuration."
            }

        # ---------------------------------------------------------------------
        # Step 1: Authenticate the request using the Bearer token
        # ---------------------------------------------------------------------
        try:
            auth_header = request.httprequest.headers.get('Authorization')
            token = self._validate_token(auth_header)
            _logger.info(
                "GPU registration request authenticated with token: %s (ID: %d)",
                token.name, token.id
            )
        except Exception as e:
            _logger.warning("GPU registration authentication failed: %s", str(e))
            return {"status": "error", "error": str(e)}

        # ---------------------------------------------------------------------
        # Step 2: Extract and validate request parameters
        # ---------------------------------------------------------------------
        try:
            params = request.httprequest.get_json(silent=True) or {}
            node_name = params.get('name')
            use_wireguard = bool(params.get('use_wireguard', True))
            node_public_key = params.get('public_key')
            subnet_ip = params.get('subnet_ip')
            requested_ip = params.get('ip')

            if not node_name:
                return {"status": "error", "error": "Missing required field: name"}

            # WireGuard key format check only in WireGuard mode.
            if use_wireguard:
                if not node_public_key:
                    return {"status": "error", "error": "Missing required field: public_key"}
                if len(node_public_key) != 44 or not all(
                    c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in node_public_key
                ):
                    return {"status": "error", "error": "Invalid WireGuard public key format"}
            else:
                # LAN mode: require subnet_ip.
                if not subnet_ip:
                    return {"status": "error",
                            "error": "Missing required field: subnet_ip (LAN IP of the spoke)"}

            if token.node_name and token.node_name != node_name:
                return {
                    "status": "error",
                    "error": f"This token is bound to node name: {token.node_name}"
                }
            if token.node_public_key and token.node_public_key != node_public_key:
                return {
                    "status": "error",
                    "error": "This token is bound to a specific public key"
                }

            # -----------------------------------------------------------------
            # Step 3: Get the GPU cluster (scoped by the token's company)
            # -----------------------------------------------------------------
            cluster = request.env['gpu.cluster'].sudo().search([
                ('company_id', '=', token.company_id.id)
            ], limit=1)

            if not cluster:
                _logger.error(
                    "No GPU cluster found for company %s. Cannot register node.",
                    token.company_id.name
                )
                return {"status": "error", "error": "No GPU cluster configured for your organization"}

            # -----------------------------------------------------------------
            # Step 4: Allocate or accept the node IP
            # -----------------------------------------------------------------
            if use_wireguard:
                try:
                    node_ip = self._allocate_ip(cluster, node_name)
                except Exception as e:
                    _logger.error("IP allocation failed: %s", str(e))
                    return {"status": "error", "error": f"IP allocation failed: {str(e)}"}
            else:
                node_ip = subnet_ip

            # -----------------------------------------------------------------
            # Step 5: Create or update the node record.
            #
            # BUG-004 (2026-10-22): gpu.node.partner_id is required=True with
            # no default and no create() override in the model. Any create()
            # that omits it raises ValidationError and blocks registration.
            #
            # IDEMPOTENT RE-REGISTRATION (2026-10-22):
            #   spoke-agent.py calls register() every time the spoke process
            #   starts - on every reboot, on every `systemctl restart`, and
            #   on every network-recovery path. If we always create(), a
            #   fleet of hundreds of spokes produces thousands of orphan
            #   gpu.node rows per year, and the health monitor tracks every
            #   one of them. That is not acceptable for a platform designed
            #   to run at scale.
            #
            #   We therefore look up an existing node by (cluster_id, name)
            #   and reuse it. A node is "the same node" if it is in the
            #   same cluster with the same name and is not archived. The
            #   spoke always uses the same node_name (system hostname, or
            #   the --node-name argument given to install-spoke.sh), so
            #   this lookup is reliable.
            #
            #   The update path rewrites every field that a re-registration
            #   should refresh: the LAN/WG IP (DHCP may have changed), the
            #   GPU inventory (hardware may have been added), the compute
            #   profile (RAM/CPU), and the inference capability. It does
            #   NOT rewrite partner_id - ownership belongs to the token,
            #   not the heartbeat, and changing it silently would break
            #   company-scoped record rules.
            #
            # Partner resolution order:
            #   1. The token's company partner - semantically correct, since
            #      a GPU node belongs to the company that issued the token.
            #   2. The token creator's partner - the operator who minted the
            #      token.
            #   3. base.partner_root - the platform's public root partner.
            #      This always exists, so registration cannot fail on a
            #      missing partner.
            # -----------------------------------------------------------------
            Node = request.env['gpu.node'].sudo()

            # BUG-004 fix - resolve partner_id before create().
            _partner = None
            if token.company_id and token.company_id.partner_id:
                _partner = token.company_id.partner_id
            elif (getattr(token, 'created_by', None)
                  and token.created_by.partner_id):
                _partner = token.created_by.partner_id
            else:
                _partner = request.env.ref(
                    'base.partner_root', raise_if_not_found=False,
                )
            if not _partner:
                _logger.error(
                    "Cannot register GPU node: no partner available for "
                    "company %s or token creator.",
                    token.company_id.name,
                )
                return {
                    "status": "error",
                    "error": "No partner available for this registration token.",
                }

            node_vals = {
                'name': node_name,
                'cluster_id': cluster.id,
                'wireguard_public_key': node_public_key or False,
                # NOTE: `wireguard_ip` is the address the RPC master connects
                # to. In LAN mode it holds the spoke's real LAN IP.
                'wireguard_ip': node_ip,
                'registration_token_id': token.id,
                'company_id': token.company_id.id,
                'state': 'pending',
                'gpus': params.get('gpus') or [],
                'compute_profile': params.get('compute_profile') or {},
                'inference_capability': params.get('inference_capability', 'rpc_worker'),
            }

            # Look up an existing active/pending node for this cluster+name.
            # `state in ('pending', 'active')` excludes archived records so
            # a deliberate decommission is not resurrected by a reboot.
            existing = Node.search([
                ('cluster_id', '=', cluster.id),
                ('name', '=', node_name),
                ('state', 'in', ('pending', 'active')),
            ], limit=1)

            try:
                if existing:
                    _logger.info(
                        "Re-registration: updating existing node id=%s "
                        "name=%r (previous state: %s, previous ip: %s)",
                        existing.id, node_name,
                        existing.state, existing.wireguard_ip or '-',
                    )
                    # Preserve partner_id on update. The token that
                    # authorized this registration already set it; changing
                    # it here would break record rules for the company that
                    # originally onboarded the node.
                    existing.write(node_vals)
                    node = existing
                else:
                    node_vals['partner_id'] = _partner.id
                    _logger.info(
                        "Registering new GPU node '%s' under partner '%s' (id=%s)",
                        node_name, _partner.display_name, _partner.id,
                    )
                    node = Node.create(node_vals)
            except Exception as e:
                # A create/update failure here is not recoverable from the
                # caller's perspective - the spoke cannot proceed. Log the
                # full exception (including traceback via .exception) so an
                # operator can diagnose from the Odoo logs without needing
                # to reproduce.
                _logger.exception(
                    "Failed to persist gpu.node for name=%r (token id=%s): %s",
                    node_name, token.id, e,
                )
                return {
                    "status": "error",
                    "error": (
                        "Failed to persist node record. "
                        "Please contact support with the node name and "
                        "registration timestamp."
                    ),
                }


            # -----------------------------------------------------------------
            # Step 6: Optionally generate the WireGuard config
            # -----------------------------------------------------------------
            wg_block = None
            if use_wireguard:
                try:
                    wg_block = self._generate_node_wireguard_config(
                        cluster, node_name, node_public_key, node_ip,
                    )
                except Exception as e:
                    _logger.exception("Failed to generate WireGuard config: %s", str(e))
                    node.unlink()
                    return {"status": "error", "error": f"WireGuard config generation failed: {str(e)}"}

            # -----------------------------------------------------------------
            # Step 7: Mark active and return
            # -----------------------------------------------------------------
            node.write({'state': 'active'})

            response_node = {
                "id": node.id,
                "name": node_name,
                "ip": node_ip,
            }
            if wg_block:
                response_node["wireguard"] = {
                    "server_public_key": wg_block['server_public_key'],
                    "server_endpoint": wg_block['server_endpoint'],
                    "address": f"{wg_block['address']}/32",
                    "allowed_ips": wg_block['allowed_ips'],
                    "persistent_keepalive": wg_block['persistent_keepalive'],
                    "dns_servers": wg_block['dns_servers'],
                }

            # Option B (2026-11-16): deliver the heartbeat secret to the
            # spoke in the registration response. The spoke uses this
            # only for /nodes/heartbeat on langgraph-server. Odoo's own
            # /api/v1/gpu/heartbeat continues to use the registration
            # token, which is why the secret is never confused with the
            # token that authorised this call.
            #
            # Security boundary: this response is only produced after
            # _validate_token() succeeded (see Step 1 above). The caller
            # already holds a valid registration token, so returning the
            # heartbeat secret to them does not expand the trust boundary
            # — a compromised token already allows full node registration.
            #
            # Delivery conditions:
            #   - Only include the field if the hub actually has a secret
            #     configured. If it is empty, omit the key entirely so
            #     the spoke falls through to its own environment / config
            #     and warns visibly, rather than persisting an empty
            #     string that would then mask later changes.
            #   - Never log the value. The token name and ID are already
            #     logged at Step 1; those are sufficient for audit.
            _hb_secret = os.getenv('LANGGRAPH_HEARTBEAT_SECRET', '').strip()
            if _hb_secret:
                response_node["heartbeat_secret"] = _hb_secret
            else:
                _logger.warning(
                    "Registration succeeded but LANGGRAPH_HEARTBEAT_SECRET is "
                    "not set on the hub. Spoke %r will not receive a heartbeat "
                    "secret and will fail /nodes/heartbeat with 401 until one "
                    "is configured and the spoke re-registers.",
                    node_name,
                )

            return {"status": "success", "node": response_node}

        except Exception as e:
            _logger.exception("Unexpected error in GPU registration endpoint: %s", str(e))
            return {
                "status": "error",
                "error": "Internal server error. Please contact support."
            }

    # =========================================================================
    # 2. WIREGUARD PEER LIST (Internal, Odoo Authenticated)
    # =========================================================================

    @http.route('/api/v1/gpu/peers', type='jsonrpc', auth='user', methods=['GET'])
    def get_wireguard_peers(self):
        """
        Return every active GPU node's WireGuard public key and allowed IPs.

        This endpoint is used by the WireGuard peer manager daemon to
        synchronise the WireGuard interface with the database.

        Returns:
            dict: A list of WireGuard peers with public_key, allowed_ips, and endpoint.
        """
        user = request.env.user
        company = user.company_id

        if not company:
            return {'error': 'User not associated with a company'}, 400

        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)

        if not cluster:
            return {'peers': []}

        # Get all online nodes in the cluster
        nodes = request.env['gpu.node'].sudo().search([
            ('cluster_id', '=', cluster.id),
            ('status', 'in', ['online', 'degraded']),
            ('wireguard_public_key', '!=', False),
        ])

        peers = []
        for node in nodes:
            if node.wireguard_public_key and node.wireguard_assigned_ip:
                peers.append({
                    'public_key': node.wireguard_public_key,
                    'allowed_ips': f"{node.wireguard_assigned_ip}/32",
                    'endpoint': node.endpoint or '',
                })

        return {'peers': peers}

    # =========================================================================
    # 3. HEARTBEAT ENDPOINT
    # =========================================================================

    @http.route(
        '/api/v1/gpu/heartbeat',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        csrf=False,
        cors='*',
    )
    def heartbeat(self, **kwargs):
        """
        Update a registered node's last_seen and telemetry.

        Token-authenticated by the same registration token used at
        registration time. The token is not consumed by heartbeats:
        unlike /register, this endpoint does not mark the token as used.

        The spoke sends this every 10 seconds. It is the durable record
        of "this node is still alive" in Odoo. The parallel push to
        LangGraph's /nodes/heartbeat endpoint is the real-time signal the
        supervisor reads on every routing decision.

        Request payload (from spoke-agent.py):
            {
                "node_id": 123,
                "timestamp": "2026-10-01T00:42:39.123456",
                "vram_total_mb": 24564,
                "gpu_count": 1,
                "model_cached": true,
                "gpu_utilization": 45.2,
                "memory_utilization": 30.0,
                "temperature": 62.0,
                "is_available": true
            }

        Response:
            {"status": "success"}
            or {"status": "error", "error": "..."}
        """
        if not _ENABLE_GPU_REGISTRATION:
            return {"status": "error", "error": "Registration disabled"}

        try:
            auth_header = request.httprequest.headers.get('Authorization')
            token = self._validate_token(auth_header)
        except Exception as e:
            return {"status": "error", "error": str(e)}

        params = request.httprequest.get_json(silent=True) or {}
        node_id = params.get('node_id')
        if not node_id:
            return {"status": "error", "error": "Missing node_id"}

        node = request.env['gpu.node'].sudo().browse(int(node_id))
        if not node.exists() or node.company_id != token.company_id:
            return {"status": "error", "error": "Node not found"}

        # Update durable state.
        #
        # NOTE ON FIELD NAMES (2026-10):
        #   The spoke sends the key "gpu_utilization" (American spelling,
        #   because that is the convention in the Python ecosystem and
        #   in the GPUInfo dataclass). The gpu.node field is named
        #   "gpu_utilisation_pct" (British spelling, matching the model's
        #   existing convention). Do not "fix" this to make the spellings
        #   match - either change both sides together, or leave it.
        #
        # NOTE ON VRAM AND GPU COUNT:
        #   vram_total_mb and gpu_count are captured at registration time
        #   in the `gpus` JSON field and re-emitted on every heartbeat.
        #   Odoo does not need to rewrite them every 10 seconds; the
        #   authoritative real-time copy lives in LangGraph's in-memory
        #   NodeHealth dataclass via POST /nodes/heartbeat. Keeping the
        #   DB write to just last_seen, gpu_utilisation_pct, and status
        #   keeps this endpoint cheap at fleet scale.

        #  Update durable state. Also merge model_cached into compute_profile
        #  so a spoke that downloads the model AFTER registration is promoted
        #  to warm-spare status on its next heartbeat. This is what makes the
        #  scheduler's _find_warm_spare() work without requiring the operator
        #  to re-register the node.

        # Base update. `status='online'` is the default - the heartbeat
        # itself is evidence the node is alive - but it is overridable
        # by the drain flag below.
        update = {
            'last_seen': fields.Datetime.now(),
            'gpu_utilisation_pct': float(params.get('gpu_utilization', 0.0)),
            'status': 'online',
        }

        # NEW (2026-10-22): reflect the drain state in the Odoo record.
        #
        # The authoritative routing signal is the LangGraph health
        # monitor (which sets `is_healthy=False` on the first drain
        # heartbeat). The Odoo `status` field is operator-facing only:
        # it drives the GPU Manager dashboard and any Odoo reports
        # that the operator has open during the demo. Keeping it in
        # sync with the drain state lets the operator see the drain
        # window in Odoo without having to grep the LangGraph logs.
        #
        # We probe the model's status Selection for a 'draining' option
        # rather than unconditionally writing 'draining'. If the field
        # does not declare that option, we fall back to 'online' (the
        # current behaviour). This keeps the change safe for
        # deployments whose gpu.node model has not been migrated.
        if params.get('draining'):
            # Use the model's _fields dict, not a `Node` variable - in
            # this method the record is `node`, and `_fields` is
            # class-level metadata identical across all records of the
            # model, so `node._fields` is the correct accessor.
            status_field = node._fields.get('status')
            valid_options = (
                dict(status_field.selection).keys()
                if status_field is not None and status_field.type == 'selection'
                else set()
            )
            update['status'] = (
                'draining' if 'draining' in valid_options else 'online'
            )
        if 'model_cached' in params:
            profile = node.compute_profile or {}
            if isinstance(profile, str):
                import json as _json
                try:
                    profile = _json.loads(profile)
                except Exception:
                    profile = {}
            profile['model_cached'] = bool(params['model_cached'])
            update['compute_profile'] = profile

        node.write(update)

        return {"status": "success"}

    # =========================================================================
    # 4. ADMINISTRATOR ACTIONS (Odoo Authenticated + Group Checks)
    # =========================================================================

    @http.route('/api/v1/admin/scan_network', type='jsonrpc', auth='user', methods=['POST'])
    def scan_network(self, **kwargs):
        """
        Scan the network for GPU-equipped machines.

        This endpoint triggers a network scan and returns discovered machines.
        Requires GPU Administrator privileges.

        Request Body:
        {
            "subnet": "192.168.1.0/24",    # optional, auto-detected if not provided
            "cluster_id": 1                # optional
        }

        Returns:
            dict: A list of discovered machines with GPU information.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can scan the network")

        subnet = kwargs.get('subnet')
        cluster_id = kwargs.get('cluster_id')

        cluster = request.env['gpu.cluster'].sudo().browse(cluster_id)
        if not cluster.exists():
            return {'error': 'Cluster not found'}

        # Scan the network for GPU-equipped machines
        try:
            discovered = cluster._scan_network_for_gpus(subnet)
            return {'discovered': discovered}
        except Exception as e:
            _logger.error(f"Network scan failed: {e}")
            return {'error': f'Network scan failed: {str(e)}'}

    @http.route('/api/v1/admin/install_node', type='jsonrpc', auth='user', methods=['POST'])
    def install_node(self, **kwargs):
        """
        Install the GPU agent on a remote host.

        This endpoint triggers remote installation of the GPU agent via SSH.
        Requires GPU Administrator privileges.

        Request Body:
        {
            "ip_address": "192.168.1.100",
            "cluster_id": 1,
            "pool": "internal",
            "ssh_user": "root",
            "ssh_key": "ssh-rsa ..."        # optional
        }

        Returns:
            dict: Installation success or error message.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can install nodes")

        ip_address = kwargs.get('ip_address')
        cluster_id = kwargs.get('cluster_id')
        pool = kwargs.get('pool', 'internal')
        ssh_user = kwargs.get('ssh_user', 'root')
        ssh_key = kwargs.get('ssh_key')

        if not ip_address:
            return {'error': 'IP address required'}

        cluster = request.env['gpu.cluster'].sudo().browse(cluster_id)
        if not cluster.exists():
            return {'error': 'Cluster not found'}

        # Install the agent on the remote host
        try:
            result = cluster._install_agent_on_host(ip_address, pool, ssh_user, ssh_key)
            return result
        except Exception as e:
            _logger.error(f"Node installation failed: {e}")
            return {'error': f'Node installation failed: {str(e)}'}

    @http.route('/api/v1/admin/remove_node', type='jsonrpc', auth='user', methods=['POST'])
    def remove_node(self, **kwargs):
        """
        Remove a GPU node from the cluster.

        This endpoint revokes the node's WireGuard peer entry and deletes the
        node record. Requires GPU Administrator privileges.

        Request Body:
        {
            "node_id": 123
        }

        Returns:
            dict: Success or error message.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can remove nodes")

        node_id = kwargs.get('node_id')
        if not node_id:
            return {'error': 'node_id is required'}, 400

        node = request.env['gpu.node'].sudo().browse(node_id)
        if not node.exists():
            return {'error': 'Node not found'}, 404

        # Revoke the WireGuard peer and cleanup node registration state
        try:
            if node.cluster_id and node.cluster_id.exists():
                node.cluster_id._revoke_wireguard_peer(node)
        except Exception as e:
            _logger.warning("Failed to revoke WireGuard peer for node %s: %s", node.id, e)

        # Delete the node record
        node.unlink()

        return {
            'success': True,
            'message': f"Node {node_id} removed successfully"
        }

    # =========================================================================
    # 5. FINE-TUNING ENDPOINTS (Admin)
    # =========================================================================

    @http.route('/api/v1/admin/finetune/start', type='jsonrpc', auth='user', methods=['POST'])
    def start_finetune(self, **kwargs):
        """
        Start a fine-tuning job.

        This endpoint is called by administrators to initiate a fine-tuning
        job on a dataset using the configured GPUStack cluster.

        N8N has been REMOVED; this now uses direct GPUStack calls.

        Request Body:
        {
            "dataset_id": 456,
            "base_model": "llama-3.2-3b",
            "mode": "single",
            "gpu_ids": [1, 2]   # optional
        }

        Returns:
            dict: Job ID and status, or error message.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can start fine-tuning")

        dataset_id = kwargs.get('dataset_id')
        base_model = kwargs.get('base_model')
        mode = kwargs.get('mode', 'single')
        gpu_node_ids = kwargs.get('gpu_ids', [])

        if not dataset_id:
            return {'error': 'Dataset ID required'}, 400
        if not base_model:
            return {'error': 'Base model required'}, 400

        # Get the dataset and field
        dataset = request.env['ft.dataset'].sudo().browse(dataset_id)
        if not dataset.exists():
            return {'error': 'Dataset not found'}, 404

        field = dataset.field_id
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', request.env.user.company_id.id),
        ], limit=1)

        if not cluster:
            return {'error': 'No GPU cluster found for this company'}, 404

        # Create a training job record
        job = request.env['ft.training.job'].sudo().create({
            'dataset_id': dataset.id,
            'field_id': field.id,
            'provider': field.finetune_provider or 'unsloth',
            'base_model': base_model,
            'status': 'pending',
            'hyperparameters': field.hyperparameters or {},
            'started_at': fields.Datetime.now(),
        })

        # Use the gpustack.sync model to submit the training job
        try:
            gpustack_sync = request.env['gpustack.sync'].sudo()
            result = gpustack_sync.submit_training_job(
                job_id=job.id,
                dataset_path=dataset.file_uri,
                base_model=base_model,
                mode=mode,
                gpu_ids=gpu_node_ids,
                hyperparameters=field.hyperparameters or {},
            )

            if result.get('success'):
                job.status = 'running'
                job.fine_tuned_model_id = result.get('model_id')
                _logger.info(f"Fine-tuning job {job.id} started successfully")
                return {
                    'success': True,
                    'job_id': job.id,
                    'status': 'running',
                }
            else:
                job.status = 'failed'
                job.error_message = result.get('error', 'Unknown error')
                _logger.error(f"Fine-tuning job {job.id} failed: {result.get('error')}")
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                }

        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            _logger.error(f"Fine-tuning job {job.id} failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }, 500

    @http.route('/api/v1/admin/finetune/status', type='jsonrpc', auth='user', methods=['GET'])
    def get_finetune_status(self, **kwargs):
        """
        Get the status of a fine-tuning job.

        This endpoint allows administrators to check the progress and
        status of a submitted fine-tuning job.

        Query Parameters:
            job_id (required): The ID of the training job.

        Returns:
            dict: Job details including status, started_at, completed_at,
                  error_message, and metrics.
        """
        job_id = kwargs.get('job_id')

        if not job_id:
            return {'error': 'Job ID required'}, 400

        job = request.env['ft.training.job'].sudo().browse(job_id)
        if not job.exists():
            return {'error': 'Job not found'}, 404

        # Check permissions (only users in the same company)
        if job.field_id.company_id != request.env.user.company_id:
            raise AccessError("You do not have access to this job")

        return {
            'job_id': job.id,
            'status': job.status,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message,
            'metrics': job.metrics,
            'fine_tuned_model_id': job.fine_tuned_model_id,
        }

    @http.route('/api/v1/admin/finetune/deploy', type='jsonrpc', auth='user', methods=['POST'])
    def deploy_finetuned_model(self, **kwargs):
        """
        Deploy a fine-tuned model.

        This endpoint deploys a previously fine-tuned model to GPUStack
        so it can be used for inference.

        Request Body:
        {
            "job_id": 789
        }

        Returns:
            dict: Success or error message.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can deploy fine-tuned models")

        job_id = kwargs.get('job_id')
        if not job_id:
            return {'error': 'Job ID required'}, 400

        job = request.env['ft.training.job'].sudo().browse(job_id)
        if not job.exists():
            return {'error': 'Job not found'}, 404

        if job.status != 'completed':
            return {'error': 'Job is not completed yet'}, 400

        try:
            gpustack_sync = request.env['gpustack.sync'].sudo()
            result = gpustack_sync.deploy_model(
                job_id=job.id,
                model_id=job.fine_tuned_model_id,
            )

            if result.get('success'):
                _logger.info(f"Model {job.fine_tuned_model_id} deployed successfully")
                return {
                    'success': True,
                    'message': 'Model deployed successfully',
                    'deployment_id': result.get('deployment_id'),
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error'),
                }

        except Exception as e:
            _logger.error(f"Model deployment failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }, 500

    # =========================================================================
    # 6. DEPRECATED / REMOVED CODE
    # =========================================================================
    # The old `_auth_method_bearer()` placeholder has been removed.
    # The old N8N webhook integration has been removed.
    # The old 'gpustack.adapter' model reference has been replaced with
    # 'gpustack.sync' as the correct model.
    # All functionality has been preserved or replaced by secure equivalents.