from odoo import fields, models

class UserNotification(models.Model):
    _name = 'user.notification'
    _description = 'User Notification'
    _order = 'create_date desc'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    notification_type = fields.Char(default='info')
    title = fields.Char(required=True)
    body = fields.Text()
    read = fields.Boolean(default=False)