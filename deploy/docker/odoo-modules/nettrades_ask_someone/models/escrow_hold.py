from odoo import fields, models

class EscrowHold(models.Model):
    _name = 'escrow.hold'
    _description = 'Escrow Hold'

    session_id = fields.Many2one('expert.session', required=True, ondelete='cascade')
    amount = fields.Float()
    currency = fields.Char(default='USD')
    provider = fields.Char(default='stripe')
    provider_hold_id = fields.Char()
    status = fields.Selection([('held','Held'),('released','Released')], default='held')
    released_at = fields.Datetime()