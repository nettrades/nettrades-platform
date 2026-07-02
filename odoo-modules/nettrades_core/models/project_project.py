# -*- coding: utf-8 -*-
# Section A-F - Forgejo repo creation and review actions, no n8n.
import json, logging, requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ProjectProject(models.Model):
    """
    Adds Forgejo Git repository links and a budget field.
    Provides actions to create a repository and to leave a review.
    """
    _inherit = 'project.project'

    forgejo_repo_url = fields.Char(
        string="Forgejo Repository URL",
        readonly=True,
        help="URL of the automatically created Git repository."
    )
    forgejo_clone_url = fields.Char(
        string="Clone URL",
        readonly=True,
        help="HTTPS clone URL for the repository."
    )
    budget = fields.Float(
        string="Budget",
        help="Total budget for the project, used for milestone payments."
    )

    def action_create_forgejo_repo(self):
        """Create a repository directly via the Forgejo API."""
        self.ensure_one()
        forgejo_url = self.env['ir.config_parameter'].sudo().get_param(
            'forgejo_api_url', 'https://git.nettrades.ai/api/v1')
        token = self.env['ir.config_parameter'].sudo().get_param(
            'forgejo_api_token', '')
        headers = {'Authorization': f'token {token}', 'Content-Type': 'application/json'}
        payload = {
            'name': self.name.lower().replace(' ', '-'),
            'private': True,
            'description': self.name,
        }
        try:
            resp = requests.post(
                f"{forgejo_url}/orgs/nettrades/repos",
                json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            self.write({
                'forgejo_repo_url': data.get('html_url'),
                'forgejo_clone_url': data.get('clone_url'),
            })
            _logger.info("Forgejo repo created for project %s", self.id)
        except requests.Timeout:
            raise UserError(_("Repository creation timed out."))
        except requests.ConnectionError:
            raise UserError(_("Cannot reach Forgejo server."))
        except requests.HTTPError as e:
            _logger.error("Forgejo API error: %s", e)
            raise UserError(_("Forgejo repository creation failed."))
        except Exception as e:
            _logger.error("Forgejo repo creation failed: %s", e)
            raise UserError(_("Could not create repository."))

    def action_leave_review(self):
        """
        Open a wizard to leave a review for the project.
        The review is linked to the project and the project's assigned user.
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Leave Review',
            'res_model': 'nettrades.review',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
                'default_reviewed_partner_id': self.user_id.id,
                'default_reviewer_id': self.env.user.partner_id.id,
            }
        }