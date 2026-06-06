from odoo import fields, models, api, _
from odoo.exceptions import UserError
import secrets

class ExpertSession(models.Model):
    _name = 'expert.session'
    _description = 'Expert Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    session_id = fields.Char(default=lambda self: secrets.token_urlsafe(16), required=True, readonly=True)
    requester_id = fields.Many2one('res.partner', required=True)
    expert_id = fields.Many2one('res.partner', required=True)
    field_id = fields.Many2one('nettrades.field')
    task_summary = fields.Text()
    ai_context_bundle = fields.Json()
    duration_minutes = fields.Integer()
    rate_per_minute = fields.Float()
    total_charged = fields.Float(compute='_compute_total')
    escrow_id = fields.Char()
    status = fields.Selection([('pending','Pending'),('accepted','Accepted'),('active','Active'),('completed','Completed'),('disputed','Disputed'),('cancelled','Cancelled')], default='pending', tracking=True)
    started_at = fields.Datetime()
    ended_at = fields.Datetime()
    rating_by_requester = fields.Integer()
    rating_by_expert = fields.Integer()
    forgejo_repo_url = fields.Char()

    @api.depends('duration_minutes', 'rate_per_minute')
    def _compute_total(self):
        for rec in self:
            rec.total_charged = rec.duration_minutes * rec.rate_per_minute

    def action_accept(self):
        self.ensure_one()
        if self.expert_id.is_online is False:
            raise UserError(_("Expert is not online."))
        self._create_escrow()
        self.status = 'active'
        self.started_at = fields.Datetime.now()

    def _create_escrow(self):
        acquirer = self.env['payment.acquirer'].search([('provider', '=', 'stripe')], limit=1)
        if not acquirer:
            raise UserError(_("Stripe acquirer not configured."))
        # simplified: in full code use payment.transaction; here placeholder
        self.escrow_id = 'escrow_dummy'

    def action_complete(self):
        self.ensure_one()
        self.status = 'completed'
        self.ended_at = fields.Datetime.now()
        # update reputation
        if self.rating_by_requester:
            rep = self.env['user.field.reputation'].search([('partner_id','=',self.expert_id.id), ('field_id','=',self.field_id.id)])
            if not rep:
                rep = self.env['user.field.reputation'].create({'partner_id':self.expert_id.id, 'field_id':self.field_id.id})
            rep.reputation_points += self.rating_by_requester