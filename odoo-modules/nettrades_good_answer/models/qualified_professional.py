from odoo import fields, models

class QualifiedProfessional(models.Model):
    _name = 'qualified.professional'
    _description = 'Qualified professionals per field'

    partner_id = fields.Many2one('res.partner', required=True)
    field_id = fields.Many2one('nettrades.field', required=True)
    points_per_vote = fields.Integer(help="Overrides field's qualified_points_per_vote if set")
    is_active = fields.Boolean(default=True)