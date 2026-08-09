# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py
# =============================================================================
# PURPOSE:
#   This model represents a GPU cluster owned by a company. It stores
#   configuration for WireGuard mesh networking, cluster-wide statistics,
#   and trust/payment modes for the GPU marketplace.
#
# RELATIONSHIPS:
#   - company_id -> res.company (the company that owns this cluster)
#   - One-to-many with gpu.node (the GPU nodes in this cluster)
#   - One-to-many with gpu.cluster.subnet (registered subnets)
#
# KEY FEATURES:
#   - Trust mode selection (multi-GPU, single-GPU, public sharing)
#   - Payment mode selection (internal credits, fiat, token)
#   - WireGuard mesh subnet configuration
#   - Computed fields for cluster-wide statistics (node count, VRAM, earnings)
#   - Methods for WireGuard config generation and peer management
#   - Time‑based sharing schedule integration for auto‑switching payment mode
#
# UPDATES (2026-08-10):
#   - Added payment_mode, platform_fee_percent, min/max booking hours
#   - Added auto_approve_bookings, token_symbol, token_contract, token_network
#   - Added fiat_currency, fiat_gateway, default_credits_per_user
#   - Added _compute_payment_mode to auto-switch based on trust_mode
#   - Added total_tokens_served, total_earnings fields and compute method
#   - Added get_peers_for_wireguard() and _revoke_wireguard_peer() methods
#   - Removed all GPUStack references (replaced by NVIDIA Dynamo)
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import json
import subprocess
import secrets
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class GPUCluster(models.Model):
    """
    GPU Cluster Model - represents a company's GPU cluster.

    This model stores all configuration for a GPU cluster, including
    WireGuard settings, trust/payment modes, and cluster-wide statistics.
    """
    _name = 'gpu.cluster'
    _description = 'Company GPU Cluster'
    _rec_name = 'name'

    # =========================================================================
    # 1. BASIC IDENTIFICATION FIELDS
    # =========================================================================

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help="The company that owns this GPU cluster."
    )

    name = fields.Char(
        string='Cluster Name',
        required=True,
        default='Default Cluster',
        help="A human-readable name for this GPU cluster."
    )

    # =========================================================================
    # 2. TRUST MODE CONFIGURATION
    # =========================================================================

    trust_mode = fields.Selection(
        [
            ('company_multi_gpu', 'Trusted - Multi-GPU'),
            ('company_single_gpu', 'Trusted - Single GPU'),
            ('public_untrusted', 'Untrusted - Public Sharing'),
        ],
        string='Trust Mode',
        required=True,
        default='company_multi_gpu',
        help="""Determines the network topology and security level:
            - Trusted - Multi-GPU: Full WireGuard mesh. Used for company
              internal clusters with multiple GPUs. Supports vLLM tensor
              parallelism and Axolotl FSDP2 training.
            - Trusted - Single GPU: Hub-and-spoke WireGuard. Used for
              company internal clusters with single GPUs.
            - Untrusted - Public Sharing: Hub-and-spoke WireGuard with
              gVisor isolation. Used for freelancers sharing GPUs publicly.
        """
    )

    # =========================================================================
    # 3. WIREGUARD CONFIGURATION
    # =========================================================================

    wireguard_mesh_subnet = fields.Char(
        string='WireGuard Mesh Subnet',
        default='10.100.0.0/24',
        help="""The IP subnet used for the WireGuard mesh network.
            For trusted mode, this is the full mesh subnet.
            For untrusted mode, nodes get /32 addresses from this subnet.
        """
    )

    wireguard_subnet = fields.Char(
        related='wireguard_mesh_subnet',
        string='WireGuard Subnet',
        readonly=False,
        store=True,
        help='Backward compatibility alias for WireGuard subnet configuration.'
    )

    wireguard_controller_public_key = fields.Char(
        string='WireGuard Controller Public Key',
        readonly=True,
        help="The public key of the controller's WireGuard interface."
    )

    wireguard_controller_private_key = fields.Char(
        string='WireGuard Controller Private Key',
        readonly=True,
        help="""The private key of the controller's WireGuard interface.
            This is sensitive information and should be protected.
            WARNING: This field is readable only by system administrators.
        """
    )

    wireguard_server_public_key = fields.Char(
        related='wireguard_controller_public_key',
        string='WireGuard Server Public Key',
        readonly=False,
        store=True,
        help='Backward compatibility alias for the WireGuard controller public key.'
    )

    wireguard_server_endpoint = fields.Char(
        related='controller_endpoint',
        string='WireGuard Server Endpoint',
        readonly=False,
        store=True,
        help='Backward compatibility alias for the WireGuard controller endpoint.'
    )

    wireguard_listen_port = fields.Integer(
        string='WireGuard Listen Port',
        default=51820,
        help="The UDP port on which the WireGuard controller listens."
    )

    controller_endpoint = fields.Char(
        string='Controller Endpoint',
        help="""The public endpoint of the WireGuard controller.
            Format: <public-ip-or-domain>:<port>
            Example: 203.0.113.10:51820
        """
    )

    # =========================================================================
    # 4. REGISTERED SUBNETS (for network discovery)
    # =========================================================================

    registered_subnet_ids = fields.One2many(
        'gpu.cluster.subnet',
        'cluster_id',
        string='Registered Subnets',
        help="The subnets registered for this cluster. Used for network scanning."
    )

    node_ids = fields.One2many(
        'gpu.node',
        'cluster_id',
        string='GPU Nodes',
        help='GPU nodes that belong to this cluster.'
    )

    # =========================================================================
    # 5. COMPUTED FIELDS - CLUSTER-WIDE STATISTICS
    # =========================================================================

    node_count = fields.Integer(
        string='Node Count',
        compute='_compute_node_count',
        store=False,
        help="Total number of GPU nodes in this cluster."
    )

    online_node_count = fields.Integer(
        string='Online Nodes',
        compute='_compute_node_count',
        store=False,
        help="Number of GPU nodes that are currently online."
    )

    total_vram_gb = fields.Float(
        string='Total VRAM (GB)',
        compute='_compute_vram',
        store=False,
        help="Total VRAM across all nodes in this cluster (in GB)."
    )

    available_vram_gb = fields.Float(
        string='Available VRAM (GB)',
        compute='_compute_vram',
        store=False,
        help="Total VRAM available across online nodes (in GB)."
    )

    total_gpu_count = fields.Integer(
        string='Total GPUs',
        compute='_compute_gpu_count',
        store=False,
        help="Total number of physical GPUs across all nodes."
    )

    total_tokens_served = fields.Integer(
        string='Total Tokens Served',
        compute='_compute_token_economics',
        store=False,
        help='Total tokens served by all nodes in this cluster.'
    )

    total_earnings = fields.Float(
        string='Total Earnings',
        compute='_compute_token_economics',
        store=False,
        help='Total token earnings earned by all nodes in this cluster.'
    )

    # =========================================================================
    # 6. PAYMENT & ECONOMICS FIELDS (NEW)
    # =========================================================================

    payment_mode = fields.Selection(
        [
            ('internal', 'Internal Credits (No Real Money)'),
            ('fiat', 'Fiat Currency (Stripe/Paddle)'),
            ('token', 'Token (USDC/Solana)'),
        ],
        string='Payment Mode',
        compute='_compute_payment_mode',
        store=True,
        help='Automatically set based on trust_mode and sharing schedules.'
    )

    platform_fee_percent = fields.Float(
        string='Platform Fee (%)',
        default=5.0,
        help='Percentage fee taken by the platform for each booking.'
    )

    min_booking_hours = fields.Float(
        string='Minimum Booking Hours',
        default=0.5,
        help='Minimum duration for a GPU booking.'
    )

    max_booking_hours = fields.Float(
        string='Maximum Booking Hours',
        default=720.0,
        help='Maximum duration for a GPU booking (30 days).'
    )

    auto_approve_bookings = fields.Boolean(
        string='Auto-Approve Bookings',
        default=True,
        help='Automatically approve bookings when credits are sufficient.'
    )

    token_symbol = fields.Char(
        string='Token Symbol',
        default='USDC',
        help='Token symbol for crypto payments (e.g., USDC, NETT).'
    )

    token_contract = fields.Char(
        string='Token Contract Address',
        help='Smart contract address for the token (if applicable).'
    )

    token_network = fields.Selection(
        [
            ('solana', 'Solana'),
            ('base', 'Base'),
            ('ethereum', 'Ethereum'),
        ],
        string='Token Network',
        default='solana',
        help='Blockchain network for token payments.'
    )

    fiat_currency = fields.Char(
        string='Fiat Currency',
        default='USD',
        help='Currency for fiat payments.'
    )

    fiat_gateway = fields.Selection(
        [
            ('stripe', 'Stripe'),
            ('paddle', 'Paddle'),
        ],
        string='Fiat Gateway',
        default='stripe',
        help='Payment gateway for fiat payments.'
    )

    default_credits_per_user = fields.Float(
        string='Default Credits per User',
        default=100.0,
        help='Default credit allocation for new users (internal mode only).'
    )

    credit_reset_interval = fields.Selection(
        [
            ('never', 'Never'),
            ('monthly', 'Monthly'),
            ('quarterly', 'Quarterly'),
            ('yearly', 'Yearly'),
        ],
        string='Credit Reset Interval',
        default='monthly',
        help='How often credits are reset for users (internal mode only).'
    )

    # =========================================================================
    # 7. GPU SELECTION FOR TRAINING
    # =========================================================================

    gpu_ids = fields.Many2many(
        'gpu.node',
        string='GPUs for Training',
        help="The GPUs selected for fine-tuning jobs. This is a Many2many "
             "field that allows administrators to select specific GPUs "
             "for training workloads."
    )

    # =========================================================================
    # 8. COMPUTATION METHODS
    # =========================================================================

    @api.depends('company_id')
    def _compute_node_count(self):
        """Compute total and online node counts for the cluster."""
        for cluster in self:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])
            cluster.node_count = len(nodes)
            cluster.online_node_count = len(
                nodes.filtered(lambda n: n.status == 'online')
            )

    @api.depends('company_id')
    def _compute_vram(self):
        """Compute total and available VRAM for the cluster."""
        for cluster in self:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            total = 0.0
            for node in nodes:
                if hasattr(node, 'total_vram_gb') and node.total_vram_gb:
                    total += node.total_vram_gb
                elif node.gpus:
                    try:
                        gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                        for gpu in gpus:
                            total += gpu.get('memory_mb', 0) / 1024.0
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

            cluster.total_vram_gb = total

            online_total = 0.0
            online_nodes = nodes.filtered(lambda n: n.status == 'online')
            for node in online_nodes:
                if hasattr(node, 'total_vram_gb') and node.total_vram_gb:
                    online_total += node.total_vram_gb
                elif node.gpus:
                    try:
                        gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                        for gpu in gpus:
                            online_total += gpu.get('memory_mb', 0) / 1024.0
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

            cluster.available_vram_gb = online_total

    @api.depends('company_id')
    def _compute_gpu_count(self):
        """Compute the total number of physical GPUs in the cluster."""
        for cluster in self:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            gpu_count = 0
            for node in nodes:
                if hasattr(node, 'gpus') and node.gpus:
                    try:
                        gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                        gpu_count += len(gpus)
                    except (json.JSONDecodeError, TypeError):
                        pass

            cluster.total_gpu_count = gpu_count

    @api.depends('company_id')
    def _compute_token_economics(self):
        """Compute cluster-level token economics metrics."""
        for cluster in self:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])
            cluster.total_tokens_served = sum((node.tokens_served or 0) for node in nodes)
            cluster.total_earnings = sum((node.token_earnings or 0.0) for node in nodes)

    @api.depends('trust_mode')
    def _compute_payment_mode(self):
        """
        Automatically set payment_mode based on trust_mode.
        If any active sharing schedule is public, override to 'token'.
        """
        for cluster in self:
            # Check if any active sharing schedule is public
            active_schedules = self.env['gpu.sharing.schedule'].search([
                ('cluster_id', '=', cluster.id),
                ('is_enabled', '=', True),
            ])
            is_public_now = any(schedule.is_active_now() for schedule in active_schedules)

            if cluster.trust_mode == 'public_untrusted' or is_public_now:
                # Public sharing requires token or fiat payment
                cluster.payment_mode = 'token'
            elif cluster.trust_mode in ('company_multi_gpu', 'company_single_gpu'):
                # Internal company sharing uses internal credits
                cluster.payment_mode = 'internal'
            else:
                cluster.payment_mode = 'internal'

    # =========================================================================
    # 9. WIREGUARD KEY MANAGEMENT
    # =========================================================================

    def _ensure_controller_keys(self):
        """
        Ensure the controller has WireGuard keys. If missing, generate them.
        """
        self.ensure_one()
        if not self.wireguard_controller_public_key or not self.wireguard_controller_private_key:
            self._generate_wireguard_config()

    def _generate_wireguard_config(self):
        """
        Generate a WireGuard configuration for the controller.

        Returns:
            dict: Contains 'private_key', 'public_key', and 'config' string
        """
        self.ensure_one()

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

            # Save to the record
            self.write({
                'wireguard_controller_private_key': private_key,
                'wireguard_controller_public_key': public_key,
            })

            # Build the WireGuard config for the controller
            config = f"""[Interface]
Address = {self.wireguard_mesh_subnet.split('/')[0]}1/24
ListenPort = {self.wireguard_listen_port}
PrivateKey = {private_key}

# This is the controller's configuration. Client nodes will have their own.
# The controller acts as the central hub for the WireGuard mesh.
"""

            _logger.info(
                "Generated WireGuard controller config for cluster %s",
                self.name
            )

            return {
                'private_key': private_key,
                'public_key': public_key,
                'config': config,
            }

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

    # =========================================================================
    # 10. WIREGUARD PEER MANAGEMENT (for the controller API)
    # =========================================================================

    def get_peers_for_wireguard(self):
        """
        Get all nodes in this cluster for WireGuard peer configuration.

        This method returns a list of all nodes in the cluster with their
        WireGuard public keys and assigned IPs, suitable for the WireGuard
        peer manager daemon.

        Called by the WireGuard peer manager via the /api/v1/gpu/peers endpoint.

        Returns:
            list: A list of dictionaries with 'public_key', 'allowed_ips',
                and 'endpoint' keys.
        """
        self.ensure_one()

        peers = []
        nodes = self.env['gpu.node'].search([
            ('cluster_id', '=', self.id),
            ('status', 'in', ['online', 'degraded'])
        ])

        for node in nodes:
            if node.wireguard_public_key and node.wireguard_assigned_ip:
                peers.append({
                    'public_key': node.wireguard_public_key,
                    'allowed_ips': f"{node.wireguard_assigned_ip}/32",
                    'endpoint': node.endpoint or '',
                })

        return peers

    def _revoke_wireguard_peer(self, node):
        """
        Revoke a WireGuard peer from the cluster.

        This method updates the node record so that it is excluded from
        WireGuard peer synchronization and clears node-specific WireGuard
        registration state.

        Args:
            node (gpu.node): The node to revoke.

        Returns:
            bool: True if successful, False otherwise.
        """
        self.ensure_one()
        if not node or not node.exists():
            return False

        cleanup_values = {
            'status': 'offline',
            'endpoint': False,
            'wireguard_public_key': False,
            'wireguard_assigned_ip': False,
        }
        if hasattr(node, 'wireguard_ip'):
            cleanup_values['wireguard_ip'] = False
        if hasattr(node, 'state'):
            cleanup_values['state'] = 'inactive'

        node.write(cleanup_values)
        _logger.info(
            "WireGuard peer revoked for node %s (ID: %s)",
            node.name, node.id
        )
        return True

    # =========================================================================
    # 11. NETWORK SCANNING (optional, zero-touch provisioning)
    # =========================================================================

    def _scan_network_for_gpus(self, subnet=None):
        """
        Scan the network for GPU-equipped machines.

        This method uses nmap or a similar tool to discover machines in the
        network that have NVIDIA GPUs. It returns a list of discovered
        machines with their IP addresses and GPU information.

        Args:
            subnet (str, optional): The subnet to scan. If not provided,
                uses the registered subnets for this cluster.

        Returns:
            list: A list of dictionaries containing discovered machine info.
                Each dict has: 'ip', 'hostname', 'gpus' (list of GPU info)

        Note:
            This requires nmap to be installed on the controller machine.
        """
        self.ensure_one()

        discovered = []
        subnets = subnet or [self.wireguard_mesh_subnet]

        if isinstance(subnets, str):
            subnets = [subnets]

        try:
            import subprocess
            import re

            for subnet_cidr in subnets:
                _logger.info(f"Scanning subnet {subnet_cidr} for GPU nodes...")

                # Simplified scan: ping sweep
                cmd = [
                    'nmap', '-sn', subnet_cidr,
                    '--min-hostgroup', '64',
                    '--max-rtt-timeout', '2000ms'
                ]

                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    ip_pattern = r'Nmap scan report for (?:[\w.-]+ )?\(?(\d+\.\d+\.\d+\.\d+)\)?'
                    ips = re.findall(ip_pattern, result.stdout)

                    for ip in ips:
                        discovered.append({
                            'ip': ip,
                            'hostname': ip,
                            'gpus': [],
                            'source': 'nmap',
                        })
                except subprocess.TimeoutExpired:
                    _logger.warning(f"Scan timeout for subnet {subnet_cidr}")
                except FileNotFoundError:
                    _logger.warning("nmap not found. Please install nmap for network scanning.")

        except Exception as e:
            _logger.error(f"Network scan failed: {e}")

        return discovered

    # =========================================================================
    # 12. CLUSTER MANAGEMENT ACTIONS
    # =========================================================================

    def action_remove_cluster(self):
        """
        Remove this GPU cluster and all its nodes.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()

        node_count = self.env['gpu.node'].search_count([
            ('cluster_id', '=', self.id)
        ])

        self.env['gpu.node'].search([
            ('cluster_id', '=', self.id)
        ]).unlink()

        self.unlink()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cluster Removed'),
                'message': _('Cluster removed with %s nodes.') % node_count,
                'type': 'success',
                'sticky': False,
            }
        }

    # =========================================================================
    # 13. HELPER METHODS
    # =========================================================================

    def get_effective_payment_mode(self):
        """
        Get the effective payment mode considering time-based schedules.
        If a public sharing schedule is active, force token mode.

        Returns:
            str: The effective payment mode.
        """
        self.ensure_one()
        active_schedules = self.env['gpu.sharing.schedule'].search([
            ('cluster_id', '=', self.id),
            ('is_enabled', '=', True),
        ])
        is_public_now = any(schedule.is_active_now() for schedule in active_schedules)

        if is_public_now and self.trust_mode != 'public_untrusted':
            return 'token'
        return self.payment_mode

    def get_default_credits_per_user(self):
        """Get the default credit allocation for new users."""
        self.ensure_one()
        return self.default_credits_per_user or 100.0

    # =========================================================================
    # 14. CONSTRAINTS AND VALIDATION
    # =========================================================================

    @api.constrains('wireguard_mesh_subnet')
    def _check_wireguard_subnet(self):
        """Validate the WireGuard subnet format (CIDR)."""
        import ipaddress

        for cluster in self:
            if cluster.wireguard_mesh_subnet:
                try:
                    ipaddress.ip_network(cluster.wireguard_mesh_subnet, strict=False)
                except ValueError:
                    raise ValidationError(_(
                        "Invalid WireGuard subnet format. "
                        "Please use CIDR notation (e.g., 10.100.0.0/24)."
                    ))

    # =========================================================================
    # 15. CRON JOBS
    # =========================================================================

    def _cron_health_watchdog(self):
        """
        Scheduled cron job to check the health of all GPU clusters.
        """
        _logger.info("Running GPU cluster health watchdog")

        clusters = self.search([])
        threshold = datetime.now() - timedelta(minutes=5)

        for cluster in clusters:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            for node in nodes:
                if node.last_seen and node.last_seen < threshold:
                    if node.status == 'online':
                        _logger.warning(
                            f"Node {node.name} ({node.hostname}) appears offline. "
                            f"Last seen: {node.last_seen}"
                        )
                        node.status = 'offline'

        _logger.info("GPU cluster health watchdog completed")