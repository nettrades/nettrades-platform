# -*- coding: utf-8 -*-
from odoo import fields, models

class NettradesField(models.Model):
    _name = 'nettrades.field'
    _description = 'Professional Field'

    name = fields.Char('Name', required=True, translate=True)
    description = fields.Text('Description')