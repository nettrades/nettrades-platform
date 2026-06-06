from odoo import fields, models, api, _
from odoo.exceptions import UserError
import secrets

class ExpertSession(models.Model):
    _name = 'expert.session'
    _description = 'Expert Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    session_id = fields.Char(string="Session ID", default=lambda self: secrets.token_urlsafe(16), required=True, readonly=True)
    requester_id = fields.Many2one('res.partner', string="Requester", required=True)
    expert_id = fields.Many2one('res.partner', string="Expert", required=True)
    field_id = fields.Many2one('nettrades.field', string="Field")
    task_summary = fields.Text(string="Task Summary")
    ai_context_bundle = fields.Json(string="AI Context")
    duration_minutes = fields.Integer(string="Duration (minutes)")
    rate_per_minute = fields.Float(string="Rate per minute")
    total_charged = fields.Float(string="Total Charged", compute='_compute_total')
    escrow_id = fields.Char(string="Escrow ID")
    status = fields.Selection([
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('disputed', 'Disputed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', tracking=True)
    started_at = fields.Datetime()
    ended_at = fields.Datetime()
    rating_by_requester = fields.Integer(string="Rating by Requester")
    rating_by_expert = fields.Integer(string="Rating by Expert")
    forgejo_repo_url = fields.Char(string="Forgejo Repo URL")

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
        # Notify participants via bus (simplified)
        bus = self.env['bus.bus']
        bus.sendone(f'user_{self.expert_id.id}', {'type': 'session_started', 'session_id': self.session_id})
        bus.sendone(f'user_{self.requester_id.id}', {'type': 'session_started', 'session_id': self.session_id})

    def _create_escrow(self):
        # Requires payment_stripe module from OCA
        acquirer = self.env['payment.acquirer'].search([('provider', '=', 'stripe')], limit=1)
        if not acquirer:
            raise UserError(_("Stripe acquirer not configured. Please install OCA payment_stripe."))
        # Create a payment transaction with manual capture
        tx = self.env['payment.transaction'].create({
            'acquirer_id': acquirer.id,
            'amount': self.total_charged,
            'currency_id': self.env.company.currency_id.id,
            'reference': f"session_{self.session_id}",
            'partner_id': self.requester_id.id,
        })
        # For manual capture, we need to set capture_method manually if Stripe module supports it
        # Placeholder: store a dummy escrow_id; the actual integration is deferred to the OCA module.
        self.escrow_id = 'escrow_placeholder'
        self.env['escrow.hold'].create({
            'session_id': self.id,
            'amount': self.total_charged,
            'provider_hold_id': self.escrow_id,
            'status': 'held',
        })

    def action_complete(self):
        self.ensure_one()
        # Capture payment (simplified)
        self.status = 'completed'
        self.ended_at = fields.Datetime.now()

        # Create invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.requester_id.id,
            'invoice_line_ids': [(0, 0, {
                'name': f"Expert session {self.session_id}",
                'quantity': self.duration_minutes,
                'price_unit': self.rate_per_minute,
            })],
        })
        invoice.action_post()

        # Platform fee
        config = self.env['ir.config_parameter'].sudo()
        fee_percent = float(config.get_param('ask_someone.platform_fee_percent', '15.0'))
        fee_line = self.env['account.move.line'].create({
            'move_id': invoice.id,
            'name': 'Platform fee',
            'price_unit': -(self.total_charged * fee_percent / 100),
            'quantity': 1,
        })

        # Update reputations
        if self.rating_by_requester:
            rep = self.env['user.field.reputation'].search([
                ('partner_id', '=', self.expert_id.id),
                ('field_id', '=', self.field_id.id),
            ], limit=1)
            if rep:
                rep.reputation_points += self.rating_by_requester