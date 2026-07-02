# Section F.2 - Extends res.partner with onboarding fields and a completeness score
# Add-on 1: Smart Onboarding & Profile Enhancement
# Purpose: Simplify registration; help users build complete profiles; allow import from LinkedIn/GitHub.
# F2 Features
#     Role detection from email domain (e.g., @company.com -> Company) or initial action (upload CV -> Job Seeker).
#     Profile completeness wizard with step-by-step forms and progress indicator.
#     CV parsing using AI (via LangGraph) to extract skills, experience, and summary.
#     One-click import from LinkedIn, GitHub, Upwork (OAuth).

from odoo import fields, models, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    onboarding_step = fields.Selection([
        ('new', 'New'),
        ('role', 'Role Selection'),
        ('basic', 'Basic Info'),
        ('skills', 'Skills & Experience'),
        ('complete', 'Complete'),
    ], default='new', help="Tracks the user's progress through the onboarding wizard.")
    profile_completeness = fields.Integer(compute='_compute_completeness', store=True, help="Percentage of profile fields that are filled (0-100).)

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