# -*- coding: utf-8 -*-
# =============================================================================
# SECTION H – Subnet used for auto-detection of GPU machines.
# =============================================================================

# -----------------------------------------------------------------------------
# IMPORTS – Each import MUST be on its own line for valid Python syntax.
# -----------------------------------------------------------------------------
from odoo import fields, models
import ipaddress


class GPUClusterSubnet(models.Model):
    _name = 'gpu.cluster.subnet'
    _description = 'Registered IP Subnet for Auto-Detection'

    cluster_id = fields.Many2one(
        'gpu.cluster',
        string='Cluster',
        required=True,
        ondelete='cascade'
    )

    subnet = fields.Char(
        string='CIDR Subnet',
        required=True,
        help='e.g. 192.168.1.0/24'
    )

    description = fields.Char(string='Description')

    def contains(self, ip_address):
        """Return True if the given IP address falls within this subnet."""
        try:
            return ipaddress.ip_address(ip_address) in ipaddress.ip_network(self.subnet)
        except (ValueError, TypeError):
            return False