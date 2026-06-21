# -*- coding: utf-8 -*-
# =============================================================================
# SECTION H – NETTRADES GPU Admin – Main Controller
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/controllers/main.py
#
# PURPOSE:
#   This file contains the main HTTP controllers for the GPU Admin module.
#   It handles GPU node registration, WireGuard peer management, and
#   administrator actions.
#
# ENDPOINTS:
#   - /api/v1/gpu/register (POST) – GPU node registration
#   - /api/v1/gpu/peers (GET) – WireGuard peer list
#   - /api/v1/admin/scan_network (POST) – Network discovery
#   - /api/v1/admin/install_node (POST) – Remote node installation
#   - /api/v1/admin/remove_node (POST) – Node removal
#   - /api/v1/admin/finetune/start (POST) – Fine-tuning job submission
#   - /api/v1/admin/finetune/status (GET) – Fine-tuning job status
#   - /api/v1/admin/finetune/deploy (POST) – Model deployment
#
# IMPORTANT FIXES:
#   - Previously, the fine-tuning trigger used an n8n webhook.
#     N8N has been REMOVED due to licensing restrictions.
#     Replaced with direct LangGraph/GPUStack calls.
#   - The ai.gpu.* model references have been removed (they don't exist).
#   - The auth mechanism has been simplified to use Odoo's native auth.
#
# =============================================================================

import json
import logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError, AccessError

_logger = logging.getLogger(__name__)


