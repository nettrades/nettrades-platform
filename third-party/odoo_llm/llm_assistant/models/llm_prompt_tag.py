from random import randint

from odoo import fields, models


class LLMPromptTag(models.Model):
    _name = "llm.prompt.tag"
    _description = "LLM Prompt Tag"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char("Tag Name", required=True, translate=True)
    color = fields.Integer("Color", default=_get_default_color)

# -------------------------------------------------------------------------
# CONSTRAINTS
# -------------------------------------------------------------------------
    _constraints = [
        models.Constraint(
            'name_uniq',
            models.Q(('name', '=', models.Q())),
            'Tag name already exists!'
        ),
    ]
