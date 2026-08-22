# =============================================================================
# FILE: odoo-modules/nettrades_core/controllers/secrets.py
# PURPOSE: REST API for secrets management
# =============================================================================

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
import json
import logging

_logger = logging.getLogger(__name__)

class SecretsController(http.Controller):
    
    @http.route('/api/secrets/list', type='http', auth='user', methods=['GET'], csrf=False)
    def list_secrets(self, categories=None):
        """List available secrets (metadata only, encrypted values hidden)"""
        if not request.env.user.has_group('nettrades_core.group_secrets_manager'):
            return request.make_response(
                json.dumps({'error': 'Access denied. Secrets Manager role required.'}),
                status=403,
                headers={'Content-Type': 'application/json'}
            )
        
        secret_model = request.env['nettrades.secrets']
        category_list = categories.split(',') if categories else None
        secrets = secret_model.get_all_secrets(categories=category_list)
        
        return request.make_response(
            json.dumps({'success': True, 'secrets': secrets}),
            headers={'Content-Type': 'application/json'}
        )
    
    @http.route('/api/secrets/<string:key>', type='http', auth='user', methods=['GET'], csrf=False)
    def get_secret(self, key):
        """Get a specific secret's value (decrypted)"""
        try:
            secret_model = request.env['nettrades.secrets']
            value = secret_model.get_secret(key, decrypt=True)
            if value is None:
                return request.make_response(
                    json.dumps({'error': f'Secret {key} not found'}),
                    status=404,
                    headers={'Content-Type': 'application/json'}
                )
            
            # Log access
            request.env['nettrades.secrets.audit'].create({
                'secret_key': key,
                'action': 'view',
                'performed_by': request.env.user.id,
                'ip_address': request.httprequest.remote_addr,
                'user_agent': request.httprequest.user_agent.string
            })
            
            return request.make_response(
                json.dumps({'success': True, 'key': key, 'value': value}),
                headers={'Content-Type': 'application/json'}
            )
        except AccessError as e:
            return request.make_response(
                json.dumps({'error': str(e)}),
                status=403,
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            _logger.error(f'Error getting secret {key}: {str(e)}')
            return request.make_response(
                json.dumps({'error': 'Internal server error'}),
                status=500,
                headers={'Content-Type': 'application/json'}
            )
    
    @http.route('/api/secrets', type='http', auth='user', methods=['POST'], csrf=False)
    def set_secret(self):
        """Set a secret (create or update)"""
        if not request.env.user.has_group('nettrades_core.group_secrets_manager'):
            return request.make_response(
                json.dumps({'error': 'Access denied. Secrets Manager role required.'}),
                status=403,
                headers={'Content-Type': 'application/json'}
            )
        
        try:
            data = json.loads(request.httprequest.data)
            key = data.get('key')
            value = data.get('value')
            description = data.get('description', '')
            category = data.get('category', 'other')
            visible_to = data.get('visible_to', 'secrets_manager')
            
            if not key or value is None:
                return request.make_response(
                    json.dumps({'error': 'Key and value required'}),
                    status=400,
                    headers={'Content-Type': 'application/json'}
                )
            
            secret_model = request.env['nettrades.secrets']
            record = secret_model.set_secret(
                key=key,
                value=value,
                description=description,
                category=category,
                visible_to=visible_to
            )
            
            # Also update .env file for runtime
            self._sync_to_env(key, value)
            
            return request.make_response(
                json.dumps({'success': True, 'id': record.id}),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            _logger.error(f'Error setting secret: {str(e)}')
            return request.make_response(
                json.dumps({'error': str(e)}),
                status=500,
                headers={'Content-Type': 'application/json'}
            )
    
    @http.route('/api/secrets/<string:key>/rotate', type='http', auth='user', methods=['POST'], csrf=False)
    def rotate_secret(self, key):
        """Rotate a secret to a new value"""
        if not request.env.user.has_group('nettrades_core.group_secrets_manager'):
            return request.make_response(
                json.dumps({'error': 'Access denied. Secrets Manager role required.'}),
                status=403,
                headers={'Content-Type': 'application/json'}
            )
        
        try:
            data = json.loads(request.httprequest.data)
            new_value = data.get('value')
            
            if not new_value:
                return request.make_response(
                    json.dumps({'error': 'New value required'}),
                    status=400,
                    headers={'Content-Type': 'application/json'}
                )
            
            secret_model = request.env['nettrades.secrets']
            record = secret_model.search([('key', '=', key)], limit=1)
            if not record:
                return request.make_response(
                    json.dumps({'error': f'Secret {key} not found'}),
                    status=404,
                    headers={'Content-Type': 'application/json'}
                )
            
            record.rotate_secret(new_value)
            
            # Update .env file
            self._sync_to_env(key, new_value)
            
            return request.make_response(
                json.dumps({'success': True}),
                headers={'Content-Type': 'application/json'}
            )
        except Exception as e:
            _logger.error(f'Error rotating secret {key}: {str(e)}')
            return request.make_response(
                json.dumps({'error': str(e)}),
                status=500,
                headers={'Content-Type': 'application/json'}
            )
    
    def _sync_to_env(self, key, value):
        """Update .env file with new secret value"""
        import os
        env_path = os.path.join(os.environ.get('PROJECT_ROOT', '.'), 'deploy/docker/.env')
        
        if not os.path.exists(env_path):
            _logger.warning(f'.env file not found at {env_path}')
            return
        
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        found = False
        with open(env_path, 'w') as f:
            for line in lines:
                if line.startswith(f'{key}='):
                    f.write(f"{key}='{value}'\n")
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write(f"{key}='{value}'\n")
        
        _logger.info(f'Synced secret {key} to .env file')