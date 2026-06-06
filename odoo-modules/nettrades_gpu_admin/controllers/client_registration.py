from odoo import http
from odoo.http import request
from datetime import datetime, timedelta
import json, logging

_logger = logging.getLogger(__name__)

class ClientRegistrationController(http.Controller):

    @http.route('/api/v1/clients/register', type='json', auth='public',
                methods=['POST'], csrf=False)
    def register_client(self, **kwargs):
        # 1. Authenticate via Bearer token
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return {'error': 'Missing or invalid Authorization header'}

        api_key = auth_header.split(' ')[1]
        key_obj = request.env['ai.gpu.api_key'].sudo().search([
            ('api_key', '=', api_key),
            ('active', '=', True)
        ], limit=1)
        if not key_obj:
            return {'error': 'Invalid API key'}

        partner = key_obj.partner_id

        # 2. Record GPU node with hardware-bound node_id
        node_id = kwargs.get('node_id')
        gpus = kwargs.get('gpus', [])
        hostname = kwargs.get('hostname')
        wg_pubkey = kwargs.get('wireguard_public_key', '')

        node = request.env['ai.gpu.node'].sudo().search([
            ('node_id', '=', node_id)
        ], limit=1)

        if node:
            node.write({
                'gpus': gpus,
                'last_seen': fields.Datetime.now(),
                'status': 'active',
                'wireguard_public_key': wg_pubkey,
            })
        else:
            node = request.env['ai.gpu.node'].sudo().create({
                'partner_id': partner.id,
                'node_id': node_id,
                'hostname': hostname,
                'gpus': gpus,
                'status': 'active',
                'last_seen': fields.Datetime.now(),
                'wireguard_public_key': wg_pubkey,
            })

        # 3. Ensure token record exists
        token = request.env['ai.gpu.user_token'].sudo().search([
            ('partner_id', '=', partner.id)
        ], limit=1)
        if not token:
            config = request.env['ir.config_parameter'].sudo()
            default_tokens = int(config.get_param(
                'ai_gpu.default_free_tokens', '100000'
            ))
            request.env['ai.gpu.user_token'].sudo().create({
                'partner_id': partner.id,
                'free_tokens_remaining': default_tokens,
            })

        # 4. Generate one-time GPUStack join token (JWT, 10-minute expiry)
        cluster = request.env['gpu.cluster'].sudo().search([
            ('company_id', '=', partner.company_id.id)
        ], limit=1)
        gpustack_token = None
        if cluster:
            gpustack_token = cluster._generate_gpustack_token()

        # 5. Return WireGuard config + GPUStack token
        config = request.env['ir.config_parameter'].sudo()
        controller_ip = config.get_param('ai_gpu.controller_ip')
        bootstrap_port = config.get_param('ai_gpu.bootstrap_port', '51820')
        controller_pubkey = config.get_param('wireguard.controller_public_key', '')

        return {
            'mesh_config': {
                'controller': f"{controller_ip}:{bootstrap_port}",
                'controller_public_key': controller_pubkey,
                'assigned_ip': f"10.100.0.{(node.id % 200) + 10}/32",
            },
            'gpustack_token': gpustack_token,
            'gpustack_server_url': cluster.gpustack_server_url if cluster else '',
            'pool': 'public',
            'default_free_tokens': int(config.get_param(
                'ai_gpu.default_free_tokens', '100000'
            )),
        }