# -*- coding: utf-8 -*-
from odoo import fields, models

class GPUNode(models.Model):
    _name = 'gpu.node'
    _description = 'GPU Node'

    cluster_id = fields.Many2one('gpu.cluster', string='Cluster', required=True, ondelete='cascade')
    name = fields.Char(string='Node Name', required=True)
    hostname = fields.Char()
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
        ('degraded', 'Degraded'),
        ('maintenance', 'Maintenance'),
    ], default='offline')
    # Add other fields as needed (gpus, vram, etc.)