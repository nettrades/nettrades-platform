# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_node.py
# =============================================================================
# DESCRIPTION:
#   GPU Node Model - represents a single GPU machine (physical or virtual)
#   that is part of a GPU cluster. Stores hardware inventory, WireGuard
#   configuration, GPU details, and operational status.
#
# RELATIONSHIPS:
#   - cluster_id -> gpu.cluster (the cluster this node belongs to)
#   - booking_ids -> gpu_sharing_schedule (bookings for this node)
#
# KEY FEATURES:
#   - Hardware inventory (GPUs, VRAM, OS, TEE capabilities)
#   - WireGuard key management (node generates its own keys)
#   - Pool assignment (internal vs public)
#   - Container runtime selection (Docker vs gVisor)
#   - Token economics (earnings, reputation)
#   - Health monitoring and attestation
#
# UPDATES (2026-08-10):
#   - Removed all GPUStack references (replaced by NVIDIA Dynamo)
#   - Added `total_earnings`, `reputation_score`, `rating`, `total_bookings`
#   - Added `uptime_percentage` computed field
#   - Added `add_earnings()`, `increment_bookings()`, `update_rating()` helpers
#   - Added `is_available_for_booking()` method
#   - Kept `pool` as a related field to `gpu_pool` for backward compatibility
# =============================================================================

