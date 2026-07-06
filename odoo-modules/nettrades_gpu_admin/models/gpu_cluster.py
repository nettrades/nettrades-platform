# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class GPUCluster(models.Model):
    _name = 'gpu.cluster'
    _description = 'Company GPU Cluster'
    _rec_name = 'name'

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
    )

    gpustack_server_url = fields.Char(
        string='GPUStack Server URL',
    )

    gpustack_api_key = fields.Char(
        string='GPUStack API Key',
    )

    # These fields are commented out because they reference other models
    # that may not be loaded yet.
    # registered_subnet_ids = fields.One2many(...)
    # node_ids = fields.One2many(...)
    # gpu_ids = fields.Many2many(...)

