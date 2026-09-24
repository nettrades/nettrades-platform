# -*- coding: utf-8 -*-
# FILE: odoo-modules/nettrades_onboarding/models/res_partner_experience.py
#
# Work history entries attached to a partner. One2many from res.partner;
# the AI import wizard populates these from LinkedIn/GitHub/CV parsing .

from odoo import fields, models


class ResPartnerExperience(models.Model):
    _name = 'res.partner.experience'
    _description = 'Partner Work Experience'
    _order = 'partner_id, date_start desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_name = fields.Char(string='Company', required=True)
    job_title = fields.Char(string='Job Title', required=True)
    location = fields.Char(string='Location')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date', help="Leave empty for current role.")
    is_current = fields.Boolean(string='Current Role', default=False)
    description = fields.Text(string='Description')