import logging
import json
import secrets
import hashlib
import subprocess
import base64
import re
from datetime import datetime, timedelta
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class GPUNode(models.Model):
    """
    GPU Node Model - represents a single GPU machine in a cluster.

    This model stores all information about a GPU node, including its
    hardware inventory, WireGuard configuration, and operational status.
    """

    _name = 'gpu.node'
    _description = 'GPU Node'
    _rec_name = 'name'

    # =========================================================================
    # 1. CLUSTER AND BASIC IDENTIFICATION
    # =========================================================================

    cluster_id = fields.Many2one(
        'gpu.cluster',
        string='Cluster',
        required=True,
        ondelete='cascade',
        help="The GPU cluster that this node belongs to."
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        help="The partner (company or user) that owns this GPU node."
    )

    name = fields.Char(
        string='Node Name',
        required=True,
        help="A human-readable name for this GPU node."
    )

    node_id = fields.Char(
        string='Hardware Node ID',
        help="Hardware-bound unique identifier generated from TPM Endorsement Key hash or MAC address hash. Prevents token farming."
    )

    hostname = fields.Char(
        string='Hostname',
        help="The network hostname of this GPU node."
    )

    ip_address = fields.Char(
        string='IP Address',
        help="The IP address of this GPU node on the network."
    )

    # =========================================================================
    # 2. OPERATIONAL STATUS
    # =========================================================================

    status = fields.Selection(
        [
            ('online', 'Online'),
            ('offline', 'Offline'),
            ('degraded', 'Degraded'),
            ('maintenance', 'Maintenance'),
        ],
        string='Status',
        default='offline',
        help="Current operational status of the node: Online, Offline, Degraded, or Maintenance."
    )

    last_seen = fields.Datetime(
        string='Last Seen',
        help="The last time this node sent a heartbeat to the server."
    )

    uptime_hours = fields.Float(
        string='Uptime (hours)',
        help="The number of hours this node has been continuously running."
    )

    gpu_utilisation_pct = fields.Float(
        string='GPU Utilisation (%)',
        help="The average GPU utilisation percentage across all GPUs."
    )

    # =========================================================================
    # 3. GPU HARDWARE INVENTORY
    # =========================================================================

    gpus = fields.Json(
        string='GPU Inventory',
        help="JSON array containing GPU information from nvidia-smi. Each entry: index, name, memory_mb, utilisation, temperature."
    )

    total_vram_gb = fields.Float(
        string='Total VRAM (GB)',
        compute='_compute_total_vram',
        store=True,
        help="Total VRAM across all GPUs in this node (in GB)."
    )

    gpu_count = fields.Integer(
        string='GPU Count',
        compute='_compute_gpu_count',
        store=True,
        help="The number of physical GPUs in this node."
    )

    # =========================================================================
    # 4. OPERATING SYSTEM AND ENVIRONMENT
    # =========================================================================

    os = fields.Char(
        string='Operating System',
        help="The operating system of the node (linux, windows, darwin)."
    )

    arch = fields.Char(
        string='Architecture',
        help="The CPU architecture of the node (x86_64, arm64, etc.)."
    )

    model = fields.Char(
        string='System Model',
        help="The system model of the machine (e.g., Dell PowerEdge R740)."
    )

    # =========================================================================
    # 5. TEE / CONFIDENTIAL COMPUTING CAPABILITIES
    # =========================================================================

    tee_capabilities = fields.Json(
        string='TEE Capabilities',
        help="JSON object containing Trusted Execution Environment capabilities: nvidia_cc, intel_sgx, amd_sev, intel_tdx."
    )

    attestation_passed = fields.Boolean(
        string='Attestation Passed',
        default=False,
        help="Whether the node has passed the hourly attestation check."
    )

    attestation_last_check = fields.Datetime(
        string='Last Attestation Check',
        help="The timestamp of the last attestation check."
    )

    # =========================================================================
    # 6. EDGE DEVICE INFORMATION
    # =========================================================================

    edge_device_info = fields.Json(
        string='Edge Device Info',
        help="JSON object containing edge device information: type, model, memory, storage."
    )

    # =========================================================================
    # 7. WIREGUARD NETWORKING
    # =========================================================================

    wireguard_public_key = fields.Text(
        string='WireGuard Public Key',
        help="The WireGuard public key of this node."
    )

    wireguard_assigned_ip = fields.Char(
        string='WireGuard Assigned IP',
        help="The IP address assigned to this node on the WireGuard network."
    )

    wireguard_ip = fields.Char(
        string='WireGuard IP',
        related='wireguard_assigned_ip',
        readonly=False,
        store=True,
        help="Backward compatibility alias for the WireGuard assigned IP."
    )

    endpoint = fields.Char(
        string='WireGuard Endpoint',
        help="The public endpoint of this node (IP:port) for WireGuard."
    )

    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('active', 'Active'),
            ('inactive', 'Inactive'),
            ('failed', 'Failed'),
        ],
        string='Registration State',
        default='pending',
        copy=False,
        help="The registration lifecycle state of the node."
    )

    registration_token_id = fields.Many2one(
        'gpu.registration.token',
        string='Registration Token',
        help='The registration token used to onboard this node.'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help='The company that owns this GPU node.'
    )

    # =========================================================================
    # 8. POOL ASSIGNMENT (RENAMED to avoid conflict with Odoo's internal 'pool' attribute)
    # =========================================================================
    # IMPORTANT: The field name 'pool' is reserved in Odoo's Model class.
    # It is used internally to refer to the model registry. Defining a field
    # named 'pool' shadows this attribute and causes the model registration
    # to fail with AssertionError: is_model_definition(model_def).
    # We rename it to 'gpu_pool' to avoid this conflict.

    # Real stored field – safe name that does not shadow Odoo's internal `pool` attribute
    gpu_pool = fields.Selection(
        [
            ('internal', 'Internal (Trusted)'),
            ('public', 'Public (Untrusted)'),
        ],
        string='Pool',
        default='internal',
        help="Internal: Company trusted network. Uses Docker runtime. Public: Untrusted freelancer network. Uses gVisor runtime."
    )

    # Backward compatibility alias – points to gpu_pool
    pool = fields.Selection(
        related='gpu_pool',
        string='Pool',
        readonly=False,
        store=True,
        help='Backward compatibility alias for the GPU pool field.'
    )

    # =========================================================================
    # 9. CONTAINER RUNTIME
    # =========================================================================

    container_runtime = fields.Selection(
        [
            ('docker', 'Docker'),
            ('gvisor', 'gVisor'),
        ],
        string='Container Runtime',
        default='docker',
        help="The container runtime used for inference workloads: Docker (internal) or gVisor (public)."
    )

    # =========================================================================
    # 10. TOKEN ECONOMICS
    # =========================================================================

    tokens_served = fields.Integer(
        string='Tokens Served',
        default=0,
        help="The total number of tokens served by this node."
    )

    token_earnings = fields.Float(
        string='Token Earnings',
        default=0.0,
        help="The total token earnings from sharing this node."
    )

    reputation_score = fields.Float(
        string='Reputation Score',
        compute='_compute_reputation',
        store=True,
        help="The reputation score of this node (based on reliability, uptime, and ratings)."
    )

    scheduled_share = fields.Boolean(
        string='Scheduled Sharing',
        default=False,
        help="Whether this node is scheduled for public sharing."
    )

    # =========================================================================
    # 11. PROVIDER ECONOMICS (NEW)
    # =========================================================================

    total_earnings = fields.Float(
        string='Total Earnings',
        default=0.0,
        help="Lifetime earnings from all bookings (in the cluster's currency)."
    )

    rating = fields.Float(
        string='Rating',
        default=0.0,
        help="Average user rating (1-5)."
    )

    total_bookings = fields.Integer(
        string='Total Bookings',
        default=0,
        help="Total number of completed bookings for this node."
    )

    uptime_percentage = fields.Float(
        string='Uptime (%)',
        compute='_compute_uptime_percentage',
        store=True,
        help="Percentage of time the node has been online."
    )

    # =========================================================================
    # 12. BOOKINGS
    # =========================================================================

    booking_ids = fields.One2many(
        'gpu_sharing_schedule',
        'node_id',
        string='Bookings',
        help="All bookings for this GPU node."
    )

    current_booking_id = fields.Many2one(
        'gpu_sharing_schedule',
        string='Current Booking',
        help="The currently active booking for this node."
    )

    # =========================================================================
    # 13. COMPUTED FIELDS
    # =========================================================================

    @api.depends('gpus')
    def _compute_total_vram(self):
        """
        Compute total VRAM from the gpus JSON field.

        This method parses the gpus JSON array and sums the memory_mb values
        for each GPU, converting from MB to GB.
        """
        for node in self:
            total = 0.0
            if node.gpus:
                try:
                    gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                    for gpu in gpus:
                        total += gpu.get('memory_mb', 0) / 1024.0
                except (json.JSONDecodeError, TypeError):
                    pass
            node.total_vram_gb = total

    @api.depends('gpus')
    def _compute_gpu_count(self):
        """
        Compute the number of GPUs from the gpus JSON field.

        This method parses the gpus JSON array and counts the number of GPUs.
        """
        for node in self:
            count = 0
            if node.gpus:
                try:
                    gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                    count = len(gpus)
                except (json.JSONDecodeError, TypeError):
                    pass
            node.gpu_count = count

    @api.depends('uptime_hours', 'status')
    def _compute_uptime_percentage(self):
        """
        Calculate uptime percentage based on status and last_seen.
        """
        for node in self:
            if node.status == 'online':
                node.uptime_percentage = 100.0
            elif node.status == 'offline':
                if node.last_seen:
                    hours_since_seen = (fields.Datetime.now() - node.last_seen).total_seconds() / 3600
                    if hours_since_seen < 1:
                        node.uptime_percentage = 90.0
                    elif hours_since_seen < 24:
                        node.uptime_percentage = 50.0
                    else:
                        node.uptime_percentage = 10.0
                else:
                    node.uptime_percentage = 0.0
            else:
                node.uptime_percentage = 50.0

    @api.depends('uptime_percentage', 'rating', 'gpu_utilisation_pct')
    def _compute_reputation(self):
        """
        Calculate reputation score based on uptime, rating, and utilisation.
        """
        for node in self:
            # Weighted score: 40% uptime, 40% rating, 20% utilisation
            uptime_score = node.uptime_percentage / 100.0 * 10
            rating_score = node.rating * 2  # 0-5 -> 0-10
            util_score = node.gpu_utilisation_pct / 100.0 * 10

            node.reputation_score = (
                uptime_score * 0.4 +
                rating_score * 0.4 +
                util_score * 0.2
            )

    # =========================================================================
    # 14. WIREGUARD CONFIGURATION GENERATION
    # =========================================================================

    def _generate_wireguard_config(self):
        """
        Generate a WireGuard configuration for this node.

        This method generates the WireGuard configuration that this node
        should use to connect to the cluster's WireGuard network.

        IMPORTANT: The node's private key is generated locally and NEVER
        stored in the database. Only the public key is stored.

        Returns:
            dict: A dictionary containing:
                - 'private_key': The node's private key (for the agent)
                - 'public_key': The node's public key (stored in the database)
                - 'config': The WireGuard configuration in INI format

        Raises:
            UserError: If WireGuard tools are not installed or key generation fails.
        """
        self.ensure_one()

        # Get the cluster's WireGuard configuration
        cluster = self.cluster_id

        # ---------------------------------------------------------------------
        # Step 1: Generate a new WireGuard key pair for this node
        # ---------------------------------------------------------------------
        # The private key is generated locally and never stored.
        # Only the public key is stored in the database.
        try:
            # Generate private key using wg(8)
            privkey_proc = subprocess.run(
                ['wg', 'genkey'],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            private_key = privkey_proc.stdout.strip()

            # Derive the public key from the private key
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
            raise UserError(_(
                "Failed to generate WireGuard keys. "
                "Please ensure WireGuard is installed and 'wg' is in PATH."
            ))
        except FileNotFoundError:
            _logger.error("WireGuard tools (wg) not found in PATH")
            raise UserError(_(
                "WireGuard tools not found. Please install WireGuard "
                "and ensure 'wg' is available in the system PATH."
            ))
        except subprocess.TimeoutExpired:
            _logger.error("WireGuard key generation timed out")
            raise UserError(_("WireGuard key generation timed out. Please try again."))

        # Store the public key on the node (private key is never stored)
        self.write({
            'wireguard_public_key': public_key,
        })

        # ---------------------------------------------------------------------
        # Step 2: Determine the assigned IP address for this node
        # ---------------------------------------------------------------------
        # Use a deterministic IP based on the node ID (for consistency)
        # In production, this should use a proper IPAM system
        subnet_parts = cluster.wireguard_mesh_subnet.split('/')
        base_ip = subnet_parts[0]
        prefix = subnet_parts[1] if len(subnet_parts) > 1 else '24'

        # Generate a stable IP suffix based on the node's ID
        node_hash = int(hashlib.md5(str(self.id).encode()).hexdigest()[:8], 16)
        ip_suffix = (node_hash % 254) + 1  # Avoid .0 and .255
        assigned_ip = f"{base_ip.rsplit('.', 1)[0]}.{ip_suffix}"

        self.write({
            'wireguard_assigned_ip': assigned_ip,
        })

        # ---------------------------------------------------------------------
        # Step 3: Build the WireGuard configuration for this node
        # ---------------------------------------------------------------------
        config = f"""[Interface]
Address = {assigned_ip}/{prefix}
PrivateKey = {private_key}
ListenPort = 51820
PersistentKeepalive = 25

[Peer]
PublicKey = {cluster.wireguard_controller_public_key or 'CHANGE_ME'}
AllowedIPs = {cluster.wireguard_mesh_subnet}
Endpoint = {cluster.controller_endpoint or 'CHANGE_ME:51820'}

# This configuration was generated by the NETTRADES GPU controller.
# Do not modify unless you know what you are doing.
"""

        _logger.info(
            "Generated WireGuard config for node %s (ID: %d) with IP %s",
            self.name, self.id, assigned_ip
        )

        # ---------------------------------------------------------------------
        # Step 4: Return the configuration (private key, public key, config)
        # ---------------------------------------------------------------------
        return {
            'private_key': private_key,
            'public_key': public_key,
            'config': config,
        }

    # =========================================================================
    # 15. PROVIDER ECONOMICS HELPERS
    # =========================================================================

    def add_earnings(self, amount):
        """
        Add earnings to the node's total earnings.

        Args:
            amount (float): The amount to add.
        """
        self.ensure_one()
        self.total_earnings += amount
        self.token_earnings += amount

    def increment_bookings(self):
        """Increment the total bookings count."""
        self.ensure_one()
        self.total_bookings += 1

    def update_rating(self, new_rating):
        """
        Update the node's average rating with a new rating.

        Args:
            new_rating (float): The new rating (1-5).
        """
        self.ensure_one()
        if self.total_bookings > 0:
            self.rating = ((self.rating * (self.total_bookings - 1)) + new_rating) / self.total_bookings
        else:
            self.rating = new_rating

    def is_available_for_booking(self):
        """
        Check if this node is available for a new booking.

        Returns:
            bool: True if available, False otherwise.
        """
        self.ensure_one()
        return (
            self.status == 'online' and
            not self.current_booking_id and
            self.state == 'active'
        )

    # =========================================================================
    # 16. NODE LIFECYCLE MANAGEMENT
    # =========================================================================

    def action_remove_node(self):
        """
        Remove this node from the cluster.

        This method:
        1. Revokes the node from the WireGuard peer list
        2. Deletes the node record

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()
        node_name = self.name

        # Step 1: Revoke the node from the cluster's WireGuard peer list
        try:
            cluster = self.cluster_id
            if cluster and cluster.exists():
                cluster._revoke_wireguard_peer(self)
        except Exception as e:
            _logger.warning(f"Failed to revoke WireGuard peer for node {self.name}: {e}")

        # Step 2: Delete the node record
        self.unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Node Removed'),
                'message': _('Node %s has been removed from the cluster.') % node_name,
                'type': 'success',
                'sticky': False,
            }
        }

    def action_reassign_pool(self, new_pool):
        """
        Reassign this node to a different pool.

        Args:
            new_pool (str): The new pool to assign the node to ('internal' or 'public').

        Returns:
            dict: Action result for the Odoo UI.

        Note:
            When reassigning from internal to public, the container runtime
            is automatically switched to gVisor for security.
            When reassigning from public to internal, the container runtime
            is switched back to Docker.
        """
        self.ensure_one()

        # Use the stored field gpu_pool for comparison
        if new_pool == self.gpu_pool:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Change'),
                    'message': _('Node is already in the %s pool.') % new_pool,
                    'type': 'info',
                    'sticky': False,
                }
            }

        # Validate the pool assignment
        if new_pool == 'public':
            # Automatically switch to gVisor for public pool
            self.write({
                'gpu_pool': new_pool,
                'container_runtime': 'gvisor',
            })
        else:
            # For internal pool, use Docker runtime
            self.write({
                'gpu_pool': new_pool,
                'container_runtime': 'docker',
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Pool Reassigned'),
                'message': _('Node %s reassigned to %s pool.') % (self.name, new_pool),
                'type': 'success',
                'sticky': False,
            }
        }

    # =========================================================================
    # 17. CRON JOBS
    # =========================================================================

    def _cron_health_watchdog(self):
        """
        Scheduled cron job to check the health of all GPU nodes.

        This method runs periodically to:
        1. Check the status of all nodes
        2. Update node statuses based on last_seen timestamps
        3. Flag nodes that need attention

        Called by the Odoo cron system via the cluster's cron method.
        """
        _logger.info("Running GPU node health watchdog")

        # Get all nodes that are supposedly online
        nodes = self.search([('status', '=', 'online')])
        threshold = datetime.now() - timedelta(minutes=5)

        for node in nodes:
            if node.last_seen and node.last_seen < threshold:
                _logger.warning(
                    f"Node {node.name} ({node.hostname}) appears offline. "
                    f"Last seen: {node.last_seen}"
                )
                node.status = 'offline'

        _logger.info(f"GPU node health watchdog completed: {len(nodes)} nodes checked")

    # =========================================================================
    # 18. CONSTRAINTS AND VALIDATION
    # =========================================================================

    @api.constrains('wireguard_public_key')
    def _check_wireguard_key(self):
        """
        Validate the WireGuard public key format.

        Ensures the key is a valid WireGuard base64-encoded public key.
        """
        for node in self:
            if node.wireguard_public_key:
                # WireGuard public keys are 44 characters of base64
                if not re.match(r'^[A-Za-z0-9+/]{43}=$', node.wireguard_public_key):
                    # Some keys might not have padding; try decoding
                    try:
                        base64.b64decode(node.wireguard_public_key + '=')
                    except Exception:
                        raise ValidationError(_(
                            "Invalid WireGuard public key format. "
                            "The key should be a valid base64-encoded key."
                        ))

    # =========================================================================
    # 19. HELPER METHODS FOR EXTERNAL ACCESS
    # =========================================================================

    def get_peer_info(self):
        """
        Get the WireGuard peer information for this node.

        Returns:
            dict: A dictionary with 'public_key', 'allowed_ips', and 'endpoint'.

        Used by the WireGuard peer manager to configure the WireGuard interface.
        """
        self.ensure_one()

        return {
            'public_key': self.wireguard_public_key,
            'allowed_ips': f"{self.wireguard_assigned_ip}/32" if self.wireguard_assigned_ip else None,
            'endpoint': self.endpoint or '',
        }