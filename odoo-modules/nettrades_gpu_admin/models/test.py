# -*- coding: utf-8 -*-
from odoo import models, fields

class GpuTest(models.Model):
    _name = 'gpu.test'
    _description = 'GPU Test'

    name = fields.Char(string='Name')