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
        # If field_id not provided, infer from question (or answer context)
        if not field_id:
            question = kwargs.get('question') or self._get_question_text(answer_model, answer_id)
            field_id = self._infer_field(question)
            if not field_id:
                return {'error': 'Could not determine professional field. Please specify.'}
        user = request.env.user.partner_id
        try:
            user.action_good_answer(answer_id, answer_model, answerer_id, field_id)
            return {'success': True}
        except Exception as e:
            _logger.error(f"Vote failed: {e}")
            return {'error': str(e)}

    def _get_question_text(self, model_name, res_id):
        if model_name == 'ai.assistant.message':
            msg = request.env[model_name].browse(res_id)
            return msg.user_message or ''
        return ''

    def _infer_field(self, question):
        """Call LangGraph (or LLM provider) to classify the question into a nettrades.field."""
        if not question:
            return False
        # Simplified: use AI provider to classify
        llm_provider = request.env['llm.provider'].search([], limit=1)
        if not llm_provider:
            return False
        import requests
        # Use LangGraph agent endpoint
        webhook_url = request.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url', 'http://langgraph:8000/invoke')
        payload = {"input": {"messages": [{"role": "user", "content": f"Which professional field does this question belong to? Question: {question}"}]}}
        headers = {'x-api-key': request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')}
        try:
            resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # parse response – assume field name returned
                field_name = data.get('analysis', '').strip().lower()
                field = request.env['nettrades.field'].search([('name', 'ilike', field_name)], limit=1)
                if field:
                    return field.id
        except Exception:
            pass
        # fallback: return first field
        return request.env['nettrades.field'].search([], limit=1).id