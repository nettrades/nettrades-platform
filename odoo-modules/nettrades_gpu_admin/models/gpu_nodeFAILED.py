# -*- coding: utf-8 -*-
# Minimal GPU Node Model for testing

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

node_id = fields.Char(string='Hardware Node ID', help="...")
hostname = fields.Char(string='Hostname')
ip_address = fields.Char(string='IP Address')
uptime_hours = fields.Float(string='Uptime (hours)')
gpu_utilisation_pct = fields.Float(string='GPU Utilisation (%)')
os = fields.Char(string='Operating System')
arch = fields.Char(string='Architecture')
model = fields.Char(string='System Model')
endpoint = fields.Char(string='WireGuard Endpoint')
gpustack_worker_id = fields.Char(string='GPUStack Worker ID')
tokens_served = fields.Integer(string='Tokens Served', default=0)
token_earnings = fields.Float(string='Token Earnings', default=0.0)
reputation_score = fields.Float(string='Reputation Score', default=0.0)
scheduled_share = fields.Boolean(string='Scheduled Sharing', default=False)

tee_capabilities = fields.Json(string='TEE Capabilities')
edge_device_info = fields.Json(string='Edge Device Info')

pool = fields.Selection([...], string='Pool', default='internal')
container_runtime = fields.Selection([...], string='Container Runtime', default='docker')

class GPUNode(models.Model):
    _name = 'gpu.node'
    _description = 'GPU Node'
    _rec_name = 'name'

    cluster_id = fields.Many2one('gpu.cluster', string='Cluster', required=True, ondelete='cascade')
    name = fields.Char(string='Node Name', required=True)
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('degraded', 'Degraded'),
        ('maintenance', 'Maintenance'),
    ], string='Status', default='offline')
    last_seen = fields.Datetime(string='Last Seen')
    gpus = fields.Json(string='GPU Inventory')
    total_vram_gb = fields.Float(string='Total VRAM (GB)', compute='_compute_total_vram', store=True)
    wireguard_public_key = fields.Text(string='WireGuard Public Key')
    wireguard_assigned_ip = fields.Char(string='WireGuard Assigned IP')

    @api.depends('gpus')
    def _compute_total_vram(self):
        for node in self:
            total = 0.0
            if node.gpus:
                try:
                    import json
                    gpus = node.gpus if isinstance(node.gpus, list) else json.loads(node.gpus)
                    for gpu in gpus:
                        total += gpu.get('memory_mb', 0) / 1024.0
                except Exception:
                    pass
            node.total_vram_gb = total