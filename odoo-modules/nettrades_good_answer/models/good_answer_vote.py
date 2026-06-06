from odoo import fields, models, api, _
from odoo.exceptions import UserError

class GoodAnswerVote(models.Model):
    _name = 'good.answer.vote'
    _description = 'Good Answer Vote'

    user_id = fields.Many2one('res.partner', required=True)
    answer_id = fields.Integer(required=True)
    answer_model = fields.Char(required=True)
    answerer_id = fields.Many2one('res.partner', required=True)
    field_id = fields.Many2one('nettrades.field', required=True)
    points = fields.Integer()
    is_qualified_vote = fields.Boolean(default=False)
    processed_for_ai = fields.Boolean(default=False)
    created_at = fields.Datetime(default=fields.Datetime.now)

    _sql_constraints = [('unique_vote', 'unique(user_id, answer_id, answer_model)', 'Already voted on this answer.')]

    @api.model
    def create(self, vals):
        # duplicate check
        existing = self.search([('user_id','=',vals['user_id']),('answer_id','=',vals['answer_id']),('answer_model','=',vals['answer_model'])])
        if existing:
            raise UserError(_("Already voted."))
        return super().create(vals)