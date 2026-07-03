# Section F.4 - Milestone model for freelancer projects.
from odoo import fields, models

class ProjectMilestone(models.Model):
    _name = 'project.milestone'
    _description = 'Project Milestone'
    _order = 'sequence, id'

    project_id = fields.Many2one('project.project', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    amount = fields.Float()  # Portion of the project budget for this milestone
    status = fields.Selection([
        ('pending', 'Pending'), ('in_progress', 'In Progress'),
        ('completed', 'Completed'), ('paid', 'Paid')
    ], default='pending')
    due_date = fields.Date()
    released = fields.Boolean(default=False)