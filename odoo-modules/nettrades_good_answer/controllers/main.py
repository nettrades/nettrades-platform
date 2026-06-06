from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class GoodAnswerController(http.Controller):

    @http.route('/api/v1/good_answer/vote', type='json', auth='user', methods=['POST'])
    def vote(self, **kwargs):
        answer_id = kwargs.get('answer_id')
        answer_model = kwargs.get('answer_model')
        answerer_id = kwargs.get('answerer_id')
        field_id = kwargs.get('field_id')
        question = kwargs.get('question', '')
        if not all([answer_id, answer_model, answerer_id]):
            return {'error': 'Missing parameters'}

        # Infer field if not provided
        if not field_id:
            field_id = self._infer_field(question) or self._get_def_field_id()
            if not field_id:
                return {'error': 'Could not determine professional field.'}

        user = request.env.user.partner_id
        try:
            user.action_good_answer(answer_id, answer_model, answerer_id, field_id)
            return {'success': True}
        except Exception as e:
            _logger.error(f"Vote failed: {e}")
            return {'error': str(e)}

    def _infer_field(self, question):
        if not question:
            return None
        # Use LangGraph classification (as in ask_someone)
        field = self._call_llm_for_field(question)
        return field.id if field else None

    def _call_llm_for_field(self, question):
        import requests
        url = request.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url', 'http://langgraph:8000/invoke')
        api_key = request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        payload = {"input": {"messages": [{"role": "user", "content": f"Which professional field does this question belong to? Question: {question}"}]}}
        headers = {'x-api-key': api_key} if api_key else {}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                field_name = data.get('analysis','').strip().lower()
                return request.env['nettrades.field'].search([('name','ilike',field_name)], limit=1)
        except Exception:
            pass
        return None

    def _get_def_field_id(self):
        return request.env['ir.config_parameter'].sudo().get_param('ask_someone.default_field_id')