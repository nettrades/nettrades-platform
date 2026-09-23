# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer - Qualified Professional Extension
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/qualified_professional.py
#
# PURPOSE:
#   Extends the qualified_professional model (owned by nettrades_core) with
#   a per-field points_per_vote override. The base model already provides
#   partner_id, field_id, verification, licensing, and reputation fields;
#   this file adds only what the Good Answer voting system needs.
#
# HISTORY:
#   Originally defined _name = "qualified.professional", which silently
#   collided with the core model because both reduce to the same SQL table
#   (qualified_professional). Converted to a proper _inherit extension so
#   there is exactly one model and one table.
# =============================================================================

from odoo import fields, models


class QualifiedProfessional(models.Model):
    _inherit = 'qualified_professional'

    points_per_vote = fields.Integer(
        string='Points per Vote',
        help="Overrides the field's qualified_points_per_vote if set.",
    )
