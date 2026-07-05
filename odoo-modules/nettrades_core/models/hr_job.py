# -*- coding: utf-8 -*-
# Section A-F - AI-matching with direct LangGraph call, no n8n.
import json
import logging
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class HrJob(models.Model):
    """
    Enhancements for job postings:
    - required_skills: free-text or structured list of skills needed
    - min_years_experience: minimum experience required
    - is_freelance_project: flag indicating a freelancer gig rather than a full-time role
    - budget: project budget (only relevant for freelance projects)
    - forgejo_repo_url: link to the automatically created Git repository
    """
    _inherit = 'hr.job'

    required_skills = fields.Text(
        string="Required Skills",
        help="Enter skills as comma-separated text. Used by the AI matching engine."
    )
    min_years_experience = fields.Integer(
        string="Minimum Years of Experience",
        help="Candidates with less experience may be filtered out by the AI."
    )
    is_freelance_project = fields.Boolean(
        string="Freelance Project",
        help="When enabled, the job is treated as a freelance gig with a budget."
    )
    budget = fields.Float(
        string="Budget",
        help="Total budget for a freelance project. Only visible when 'Freelance Project' is ticked."
    )
    forgejo_repo_url = fields.Char(
        string="Forgejo Repository URL",
        help="Automatically populated after a project repository is created via n8n."
    )

    def action_match_candidates(self):
        """
        Run AI matching synchronously.  All Odoo writes happen inside this
        transaction - if the LangGraph call fails the transaction rolls back.
        For very long matches, use the `_do_ai_matching` queue job instead.
        """
        self.ensure_one()
        self._do_ai_matching()

    def _do_ai_matching(self):
        """Core matching logic - can be called from a queue job."""
        self.ensure_one()
        url = self.env['ir.config_parameter'].sudo().get_param(
            'langgraph_invoke_url', 'http://langgraph:8000/invoke')
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'langgraph_api_key', '')
        payload = {
            "input": {"messages": [{"role": "user", "content": json.dumps({
                "intent": "match_candidates",
                "job_id": self.id,
                "job_title": self.name,
                "description": self.description or '',
                "required_skills": self.required_skills or '',
            })}]}
        }
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            result = resp.json()
        except requests.Timeout:
            raise UserError(_("The AI matching service timed out."))
        except requests.ConnectionError:
            raise UserError(_("Cannot reach the AI matching service."))
        except requests.HTTPError as e:
            _logger.error("LangGraph HTTP error: %s", e)
            raise UserError(_("AI matching service returned an error."))
        except json.JSONDecodeError:
            raise UserError(_("Invalid response from AI matching service."))

        # Parse LangGraph output - expect a JSON list of matches
        matches = json.loads(result.get('analysis', '[]'))
        for match in matches:
            self.env['crm.lead'].create({
                'name': f"Match for {self.name}: {match.get('candidate_name', 'Unknown')}",
                'partner_id': match.get('partner_id'),
                'description': match.get('reasoning', ''),
            })

    def action_match_candidates_async(self):
        """Enqueue matching as a background job."""
        self.ensure_one()
        self.with_delay()._do_ai_matching()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Matching started',
                'message': 'AI matching is running in the background.',
                'type': 'info',
            }
        }