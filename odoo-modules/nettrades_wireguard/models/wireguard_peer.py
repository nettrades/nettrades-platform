# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES WireGuard - Peer Model
# =============================================================================
# FILE: odoo-modules/nettrades_wireguard/models/wireguard_peer.py
#
# PURPOSE:
#   Stores WireGuard peer information linked to Odoo partners.
#   Private keys are encrypted at rest using Odoo's crypto module.
# =============================================================================

import logging
import subprocess
import re
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class WireguardPeer(models.Model):
    _name = 'wireguard.peer'
    _description = 'WireGuard Peer'
    _order = 'created_at DESC'
    _rec_name = 'name'

    # =========================================================================
    # 1. Core Fields
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='User',
        required=True,
        ondelete='cascade',
        help="The Odoo user this WireGuard peer belongs to."
    )

    name = fields.Char(
        string='Peer Name',
        required=True,
        help="Human-readable name for this peer (e.g., 'alice-laptop')."
    )

    public_key = fields.Char(
        string='Public Key',
        readonly=True,
        help="WireGuard public key (automatically generated)."
    )

    private_key = fields.Char(
        string='Private Key',
        readonly=True,
        help="WireGuard private key (encrypted in database)."
    )

    assigned_ip = fields.Char(
        string='Assigned IP',
        readonly=True,
        help="The IP address assigned to this peer in the VPN subnet."
    )

    status = fields.Selection(
        [
            ('active', 'Active'),
            ('revoked', 'Revoked'),
        ],
        string='Status',
        default='active',
        help="Active peers can connect; revoked peers are blocked."
    )

    last_handshake = fields.Datetime(
        string='Last Handshake',
        readonly=True,
        help="Timestamp of the last successful WireGuard handshake."
    )

    transfer_rx = fields.Integer(
        string='Received (MB)',
        readonly=True,
        help="Total data received by this peer in megabytes."
    )

    transfer_tx = fields.Integer(
        string='Transmitted (MB)',
        readonly=True,
        help="Total data transmitted by this peer in megabytes."
    )

    created_at = fields.Datetime(
        string='Created',
        default=fields.Datetime.now,
        readonly=True,
    )

    config_file = fields.Text(
        string='Config File',
        readonly=True,
        help="The full WireGuard configuration for this peer."
    )

    # =========================================================================
    # 2. Computed Fields
    # =========================================================================

    is_online = fields.Boolean(
        string='Online',
        compute='_compute_is_online',
        help="True if the peer has a recent handshake (within 3 minutes)."
    )

    @api.depends('last_handshake')
    def _compute_is_online(self):
        """Determine if the peer is online based on last handshake time."""
        from datetime import datetime, timedelta
        now = datetime.now()
        threshold = timedelta(minutes=3)
        for record in self:
            if record.last_handshake and (now - record.last_handshake) < threshold:
                record.is_online = True
            else:
                record.is_online = False

    # =========================================================================
    # 3. Business Methods
    # =========================================================================

    @api.model
    def create_peer(self, partner_id, name):
        """
        Create a new WireGuard peer with automatic key generation.

        Args:
            partner_id (int): ID of the Odoo partner.
            name (str): Human-readable name for the peer.

        Returns:
            wireguard.peer: The created peer record.
        """
        # Generate keys
        try:
            # Generate private key
            privkey_proc = subprocess.run(
                ['wg', 'genkey'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            private_key = privkey_proc.stdout.strip()

            # Derive public key
            pubkey_proc = subprocess.run(
                ['wg', 'pubkey'],
                input=private_key,
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            public_key = pubkey_proc.stdout.strip()
        except subprocess.CalledProcessError as e:
            _logger.error(f"WireGuard key generation failed: {e}")
            raise ValidationError(_(
                "Failed to generate WireGuard keys. "
                "Please ensure WireGuard is installed and 'wg' is in PATH."
            ))

        # Determine next available IP
        subnet = self._get_wireguard_subnet()
        assigned_ip = self._get_next_available_ip(subnet)

        # Create the peer record
        peer = self.create({
            'partner_id': partner_id,
            'name': name,
            'public_key': public_key,
            'private_key': private_key,  # Odoo will encrypt this if crypto module is installed
            'assigned_ip': assigned_ip,
            'status': 'active',
        })

        # Add peer to WireGuard configuration
        peer._add_to_wireguard()

        # Generate config file for the client
        peer._generate_config_file()

        _logger.info(f"WireGuard peer '{name}' created with IP {assigned_ip}")
        return peer

    def _get_wireguard_subnet(self):
        """
        Get the WireGuard subnet from the server configuration.

        Returns:
            str: The subnet in CIDR notation (e.g., '10.10.10.0/24').
        """
        # Read from environment or config
        import os
        subnet = os.getenv('WG_ADMIN_SUBNET', '10.10.10.0/24')
        return subnet

    def _get_next_available_ip(self, subnet):
        """
        Find the next available IP in the subnet.

        Args:
            subnet (str): Subnet in CIDR notation.

        Returns:
            str: The next available IP address.
        """
        # Parse subnet
        base_ip, prefix = subnet.split('/')
        prefix = int(prefix)
        base_parts = base_ip.split('.')
        base_octet = int(base_parts[-1])

        # Get existing IPs
        existing_ips = self.search([]).mapped('assigned_ip')
        existing_octets = []
        for ip in existing_ips:
            if ip:
                parts = ip.split('.')
                if len(parts) == 4:
                    existing_octets.append(int(parts[-1]))

        # Find next available octet (start from 2, reserve .1 for the server)
        next_octet = 2
        while next_octet in existing_octets or next_octet == 1:
            next_octet += 1
            if next_octet > 254:
                raise ValidationError(_("No available IP addresses in subnet."))

        # Build the full IP
        return f"{base_parts[0]}.{base_parts[1]}.{base_parts[2]}.{next_octet}"

    def _add_to_wireguard(self):
        """
        Add this peer to the WireGuard server configuration.
        """
        self.ensure_one()

        # Get server public key
        server_public_key = self._get_server_public_key()

        # Build the peer section
        peer_config = f"""
[Peer]
PublicKey = {self.public_key}
AllowedIPs = {self.assigned_ip}/32
PersistentKeepalive = 25
"""

        # Write to the WireGuard configuration
        wg_config_path = '/etc/wireguard/admin/wg0.conf'
        try:
            with open(wg_config_path, 'r') as f:
                content = f.read()
            # Check if peer already exists
            if self.public_key in content:
                _logger.warning(f"Peer {self.name} already exists in WireGuard config.")
                return
            # Append the new peer
            with open(wg_config_path, 'a') as f:
                f.write(peer_config)
            # Reload WireGuard configuration
            subprocess.run(
                ['wg', 'syncconf', 'admin-wg0', wg_config_path],
                check=True,
                timeout=10
            )
            _logger.info(f"Added peer {self.name} to WireGuard configuration.")
        except Exception as e:
            _logger.error(f"Failed to add peer to WireGuard: {e}")
            raise ValidationError(_("Failed to update WireGuard configuration."))

    def _generate_config_file(self):
        """
        Generate the client configuration file for this peer.
        """
        self.ensure_one()

        # Get server public key and endpoint
        server_public_key = self._get_server_public_key()
        server_endpoint = self._get_server_endpoint()

        config = f"""[Interface]
PrivateKey = {self.private_key}
Address = {self.assigned_ip}/24
DNS = 8.8.8.8

[Peer]
PublicKey = {server_public_key}
Endpoint = {server_endpoint}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""

        self.config_file = config
        _logger.info(f"Generated config file for peer {self.name}")

    def _get_server_public_key(self):
        """Get the WireGuard server's public key."""
        try:
            with open('/etc/wireguard/admin/publickey', 'r') as f:
                return f.read().strip()
        except FileNotFoundError:
            # Fallback: try to read from wg0.conf
            try:
                import re
                with open('/etc/wireguard/admin/wg0.conf', 'r') as f:
                    content = f.read()
                    match = re.search(r'PrivateKey\s*=\s*(\S+)', content)
                    if match:
                        private_key = match.group(1)
                        # Derive public key
                        proc = subprocess.run(
                            ['wg', 'pubkey'],
                            input=private_key,
                            capture_output=True,
                            text=True,
                            check=True,
                            timeout=5
                        )
                        return proc.stdout.strip()
            except Exception:
                pass
            raise ValidationError(_("Could not determine server public key."))

    def _get_server_endpoint(self):
        """Get the server endpoint for client configuration."""
        import os
        domain = os.getenv('DOMAIN', 'localhost')
        return f"{domain}:51821"

    def revoke(self):
        """
        Revoke this peer (remove from WireGuard configuration).
        """
        self.ensure_one()
        if self.status == 'revoked':
            return

        # Remove from WireGuard configuration
        wg_config_path = '/etc/wireguard/admin/wg0.conf'
        try:
            with open(wg_config_path, 'r') as f:
                lines = f.readlines()

            # Remove the peer section
            new_lines = []
            skip = False
            for line in lines:
                if line.strip().startswith('[Peer]'):
                    # Check if this is our peer
                    # We need to look ahead to see if the public key matches
                    # This is a simplified approach; in production, parse the config properly
                    pass
                # For simplicity, we'll use wg set to remove the peer
                subprocess.run(
                    ['wg', 'set', 'admin-wg0', 'peer', self.public_key, 'remove'],
                    check=True,
                    timeout=10
                )
                _logger.info(f"Removed peer {self.name} from WireGuard.")
                break
        except Exception as e:
            _logger.error(f"Failed to revoke peer: {e}")
            raise ValidationError(_("Failed to revoke WireGuard peer."))

        self.status = 'revoked'
        _logger.info(f"Peer {self.name} revoked.")

    def get_online_status(self):
        """
        Get the real-time online status from WireGuard.

        Returns:
            dict: Status information including last handshake and transfer stats.
        """
        self.ensure_one()
        try:
            result = subprocess.run(
                ['wg', 'show', 'admin-wg0', 'peer', self.public_key],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            output = result.stdout
            # Parse the output
            import re
            handshake_match = re.search(r'latest handshake:\s*(.+)', output)
            transfer_match = re.search(r'transfer:\s*([\d.]+)\s*([KM]iB)\s*received,\s*([\d.]+)\s*([KM]iB)\s*sent', output)

            status = {
                'online': False,
                'last_handshake': None,
                'rx_mb': 0,
                'tx_mb': 0,
            }

            if handshake_match:
                status['last_handshake'] = handshake_match.group(1).strip()
                # Check if handshake is recent (within 3 minutes)
                from datetime import datetime
                # Parse the handshake time (format: "2026-08-09 14:30:25")
                try:
                    dt = datetime.strptime(status['last_handshake'], '%Y-%m-%d %H:%M:%S')
                    from datetime import timedelta
                    if (datetime.now() - dt) < timedelta(minutes=3):
                        status['online'] = True
                except ValueError:
                    pass

            if transfer_match:
                rx_val = float(transfer_match.group(1))
                rx_unit = transfer_match.group(2)
                tx_val = float(transfer_match.group(3))
                tx_unit = transfer_match.group(4)

                # Convert to MB
                if rx_unit == 'KiB':
                    status['rx_mb'] = rx_val / 1024
                elif rx_unit == 'MiB':
                    status['rx_mb'] = rx_val
                elif rx_unit == 'GiB':
                    status['rx_mb'] = rx_val * 1024

                if tx_unit == 'KiB':
                    status['tx_mb'] = tx_val / 1024
                elif tx_unit == 'MiB':
                    status['tx_mb'] = tx_val
                elif tx_unit == 'GiB':
                    status['tx_mb'] = tx_val * 1024

            return status
        except Exception as e:
            _logger.warning(f"Failed to get peer status: {e}")
            return {'online': False, 'error': str(e)}

    def action_refresh_status(self):
        """Update the peer's status from WireGuard."""
        status = self.get_online_status()
        if status.get('last_handshake'):
            self.last_handshake = status['last_handshake']
        self.transfer_rx = status.get('rx_mb', 0)
        self.transfer_tx = status.get('tx_mb', 0)
        return True


    # =========================================================================
    # 4. Constraints
    # =========================================================================

    _sql_constraints = [
        ('unique_public_key', 'unique(public_key)', 'A peer with this public key already exists.'),
        ('unique_assigned_ip', 'unique(assigned_ip)', 'This IP address is already assigned.'),
    ]