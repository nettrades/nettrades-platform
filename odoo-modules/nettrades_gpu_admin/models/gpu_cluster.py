# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py
# =============================================================================
# ... (existing copyright and description remain) ...
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import subprocess
import os
import tempfile

_logger = logging.getLogger(__name__)


class GPUCluster(models.Model):
    _name = 'gpu.cluster'
    _description = 'Company GPU Cluster'
    _rec_name = 'name'

    # =========================================================================
    # Existing fields (keep all)
    # =========================================================================
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    name = fields.Char(
        string='Cluster Name',
        required=True,
        default='Default Cluster',
    )
    trust_mode = fields.Selection(
        [
            ('company_multi_gpu', 'Trusted - Multi-GPU'),
            ('company_single_gpu', 'Trusted - Single GPU'),
            ('public_untrusted', 'Untrusted - Public Sharing'),
        ],
        string='Trust Mode',
        required=True,
        default='company_multi_gpu',
    )
    wireguard_mesh_subnet = fields.Char(
        string='WireGuard Mesh Subnet',
        default='10.100.0.0/24',
    )
    wireguard_controller_public_key = fields.Char(
        string='WireGuard Controller Public Key',
        readonly=True,
    )
    wireguard_controller_private_key = fields.Char(
        string='WireGuard Controller Private Key',
        readonly=True,
    )
    wireguard_listen_port = fields.Integer(
        string='WireGuard Listen Port',
        default=51820,
    )
    controller_endpoint = fields.Char(
        string='Controller Endpoint',
        help='Public endpoint (IP:port) for peers to reach the controller.',
    )
    gpustack_server_url = fields.Char(
        string='GPUStack Server URL',  # kept for compatibility; Dynamo will use the inference router
    )
    gpustack_api_key = fields.Char(
        string='GPUStack API Key',
    )

    # =========================================================================
    # NEW: WireGuard Peer Management
    # =========================================================================

    def _ensure_controller_keys(self):
        """
        Ensure the controller has WireGuard keys. If missing, generate them.
        """
        self.ensure_one()
        if not self.wireguard_controller_private_key:
            try:
                # Generate private key
                privkey = subprocess.check_output(['wg', 'genkey'], text=True).strip()
                # Derive public key
                pubkey = subprocess.check_output(['wg', 'pubkey'], input=privkey, text=True).strip()
                self.write({
                    'wireguard_controller_private_key': privkey,
                    'wireguard_controller_public_key': pubkey,
                })
                _logger.info("Generated WireGuard keys for cluster %s", self.name)
            except Exception as e:
                _logger.error("Failed to generate WireGuard keys for cluster %s: %s", self.name, e)
                raise UserError(_("WireGuard tools (wg) not found. Please install WireGuard."))

    def _get_wireguard_config_path(self):
        """Return the path to the WireGuard config file for this cluster."""
        return f"/etc/wireguard/wg-{self.id}.conf"

    def _write_wireguard_config(self):
        """
        Write the WireGuard configuration for the controller to disk and
        bring up the interface.
        """
        self.ensure_one()
        self._ensure_controller_keys()

        # Build the configuration
        config = f"""[Interface]
Address = {self.wireguard_mesh_subnet.split('/')[0]}/32
PrivateKey = {self.wireguard_controller_private_key}
ListenPort = {self.wireguard_listen_port}
SaveConfig = false

# Peers will be added dynamically via 'wg set' commands
"""
        config_path = self._get_wireguard_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            f.write(config)
        os.chmod(config_path, 0o600)

        # Bring up the interface
        try:
            subprocess.check_call(['wg-quick', 'up', f'wg-{self.id}'], stderr=subprocess.DEVNULL)
            _logger.info("WireGuard interface wg-%d is up for cluster %s", self.id, self.name)
        except subprocess.CalledProcessError:
            _logger.warning("WireGuard interface wg-%d may already be up or failed to start", self.id)

    def _add_wireguard_peer(self, node):
        """
        Add a node as a peer to the controller's WireGuard interface.
        """
        self.ensure_one()
        if not node.wireguard_public_key:
            raise UserError(_("Node %s has no WireGuard public key.", node.name))
        if not node.wireguard_assigned_ip:
            raise UserError(_("Node %s has no assigned IP.", node.name))

        # Ensure the interface is up
        self._write_wireguard_config()

        # Add peer using wg set
        peer_config = f"{node.wireguard_public_key} allowed-ips={node.wireguard_assigned_ip}/32"
        try:
            subprocess.check_call(
                ['wg', 'set', f'wg-{self.id}', 'peer', node.wireguard_public_key,
                 'allowed-ips', f'{node.wireguard_assigned_ip}/32'],
                stderr=subprocess.DEVNULL
            )
            _logger.info("Added peer %s (%s) to cluster %s WireGuard", node.name, node.wireguard_assigned_ip, self.name)
        except Exception as e:
            _logger.error("Failed to add peer: %s", e)
            raise UserError(_("Failed to add WireGuard peer. Ensure 'wg' is available."))

    def _revoke_wireguard_peer(self, node):
        """
        Remove a node from the controller's WireGuard interface.
        """
        self.ensure_one()
        if not node.wireguard_public_key:
            return

        try:
            subprocess.check_call(
                ['wg', 'set', f'wg-{self.id}', 'peer', node.wireguard_public_key, 'remove'],
                stderr=subprocess.DEVNULL
            )
            _logger.info("Removed peer %s from cluster %s WireGuard", node.name, self.name)
        except Exception as e:
            _logger.error("Failed to remove peer: %s", e)
            # Don't raise; we want to continue cleanup.

    # =========================================================================
    # Existing methods (keep any you already have)
    # =========================================================================
    # ... (any existing methods like cron health checks remain)