# -*- coding: utf-8 -*-
# Minimal GPU Node Model for testing

from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


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