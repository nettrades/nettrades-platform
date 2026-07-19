# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge - WireGuard Management
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/wireguard.py
#
# PURPOSE:
#   This module provides Odoo integration for WireGuard peer management.
#   It allows administrators to manage WireGuard clients directly from the
#   Odoo interface, without needing to use the command line.
#
#   The module calls the wireguard-manager.sh script (installed at
#   /usr/local/bin/wireguard-manager.sh) to perform actual WireGuard
#   operations. This ensures consistency between CLI and Odoo management.
#
# INTEGRATION POINTS:
#   - Server actions: Add/remove peers from Odoo workflows
#   - Cron jobs: Automated peer cleanup and health checks
#   - API endpoints: Expose WireGuard management via Odoo's REST API
#   - Dashboard widgets: Show WireGuard status in Odoo dashboards
#
# USAGE:
#   In Odoo, navigate to Settings → Technical → Server Actions to create
#   actions that call these methods. Or use them directly in Python code:
#
#       wireguard = env['nettrades.wireguard']
#       wireguard.add_peer('laptop', '10.10.10.50')
#       wireguard.list_peers()
#       wireguard.remove_peer('laptop')
#
# DEPENDENCIES:
#   - subprocess (Python standard library)
#   - wireguard-manager.sh must be installed at /usr/local/bin/
# =============================================================================

