# -*- coding: utf-8 -*-
# =============================================================================
# Section H –  NETTRADES GPU Admin – Main Controller
Is there anything in client_registration.py that this file needs?
# =============================================================================
# Provides endpoints for:
#   - GPU agent registration (stores OS, TEE capabilities)
#   - WireGuard peer list (for the peer manager daemon)
#   - Administrator actions: network scan, node install/remove
#   - GPUStack worker token refresh
#   - Fine-tuning: start, status, deploy
# =============================================================================
import json, logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

class GPUController(http.Controller):

    # -------------------------------------------------------------------------
    # Agent registration – called by the NETTRADES GPU agent
    # -------------------------------------------------------------------------
    @http.route('/api/v1/gpu/register', type='json', auth='public',
                methods=['POST'], csrf=False)
    def register_gpu_node(self, **kwargs):
        """
        Register or update a GPU node from the agent.
        Expects a Bearer token for authentication.
        """
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'error': 'Missing or invalid Authorization header'}

        api_key = auth_header.split(' ')[1]
        key_obj = request.env['ai.gpu.api_key'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True),
        ], limit=1)
        if not key_obj:
            return {'error': 'Invalid API key'}

        partner = key_obj.partner_id
        company = partner.company_id
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', company.id),
        ], limit=1)
        if not cluster:
            return {'error': 'No GPU cluster registered for this company'}

        node_id = kwargs.get('node_id')
        hostname = kwargs.get('hostname', '')
        gpus = kwargs.get('gpus', [])
        pubkey = kwargs.get('wireguard_public_key', '')
        os_name = kwargs.get('os', 'linux')
        tee_caps = kwargs.get('tee_capabilities', {})

        # Find or create the node record
        node = request.env['gpu.node'].sudo().search([
            ('cluster_id', '=', cluster.id),
            ('wireguard_public_key', '=', pubkey),
        ], limit=1) if pubkey else None

        if not node:
            node = request.env['gpu.node'].sudo().create({
                'cluster_id': cluster.id,
                'hostname': hostname,
                'gpus': gpus,
                'wireguard_public_key': pubkey,
                'os': os_name,
                'tee_capabilities': tee_caps,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
            })
        else:
            node.write({
                'hostname': hostname,
                'gpus': gpus,
                'os': os_name,
                'tee_capabilities': tee_caps,
                'status': 'online',
                'last_seen': fields.Datetime.now(),
            })

        # Generate WireGuard config and GPUStack token for the agent
        wg_config = node._generate_wireguard_config()
        gpustack_token = node._generate_gpustack_token()

        return {
            'node_id': node.id,
            'wireguard_config': wg_config,
            'gpustack_token': gpustack_token,
            'gpustack_server_url': cluster.gpustack_server_url,
            'pool': node.pool,
            'trust_mode': cluster.trust_mode,
        }

    # -------------------------------------------------------------------------
    # WireGuard peer list – used by the wg-peer-manager daemon
    # -------------------------------------------------------------------------
    @http.route('/api/v1/gpu/peers', type='json', auth='user', methods=['GET'])
    def get_wireguard_peers(self):
        """
        Return every active GPU node's WireGuard public key and AllowedIPs.
        The controller-side peer manager reconciles this list against the
        live WireGuard interface – adding new peers, updating existing ones,
        and removing any peer NOT in this list (i.e. a node that was
        permanently deleted by the administrator).

        A node that is simply offline (e.g. computer turned off at night) will
        still appear here and will NOT be removed from WireGuard.
        """
        nodes = request.env['gpu.node'].sudo().search([
            ('cluster_id.company_id', '=', request.env.user.company_id.id),
        ])
        peers = []
        for node in nodes:
            if node.wireguard_public_key and node.wireguard_assigned_ip:
                peers.append({
                    'public_key': node.wireguard_public_key,
                    'allowed_ip': node.wireguard_assigned_ip,
                })
        return peers

    # -------------------------------------------------------------------------
    # Administrator actions
    # -------------------------------------------------------------------------
    @http.route('/api/v1/admin/scan_network', type='json', auth='user',
                methods=['POST'])
    def scan_network(self, **kwargs):
        """Scan local subnets for GPU-capable machines (requires GPU Administrator group)."""
        if not request.env.user.has_group('gpu_admin_panel.group_gpu_administrator'):
            return {'error': 'Insufficient permissions.'}
        cluster_id = kwargs.get('cluster_id')
        cluster = request.env['gpu.cluster'].browse(cluster_id)
        discovered = cluster._scan_network_for_gpus()
        return {'discovered': discovered}

    @http.route('/api/v1/admin/install_node', type='json', auth='user',
                methods=['POST'])
    def install_node(self, **kwargs):
        """Trigger remote installation on a discovered machine."""
        if not request.env.user.has_group('gpu_admin_panel.group_gpu_administrator'):
            return {'error': 'Insufficient permissions.'}
        ip_address = kwargs.get('ip_address')
        pool = kwargs.get('pool', 'internal')
        cluster_id = kwargs.get('cluster_id')
        cluster = request.env['gpu.cluster'].browse(cluster_id)
        result = cluster._install_agent_on_host(ip_address, pool)
        return result

    @http.route('/api/v1/admin/remove_node', type='json', auth='user',
                methods=['POST'])
    def remove_node(self, **kwargs):
        """Remove a GPU node (permanently)."""
        if not request.env.user.has_group('gpu_admin_panel.group_gpu_administrator'):
            return {'error': 'Insufficient permissions.'}
        node_id = kwargs.get('node_id')
        node = request.env['gpu.node'].browse(node_id)
        node.action_remove_node()
        return {'success': True}

    @http.route('/api/v1/clients/gpustack_token', type='json', auth='public',
                methods=['POST'], csrf=False)
    def refresh_gpustack_token(self, **kwargs):
        """Issue a fresh GPUStack worker token (agent refresh)."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'error': 'Missing or invalid Authorization header'}
        api_key = auth_header.split(' ')[1]
        key_obj = request.env['ai.gpu.api_key'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True),
        ], limit=1)
        if not key_obj:
            return {'error': 'Invalid API key'}
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', key_obj.partner_id.company_id.id),
        ], limit=1)
        if not cluster:
            return {'error': 'No cluster found'}
        new_token = cluster._generate_gpustack_token()
        return {'gpustack_token': new_token}

    # -------------------------------------------------------------------------
    # Fine-tuning endpoints
    # -------------------------------------------------------------------------
    @http.route('/api/v1/admin/finetune/start', type='json', auth='user',
                methods=['POST'])
    def start_finetune(self, **kwargs):
        """Launch a fine-tuning job on the company's trusted GPU cluster."""
        if not request.env.user.has_group('gpu_admin_panel.group_gpu_administrator'):
            return {'error': 'Insufficient permissions.'}
        cluster_id = kwargs.get('cluster_id')
        dataset_id = kwargs.get('dataset_id')
        base_model = kwargs.get('base_model', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-14B')
        mode = kwargs.get('mode', 'multi')
        gpu_node_ids = kwargs.get('gpu_ids', [])

        cluster = request.env['gpu.cluster'].browse(cluster_id)
        if not cluster or cluster.trust_mode not in ('company_multi_gpu', 'company_single_gpu'):
            return {'error': 'Fine-tuning requires a trusted internal cluster.'}
        if not gpu_node_ids:
            return {'error': 'No GPUs selected for training.'}

        job = request.env['ft.training.job'].create({
            'dataset_id': dataset_id,
            'field_id': request.env['ft.dataset'].browse(dataset_id).field_id.id,
            'provider': mode == 'multi' and 'axolotl' or 'unsloth',
            'base_model': base_model,
            'status': 'pending',
        })

        webhook_url = request.env['ir.config_parameter'].sudo().get_param(
            'n8n_finetune_webhook', 'https://n8n.nettrades.ai/webhook/fine-tuning-trigger')
        try:
            import requests
            resp = requests.post(webhook_url, json={
                'job_id': job.id,
                'dataset_id': dataset_id,
                'base_model': base_model,
                'mode': mode,
                'gpu_ids': gpu_node_ids,
            }, timeout=10)
            resp.raise_for_status()
            job.status = 'running'
            return {'job_id': job.id, 'status': 'running'}
        except Exception as e:
            _logger.error("Failed to start fine-tuning: %s", e)
            job.status = 'failed'
            job.error_message = str(e)
            return {'error': str(e)}

    @http.route('/api/v1/admin/finetune/status/<int:job_id>', type='json',
                auth='user', methods=['GET'])
    def finetune_status(self, job_id):
        """Poll the status of a fine-tuning job."""
        job = request.env['ft.training.job'].browse(job_id)
        return {
            'id': job.id,
            'status': job.status,
            'base_model': job.base_model,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message,
        }

    @http.route('/api/v1/admin/finetune/deploy', type='json', auth='user',
                methods=['POST'])
    def deploy_finetuned_model(self, **kwargs):
        """Register a completed fine-tuned model as an Odoo llm.provider."""
        job_id = kwargs.get('job_id')
        job = request.env['ft.training.job'].browse(job_id)
        if job.status != 'completed':
            return {'error': 'Training job is not completed.'}

        provider = request.env['llm.provider'].create({
            'name': f"Field {job.field_id.name} Fine-tuned",
            'provider_type': 'openai_compatible',
            'api_base': "http://gpustack-company.gpustack.svc.cluster.local/v1-openai",
            'model_name': job.fine_tuned_model_id or job.base_model,
            'is_enabled': True,
        })
        job.field_id.write({'default_llm_provider_id': provider.id})
        return {'provider_id': provider.id, 'model_name': provider.model_name}