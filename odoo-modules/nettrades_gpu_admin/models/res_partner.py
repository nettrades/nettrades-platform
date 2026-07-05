# -*- coding: utf-8 -*-
# 
# FILE: odoo-modules/nettrades_gpu_admin/models/res_partner.py
# 
# PURPOSE:
#   Extends res.partner with GPU-related fields.
#   This is defined in nettrades_gpu_admin to avoid circular dependency
#   with nettrades_core.
#
#  Moved gpu_nodes from nettrades_core/models/res_partner.py to nettrades_gpu_admin/models/res_partner.py to eliminatecircular dependency. 
#
# RELATIONSHIPS:
#   - gpu_nodes: One2many to gpu.node (GPU nodes owned by this partner)
# 

from odoo import fields, models


class ResPartner(models.Model):
    """
    Extend res.partner with GPU node relationship.
    """
    _inherit = 'res.partner'

    gpu_nodes = fields.One2many(
        'gpu.node',
        'partner_id',
        string='GPU Nodes',
        help="GPU nodes owned by this partner."
    )