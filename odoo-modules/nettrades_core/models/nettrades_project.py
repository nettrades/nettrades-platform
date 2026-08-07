from odoo import fields, models

class NettradesProject(models.Model):
    _name = 'nettrades.project'
    _description = 'NetTrades Project'
    _rec_name = 'title'
    _order = 'create_date DESC'

    # =========================================================================
    # Core Fields
    # =========================================================================

    title = fields.Char(
        string='Title',
        required=True
    )

    description = fields.Text(
        string='Description'
    )

    company_id = fields.Many2one(
        'nettrades.company',
        string='Company'
    )

    budget = fields.Float(
        string='Budget'
    )

    status = fields.Selection([
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='open')

    required_skills = fields.Char(
        string='Required Skills'
    )

    create_date = fields.Datetime(
        default=fields.Datetime.now,
        readonly=True
    )