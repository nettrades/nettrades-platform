# -*- coding: utf-8 -*-
from odoo import fields, models, api

class GPUCluster(models.Model):
    _name = 'gpu.cluster'
    _description = 'Company GPU Cluster'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    name = fields.Char(required=True, default='Default Cluster')
    trust_mode = fields.Selection([
        ('company_multi_gpu', 'Trusted – Multi-GPU'),
        ('company_single_gpu', 'Trusted – Single GPU'),
        ('public_untrusted', 'Untrusted – Public Sharing'),
    ], required=True, default='company_multi_gpu')

    wireguard_mesh_subnet = fields.Char(default='10.100.0.0/24')
    wireguard_controller_public_key = fields.Char(readonly=True)
    wireguard_controller_private_key = fields.Char(readonly=True)
    wireguard_listen_port = fields.Integer(default=51820)
    controller_endpoint = fields.Char()

    # Auto-detection (commented until gpu.cluster.subnet is ready)
    # registered_subnet_ids = fields.One2many('gpu.cluster.subnet', 'cluster_id')

    # GPUStack integration
    gpustack_server_url = fields.Char()
    gpustack_api_key = fields.Char()

    # Temporary: all fields that depend on gpu.node are removed
    # They will be added back later via upgrade or computed fields

    # Computed fields (no stored One2many)
node_count = fields.Integer(string='Node Count', compute='_compute_node_count')
online_node_count = fields.Integer(string='Online Nodes', compute='_compute_node_count')
total_vram_gb = fields.Float(string='Total VRAM (GB)', compute='_compute_vram')
available_vram_gb = fields.Float(string='Available VRAM (GB)', compute='_compute_vram')
total_gpu_count = fields.Integer(string='Total GPUs', compute='_compute_gpu_count')

@api.depends()
def _compute_node_count(self):
    for cluster in self:
        nodes = self.env['gpu.node'].search([('cluster_id', '=', cluster.id)])
        cluster.node_count = len(nodes)
        cluster.online_node_count = len(nodes.filtered(lambda n: n.status == 'online'))

@api.depends()
def _compute_vram(self):
    for cluster in self:
        nodes = self.env['gpu.node'].search([('cluster_id', '=', cluster.id)])
        total = sum(node.total_vram_gb for node in nodes if hasattr(node, 'total_vram_gb'))
        online_total = sum(node.total_vram_gb for node in nodes if node.status == 'online' and hasattr(node, 'total_vram_gb'))
        cluster.total_vram_gb = total
        cluster.available_vram_gb = online_total

@api.depends()
def _compute_gpu_count(self):
    for cluster in self:
        nodes = self.env['gpu.node'].search([('cluster_id', '=', cluster.id)])
        gpu_count = sum(len(node.gpus or []) for node in nodes if hasattr(node, 'gpus'))
        cluster.total_gpu_count = gpu_count

gpu_ids = fields.Many2many('gpu.node', string='GPUs for Training')  # Many2many field for training GPUs