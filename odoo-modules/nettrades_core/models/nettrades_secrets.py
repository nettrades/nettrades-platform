# odoo-modules/nettrades_core/models/nettrades_secrets.py
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_secrets.py
# PURPOSE: Encrypted secret storage for NETTRADES platform
# =============================================================================

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class NettradesSecrets(models.Model):
    _name = 'nettrades.secrets'
    _description = 'NETTRADES Encrypted Secrets'
    _log_access = True
    _order = 'key asc'

    key = fields.Char(
        string='Secret Key',
        required=True,
        index=True,
        help='Unique identifier for the secret (e.g., POSTGRES_PASSWORD)'
    )
    
    value_encrypted = fields.Binary(
        string='Encrypted Value',
        required=True,
        help='Value encrypted with pgcrypto using the master key'
    )
    
    description = fields.Char(
        string='Description',
        help='Human-readable description of what this secret is used for'
    )
    
    category = fields.Selection([
        ('database', 'Database'),
        ('api', 'API Key'),
        ('wireguard', 'WireGuard VPN'),
        ('admin', 'Admin Credentials'),
        ('ssh', 'SSH Key'),
        ('jwt', 'JWT Secret'),
        ('odoo', 'Odoo Credentials'),
        ('other', 'Other')
    ], string='Category', default='other', required=True)
    
    visible_to = fields.Selection([
        ('admin', 'Administrators Only'),
        ('secrets_manager', 'Secrets Managers'),
        ('gpu_admin', 'GPU Administrators'),
        ('all', 'All Authenticated Users')
    ], string='Visibility', default='secrets_manager', required=True)
    
    version = fields.Integer(string='Version', default=1, readonly=True)
    
    expires_at = fields.Datetime(
        string='Expires At',
        help='Optional expiration date for the secret'
    )
    
    created_by = fields.Many2one(
        'res.users',
        string='Created By',
        default=lambda self: self.env.user
    )
    
    created_at = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True
    )
    
    updated_at = fields.Datetime(
        string='Updated At',
        default=fields.Datetime.now,
        readonly=True
    )
    
    # Security constraints
    _sql_constraints = [
        ('unique_key', 'unique(key)', 'A secret with this key already exists!')
    ]
    
    @api.model
    def get_master_key(self):
        """Get the master encryption key from environment or Odoo config"""
        master_key = self.env['ir.config_parameter'].sudo().get_param(
            'nettrades.secrets.master_key'
        )
        if not master_key:
            # Generate master key if not exists
            import secrets
            master_key = secrets.token_hex(32)
            self.env['ir.config_parameter'].sudo().set_param(
                'nettrades.secrets.master_key', master_key
            )
            _logger.warning('Master key generated and stored in Odoo config')
        return master_key
    
    def _encrypt_value(self, value):
        """Encrypt a value using pgcrypto"""
        master_key = self.get_master_key()
        self.env.cr.execute(
            "SELECT pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256')",
            (value, master_key)
        )
        return self.env.cr.fetchone()[0]
    
    def _decrypt_value(self, encrypted_value):
        """Decrypt a value using pgcrypto"""
        master_key = self.get_master_key()
        self.env.cr.execute(
            "SELECT pgp_sym_decrypt(%s, %s)",
            (encrypted_value, master_key)
        )
        result = self.env.cr.fetchone()
        return result[0] if result else None
    
    @api.model
    def set_secret(self, key, value, description='', category='other', visible_to='secrets_manager'):
        """Set a secret (create or update)"""
        # Security check: only secrets managers can set secrets
        if not self.env.user.has_group('nettrades_core.group_secrets_manager'):
            raise AccessError(_('You do not have permission to set secrets'))
        
        # Validate key format (alphanumeric + underscore)
        import re
        if not re.match(r'^[A-Za-z0-9_]+$', key):
            raise ValidationError(_('Key must contain only alphanumeric characters and underscores'))
        
        # Encrypt the value
        encrypted = self._encrypt_value(value)
        
        # Find existing or create new
        existing = self.search([('key', '=', key)], limit=1)
        if existing:
            existing.write({
                'value_encrypted': encrypted,
                'description': description,
                'category': category,
                'visible_to': visible_to,
                'version': existing.version + 1,
                'updated_at': fields.Datetime.now()
            })
            # Log the rotation
            self.env['nettrades.secrets.audit'].create({
                'secret_key': key,
                'action': 'update',
                'performed_by': self.env.user.id,
                'ip_address': self.env.context.get('ip_address', '127.0.0.1'),
            })
            _logger.info(f'Secret updated: {key} by user {self.env.user.login}')
            return existing
        else:
            record = self.create({
                'key': key,
                'value_encrypted': encrypted,
                'description': description,
                'category': category,
                'visible_to': visible_to,
                'created_by': self.env.user.id,
            })
            # Log the creation
            self.env['nettrades.secrets.audit'].create({
                'secret_key': key,
                'action': 'create',
                'performed_by': self.env.user.id,
                'ip_address': self.env.context.get('ip_address', '127.0.0.1'),
            })
            _logger.info(f'Secret created: {key} by user {self.env.user.login}')
            return record
    
    @api.model
    def get_secret(self, key, decrypt=True):
        """Get a secret by key (returns plaintext if decrypt=True)"""
        record = self.search([('key', '=', key)], limit=1)
        if not record:
            return None
        
        # Check visibility
        if not self._can_access_secret(record):
            raise AccessError(_('You do not have permission to access this secret'))
        
        # Log access
        self.env['nettrades.secrets.audit'].create({
            'secret_key': key,
            'action': 'view',
            'performed_by': self.env.user.id,
            'ip_address': self.env.context.get('ip_address', '127.0.0.1'),
        })
        
        if decrypt:
            return self._decrypt_value(record.value_encrypted)
        return record
    
    def _can_access_secret(self, record):
        """Check if current user can access a secret"""
        if self.env.user.has_group('nettrades_core.group_secrets_manager'):
            return True
        if self.env.user.has_group('base.group_system'):
            return True
        if record.visible_to == 'admin':
            return self.env.user.has_group('base.group_system')
        if record.visible_to == 'secrets_manager':
            return self.env.user.has_group('nettrades_core.group_secrets_manager')
        if record.visible_to == 'gpu_admin':
            return self.env.user.has_group('nettrades_core.group_gpu_admin')
        return True
    
    @api.model
    def sync_from_env(self):
        """Sync secrets from .env file to Odoo DB"""
        import os
        import configparser
        
        config = configparser.ConfigParser()
        env_path = os.path.join(os.environ.get('PROJECT_ROOT', '.'), 'deploy/docker/.env')
        
        if not os.path.exists(env_path):
            _logger.warning(f'.env file not found at {env_path}')
            return
        
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip("'")
                    # Skip empty or placeholder values
                    if value and value != 'changeit':
                        self.set_secret(
                            key=key,
                            value=value,
                            description=f'Synced from .env at {fields.Datetime.now()}',
                            category='other',
                            visible_to='secrets_manager'
                        )
        _logger.info('Secrets synced from .env to Odoo DB')
    
    def rotate_secret(self, new_value):
        """Rotate a secret to a new value"""
        self.ensure_one()
        self.set_secret(
            key=self.key,
            value=new_value,
            description=self.description,
            category=self.category,
            visible_to=self.visible_to
        )
        _logger.info(f'Secret rotated: {self.key}')
        return True
    
    @api.model
    def get_all_secrets(self, categories=None):
        """Get all secrets (encrypted) for UI display"""
        domain = []
        if categories:
            domain.append(('category', 'in', categories))
        records = self.search(domain)
        result = []
        for rec in records:
            if self._can_access_secret(rec):
                result.append({
                    'id': rec.id,
                    'key': rec.key,
                    'description': rec.description,
                    'category': rec.category,
                    'version': rec.version,
                    'created_at': rec.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': rec.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'visible_to': rec.visible_to,
                    'has_value': bool(rec.value_encrypted),
                })
        return result


class NettradesSecretsAudit(models.Model):
    _name = 'nettrades.secrets.audit'
    _description = 'NETTRADES Secrets Audit Log'
    _order = 'performed_at desc'
    _log_access = False

    secret_key = fields.Char(string='Secret Key', required=True)
    action = fields.Selection([
        ('view', 'View'),
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('rotate', 'Rotate'),
        ('sync', 'Sync from .env')
    ], string='Action', required=True)
    performed_by = fields.Many2one('res.users', string='Performed By')
    ip_address = fields.Char(string='IP Address', size=45)
    user_agent = fields.Char(string='User Agent')
    performed_at = fields.Datetime(string='Performed At', default=fields.Datetime.now)