import subprocess
import logging
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class NettradesWireGuard(models.Model):
    """
    Odoo model for managing WireGuard peers.
    This model provides a clean API for WireGuard management.
    """
    _name = 'nettrades.wireguard'
    _description = 'NETTRADES WireGuard Manager'
    _rec_name = 'client_name'

    # -------------------------------------------------------------------------
    # Model Fields
    # -------------------------------------------------------------------------

    client_name = fields.Char(
        string='Client Name',
        required=True,
        help='Unique identifier for the WireGuard client (e.g., laptop, server-01)'
    )

    client_ip = fields.Char(
        string='Client IP',
        help='IP address assigned to the client (e.g., 10.10.10.50). '
             'Leave empty for automatic allocation.'
    )

    public_key = fields.Char(
        string='Public Key',
        readonly=True,
        help='WireGuard public key (generated automatically)'
    )

    private_key = fields.Char(
        string='Private Key',
        readonly=True,
        help='WireGuard private key (generated automatically)'
    )

    status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('pending', 'Pending'),
        ],
        string='Status',
        default='pending',
        help='Current status of the WireGuard peer'
    )

    created_at = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True
    )

    last_used = fields.Datetime(
        string='Last Used',
        readonly=True,
        help='Timestamp of the last handshake'
    )

    transfer_rx = fields.Integer(
        string='Received (MB)',
        readonly=True,
        help='Data received in MB'
    )

    transfer_tx = fields.Integer(
        string='Sent (MB)',
        readonly=True,
        help='Data sent in MB'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, the peer is disabled but not removed'
    )

    # -------------------------------------------------------------------------
    # Internal Methods
    # -------------------------------------------------------------------------

    def _run_wireguard_command(self, *args):
        """
        Execute the wireguard-manager.sh script with the given arguments.

        Args:
            *args: Command-line arguments to pass to the script.

        Returns:
            tuple: (return_code, stdout, stderr)

        Raises:
            UserError: If the script is not found or execution fails.
        """
        script_path = '/usr/local/bin/wireguard-manager.sh'

        # Check if the script exists
        import os
        if not os.path.exists(script_path):
            raise UserError(_(
                'WireGuard manager script not found at %s.\n'
                'Please ensure wireguard-manager.sh is installed in /usr/local/bin/'
            ) % script_path)

        # Build the command
        cmd = [script_path] + list(args)

        try:
            _logger.info('Running WireGuard command: %s', ' '.join(cmd))
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False
            )
            _logger.info('WireGuard command completed with exit code: %s', result.returncode)

            if result.stdout:
                _logger.debug('WireGuard stdout: %s', result.stdout)
            if result.stderr:
                _logger.warning('WireGuard stderr: %s', result.stderr)

            return result.returncode, result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            _logger.error('WireGuard command timed out: %s', ' '.join(cmd))
            raise UserError(_('WireGuard command timed out after 60 seconds.'))
        except Exception as e:
            _logger.error('WireGuard command failed: %s', str(e))
            raise UserError(_('Failed to execute WireGuard command: %s') % str(e))

    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------

    def add_peer(self, client_name, client_ip=None):
        """
        Add a new WireGuard peer.

        Args:
            client_name (str): Unique name for the client.
            client_ip (str, optional): IP address to assign. If None, auto-allocate.

        Returns:
            dict: Information about the created peer.

        Raises:
            UserError: If the peer already exists or the command fails.
        """
        _logger.info('Adding WireGuard peer: %s (IP: %s)', client_name, client_ip or 'auto')

        # Validate client name
        if not client_name or not client_name.strip():
            raise ValidationError(_('Client name cannot be empty.'))

        # Check if peer already exists
        existing = self.search([('client_name', '=', client_name)])
        if existing:
            raise UserError(_('Peer "%s" already exists.') % client_name)

        # Build command arguments
        args = ['add', client_name]
        if client_ip:
            args.append(client_ip)

        # Execute the command
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to add WireGuard peer: %s') % stderr or stdout)

        # Parse the output to extract the public key and IP
        public_key = None
        assigned_ip = None
        for line in stdout.split('\n'):
            if 'Public key:' in line:
                public_key = line.split('Public key:')[-1].strip()
            if 'added with IP' in line:
                assigned_ip = line.split('IP')[-1].strip()

        # Create the Odoo record
        peer = self.create({
            'client_name': client_name,
            'client_ip': assigned_ip or client_ip,
            'public_key': public_key,
            'status': 'active',
        })

        _logger.info('WireGuard peer created: %s (ID: %s)', client_name, peer.id)

        return {
            'id': peer.id,
            'client_name': client_name,
            'client_ip': assigned_ip or client_ip,
            'public_key': public_key,
        }

    def remove_peer(self, client_name):
        """
        Remove a WireGuard peer.

        Args:
            client_name (str): Name of the client to remove.

        Raises:
            UserError: If the peer does not exist or the command fails.
        """
        _logger.info('Removing WireGuard peer: %s', client_name)

        # Find the peer in Odoo
        peer = self.search([('client_name', '=', client_name)], limit=1)
        if not peer:
            raise UserError(_('Peer "%s" not found.') % client_name)

        # Execute the command
        args = ['remove', client_name]
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to remove WireGuard peer: %s') % stderr or stdout)

        # Delete the Odoo record
        peer.unlink()

        _logger.info('WireGuard peer removed: %s', client_name)

    def list_peers(self):
        """
        List all WireGuard peers.

        Returns:
            list: List of peer dictionaries with name, ip, public_key, status.

        Raises:
            UserError: If the command fails.
        """
        _logger.info('Listing WireGuard peers')

        args = ['list']
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to list WireGuard peers: %s') % stderr or stdout)

        # Parse the output
        peers = []
        lines = stdout.split('\n')
        for line in lines:
            # Look for lines like: "name | ip | public_key | status"
            if '|' in line and not line.startswith('---'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    peers.append({
                        'name': parts[0],
                        'ip': parts[1],
                        'public_key': parts[2],
                        'status': parts[3],
                    })

        return peers

    def generate_client_config(self, client_name):
        """
        Generate a WireGuard client configuration file.

        Args:
            client_name (str): Name of the client.

        Returns:
            str: Path to the generated configuration file.

        Raises:
            UserError: If the peer does not exist or the command fails.
        """
        _logger.info('Generating WireGuard client config: %s', client_name)

        # Check if the peer exists
        peer = self.search([('client_name', '=', client_name)], limit=1)
        if not peer:
            raise UserError(_('Peer "%s" not found.') % client_name)

        args = ['generate', client_name]
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to generate client config: %s') % stderr or stdout)

        config_path = '/root/wireguard-clients/%s.conf' % client_name
        _logger.info('Client config generated: %s', config_path)

        return config_path

    def generate_qr(self, client_name):
        """
        Generate a QR code for a WireGuard client (mobile app).

        Args:
            client_name (str): Name of the client.

        Returns:
            str: Path to the generated QR code image.

        Raises:
            UserError: If the peer does not exist or qrencode is not installed.
        """
        _logger.info('Generating WireGuard QR code: %s', client_name)

        peer = self.search([('client_name', '=', client_name)], limit=1)
        if not peer:
            raise UserError(_('Peer "%s" not found.') % client_name)

        args = ['qr', client_name]
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to generate QR code: %s') % stderr or stdout)

        qr_path = '/root/wireguard-clients/%s.png' % client_name
        _logger.info('QR code generated: %s', qr_path)

        return qr_path

    def backup_configs(self):
        """
        Create a backup of all WireGuard configurations.

        Returns:
            str: Path to the backup file.

        Raises:
            UserError: If the backup fails.
        """
        _logger.info('Creating WireGuard backup')

        args = ['backup']
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to create WireGuard backup: %s') % stderr or stdout)

        # Extract the backup file path from the output
        backup_path = None
        for line in stdout.split('\n'):
            if 'Backup created:' in line:
                backup_path = line.split('Backup created:')[-1].strip()

        _logger.info('WireGuard backup created: %s', backup_path)

        return backup_path

    def get_status(self):
        """
        Get the current WireGuard status.

        Returns:
            dict: Status information including interface, port, subnet, peers.

        Raises:
            UserError: If the command fails.
        """
        _logger.info('Getting WireGuard status')

        args = ['status']
        returncode, stdout, stderr = self._run_wireguard_command(*args)

        if returncode != 0:
            raise UserError(_('Failed to get WireGuard status: %s') % stderr or stdout)

        # Parse the output
        status = {
            'interface': 'wg0',
            'port': 51821,
            'subnet': '10.10.10.0/24',
            'peers': 0,
            'active_peers': 0,
        }

        for line in stdout.split('\n'):
            if 'Interface:' in line:
                status['interface'] = line.split('Interface:')[-1].strip()
            if 'Port:' in line:
                status['port'] = int(line.split('Port:')[-1].strip())
            if 'Subnet:' in line:
                status['subnet'] = line.split('Subnet:')[-1].strip()
            if 'Peers:' in line:
                status['peers'] = int(line.split('Peers:')[-1].strip())

        return status

    # -------------------------------------------------------------------------
    # Server Action Methods
    # -------------------------------------------------------------------------

    @api.model
    def action_add_peer(self):
        """
        Server action: Add a WireGuard peer from a form view.
        This method is called from Odoo's server actions.
        """
        context = self.env.context
        client_name = context.get('default_client_name')
        client_ip = context.get('default_client_ip')

        if not client_name:
            raise UserError(_('Client name is required.'))

        return self.add_peer(client_name, client_ip)

    @api.model
    def action_remove_peer(self):
        """
        Server action: Remove a WireGuard peer from a form view.
        """
        context = self.env.context
        client_name = context.get('active_client_name')

        if not client_name:
            raise UserError(_('Client name is required.'))

        return self.remove_peer(client_name)

    @api.model
    def action_generate_config(self):
        """
        Server action: Generate a client configuration file.
        """
        context = self.env.context
        client_name = context.get('active_client_name')

        if not client_name:
            raise UserError(_('Client name is required.'))

        return self.generate_client_config(client_name)

    # -------------------------------------------------------------------------
    # Cron Job Methods
    # -------------------------------------------------------------------------

    @api.model
    def cron_sync_peers(self):
        """
        Cron job: Synchronise Odoo peer records with the WireGuard server.
        This runs periodically to keep Odoo and the WireGuard server in sync.
        """
        _logger.info('Syncing WireGuard peers')

        # Get the current list from the server
        server_peers = self.list_peers()
        server_names = [p['name'] for p in server_peers]

        # Get the current list from Odoo
        odoo_peers = self.search([])
        odoo_names = [p.client_name for p in odoo_peers]

        # Add peers that exist on the server but not in Odoo
        for name in server_names:
            if name not in odoo_names:
                # Find the peer data
                peer_data = next((p for p in server_peers if p['name'] == name), None)
                if peer_data:
                    self.create({
                        'client_name': name,
                        'client_ip': peer_data.get('ip'),
                        'public_key': peer_data.get('public_key'),
                        'status': 'active' if peer_data.get('status') == 'active' else 'inactive',
                    })
                    _logger.info('Added missing peer to Odoo: %s', name)

        # Remove peers that exist in Odoo but not on the server
        for peer in odoo_peers:
            if peer.client_name not in server_names:
                peer.unlink()
                _logger.info('Removed stale peer from Odoo: %s', peer.client_name)

        _logger.info('WireGuard sync completed')

    # -------------------------------------------------------------------------
    # View Methods (for Odoo UI)
    # -------------------------------------------------------------------------

    def action_view_status(self):
        """
        Action: Open the WireGuard status dashboard.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'WireGuard Status',
            'res_model': 'nettrades.wireguard.status',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    def action_view_peers(self):
        """
        Action: Open the WireGuard peers list.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'WireGuard Peers',
            'res_model': 'nettrades.wireguard',
            'view_mode': 'tree,form',
            'target': 'current',
        }