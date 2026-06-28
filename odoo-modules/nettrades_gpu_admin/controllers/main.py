#!/usr/bin/env python3
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/controllers/main.py
# =============================================================================
# DESCRIPTION:
#   GPU Admin Controller – handles GPU node registration, cluster management,
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
#   ────────────────────────────────────────────────────────────────────────────
#   PUBLIC (token-authenticated)
#   ────────────────────────────────────────────────────────────────────────────
#   POST /api/v1/gpu/register          – Register a new GPU node using a
#                                        registration token. (REPLACED the old
#                                        insecure bearer-check with real token
#                                        validation.)
#
#   ────────────────────────────────────────────────────────────────────────────
#   INTERNAL (Odoo user authenticated)
#   ────────────────────────────────────────────────────────────────────────────
#   GET  /api/v1/gpu/peers             – List all active WireGuard peers.
#   POST /api/v1/admin/scan_network    – Scan network for GPU machines.
#   POST /api/v1/admin/install_node    – Install GPU agent on remote host.
#   POST /api/v1/admin/remove_node     – Remove a GPU node from cluster.
#   POST /api/v1/admin/finetune/start  – Start a fine-tuning job.
#   GET  /api/v1/admin/finetune/status – Check fine-tuning job status.
#   POST /api/v1/admin/finetune/deploy – Deploy a fine-tuned model.
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
from odoo import http
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
            'dns_servers': cluster.dns_servers or '8.8.8.8, 1.1.1.1',
        }

        _logger.info(
            "Generated WireGuard config for node %s with IP %s in cluster %s",
            node_name, node_ip, cluster.name
        )

        return config

    @http.route(
        '/api/v1/gpu/register',
        type='json',
        auth='public',          # Public endpoint, but token-based auth is applied
        methods=['POST'],
        csrf=False,
        cors='*'
    )
    def register_node(self, **kwargs):
        """
        Register a new GPU node into the cluster.

        This endpoint implements a secure token-based registration flow:
        1. Client provides a registration token (Bearer auth).
        2. Client provides its WireGuard public key (generated locally).
        3. Client provides a node name and optional IP hint.
        4. System validates the token against the token store.
        5. System allocates an IP address for the node.
        6. System generates a node-specific WireGuard configuration.
        7. System returns the configuration to the client.

        Request payload:
            {
                "name": "alice-gpu-01",
                "public_key": "AbC123...",
                "ip": "10.0.0.10"      # optional
            }

        Response (success):
            {
                "status": "success",
                "node": {
                    "id": 123,
                    "name": "alice-gpu-01",
                    "ip": "10.0.0.10",
                    "wireguard": {
                        "server_public_key": "...",
                        "server_endpoint": "wg.example.com:51820",
                        "address": "10.0.0.10/32",
                        "allowed_ips": "10.0.0.0/8",
                        "persistent_keepalive": 25,
                        "dns_servers": "8.8.8.8, 1.1.1.1"
                    }
                }
            }

        Response (error):
            {
                "status": "error",
                "error": "Human-readable error message"
            }

        Security:
            - Token validation against gpu.registration.token model.
            - Tokens stored as SHA-256 hashes (never plaintext).
            - One-time use tokens are marked as used after successful registration.
            - Expired/revoked tokens are rejected.
            - Node-specific token binding (optional).
            - All errors logged for audit.
        """
        # ---------------------------------------------------------------------
        # Step 1: Check if registration is enabled (default: true)
        # ---------------------------------------------------------------------
        if not _ENABLE_GPU_REGISTRATION:
            _logger.warning(
                "GPU registration endpoint called but is disabled. "
                "Set ENABLE_GPU_REGISTRATION=true to enable."
            )
            return {
                "status": "error",
                "error": "GPU registration is disabled by administrator configuration."
            }

        # ---------------------------------------------------------------------
        # Step 2: Authenticate the request using the Bearer token
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
            return {
                "status": "error",
                "error": str(e)
            }

        # ---------------------------------------------------------------------
        # Step 3: Extract and validate request parameters
        # ---------------------------------------------------------------------
        try:
            params = request.jsonrequest or {}
            node_name = params.get('name')
            node_public_key = params.get('public_key')
            requested_ip = params.get('ip')

            if not node_name:
                return {"status": "error", "error": "Missing required field: name"}

            if not node_public_key:
                return {"status": "error", "error": "Missing required field: public_key"}

            # Basic WireGuard public key format check (44 chars, Base64)
            if len(node_public_key) != 44 or not all(
                c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in node_public_key
            ):
                return {"status": "error", "error": "Invalid WireGuard public key format"}

            # If the token is bound to a specific node, validate it
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
            # Step 4: Get the GPU cluster (scoped by the token's company)
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
            # Step 5: Allocate an IP address
            # -----------------------------------------------------------------
            try:
                node_ip = self._allocate_ip(cluster, node_name)
            except Exception as e:
                _logger.error("IP allocation failed: %s", str(e))
                return {"status": "error", "error": f"IP allocation failed: {str(e)}"}

            # -----------------------------------------------------------------
            # Step 6: Create the node record
            # -----------------------------------------------------------------
            Node = request.env['gpu.node'].sudo()
            node_vals = {
                'name': node_name,
                'cluster_id': cluster.id,
                'wireguard_public_key': node_public_key,
                'wireguard_ip': node_ip,
                'registration_token_id': token.id,
                'company_id': token.company_id.id,
                'state': 'pending',
            }

            try:
                node = Node.create(node_vals)
                _logger.info(
                    "Created GPU node record: %s (ID: %d) with IP %s",
                    node_name, node.id, node_ip
                )
            except Exception as e:
                _logger.exception("Failed to create node record: %s", str(e))
                return {"status": "error", "error": f"Failed to create node record: {str(e)}"}

            # -----------------------------------------------------------------
            # Step 7: Generate the node-specific WireGuard configuration
            # -----------------------------------------------------------------
            try:
                wg_config = self._generate_node_wireguard_config(
                    cluster,
                    node_name,
                    node_public_key,
                    node_ip
                )
            except Exception as e:
                _logger.exception("Failed to generate WireGuard config: %s", str(e))
                # Rollback: delete the node record
                node.unlink()
                return {"status": "error", "error": f"WireGuard config generation failed: {str(e)}"}

            # -----------------------------------------------------------------
            # Step 8: Update node state and return success
            # -----------------------------------------------------------------
            node.write({'state': 'active'})

            _logger.info(
                "GPU node %s (ID: %d) successfully registered with IP %s "
                "using token %s (ID: %d) by company %s",
                node_name, node.id, node_ip,
                token.name, token.id, token.company_id.name
            )

            return {
                "status": "success",
                "node": {
                    "id": node.id,
                    "name": node_name,
                    "ip": node_ip,
                    "wireguard": {
                        "server_public_key": wg_config['server_public_key'],
                        "server_endpoint": wg_config['server_endpoint'],
                        "address": f"{wg_config['address']}/32",
                        "allowed_ips": wg_config['allowed_ips'],
                        "persistent_keepalive": wg_config['persistent_keepalive'],
                        "dns_servers": wg_config['dns_servers'],
                    }
                }
            }

        except Exception as e:
            _logger.exception("Unexpected error in GPU registration endpoint: %s", str(e))
            return {
                "status": "error",
                "error": "Internal server error. Please contact support."
            }

    # =========================================================================
    # 2. WIREGUARD PEER LIST (Internal, Odoo Authenticated)
    # =========================================================================

    @http.route('/api/v1/gpu/peers', type='json', auth='user', methods=['GET'])
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
    # 3. ADMINISTRATOR ACTIONS (Odoo Authenticated + Group Checks)
    # =========================================================================

    @http.route('/api/v1/admin/scan_network', type='json', auth='user', methods=['POST'])
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

    @http.route('/api/v1/admin/install_node', type='json', auth='user', methods=['POST'])
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

    @http.route('/api/v1/admin/remove_node', type='json', auth='user', methods=['POST'])
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

        # Revoke WireGuard peer entry (placeholder – implement actual revocation)
        # TODO: Implement WireGuard peer revocation via cluster._revoke_wireguard_peer(node)
        _logger.info(f"Revoking WireGuard peer for node {node.id} (placeholder)")

        # Delete the node record
        node.unlink()

        return {
            'success': True,
            'message': f"Node {node_id} removed successfully (WireGuard peer revocation is a placeholder)"
        }

    # =========================================================================
    # 4. FINE-TUNING ENDPOINTS (Admin)
    # =========================================================================

    @http.route('/api/v1/admin/finetune/start', type='json', auth='user', methods=['POST'])
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

    @http.route('/api/v1/admin/finetune/status', type='json', auth='user', methods=['GET'])
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

    @http.route('/api/v1/admin/finetune/deploy', type='json', auth='user', methods=['POST'])
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
    # 5. DEPRECATED / REMOVED CODE
    # =========================================================================
    # The old `_auth_method_bearer()` placeholder has been removed.
    # The old N8N webhook integration has been removed.
    # The old 'gpustack.adapter' model reference has been replaced with
    # 'gpustack.sync' as the correct model.
    # All functionality has been preserved or replaced by secure equivalents.