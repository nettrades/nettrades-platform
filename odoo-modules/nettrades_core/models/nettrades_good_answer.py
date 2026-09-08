# -*- coding: utf-8 -*-
from odoo import fields, models, api

class NettradesGoodAnswer(models.Model):
    _name = 'nettrades.good_answer'
    _description = 'Good Answer'
    _rec_name = 'question'

    question = fields.Text(string='Question', required=True)
    answer = fields.Text(string='Answer', required=True)
    user_id = fields.Many2one('nettrades.user', string='User', required=True)
    model_used = fields.Char(string='Model Used')
    votes_positive = fields.Integer(string='Positive Votes', default=0)
    votes_negative = fields.Integer(string='Negative Votes', default=0)
    is_verified = fields.Boolean(string='Verified', default=False)
    create_date = fields.Datetime(string='Created', readonly=True)
    write_date = fields.Datetime(string='Updated', readonly=True)