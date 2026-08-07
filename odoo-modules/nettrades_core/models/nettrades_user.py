from odoo import fields, models, api

class NettradesUser(models.Model):
    _name = 'nettrades.user'
    _description = 'NetTrades User'
    _rec_name = 'partner_id'
    _order = 'create_date DESC'

    # =========================================================================
    # Link to Odoo Core
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
        help="Link to the Odoo partner record"
    )

    # =========================================================================
    # NetTrades-Specific Fields
    # =========================================================================

    username = fields.Char(
        string='Username',
        required=True,
        help="NetTrades username"
    )

    wallet_address = fields.Char(
        string='Wallet Address',
        help="Blockchain wallet address for payments"
    )

    karma_score = fields.Integer(
        string='Karma Score',
        default=0,
        help="User reputation score"
    )

    reputation_score = fields.Float(
        string='Reputation Score',
        default=0.0,
        help="Weighted reputation score"
    )

    is_verified = fields.Boolean(
        string='Verified',
        default=False,
        help="Whether the user has been verified"
    )

    is_online = fields.Boolean(
        string='Online',
        default=False,
        help="Whether the user is currently online"
    )

    # =========================================================================
    # Security & Audit
    # =========================================================================

    is_active = fields.Boolean(
        string='Active',
        default=True,
        help="Whether this user is active in NetTrades"
    )

    create_date = fields.Datetime(
        string='Created On',
        readonly=True,
        default=fields.Datetime.now
    )

    write_date = fields.Datetime(
        string='Last Modified',
        readonly=True,
        default=fields.Datetime.now
    )

    # =========================================================================
    # Computed Fields
    # =========================================================================

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
        help="Computed from partner_id"
    )

    email = fields.Char(
        string='Email',
        compute='_compute_email',
        store=True,
        help="Computed from partner_id"
    )

    @api.depends('partner_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.partner_id.name if rec.partner_id else ''

    @api.depends('partner_id')
    def _compute_email(self):
        for rec in self:
            rec.email = rec.partner_id.email if rec.partner_id else ''

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @api.model
    def get_or_create(self, partner_id):
        """Get or create a NetTrades user for an Odoo partner."""
        user = self.search([('partner_id', '=', partner_id)], limit=1)
        if not user:
            partner = self.env['res.partner'].browse(partner_id)
            user = self.create({
                'partner_id': partner_id,
                'username': partner.email or partner.name,
            })
        return user