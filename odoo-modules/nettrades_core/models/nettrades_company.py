from odoo import fields, models, api

class NettradesCompany(models.Model):
    _name = 'nettrades.company'
    _description = 'NetTrades Company'
    _rec_name = 'partner_id'

    # =========================================================================
    # Link to Odoo Core
    # =========================================================================

    partner_id = fields.Many2one(
        'res.partner',
        string='Company',
        required=True,
        ondelete='cascade',
        help="Link to the Odoo partner record"
    )

    # =========================================================================
    # NetTrades-Specific Fields
    # =========================================================================

    is_active = fields.Boolean(
        string='Active',
        default=True
    )

    industry = fields.Char(
        string='Industry'
    )

    website = fields.Char(
        string='Website'
    )

    description = fields.Text(
        string='Description'
    )

    # =========================================================================
    # Computed Fields
    # =========================================================================

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )

    @api.depends('partner_id')
    def _compute_name(self):
        for rec in self:
            rec.name = rec.partner_id.name if rec.partner_id else ''