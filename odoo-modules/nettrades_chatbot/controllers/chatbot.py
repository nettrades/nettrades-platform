# Section F.7 – Floating AI chatbot widget.
import json, logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class ChatbotController(http.Controller):
    @http.route('/chatbot/message', type='json', auth='user', methods=['POST'])
    def message(self, message):
        url = request.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url',
                                                                   'http://langgraph:8000/invoke')
        api_key = request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key
        import requests
        resp = requests.post(url, json={"input": {"messages": [{"role":"user","content":message}]}},
                             headers=headers, timeout=30)
        reply = "Sorry, I couldn't process your request."
        if resp.ok:
            data = resp.json()
            reply = data.get('analysis', reply)
        # Broadcast reply via Odoo bus
        request.env['bus.bus'].sendone('chatbot', {'message': reply})
        return {'success': True, 'reply': reply}