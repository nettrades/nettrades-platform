from odoo import fields, models

class ResearchProject(models.Model):
    _name = 'research.project'
    _inherit = 'project.project'

    research_field = fields.Char()
    expected_publication = fields.Text()
    researcher_ids = fields.Many2many('res.partner', string="Researchers",
                                      domain=[('user_type', '=', 'partner')])