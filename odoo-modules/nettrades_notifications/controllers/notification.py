# Section F.8 - In-app notification centre, reviews, and dispute workflow.
from odoo import http
from odoo.http import request

class NotificationController(http.Controller):
    @http.route('/api/notifications', type='json', auth='user')
    def list_notifications(self):
        notifs = request.env['user.notification'].search([
            ('partner_id', '=', request.env.user.partner_id.id),
            ('read', '=', False)
        ])
        return [{'id': n.id, 'title': n.title, 'body': n.body} for n in notifs]