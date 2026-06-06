from odoo import models, fields
import requests

class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    cover_letter_draft = fields.Text(readonly=True)

    def action_quick_apply(self):
        self.ensure_one()
        # Generate cover letter via LangGraph
        job = self.job_id
        user = self.env.user.partner_id
        prompt = f"Write a cover letter for {job.name}. Skills: {user.skills}."
        url = self.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url',
                                                                'http://langgraph:8000/invoke')
        api_key = self.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key
        resp = requests.post(url, json={"input": {"messages": [{"role":"user","content":prompt}]}},
                             headers=headers, timeout=30)
        if resp.ok:
            self.cover_letter_draft = resp.json().get('analysis', '')
        else:
            self.cover_letter_draft = "Could not generate cover letter."