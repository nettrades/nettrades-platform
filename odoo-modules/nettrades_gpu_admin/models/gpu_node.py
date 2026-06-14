# -*- coding: utf-8 -*-
# =============================================================================
# Section H – GPU Node model (nettrades_gpu_admin)
# =============================================================================
# This model represents a single GPU-equipped machine registered with a
# company's GPU cluster.  Every field that is set by the agent during
# registration is marked `readonly=True` to prevent manual tampering.
#
# Features added:
#   - Pool assignment (internal / public) with macOS restriction
#   - Container runtime selection (gVisor preferred, Docker fallback)
#   - Operating system auto-detection (linux / windows / darwin)
#   - Hardware-backed Confidential Computing (TEE) capabilities (JSON)
#   - Edge-device information (Jetson, Raspberry Pi, Coral TPU) (JSON)
#   - Autonomous health watchdog (creates Odoo activities for offline nodes)
#   - WireGuard peer management helper methods
#   - GPUStack worker deregistration
# =============================================================================
import json
import subprocess
import logging
from datetime import timedelta

from odoo import fields, models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GPUNode(models.Model):
    _name = 'gpu.node'
    _description = 'GPU Node'
    _order = 'pool, hostname'

    # ------------------------------------------------------------------
    # Cluster relationship
    # ------------------------------------------------------------------
    cluster_id = fields.Many2one(
        'gpu.cluster', string='Cluster', required=True, ondelete='cascade',
        help="The GPU cluster this node belongs to."
    )

    # ------------------------------------------------------------------
    # Basic identification
    # ------------------------------------------------------------------
    hostname = fields.Char(string='Hostname', required=True)
    ip_address = fields.Char(string='IP Address')
    mac_address = fields.Char(string='MAC Address')

    # ------------------------------------------------------------------
    # WireGuard identity (set by agent)
    # ------------------------------------------------------------------
    wireguard_public_key = fields.Char(
        string='WireGuard Public Key', readonly=True,
        help="Public key of this node's WireGuard interface.  Used by the "
             "peer manager to add/remove the node from the controller's wg0."
    )
    wireguard_assigned_ip = fields.Char(
        string='WireGuard Assigned IP', readonly=True,
        help="IP address assigned to this node on the WireGuard mesh.  "
             "For public nodes this is a /32 pointing only to the controller."
    )

    # ------------------------------------------------------------------
    # GPU inventory (set by agent)
    # ------------------------------------------------------------------
    gpus = fields.Json(
        string='GPU Inventory',
        help='List of GPU objects, e.g. [{"index":0,"name":"RTX 4090","memory_mb":24564}]'
    )
    total_vram_gb = fields.Float(
        string='Total VRAM (GB)', compute='_compute_vram',
        help="Sum of VRAM across all GPUs on this node."
    )
    gpu_count = fields.Integer(
        string='GPU Count', compute='_compute_vram',
        help="Number of GPUs detected on this node."
    )

    # ------------------------------------------------------------------
    # Pool assignment
    # ------------------------------------------------------------------
    pool = fields.Selection([
        ('internal', 'Pool A – Internal (Trusted Multi-GPU)'),
        ('public',   'Pool B – Public Sharing'),
    ], string='Pool Assignment', required=True, default='internal',
       help="Internal: free, company-wide, multi-GPU. "
            "Public: shared with NETTRADES marketplace, earns tokens."
    )

    # ------------------------------------------------------------------
    # Container isolation
    # ------------------------------------------------------------------
    container_runtime = fields.Selection([
        ('gvisor', 'gVisor (syscall isolation, recommended)'),
        ('docker', 'Docker (standard, trusted pools only)'),
    ], string='Container Runtime', default='gvisor',
       help="gVisor is recommended for all GPU pools. "
            "It provides syscall-level isolation without the memory-hoarding "
            "problem of VM-based solutions. "
            "Docker is available as a fallback for trusted internal pools only."
    )

    # ------------------------------------------------------------------
    # Operating system (auto-detected by agent)
    # ------------------------------------------------------------------
    os = fields.Selection([
        ('linux',   'Linux'),
        ('windows', 'Windows'),
        ('darwin',  'macOS'),
    ], string='Operating System', readonly=True,
       help="Detected automatically during agent registration. "
            "Public GPU sharing is blocked on macOS because Apple Silicon "
            "GPUs cannot be passed to Linux containers with gVisor/Kata."
    )

    # ------------------------------------------------------------------
    # Hardware-backed Confidential Computing (TEE) capabilities
    # ------------------------------------------------------------------
    tee_capabilities = fields.Json(
        string='TEE Capabilities', readonly=True,
        help=(
            "Auto-detected Confidential Computing capabilities of this node.\n"
            "Contains keys: nvidia_cc, intel_sgx, amd_sev, intel_tdx, generic_tee, has_any_tee.\n"
            "Consumer GPUs (RTX 4090, RTX 3090, Apple Silicon) will show all False – "
            "this is expected and correct.  Only data-center GPUs (H100, H200) and "
            "server CPUs with TEE extensions will report True.\n"
            "Used by the platform to prefer TEE-capable nodes for high-sensitivity workloads."
        )
    )

    # ------------------------------------------------------------------
    # Edge-device information (set by agent, new for multimodal/IoT)
    # ------------------------------------------------------------------
    edge_device_info = fields.Json(
        string='Edge Device Info', readonly=True,
        help="Auto-detected edge device capabilities (Jetson, Raspberry Pi, Coral TPU). "
             "Contains keys: jetson (model string or null), raspberry_pi (model string or null), "
             "coral_tpu (bool), is_edge_device (bool)."
    )

    # ------------------------------------------------------------------
    # GPUStack identity (set by agent)
    # ------------------------------------------------------------------
    gpustack_worker_id = fields.Char(
        string='GPUStack Worker ID', readonly=True,
        help="Unique worker identifier assigned by GPUStack during registration."
    )

    # ------------------------------------------------------------------
    # Status and health
    # ------------------------------------------------------------------
    status = fields.Selection([
        ('online',      'Online'),
        ('offline',     'Offline'),
        ('degraded',    'Degraded'),
        ('maintenance', 'Maintenance'),
    ], string='Status', default='offline')
    last_seen = fields.Datetime(string='Last Seen')
    uptime_hours = fields.Float(string='Uptime (hours)')
    gpu_utilisation_pct = fields.Float(string='GPU Utilisation %')

    # ------------------------------------------------------------------
    # Token accounting
    # ------------------------------------------------------------------
    tokens_served = fields.Integer(string='Tokens Served', default=0)
    token_earnings = fields.Float(string='Token Earnings (USD)', default=0.0)

    # ------------------------------------------------------------------
    # Security & reputation
    # ------------------------------------------------------------------
    reputation_score = fields.Float(
        string='Reputation Score', default=100.0,
        help="Starts at 100.  Decremented if attestation fails or the node "
             "misbehaves.  Nodes with low scores are deprioritised."
    )
    attestation_passed = fields.Boolean(
        string='Attestation Passed', default=True,
        help="Set by the hourly canary-inference CronJob.  False means the "
             "node may be running tampered model weights."
    )
    attestation_last_check = fields.Datetime(string='Last Attestation')
    scheduled_share = fields.Boolean(
        string='Scheduled Sharing Active', default=False,
        help="When True, this node follows the company's public sharing schedule."
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------
    @api.depends('gpus')
    def _compute_vram(self):
        for node in self:
            gpu_list = node.gpus or []
            node.total_vram_gb = sum(
                g.get('memory_mb', 0) for g in gpu_list
            ) / 1024.0
            node.gpu_count = len(gpu_list)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_remove_node(self):
        """Remove node: revoke WireGuard peer, deregister from GPUStack, delete record."""
        self.ensure_one()
        try:
            if self.wireguard_public_key:
                self._revoke_wireguard_peer()
            if self.gpustack_worker_id:
                self._deregister_gpustack()
        except Exception as e:
            raise UserError(_('Failed to fully remove node: %s') % str(e))
        self.unlink()

    def action_reassign_pool(self, new_pool):
        """
        Reassign a GPU node from one pool to another.
        Public pool is blocked on macOS because GPU isolation is not available.
        """
        self.ensure_one()
        if new_pool == self.pool:
            return

        # Block public pool for macOS
        if new_pool == 'public' and self.os == 'darwin':
            raise UserError(_(
                "Public GPU sharing is not available on macOS.\n"
                "Apple Silicon GPUs cannot be passed to Linux containers "
                "with the required isolation (gVisor/Kata).\n"
                "You can still use the NETTRADES platform via your web browser."
            ))

        self._revoke_wireguard_peer()
        if new_pool == 'public':
            self.write({'pool': 'public'})
            self._configure_hub_spoke_wireguard()
        else:
            self.write({'pool': 'internal'})
            self._configure_mesh_wireguard()
        self._register_wireguard_peer()

    def action_enable_maintenance(self):
        """Put node into maintenance mode (graceful drain)."""
        self.ensure_one()
        self.write({'status': 'maintenance'})

    def action_disable_maintenance(self):
        """Return node from maintenance to active."""
        self.ensure_one()
        self.write({'status': 'online'})

    # ------------------------------------------------------------------
    # WireGuard helper methods (call wg set on the controller)
    # ------------------------------------------------------------------
    def _register_wireguard_peer(self):
        cluster = self.cluster_id
        pubkey = self.wireguard_public_key
        if not pubkey or not cluster.controller_endpoint:
            return
        subprocess.run([
            'wg', 'set', 'wg0',
            'peer', pubkey,
            'allowed-ips', self.wireguard_assigned_ip or '10.100.0.0/32',
        ])

    def _revoke_wireguard_peer(self):
        if self.wireguard_public_key:
            subprocess.run([
                'wg', 'set', 'wg0',
                'peer', self.wireguard_public_key, 'remove',
            ])

    def _configure_hub_spoke_wireguard(self):
        """Restrict this node to only communicate with the controller."""
        controller_ip = self.cluster_id.controller_endpoint.split(':')[0]
        self.write({'wireguard_assigned_ip': controller_ip + '/32'})

    def _configure_mesh_wireguard(self):
        """Allow this node to communicate with all other nodes in the cluster."""
        subnet = self.cluster_id.wireguard_mesh_subnet
        self.write({'wireguard_assigned_ip': subnet})

    # --- GPUStack helper methods ---
    def _deregister_gpustack(self):
        server_url = self.cluster_id.gpustack_server_url
        worker_id = self.gpustack_worker_id
        import requests
        url = f'{server_url}/api/v2/workers/{worker_id}'
        headers = {'Authorization': f'Bearer {self.cluster_id.gpustack_api_key}'}
        requests.delete(url, headers=headers)

    # ------------------------------------------------------------------
    # Autonomous Health Watchdog (cron job)
    # ------------------------------------------------------------------
    def _cron_health_watchdog(self):
        """
        Runs every hour via ir.cron.
        When a node has been offline for more than 1 day, an Odoo activity
        is created for the GPU administrator – no manual monitoring needed.
        Duplicate activities for the same node on the same day are avoided.
        """
        threshold = fields.Datetime.now() - timedelta(days=1)
        offline_nodes = self.search([
            ('status', '=', 'offline'),
            ('last_seen', '<', threshold),
        ])
        activity_type = self.env.ref('mail.mail_activity_data_warning')
        for node in offline_nodes:
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'gpu.node'),
                ('res_id', '=', node.id),
                ('activity_type_id', '=', activity_type.id),
                ('date_deadline', '>=', fields.Date.today()),
            ], limit=1)
            if not existing:
                node.activity_schedule(
                    activity_type_id=activity_type.id,
                    summary=f"GPU node {node.hostname} offline since {node.last_seen}",
                    note=(
                        "The node has been unreachable for over a day. "
                        "WireGuard peer remains configured – the tunnel will "
                        "re-establish automatically when the machine restarts."
                    ),
                    date_deadline=fields.Date.today(),
                )