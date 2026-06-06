from odoo import fields, models

class ExpertAgreement(models.Model):
    _name = 'expert.agreement'
    _description = 'Expert Agreement'

    partner_id = fields.Many2one('res.partner', required=True)
    version = fields.Char(required=True)
    signed_at = fields.Datetime(default=fields.Datetime.now)