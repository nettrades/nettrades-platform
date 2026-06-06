import requests
import logging
import time
from odoo import models

_logger = logging.getLogger(__name__)

class GPUStackSync(models.AbstractModel):
    _name = 'gpustack.sync'

    def _call_gpustack_api(self, url, headers, method='GET', json=None, timeout=10, retries=3):
        """Make a GPUStack API call with retry on transient errors."""
        last_exc = None
        for attempt in range(retries):
            try:
                if method == 'GET':
                    resp = requests.get(url, headers=headers, timeout=timeout)
                elif method == 'POST':
                    resp = requests.post(url, headers=headers, json=json, timeout=timeout)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _logger.warning("GPUStack API call %s attempt %d failed: %s", url, attempt+1, e)
                time.sleep(2 ** attempt)
            except requests.HTTPError as e:
                _logger.error("GPUStack API returned HTTP error: %s", e)
                raise
        raise last_exc

    def _generate_gpustack_token(self, cluster):
        """Obtain a short-lived JWT token for registering a new worker."""
        url = f"{cluster.gpustack_server_url}/api/v2/registration-tokens"
        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        payload = {'name': 'worker-token', 'expires_in': 3600}
        try:
            data = self._call_gpustack_api(url, headers, method='POST', json=payload)
            return data.get('token')
        except Exception as e:
            _logger.error(f"Failed to generate GPUStack token: {e}")
            return None

    def sync_token_usage(self):
        """Fetch per-worker token usage from GPUStack v2 and update Odoo node records."""
        clusters = self.env['gpu.cluster'].search([])
        for cluster in clusters:
            if not cluster.gpustack_server_url or not cluster.gpustack_api_key:
                continue
            headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
            # First, get list of workers from GPUStack
            workers_url = f"{cluster.gpustack_server_url}/api/v2/workers"
            try:
                workers = self._call_gpustack_api(workers_url, headers)
            except Exception as e:
                _logger.warning(f"Failed to fetch workers for {cluster.name}: {e}")
                continue
            # Then, for each worker, fetch its usage
            for worker in workers:
                worker_id = worker.get('id')
                if not worker_id:
                    continue
                usage_url = f"{cluster.gpustack_server_url}/api/v2/workers/{worker_id}/usage"
                try:
                    usage_data = self._call_gpustack_api(usage_url, headers)
                    tokens = usage_data.get('tokens', 0)
                except Exception as e:
                    _logger.warning(f"Failed to fetch usage for worker {worker_id}: {e}")
                    tokens = 0

                if tokens <= 0:
                    continue
                # Find matching Odoo node by GPUStack worker ID
                node = self.env['gpu.node'].search(
                    [('cluster_id', '=', cluster.id), ('gpustack_worker_id', '=', worker_id)],
                    limit=1
                )
                if node:
                    node.tokens_served += tokens
                    rate = self.env['gpu.token.economics'].search(
                        [('company_id', '=', cluster.company_id.id)], limit=1
                    ).earn_rate_per_1k_tokens or 0.015
                    node.token_earnings += tokens * rate / 1000.0