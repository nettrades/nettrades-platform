# -*- coding: utf-8 -*-
# Section A-F – Simple skill model used for Many2many tagging on partner profiles.
from odoo import fields, models

class NettradesSkill(models.Model):
    """
    Represents a skill (e.g. "Python", "Django") that can be linked to a partner.
    Used for AI matching and search filters.
    """
    _name = 'nettrades.skill'
    _description = 'Skill'

    name = fields.Char('Name', required=True, help="Skill name, e.g. 'Python'.")
    # partner_ids = fields.Many2many('res.partner', string='Partners')