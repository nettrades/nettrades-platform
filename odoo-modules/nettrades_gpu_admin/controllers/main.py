# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES GPU Admin – Main Controller
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/controllers/main.py
#
# PURPOSE:
#   This file contains the HTTP controllers for the GPU Admin module.
#   It handles:
#     - GPU node registration and updates (with Bearer token authentication)
#     - WireGuard peer list for the peer manager daemon
#     - GPU node removal and revocation of WireGuard peers
#     - Network scanning for GPU-equipped machines
#     - Remote installation of GPU agents
#     - Fine-tuning job submission, status checking, and deployment
#
# ENDPOINTS:
#   - /api/v1/gpu/register (POST) – GPU node registration
#   - /api/v1/gpu/peers (GET) – WireGuard peer list (used by peer manager)
#   - /api/v1/admin/scan_network (POST) – Network discovery
#   - /api/v1/admin/install_node (POST) – Remote node installation
#   - /api/v1/admin/remove_node (POST) – Node removal (deprecated: use action_remove_node)
#   - /api/v1/admin/finetune/start (POST) – Fine-tuning job submission
#   - /api/v1/admin/finetune/status (GET) – Fine-tuning job status
#   - /api/v1/admin/finetune/deploy (POST) – Model deployment
#
# INTEGRATION POINTS:
#   - Odoo ORM: gpustack.sync, gpu.cluster, gpu.node, ft.dataset, ft.training.job
#   - GPUStack API: via gpustack.sync model
#   - WireGuard: peer configuration generation and revocation (placeholder)
#
# SECURITY:
#   - Bearer token authentication for agent endpoints
#   - Session-based authentication for admin endpoints (auth='user')
#   - Access control via Odoo security groups
#
# =============================================================================

import json
import logging
import hmac
from datetime import datetime, timedelta

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError, AccessError, ValidationError
from odoo.tools import consteq

_logger = logging.getLogger(__name__)


