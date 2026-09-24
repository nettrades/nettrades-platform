# -*- coding: utf-8 -*-
# FILE: odoo-modules/nettrades_onboarding/models/res_partner_skill.py
#
# Skill entries attached to a partner. Declared as a standalone model so
# that the same skill text can be shared across partners and queried
# efficiently (which a simple Text field on res.partner cannot do) .

from odoo import fields, models


class ResPartnerSkill(models.Model):
    _name = 'res.partner.skill'
    _description = 'Partner Skill'
    _order = 'partner_id, sequence, name'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Skill', required=True)
    level = fields.Selection(
        [
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced'),
            ('expert', 'Expert'),
        ],
        string='Level',
        default='intermediate',
    )
    years = fields.Integer(string='Years of Experience', default=0)
    sequence = fields.Integer(default=10)