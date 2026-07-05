# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core - Work Experience Model
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_experience.py
#
# PURPOSE:
#   This model stores a user's work experience entries. Each experience
#   belongs to a partner (user) and contains job title, company, dates,
#   and a description.
#
# RELATIONSHIPS:
#   - Many-to-one with res.partner (the user)
#
# USAGE:
#   This model is referenced by res.partner via a One2many field:
#       experience_ids = fields.One2many('nettrades.experience', 'partner_id')
#
#   The model is also used in the onboarding wizard to collect experience.
#
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class NettradesExperience(models.Model):
#   Work Experience - represents a single job or role in a user's career.
#   Each record stores the job title, company, start/end dates, and a
#    description of responsibilities and achievements.

    _name = 'nettrades.experience'
    _description = 'Work Experience'
    _order = 'start_date DESC'

    # =========================================================================
    # 1. BASIC FIELDS
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        help="The user who owns this experience record."
    )

    job_title = fields.Char(
        string='Job Title',
        required=True,
        help="The title of the role (e.g., 'Senior Python Developer')."
    )

    company = fields.Char(
        string='Company',
        required=True,
        help="The name of the company or organisation."
    )

    start_date = fields.Date(
        string='Start Date',
        required=True,
        help="The date the user started this role."
    )

    end_date = fields.Date(
        string='End Date',
        help="The date the user ended this role. If empty, this is the current role."
    )

    description = fields.Text(
        string='Description',
        help="A brief description of responsibilities, achievements, and skills used."
    )

    # =========================================================================
    # 2. COMPUTED FIELDS
    # =========================================================================

    is_current = fields.Boolean(
        string='Current Position',
        compute='_compute_is_current',
        store=True,
        help="True if this is the current job (end_date is empty)."
    )

    @api.depends('end_date')
    def _compute_is_current(self):

#        Automatically set is_current based on whether end_date is empty.

        for record in self:
            record.is_current = not bool(record.end_date)

    # =========================================================================
    # 3. CONSTRAINTS
    # =========================================================================

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        """
        Ensure that the end date is not earlier than the start date.
        """
        for record in self:
            if record.start_date and record.end_date and record.end_date < record.start_date:
                raise ValidationError(_("End date cannot be earlier than start date."))

    # =========================================================================
    # 4. OVERRIDES (optional)
    # =========================================================================

    def name_get(self):

#        Custom name_get to show job title and company.

        result = []
        for record in self:
            name = f"{record.job_title} at {record.company}"
            if record.start_date:
                name += f" ({record.start_date.year})"
            result.append((record.id, name))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100):

 #       Search by job title or company.

        args = args or []
        domain = []
        if name:
            domain = [
                '|',
                ('job_title', operator, name),
                ('company', operator, name),
            ]
        return self.search(domain + args, limit=limit).name_get()