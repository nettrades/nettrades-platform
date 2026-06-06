# -*- coding: utf-8 -*-
# Section H – GPU Cluster model (nettrades_gpu_admin)
from odoo import fields, models, api

class GPUCluster(models.Model):
    _name = 'gpu.cluster'
    _description = 'Company GPU Cluster'

    company_id = fields.Many2one('res.company', string='Company', required=True,
                                  default=lambda self: self.env.company)
    name = fields.Char(string='Cluster Name', required=True, default='Default Cluster')
    trust_mode = fields.Selection([
        ('company_multi_gpu', 'Trusted – Multi-GPU'),
        ('company_single_gpu', 'Trusted – Single GPU'),
        ('public_untrusted', 'Untrusted – Public Sharing'),
    ], string='Trust Mode', required=True, default='company_multi_gpu', help='Determines network topology and container isolation.')

    # WireGuard configuration
    wireguard_mesh_subnet = fields.Char(string='WireGuard Mesh Subnet', default='10.100.0.0/24')
    wireguard_controller_public_key = fields.Char(string='Controller Public Key', readonly=True)
    wireguard_controller_private_key = fields.Char(string='Controller Private Key', readonly=True)
    wireguard_listen_port = fields.Integer(string='WireGuard Listen Port', default=51820)
    controller_endpoint = fields.Char(string='Controller Endpoint', help='Public IP:port for worker WireGuard connections')

    # Auto-detection
    registered_subnet_ids = fields.One2many('gpu.cluster.subnet', 'cluster_id', string='Registered IP Subnets')

    # GPU Nodes
    node_ids = fields.One2many('gpu.node', 'cluster_id', string='GPU Nodes')
    node_count = fields.Integer(string='Node Count', compute='_compute_node_count')
    online_node_count = fields.Integer(string='Online Nodes', compute='_compute_node_count')

    # Status
    status = fields.Selection([
        ('offline', 'Offline'),
        ('online', 'Online'),
        ('degraded', 'Degraded'),
    ], string='Status', compute='_compute_status', store=True)

    # Capacity
    total_vram_gb = fields.Float(string='Total VRAM (GB)', compute='_compute_vram')
    available_vram_gb = fields.Float(string='Available VRAM (GB)', compute='_compute_vram')
    total_gpu_count = fields.Integer(string='Total GPUs', compute='_compute_gpu_count')

    # Earnings
    total_tokens_served = fields.Integer(string='Total Tokens Served', compute='_compute_earnings')
    total_earnings = fields.Float(string='Total Earnings', compute='_compute_earnings',
                                   currency_field='company_id.currency_id')

    # GPUStack integration
    gpustack_server_url = fields.Char(string='GPUStack Server URL')
    gpustack_api_key = fields.Char(string='GPUStack API Key')

    # ---- Fine-Tuning transient fields (wizard) ----
    dataset_id = fields.Many2one('ft.dataset', string='Dataset')
    base_model = fields.Char(string='Base Model', default='deepseek-ai/DeepSeek-R1-Distill-Qwen-14B')
    training_mode = fields.Selection([
        ('multi', 'Multi-GPU (Axolotl)'),
        ('single', 'Single-GPU (Unsloth)'),
    ], default='multi')
    gpu_ids = fields.Many2many('gpu.node', string='GPUs for Training',
                               domain="[('cluster_id','=',id),('pool','=','internal')]")

    # ---- Computed fields ----
    @api.depends('node_ids.status')
    def _compute_status(self):
        for cluster in self:
            nodes = cluster.node_ids
            total = len(nodes)
            online = len(nodes.filtered(lambda n: n.status == 'online'))
            if total == 0:
                cluster.status = 'offline'
            elif online == total:
                cluster.status = 'online'
            elif online > 0:
                cluster.status = 'degraded'
            else:
                cluster.status = 'offline'

    @api.depends('node_ids.status')
    def _compute_node_count(self):
        for cluster in self:
            nodes = cluster.node_ids
            cluster.node_count = len(nodes)
            cluster.online_node_count = len(nodes.filtered(lambda n: n.status == 'online'))

    @api.depends('node_ids.gpus', 'node_ids.status')
    def _compute_vram(self):
        for cluster in self:
            cluster.total_vram_gb = sum(n.total_vram_gb for n in cluster.node_ids)
            cluster.available_vram_gb = sum(n.total_vram_gb for n in cluster.node_ids.filtered(lambda n: n.status == 'online'))

    @api.depends('node_ids.gpus')
    def _compute_gpu_count(self):
        for cluster in self:
            cluster.total_gpu_count = sum(len(node.gpus or []) for node in cluster.node_ids)

    @api.depends('node_ids.tokens_served', 'node_ids.token_earnings')
    def _compute_earnings(self):
        for cluster in self:
            cluster.total_tokens_served = sum(cluster.node_ids.mapped('tokens_served'))
            cluster.total_earnings = sum(cluster.node_ids.mapped('token_earnings'))

    # ---- Actions ----
    def action_scan_network(self):
        """Trigger network discovery scan."""
        return {
            'type': 'ir.actions.client',
            'tag': 'gpu_network_scan',
            'target': 'new',
            'context': {'default_cluster_id': self.id},
        }

    def action_generate_wireguard_keys(self):
        """Generate a new WireGuard keypair for the controller."""
        import subprocess
        privkey = subprocess.run(['wg', 'genkey'], capture_output=True, text=True).stdout.strip()
        pubkey = subprocess.run(['wg', 'pubkey'], input=privkey, capture_output=True, text=True).stdout.strip()
        self.write({
            'wireguard_controller_private_key': privkey,
            'wireguard_controller_public_key': pubkey,
        })

    def action_start_finetune(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fine-Tuning',
            'res_model': 'ft.dataset',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_cluster_id': self.id},
        }

    # ---- Autonomous methods ----
    def _cron_high_utilisation_alert(self):
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        for cluster in self.search([('trust_mode', 'in', ['company_multi_gpu', 'company_single_gpu'])]):
            nodes = cluster.node_ids.filtered(lambda n: n.pool == 'internal')
            if not nodes:
                continue
            high_nodes = nodes.filtered(lambda n: n.gpu_utilisation_pct and n.gpu_utilisation_pct > 90)
            if len(high_nodes) == len(nodes):
                existing = self.env['mail.activity'].search([
                    ('res_model', '=', 'gpu.cluster'),
                    ('res_id', '=', cluster.id),
                    ('activity_type_id', '=', activity_type.id),
                    ('date_deadline', '>=', fields.Date.today()),
                ], limit=1)
                if not existing:
                    cluster.activity_schedule(
                        activity_type_id=activity_type.id,
                        summary="GPU utilisation consistently high – consider adding a node or enabling public sharing",
                        note=f"All {len(nodes)} internal GPU nodes are above 90 % utilisation.",
                        date_deadline=fields.Date.today(),
                    )