# -*- coding: utf-8 -*-
# =============================================================================
# LLM Prompt Tag Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_assistant/models/llm_prompt_tag.py
#
# PURPOSE:
#   This model represents a tag that can be applied to prompt templates.
#   Tags provide a flexible way to categorise and filter prompts.
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMPromptTag(models.Model):
    """
    LLM Prompt Tag.

    A tag is a simple label that can be applied to prompt templates
    for categorisation, filtering, and search.

    Tags are typically used for:
        - Domain classification (e.g., 'finance', 'customer_service')
        - Use case categorisation (e.g., 'summarisation', 'classification')
        - Version tracking (e.g., 'stable', 'experimental')
    """
    _name = "llm.prompt.tag"
    _description = "LLM Prompt Tag"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        tracking=True,
        help="The name of the tag."
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Whether this tag is active."
    )

    description = fields.Text(
        string="Description",
        tracking=True,
        help="A description of what this tag represents."
    )

    color = fields.Integer(
        string="Color Index",
        default=0,
        help="Color index for visual distinction in the UI."
    )

    # -------------------------------------------------------------------------
    # 2. RELATIONSHIPS
    # -------------------------------------------------------------------------

    prompt_ids = fields.Many2many(
        "llm.prompt",
        string="Prompts",
        help="Prompts that have this tag."
    )

    # -------------------------------------------------------------------------
    # 3. CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('name')
    def _check_unique_name(self):
        """
        Ensure that tag names are unique.

        This is the Odoo 19-compatible version of the constraint.
        It replaces the old _sql_constraints approach that used models.Q.
        """
        for record in self:
            existing = self.search_count([
                ('name', '=', record.name)
            ])
            if existing > 1:
                raise ValidationError(
                    _("Tag name must be unique.")
                )

    # -------------------------------------------------------------------------
    # 4. STATISTICS
    # -------------------------------------------------------------------------

    def get_prompt_count(self):
        """
        Get the number of prompts with this tag.

        Returns:
            int: The count of prompts.
        """
        self.ensure_one()
        return len(self.prompt_ids)