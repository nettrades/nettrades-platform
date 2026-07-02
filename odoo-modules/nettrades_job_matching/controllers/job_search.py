# Section F.3 - Conversational job search.
import json, logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class JobSearchController(http.Controller):
    @http.route('/api/job_search', type='json', auth='user', methods=['POST'])
    def search(self, query, limit=10):
        """
        Accept a natural-language query and return matching job IDs ranked by relevance.
        The AI analyses both the query and the user's profile to find the best matches.
        """
        user = request.env.user.partner_id
        jobs = request.env['hr.job'].search([], limit=100)    # fetch all open jobs; in production use a smart domain
        job_data = [{'id': j.id, 'name': j.name, 'description': j.description or ''} for j in jobs]
        # Build prompt for LangGraph
        prompt = f"User query: {query}\nJobs: {json.dumps(job_data)}"
        result = self._call_langgraph(prompt)
        try:
            ranked_ids = json.loads(result.get('analysis', '[]'))
        except Exception:
            # Expect a JSON list of job IDs
            ranked_ids = [j['id'] for j in job_data[:limit]]
        return ranked_ids[:limit]

    def _call_langgraph(self, prompt):
        url = request.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url',
                                                                   'http://langgraph:8000/invoke')
        api_key = request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key
        import requests
        resp = requests.post(url, json={"input": {"messages": [{"role":"user","content":prompt}]}}, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()