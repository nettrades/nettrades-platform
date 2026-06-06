from odoo import fields, models

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    lead_score = fields.Integer(string="AI Lead Score", default=0,
                                help="Automatically calculated from platform interactions.")