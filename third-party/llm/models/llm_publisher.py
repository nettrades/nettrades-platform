from odoo import api, fields, models


class LLMPublisher(models.Model):
    _name = "llm.publisher"
    _description = "LLM Publisher"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    logo = fields.Image(
        max_width=1024, max_height=1024, verify_resolution=True, help="Publisher logo"
    )
    description = fields.Text(tracking=True)
    meta = fields.Json(string="Publisher Metadata")
    official = fields.Boolean(
        default=False,
        tracking=True,
        help="Indicates if this is an official model publisher",
    )
    frontier = fields.Boolean(
        default=False,
        tracking=True,
        help="Indicates if this publisher is working on frontier AI models",
    )

    # Relationships
    model_ids = fields.One2many("llm.model", "publisher_id", string="Models")
    model_count = fields.Integer(compute="_compute_model_count", store=True)

    @api.depends("model_ids")
    def _compute_model_count(self):
        for record in self:
            record.model_count = len(record.model_ids)
