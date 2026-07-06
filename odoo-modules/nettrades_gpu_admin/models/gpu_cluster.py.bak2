# -*- coding: utf-8 -*-
# =============================================================================
# SECTION H - GPU CLUSTER MODEL
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py
#
# PURPOSE:
#   This model represents a GPU cluster owned by a company. It stores
#   configuration for WireGuard mesh networking, GPUStack integration,
#   and tracks cluster-wide statistics (node count, VRAM, etc.).
#
# RELATIONSHIPS:
#   - company_id -> res.company (the company that owns this cluster)
#   - One-to-many with gpu.node (the GPU nodes in this cluster)
#   - One-to-many with gpu.cluster.subnet (registered subnets)
#
# KEY FEATURES:
#   - Trust mode selection (multi-GPU, single-GPU, public sharing)
#   - WireGuard mesh subnet configuration
#   - GPUStack server connection settings
#   - Computed fields for cluster-wide statistics
#   - Methods for WireGuard config generation and token management
#
# USAGE:
#   - Created automatically when a company first registers a GPU node
#   - Managed by the GPU Administrator via the Odoo admin panel
# =============================================================================

# -----------------------------------------------------------------------------
# IMPORTS - Each import MUST be on its own line for valid Python syntax.
# -----------------------------------------------------------------------------
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import logging
import secrets
import json
import requests
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class GPUCluster(models.Model):
    """
    GPU Cluster Model - represents a company's GPU cluster.

    This model stores all configuration for a GPU cluster, including
    WireGuard settings, GPUStack integration, and cluster-wide statistics.
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
            ?????? WARNING: This field is readable only by system administrators.
        """
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
    # 4. GPUSTACK INTEGRATION
    # =========================================================================

    gpustack_server_url = fields.Char(
        string='GPUStack Server URL',
        help="""The URL of the GPUStack server for this cluster.
            Example: https://gpustack.nettrades.ai
            For company-internal clusters, this is the internal GPUStack
            server URL.
        """
    )

    gpustack_api_key = fields.Char(
        string='GPUStack API Key',
        help="""The API key for authenticating with GPUStack.
            This is a sensitive credential and should be protected.
            ?????? WARNING: This field is readable only by system administrators.
        """
    )

    # =========================================================================
    # 5. REGISTERED SUBNETS (for network discovery)
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
    # 6. COMPUTED FIELDS - CLUSTER-WIDE STATISTICS
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
    # 8. FIELD COMPUTATION METHODS
    # =========================================================================

    @api.depends('company_id')
    def _compute_node_count(self):
        """
        Compute the total and online node counts for each cluster.

        This method queries the gpu.node model to count nodes belonging
        to this cluster and determines how many are online.

        The @api.depends('company_id') ensures this recomputes when the
        cluster's company changes (though the actual dependency should be
        on the one2many relationship, which is handled via the search).
        """
        for cluster in self:
            # Search for all nodes in this cluster
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            # Count total nodes
            cluster.node_count = len(nodes)

            # Count nodes with status 'online'
            cluster.online_node_count = len(
                nodes.filtered(lambda n: n.status == 'online')
            )

    @api.depends('company_id')
    def _compute_vram(self):
        """
        Compute total and available VRAM for each cluster.

        This method sums the VRAM across all nodes in the cluster.
        Available VRAM only considers nodes that are online.

        Note: This uses the total_vram_gb field from gpu.node, which must
        be computed from the gpus JSON field.
        """
        for cluster in self:
            # Search for all nodes in this cluster
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            # Sum total VRAM across all nodes
            total = 0.0
            for node in nodes:
                # Each node should have a total_vram_gb field
                # If not, fall back to calculating from gpus JSON
                if hasattr(node, 'total_vram_gb') and node.total_vram_gb:
                    total += node.total_vram_gb
                elif node.gpus:
                    # Calculate from gpus JSON
                    try:
                        gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                        for gpu in gpus:
                            total += gpu.get('memory_mb', 0) / 1024.0  # Convert MB to GB
                    except (json.JSONDecodeError, TypeError, KeyError):
                        pass

            cluster.total_vram_gb = total

            # Sum available VRAM from online nodes only
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
        """
        Compute the total number of physical GPUs in the cluster.

        This method sums the GPU count from each node's gpus JSON field.
        """
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
        """
        Compute cluster-level token economics metrics.

        This method aggregates the tokens served and earnings from all
        nodes in the cluster.
        """
        for cluster in self:
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])
            cluster.total_tokens_served = sum((node.tokens_served or 0) for node in nodes)
            cluster.total_earnings = sum((node.token_earnings or 0.0) for node in nodes)

    # =========================================================================
    # 9. WIREGUARD KEY MANAGEMENT
    # =========================================================================

    def _generate_wireguard_config(self):
        """
        Generate a WireGuard configuration for a new node.

        This method generates a new WireGuard key pair for the controller
        and returns the configuration that a client node needs to connect.

        Returns:
            dict: Contains 'private_key', 'public_key', and 'config' string

        The config string is in WireGuard's INI format and can be written
        directly to /etc/wireguard/wg0.conf on the client node.
        """
        self.ensure_one()

        # Import the wgconfig module if available
        # In production, this should use the Python WireGuard library
        try:
            import subprocess
            import base64

            # Generate a new key pair using wg(8)
            # This is a fallback; in production, consider using the
            # wireguard-tools Python bindings or wgconfig library
            privkey_proc = subprocess.run(
                ['wg', 'genkey'],
                capture_output=True,
                text=True,
                check=True
            )
            private_key = privkey_proc.stdout.strip()

            pubkey_proc = subprocess.run(
                ['wg', 'pubkey'],
                input=private_key,
                capture_output=True,
                text=True,
                check=True
            )
            public_key = pubkey_proc.stdout.strip()

            # Save the controller's public key for future reference
            self.write({
                'wireguard_controller_private_key': private_key,
                'wireguard_controller_public_key': public_key,
            })

            # Build the WireGuard config
            config = f"""[Interface]
Address = {self.wireguard_mesh_subnet.split('/')[0]}1/24
ListenPort = {self.wireguard_listen_port}
PrivateKey = {private_key}

# This is the controller's configuration. Client nodes will have their own.
# The controller acts as the central hub for the WireGuard mesh.
"""

            return {
                'private_key': private_key,
                'public_key': public_key,
                'config': config,
            }

        except (ImportError, subprocess.CalledProcessError) as e:
            _logger.error(f"Failed to generate WireGuard keys: {e}")
            raise UserError(_("Failed to generate WireGuard keys. "
                              "Please ensure WireGuard is installed."))

    def _generate_gpustack_token(self, node_id=None):
        """
        Generate a GPUStack token for a new node.

        This method calls the GPUStack API to generate a registration token
        for a new worker node. The token is used by the GPUStack worker to
        authenticate with the server.

        Args:
            node_id (int, optional): The ID of the node requesting the token.

        Returns:
            str: The GPUStack token, or None if generation fails.

        Note:
            This requires the GPUStack server to be reachable and the
            API key to be valid.
        """
        self.ensure_one()

        if not self.gpustack_server_url or not self.gpustack_api_key:
            _logger.warning("GPUStack server URL or API key not configured")
            return None

        try:
            # Call GPUStack API to generate a worker token
            # GPUStack API endpoint: POST /api/v1/workers/token
            url = f"{self.gpustack_server_url.rstrip('/')}/api/v1/workers/token"
            headers = {
                'Authorization': f'Bearer {self.gpustack_api_key}',
                'Content-Type': 'application/json',
            }
            payload = {}
            if node_id:
                payload['node_id'] = str(node_id)

            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()
            return result.get('token')

        except requests.exceptions.RequestException as e:
            _logger.error(f"Failed to generate GPUStack token: {e}")
            return None

    # =========================================================================
    # 10. NETWORK SCANNING
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
                # Use nmap to scan for machines with port 8069 (Odoo) open
                # This is a simple heuristic; production should use a more
                # sophisticated approach like scanning for the GPU agent
                _logger.info(f"Scanning subnet {subnet_cidr} for GPU nodes...")

                # Simplified scan: just ping sweep and check for SSH
                # In production, this would use the GPU agent's discovery
                # protocol or use nmap with custom scripts
                cmd = [
                    'nmap', '-sn', subnet_cidr,
                    '--min-hostgroup', '64',
                    '--max-rtt-timeout', '2000ms'
                ]

                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    # Parse the output to extract IPs
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

    def _install_agent_on_host(self, ip_address, pool='internal', ssh_user='root', ssh_key=None):
        """
        Install the GPU agent on a remote host.

        This method attempts to SSH into a remote host and verify the
        connection. It does not install the agent automatically unless
        a dedicated installer script is available.

        Args:
            ip_address (str): The IP address of the remote host.
            pool (str): The pool to assign the node to ('internal' or 'public').
            ssh_user (str): SSH user for remote access.
            ssh_key (str, optional): SSH private key path for authentication.

        Returns:
            dict: Status of the installation.
        """
        self.ensure_one()

        _logger.info(
            "Attempting remote install of GPU agent on %s as %s in pool %s",
            ip_address, ssh_user, pool
        )

        try:
            import shutil
            import subprocess

            ssh_bin = shutil.which('ssh')
            if not ssh_bin:
                raise UserError(_(
                    "SSH client not found on the controller machine. "
                    "Install OpenSSH client and try again."
                ))

            cmd = [ssh_bin, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no']
            if ssh_key:
                cmd.extend(['-i', ssh_key])
            cmd.append(f"{ssh_user}@{ip_address}")
            cmd.append('echo NETTRADES GPU agent install check')

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if result.returncode != 0:
                _logger.warning(
                    "Remote SSH check failed for %s: %s",
                    ip_address, result.stderr.strip() or result.stdout.strip()
                )
                return {
                    'status': 'failed',
                    'message': (
                        'Unable to reach remote host via SSH. '
                        'Verify connectivity, credentials, and that SSH is enabled.'
                    ),
                    'ip': ip_address,
                }

            _logger.info("Remote host %s is reachable via SSH", ip_address)
            return {
                'status': 'pending',
                'message': (
                    'Remote host is reachable. Please run the NETTRADES GPU agent '
                    'installer on the host or configure an automated deployment script.'
                ),
                'ip': ip_address,
                'ssh_user': ssh_user,
            }

        except subprocess.TimeoutExpired:
            _logger.warning("SSH connection timed out to %s", ip_address)
            return {
                'status': 'failed',
                'message': 'SSH connection timed out. Please verify network connectivity.',
                'ip': ip_address,
            }
        except FileNotFoundError:
            return {
                'status': 'failed',
                'message': 'SSH client executable not found. Please install OpenSSH.',
                'ip': ip_address,
            }
        except Exception as e:
            _logger.warning("Remote install check failed: %s", e)
            return {
                'status': 'failed',
                'message': str(e),
                'ip': ip_address,
            }

    # =========================================================================
    # 11. CLUSTER MANAGEMENT ACTIONS
    # =========================================================================

    def action_remove_cluster(self):
        """
        Remove this GPU cluster and all its nodes.

        This method deletes all GPU nodes in the cluster and then deletes
        the cluster itself. It does not remove the WireGuard configuration
        from the nodes; that must be done separately.

        Returns:
            dict: Action result for the Odoo UI.

        Note:
            This is a destructive operation and should be used with caution.
        """
        self.ensure_one()

        # Count nodes before deletion
        node_count = self.env['gpu.node'].search_count([
            ('cluster_id', '=', self.id)
        ])

        # Delete all nodes in the cluster
        self.env['gpu.node'].search([
            ('cluster_id', '=', self.id)
        ]).unlink()

        # Delete the cluster itself
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
    # 12. CONSTRAINTS AND VALIDATION
    # =========================================================================

    @api.constrains('wireguard_mesh_subnet')
    def _check_wireguard_subnet(self):
        """
        Validate the WireGuard subnet format.

        Ensures the subnet is a valid CIDR notation (e.g., 10.100.0.0/24).
        """
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

    @api.constrains('gpustack_server_url')
    def _check_gpustack_url(self):
        """
        Validate the GPUStack server URL format.

        Ensures the URL starts with http:// or https://.
        """
        for cluster in self:
            if cluster.gpustack_server_url and not cluster.gpustack_server_url.startswith(('http://', 'https://')):
                raise ValidationError(_(
                    "GPUStack server URL must start with http:// or https://"
                ))

    # =========================================================================
    # 13. CRON JOBS
    # =========================================================================

    def _cron_health_watchdog(self):
        """
        Scheduled cron job to check the health of all GPU clusters.

        This method runs periodically to:
        1. Check the status of all GPU nodes
        2. Update node statuses based on last_seen timestamps
        3. Alert administrators of offline nodes

        Called by the Odoo cron system.
        """
        _logger.info("Running GPU cluster health watchdog")

        # Get all active clusters
        clusters = self.search([])

        for cluster in clusters:
            # Check each node in the cluster
            nodes = self.env['gpu.node'].search([
                ('cluster_id', '=', cluster.id)
            ])

            # If a node hasn't been seen in 5 minutes, mark it as offline
            threshold = datetime.now() - timedelta(minutes=5)

            for node in nodes:
                if node.last_seen and node.last_seen < threshold:
                    if node.status == 'online':
                        _logger.warning(
                            f"Node {node.name} ({node.hostname}) appears offline. "
                            f"Last seen: {node.last_seen}"
                        )
                        node.status = 'offline'

                    # Could send a notification here
                    # self.env['user.notification'].create({...})

        _logger.info("GPU cluster health watchdog completed")

    # ==============

    def _revoke_wireguard_peer(self, node):
        """
        Revoke a WireGuard peer from the cluster.

        This method updates the node record so that it is excluded from
        WireGuard peer synchronization and clears node-specific WireGuard
        registration state.
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
    # 14. API FOR EXTERNAL ACCESS
    # =========================================================================

    def get_peers_for_wireguard(self):
        """
        Get all nodes in this cluster for WireGuard peer configuration.

        This method returns a list of all nodes in the cluster with their
        WireGuard public keys and assigned IPs, suitable for the WireGuard
        peer manager to use.

        Returns:
            list: A list of dictionaries with 'public_key', 'allowed_ips',
                and 'endpoint' keys.

        Called by the WireGuard peer manager daemon via the /api/v1/gpu/peers
        endpoint.
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