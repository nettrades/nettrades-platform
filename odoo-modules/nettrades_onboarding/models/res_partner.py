# Section F.2 - Extends res.partner with onboarding fields and a completeness score
#
# FILE: odoo-modules/nettrades_onboarding/models/res_partner.py
#
# Add-on 1: Smart Onboarding & Profile Enhancement
# Purpose: Simplify registration; help users build complete profiles; allow import from LinkedIn/GitHub.
# F2 Features
#     Role detection from email domain (e.g., @company.com -> Company) or initial action (upload CV -> Job Seeker).
#     Profile completeness wizard with step-by-step forms and progress indicator.
#     CV parsing using AI (via LangGraph) to extract skills, experience, and summary.
#     One-click import from LinkedIn, GitHub, Upwork (OAuth).

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    onboarding_step = fields.Selection([
        ('new', 'New'),
        ('role', 'Role Selection'),
        ('basic', 'Basic Info'),
        ('skills', 'Skills & Experience'),
        ('complete', 'Complete'),
    ], default='new', help="Tracks the user's progress through the onboarding wizard.")

    profile_completeness = fields.Integer(
    compute='_compute_completeness',
    store=True,
    help="Percentage of profile fields that are filled (0-100)."
    )

    @api.depends('name', 'email', 'phone', 'professional_summary',
                 'skill_ids', 'experience_ids', 'resume_pdf')
    def _compute_completeness(self):
        for partner in self:
            score = 0
            if partner.name: score += 10
            if partner.email: score += 10
            if partner.phone: score += 5
            if partner.professional_summary: score += 20
            if partner.skill_ids: score += 20
            if partner.experience_ids: score += 20
            if partner.resume_pdf: score += 10
            partner.profile_completeness = min(score, 100)

    # -------------------------------------------------------------------------
    # Button actions (called from onboarding_wizard.xml)
    # -------------------------------------------------------------------------
    def action_parse_cv(self):
        """
        Extract text from the uploaded CV PDF and populate the profile.

        Called by the "Extract from CV" button on the onboarding wizard.
        Reads the PDF attached to `resume_pdf`, extracts the text, and
        (in a later iteration) will pass it to the LangGraph agent to
        fill `professional_summary` and `skill_ids` automatically.

        For now this confirms the PDF is readable and reports the
        character count. The LangGraph call is left as a TODO so the
        wizard is functional without requiring the full agent stack.

        Raises:
            UserError: if no PDF is attached or pdfplumber fails to read it.
        """
        self.ensure_one()

        if not self.resume_pdf:
            raise UserError(_("Please upload a CV (PDF) before extracting."))

        import base64
        import io
        import pdfplumber

        try:
            pdf_bytes = base64.b64decode(self.resume_pdf)
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text = "\n".join(page.extract_text() or '' for page in pdf.pages)
        except Exception as e:
            _logger.warning("CV parse failed for partner %s: %s", self.id, e)
            raise UserError(_("Could not read the PDF: %s") % str(e))

        # TODO: send `text` to the LangGraph agent and apply the response:
        #   extracted = self._call_cv_extractor(text)
        #   self.write({
        #       'professional_summary': extracted.get('summary', ''),
        #       'skill_ids': [(0, 0, {'name': s}) for s in extracted.get('skills', [])],
        #   })
        _logger.info(
            "Extracted %d characters from CV for partner %s",
            len(text), self.id,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('CV Parsed'),
                'message': _('Extracted %d characters.') % len(text),
                'type': 'success',
                'sticky': False,
            }
        }


    # -------------------------------------------------------------------------
    # Profile fields — referenced by _compute_completeness above.
    # -------------------------------------------------------------------------
    professional_summary = fields.Text(
        string='Professional Summary',
        help="Short bio shown on the user's public profile.",
    )

    skill_ids = fields.Many2many(
        'res.partner.skill',
        'res_partner_skill_rel',
        'partner_id',
        'skill_id',
        string='Skills',
    )

    experience_ids = fields.One2many(
        'res.partner.experience',
        'partner_id',
        string='Work Experience',
    )

    resume_pdf = fields.Binary(
        string='Resume (PDF)',
        attachment=True,
        help="Uploaded CV, parsed by the AI on import.",
    )