class GPUController(http.Controller):
    """
    GPU Admin Controller – handles all GPU-related API endpoints.
    """

    # =========================================================================
    # 1. GPU NODE REGISTRATION
    # =========================================================================

    @http.route('/api/v1/gpu/register', type='json', auth='user', methods=['POST'], csrf=False)
    def register_gpu_node(self, **kwargs):
        """
        Register or update a GPU node from the agent.

        This endpoint is called by the NETTRADES GPU agent when a node starts up.
        It creates or updates the node record in Odoo and returns WireGuard
        configuration and GPUStack token.

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
        """
        # Get the authenticated user
        user = request.env.user
        company = user.company_id

        if not company:
            return {'error': 'User not associated with a company'}

        # Get or create the GPU cluster for this company
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)

        if not cluster:
            # Create a default cluster for this company
            cluster = request.env['gpu.cluster'].sudo().create({
                'company_id': company.id,
                'name': f"{company.name} GPU Cluster",
                'trust_mode': 'company_multi_gpu',
            })
            _logger.info(f"Created new cluster for company {company.name}")

        # Extract node data from request
        node_id = kwargs.get('node_id')
        hostname = kwargs.get('hostname', '')
        gpus = kwargs.get('gpus', [])
        pubkey = kwargs.get('wireguard_public_key', '')
        os_name = kwargs.get('os', 'linux')
        tee_caps = kwargs.get('tee_capabilities', {})
        edge_info = kwargs.get('edge_device_info', {})
        ip_address = kwargs.get('ip_address', '')

        # Find or create the node record
        node = request.env['gpu.node'].sudo().search([
            ('cluster_id', '=', cluster.id),
            ('node_id', '=', node_id),
        ], limit=1)

        if not node and pubkey:
            # Try to find by WireGuard public key (legacy)
            node = request.env['gpu.node'].sudo().search([
                ('cluster_id', '=', cluster.id),
                ('wireguard_public_key', '=', pubkey),
            ], limit=1)

        if not node:
            # Create a new node
            node = request.env['gpu.node'].sudo().create({
                'cluster_id': cluster.id,
                'node_id': node_id,
                'name': hostname or node_id,
                'hostname': hostname,
                'ip_address': ip_address,
                'gpus': gpus,
                'wireguard_public_key': pubkey,
                'os': os_name,
                'tee_capabilities': tee_caps,
                'edge_device_info': edge_info,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
            })
            _logger.info(f"Created new node {node.name} in cluster {cluster.name}")
        else:
            # Update existing node
            node.write({
                'hostname': hostname,
                'ip_address': ip_address,
                'gpus': gpus,
                'wireguard_public_key': pubkey or node.wireguard_public_key,
                'os': os_name,
                'tee_capabilities': tee_caps,
                'edge_device_info': edge_info,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
            })
            _logger.info(f"Updated node {node.name}")

        # Generate WireGuard configuration
        try:
            wg_config = node._generate_wireguard_config()
        except Exception as e:
            _logger.error(f"Failed to generate WireGuard config: {e}")
            return {'error': f'Failed to generate WireGuard config: {str(e)}'}

        # Generate GPUStack token
        try:
            gpustack_token = node._generate_gpustack_token()
        except Exception as e:
            _logger.error(f"Failed to generate GPUStack token: {e}")
            gpustack_token = None

        return {
            'node_id': node.id,
            'wireguard_config': wg_config,
            'gpustack_token': gpustack_token,
            'gpustack_server_url': cluster.gpustack_server_url,
            'pool': node.pool,
            'trust_mode': cluster.trust_mode,
        }

    # =========================================================================
    # 2. WIREGUARD PEER LIST
    # =========================================================================

    @http.route('/api/v1/gpu/peers', type='json', auth='user', methods=['GET'])
    def get_wireguard_peers(self):
        """
        Return every active GPU node's WireGuard public key and allowed IPs.

        This endpoint is used by the WireGuard peer manager daemon to
        synchronise the WireGuard interface with the database.
        """
        user = request.env.user
        company = user.company_id

        if not company:
            return {'error': 'User not associated with a company'}

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
    # 3. ADMINISTRATOR ACTIONS
    # =========================================================================

    @http.route('/api/v1/admin/scan_network', type='json', auth='user', methods=['POST'])
    def scan_network(self, **kwargs):
        """
        Scan the network for GPU-equipped machines.

        This endpoint triggers a network scan and returns discovered machines.
        Requires GPU Administrator privileges.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can scan the network")

        subnet = kwargs.get('subnet')
        cluster_id = kwargs.get('cluster_id')

        cluster = request.env['gpu.cluster'].sudo().browse(cluster_id)
        if not cluster.exists():
            return {'error': 'Cluster not found'}

        # Scan the network
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

        This endpoint triggers remote installation of the GPU agent.
        Requires GPU Administrator privileges.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can install nodes")

        ip_address = kwargs.get('ip_address')
        cluster_id = kwargs.get('cluster_id')
        pool = kwargs.get('pool', 'internal')

        if not ip_address:
            return {'error': 'IP address required'}

        cluster = request.env['gpu.cluster'].sudo().browse(cluster_id)
        if not cluster.exists():
            return {'error': 'Cluster not found'}

        # Install the agent on the remote host
        try:
            result = cluster._install_agent_on_host(ip_address, pool)
            return result
        except Exception as e:
            _logger.error(f"Node installation failed: {e}")
            return {'error': f'Node installation failed: {str(e)}'}

    @http.route('/api/v1/admin/remove_node', type='json', auth='user', methods=['POST'])
    def remove_node(self, **kwargs):
        """
        Remove a GPU node from the cluster.

        This endpoint removes a node from the cluster, revokes its WireGuard
        peer, and deregisters it from GPUStack.
        Requires GPU Administrator privileges.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can remove nodes")

        node_id = kwargs.get('node_id')

        if not node_id:
            return {'error': 'Node ID required'}

        node = request.env['gpu.node'].sudo().browse(node_id)
        if not node.exists():
            return {'error': 'Node not found'}

        try:
            result = node.action_remove_node()
            return {'success': True, 'message': 'Node removed successfully'}
        except Exception as e:
            _logger.error(f"Node removal failed: {e}")
            return {'error': f'Node removal failed: {str(e)}'}

    # =========================================================================
    # 4. FINE-TUNING ENDPOINTS
    # =========================================================================

    @http.route('/api/v1/admin/finetune/start', type='json', auth='user', methods=['POST'])
    def start_finetune(self, **kwargs):
        """
        Start a fine-tuning job.

        This endpoint triggers a fine-tuning job on the selected GPUs.
        Requires GPU Administrator privileges.

        ⚠️ IMPORTANT: Previously, this used an n8n webhook.
        N8N has been REMOVED. Now uses direct GPUStack API calls.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can start fine-tuning")

        dataset_id = kwargs.get('dataset_id')
        base_model = kwargs.get('base_model')
        mode = kwargs.get('mode', 'single')  # 'single' or 'multi'
        gpu_node_ids = kwargs.get('gpu_ids', [])

        if not dataset_id:
            return {'error': 'Dataset ID required'}

        if not base_model:
            return {'error': 'Base model required'}

        # Get the dataset and field
        dataset = request.env['ft.dataset'].sudo().browse(dataset_id)
        if not dataset.exists():
            return {'error': 'Dataset not found'}

        field = dataset.field_id
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', request.env.user.company_id.id),
        ], limit=1)

        if not cluster:
            return {'error': 'No GPU cluster found for this company'}

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

        # =========================================================================
        # N8N REMOVED – Direct GPUStack Call
        # =========================================================================
        # Previously, this code used an n8n webhook:
        #   webhook_url = request.env['ir.config_parameter'].sudo().get_param(
        #       'n8n_finetune_webhook', 'https://n8n.nettrades.ai/webhook/fine-tuning-trigger'
        #   )
        #   requests.post(webhook_url, json={...})
        #
        # N8N has been REMOVED due to licensing restrictions.
        # Now we call GPUStack directly via the adapter.
        # =========================================================================

        try:
            # Call the GPUStack adapter to submit the training job
            # The adapter handles the communication with GPUStack's API
            gpustack_adapter = request.env['gpustack.adapter'].sudo()
            result = gpustack_adapter.submit_training_job(
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
            }

    @http.route('/api/v1/admin/finetune/status', type='json', auth='user', methods=['GET'])
    def get_finetune_status(self, **kwargs):
        """
        Get the status of a fine-tuning job.
        """
        job_id = kwargs.get('job_id')

        if not job_id:
            return {'error': 'Job ID required'}

        job = request.env['ft.training.job'].sudo().browse(job_id)
        if not job.exists():
            return {'error': 'Job not found'}

        # Check permissions
        if job.field_id.company_id != request.env.user.company_id:
            raise AccessError("You do not have access to this job")

        return {
            'job_id': job.id,
            'status': job.status,
            'started_at': job.started_at,
            'completed_at': job.completed_at,
            'error_message': job.error_message,
            'metrics': job.metrics,
        }

    @http.route('/api/v1/admin/finetune/deploy', type='json', auth='user', methods=['POST'])
    def deploy_finetuned_model(self, **kwargs):
        """
        Deploy a fine-tuned model.

        This endpoint deploys a completed fine-tuned model to GPUStack.
        Requires GPU Administrator privileges.
        """
        # Check permissions
        if not request.env.user.has_group('nettrades_gpu_admin.group_gpu_administrator'):
            raise AccessError("Only GPU administrators can deploy models")

        job_id = kwargs.get('job_id')

        if not job_id:
            return {'error': 'Job ID required'}

        job = request.env['ft.training.job'].sudo().browse(job_id)
        if not job.exists():
            return {'error': 'Job not found'}

        if job.status != 'completed':
            return {'error': 'Job is not completed'}

        # Deploy the model via GPUStack
        try:
            gpustack_adapter = request.env['gpustack.adapter'].sudo()
            result = gpustack_adapter.deploy_model(
                model_id=job.fine_tuned_model_id,
                field_id=job.field_id.id,
            )

            if result.get('success'):
                # Update the field's default provider
                job.field_id.default_llm_provider_id = result.get('provider_id')
                _logger.info(f"Model {job.fine_tuned_model_id} deployed successfully")
                return {
                    'success': True,
                    'message': 'Model deployed successfully',
                    'provider_id': result.get('provider_id'),
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
            }