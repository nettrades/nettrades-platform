from odoo import http
from odoo.http import request

class GPUStackController(http.Controller):
    @http.route('/api/v1/gpustack/workers', type='json', auth='public', methods=['GET'], csrf=False)
    def get_workers(self):
        # Proxy to GPUStack server (simplified)
        cluster = request.env['gpu.cluster'].sudo().search([], limit=1)
        if not cluster:
            return []
        import requests
        url = cluster.gpustack_server_url + '/api/workers'
        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        resp = requests.get(url, headers=headers)
        return resp.json()