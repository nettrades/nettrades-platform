import requests
import logging
import time
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class GPUStackSync(models.AbstractModel):
    _name = 'gpustack.sync'
    _description = 'GPUStack Adapter for training and inference'

    # =========================================================================
    # 1. Existing Methods (Preserved)
    # =========================================================================

    def _call_gpustack_api(self, url, headers, method='GET', json=None,
                           timeout=10, retries=3):
        """
        Make a GPUStack API call with retry on transient errors.

        This method is preserved from the original implementation.
        """
        last_exc = None
        for attempt in range(retries):
            try:
                if method == 'GET':
                    resp = requests.get(url, headers=headers, timeout=timeout)
                elif method == 'POST':
                    resp = requests.post(url, headers=headers, json=json,
                                         timeout=timeout)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                resp.raise_for_status()
                return resp.json()
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                _logger.warning("GPUStack API call %s attempt %d failed: %s",
                                url, attempt + 1, e)
                time.sleep(2 ** attempt)
            except requests.HTTPError as e:
                _logger.error("GPUStack API returned HTTP error: %s", e)
                raise
        raise last_exc

    def _generate_gpustack_token(self, cluster):
        """
        Obtain a short-lived JWT token for registering a new worker.
        """
        url = f"{cluster.gpustack_server_url}/api/v2/registration-tokens"
        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        payload = {'name': 'worker-token', 'expires_in': 3600}

        try:
            data = self._call_gpustack_api(url, headers, method='POST',
                                           json=payload)
            return data.get('token')
        except Exception as e:
            _logger.error(f"Failed to generate GPUStack token: {e}")
            return None

    def sync_token_usage(self):
        """
        Fetch per-worker token usage from GPUStack v2 and update Odoo node records.
        """
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
                node = self.env['gpu.node'].search([
                    ('cluster_id', '=', cluster.id),
                    ('gpustack_worker_id', '=', worker_id),
                ], limit=1)

                if node:
                    node.tokens_served += tokens
                    rate = self.env['gpu.token.economics'].search([
                        ('company_id', '=', cluster.company_id.id),
                    ], limit=1).earn_rate_per_1k_tokens or 0.015
                    node.token_earnings += tokens * rate / 1000.0

    # =========================================================================
    # 2. NEW METHODS FOR TRAINING
    # =========================================================================

    def submit_training_job(self, job_id, dataset_path, base_model,
                            mode='single', gpu_ids=None, hyperparameters=None):
        """
        Submit a fine-tuning job to GPUStack.

        This method is called by the fine-tuning endpoint.

        Args:
            job_id (int): The Odoo training job ID
            dataset_path (str): Path to the training dataset
            base_model (str): Base model to fine-tune
            mode (str): 'single' or 'multi'
            gpu_ids (list): Optional list of GPU node IDs
            hyperparameters (dict): Training hyperparameters

        Returns:
            dict: Result with 'success' and 'model_id' or 'error'
        """
        _logger.info(f"Submitting training job {job_id} with base_model {base_model}")

        # Get the cluster
        cluster = self.env['gpu.cluster'].sudo().search([
            ('company_id', '=', self.env.user.company_id.id),
        ], limit=1)

        if not cluster:
            return {'success': False, 'error': 'No GPU cluster found'}

        # Build the training request
        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        url = f"{cluster.gpustack_server_url}/api/v2/training-jobs"

        payload = {
            'name': f"job_{job_id}",
            'base_model': base_model,
            'dataset_path': dataset_path,
            'mode': mode,
            'hyperparameters': hyperparameters or {},
        }

        if gpu_ids:
            payload['gpu_ids'] = gpu_ids

        try:
            data = self._call_gpustack_api(url, headers, method='POST',
                                           json=payload, timeout=60, retries=5)
            model_id = data.get('model_id')
            _logger.info(f"Training job {job_id} submitted, model_id: {model_id}")
            return {
                'success': True,
                'model_id': model_id,
                'job_id': data.get('job_id'),
            }
        except Exception as e:
            _logger.error(f"Failed to submit training job {job_id}: {e}")
            return {'success': False, 'error': str(e)}

    def deploy_model(self, job_id, model_id):
        """
        Deploy a fine-tuned model to GPUStack.

        Args:
            job_id (int): The Odoo training job ID
            model_id (str): The model ID to deploy

        Returns:
            dict: Result with 'success' and 'deployment_id' or 'error'
        """
        _logger.info(f"Deploying model {model_id} from job {job_id}")

        # Get the cluster
        cluster = self.env['gpu.cluster'].sudo().search([
            ('company_id', '=', self.env.user.company_id.id),
        ], limit=1)

        if not cluster:
            return {'success': False, 'error': 'No GPU cluster found'}

        # Build the deployment request
        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        url = f"{cluster.gpustack_server_url}/api/v2/models/{model_id}/deploy"

        try:
            data = self._call_gpustack_api(url, headers, method='POST',
                                           timeout=120, retries=5)
            deployment_id = data.get('deployment_id')
            _logger.info(f"Model {model_id} deployed, deployment_id: {deployment_id}")
            return {
                'success': True,
                'deployment_id': deployment_id,
            }
        except Exception as e:
            _logger.error(f"Failed to deploy model {model_id}: {e}")
            return {'success': False, 'error': str(e)}

    def get_training_status(self, job_id):
        """
        Get the status of a training job from GPUStack.

        Args:
            job_id (int): The Odoo training job ID

        Returns:
            dict: Status information
        """
        cluster = self.env['gpu.cluster'].sudo().search([
            ('company_id', '=', self.env.user.company_id.id),
        ], limit=1)

        if not cluster:
            return {'error': 'No GPU cluster found'}

        headers = {'Authorization': f'Bearer {cluster.gpustack_api_key}'}
        url = f"{cluster.gpustack_server_url}/api/v2/training-jobs/{job_id}"

        try:
            data = self._call_gpustack_api(url, headers, method='GET')
            return {
                'success': True,
                'status': data.get('status'),
                'progress': data.get('progress', 0),
                'metrics': data.get('metrics', {}),
            }
        except Exception as e:
            _logger.error(f"Failed to get training status for job {job_id}: {e}")
            return {'success': False, 'error': str(e)}