# odoo-modules/nettrades_bridge/controllers/route_controller.py

from odoo import http
from odoo.http import request


class RouteController(http.Controller):

    @http.route('/api/bridge/route/decide', type='json', auth='user', methods=['POST'])
    def decide_route(self, **kwargs):
        """
        API endpoint for LangGraph agents to get a route decision.
        """
        request_type = kwargs.get('request_type', 'inference')
        request_data = kwargs.get('request_data', {})

        route_model = request.env['nettrades_bridge.route'].sudo()
        decision = route_model.get_route_for_request(request_type, request_data)

        return decision