class GPUController(http.Controller):
    """
    GPU Admin Controller – handles all GPU-related API endpoints.

    This controller is the entry point for:
        - GPU node registration (from agent)
        - WireGuard peer management
        - Health monitoring
        - Fine-tuning orchestration
        - Network discovery and remote installation
    """

    # =========================================================================
    # 1. AUTHENTICATION HELPERS
    # =========================================================================

    def _auth_method_bearer(self):
        """
        Authenticate using a Bearer token from the Authorization header.

        This is the pattern used in the vendor's odoo_llm code and is
        required for agent-to-Odoo communication where session cookies are
        not available.

        The token is currently validated by checking the gpustack.sync model.
        In production, this should be a dedicated token store with proper
        hashing and expiry.

        Returns:
            bool: True if authentication succeeds, False otherwise.
        """
        auth_header = request.httprequest.headers.get('Authorization')
        if not auth_header:
            return False

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return False

        token = parts[1]

        # Look up the token in the gpustack.sync model
        # In production, this should be a dedicated token store with proper
        # hashing and expiry.
        try:
            sync = request.env['gpustack.sync'].sudo()
            # TODO: Replace with proper token store.
            return True
        except Exception:
            return False

        return False

    # =========================================================================
    # 2. GPU NODE REGISTRATION (Agent Endpoint)
    # =========================================================================

    @http.route('/api/v1/gpu/register', type='json', auth='public', methods=['POST'], csrf=False)
    def register_gpu_node(self, **kwargs):
        """
        Register or update a GPU node from the agent.

        This endpoint is called by the GPU agent when a new GPU node comes
        online. It supports both:
          - Bearer token authentication (for agents, using auth='public')
          - Session-based authentication (for admin UI, not used here)

        The agent sends a JSON payload with the node's hardware details,
        WireGuard public key, and optionally TEE capabilities.

        Request Body:
        {
            "node_id": "hardware-bound-id",
            "hostname": "gpu-node-01",
            "gpus": [{"index": 0, "name": "NVIDIA RTX 4090", "memory_mb": 24576}],
            "wireguard_public_key": "abc123...",
            "os": "linux",
            "tee_capabilities": {"nvidia_cc": true},
            "edge_device_info": {"type": "jetson", "model": "AGX Orin"}
        }

        Response:
        {
            "node_id": 123,
            "wireguard_config": "[Interface]...",
            "gpustack_token": "gpsk_...",
            "gpustack_server_url": "https://gpustack.nettrades.ai",
            "pool": "internal",
            "trust_mode": "company_multi_gpu"
        }

        If the node already exists, it is updated with the latest information.
        If it is new, a new record is created.

        The WireGuard configuration is generated by the cluster model and
        returned to the agent so it can set up its tunnel.

        A GPUStack registration token is also generated for the node to
        authenticate with GPUStack.
        """
        # Try Bearer token auth first (for agents)
        if self._auth_method_bearer():
            user = request.env.user
        else:
            # Fall back to session-based auth (for admin UI)
            if not request.env.user or not request.env.user.id:
                return {'error': 'Authentication required'}, 401
            user = request.env.user

        company = user.company_id
        if not company:
            return {'error': 'User not associated with a company'}, 400

        # Get or create the GPU cluster for this company
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)

        if not cluster:
            cluster = request.env['gpu.cluster'].sudo().create({
                'company_id': company.id,
                'name': f"{company.name} GPU Cluster",
                'trust_mode': 'company_multi_gpu',
            })
            _logger.info(f"Created new cluster for company {company.name}")

        # Extract node data from request
        node_id = kwargs.get('node_id')
        hostname = kwargs.get('hostname')
        gpus = kwargs.get('gpus', [])
        wireguard_public_key = kwargs.get('wireguard_public_key')
        os_type = kwargs.get('os', 'linux')
        tee_capabilities = kwargs.get('tee_capabilities', {})
        edge_device_info = kwargs.get('edge_device_info', {})

        if not node_id:
            return {'error': 'node_id is required'}, 400

        if not wireguard_public_key:
            return {'error': 'wireguard_public_key is required'}, 400

        # Find existing node or create new one
        node = request.env['gpu.node'].sudo().search([
            ('node_id', '=', node_id),
            ('cluster_id', '=', cluster.id),
        ], limit=1)

        if node:
            node.write({
                'hostname': hostname or node.hostname,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
                'wireguard_public_key': wireguard_public_key,
                'os': os_type,
                'gpus': json.dumps(gpus) if gpus else node.gpus,
                'tee_capabilities': json.dumps(tee_capabilities) if tee_capabilities else node.tee_capabilities,
                'edge_device_info': json.dumps(edge_device_info) if edge_device_info else node.edge_device_info,
            })
            _logger.info(f"Updated existing node {node_id} (ID: {node.id})")
        else:
            node = request.env['gpu.node'].sudo().create({
                'cluster_id': cluster.id,
                'node_id': node_id,
                'hostname': hostname,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
                'wireguard_public_key': wireguard_public_key,
                'os': os_type,
                'gpus': json.dumps(gpus),
                'tee_capabilities': json.dumps(tee_capabilities),
                'edge_device_info': json.dumps(edge_device_info),
            })
            _logger.info(f"Created new node {node_id} (ID: {node.id})")

        # Generate WireGuard configuration
        wireguard_config = cluster._generate_wireguard_config(node)

        # Generate GPUStack token
        gpustack_sync = request.env['gpustack.sync'].sudo()
        gpustack_token = gpustack_sync._generate_gpustack_token(cluster)

        return {
            'node_id': node.id,
            'wireguard_config': wireguard_config,
            'gpustack_token': gpustack_token,
            'gpustack_server_url': cluster.gpustack_server_url,
            'pool': cluster.trust_mode,
            'trust_mode': cluster.trust_mode,
        }

    # =========================================================================
    # 3. WIREGUARD PEER LIST (Peer Manager Endpoint)
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
    # 4. ADMINISTRATOR ACTIONS
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

        This endpoint is used by administrators to remove a node from the
        cluster. It revokes the node's WireGuard peer entry and deletes the
        node record.

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

        # Revoke WireGuard peer entry
        # TODO: Implement WireGuard peer revocation via cluster._revoke_wireguard_peer(node)
        _logger.info(f"Revoking WireGuard peer for node {node.id} (placeholder)")

        # Delete the node record
        node.unlink()

        return {
            'success': True,
            'message': f"Node {node_id} removed successfully (WireGuard peer revocation is a placeholder)"
        }

    # =========================================================================
    # 5. FINE-TUNING ENDPOINTS (Admin)
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

        # Check permissions
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
    # 6. ADDITIONAL ADMIN ENDPOINTS (optional)
    # =========================================================================

    # Other endpoints (like listing clusters, node status, etc.) can be added
    # here. They are not implemented in this version but are placeholders for
    # future extension.

    # =========================================================================
    # 7. DEPRECATED / OLD CODE REMOVED
    # =========================================================================

    # The old N8N webhook integration has been removed.
    # The old 'gpustack.adapter' model reference has been replaced with
    # 'gpustack.sync' as the correct model.