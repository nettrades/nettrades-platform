# -*- coding: utf-8 -*-
from odoo import models, fields, api

class NettradesReview(models.Model):
    _name = 'nettrades.review'
    _description = 'NETTRADES Review'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Review Title", required=True)
    rating = fields.Integer(string="Rating", default=5)
    comment = fields.Text(string="Comment")
    partner_id = fields.Many2one('res.partner', string="Partner", required=True)
    user_id = fields.Many2one('res.users', string="User", default=lambda self: self.env.user)
    review_date = fields.Date(string="Review Date", default=fields.Date.today)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company)

    _sql_constraints = [
        ('rating_range', 'CHECK(rating >= 1 AND rating <= 5)', 'Rating must be between 1 and 5.'),
    ]
