# -*- coding: utf-8 -*-
# =============================================================================
# LLM Prompt Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_assistant/models/llm_prompt.py
#
# PURPOSE:
#   This model represents a reusable prompt template for LLM assistants.
#   Prompts can be versioned, categorised, and shared across assistants.
#   They support dynamic rendering with context variables.
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMPrompt(models.Model):
    """
    LLM Prompt Template.

    A prompt template is a reusable text template that can be rendered
    with context variables to produce system prompts or user messages.
    Prompts can be categorised, tagged, and versioned.

    Use cases:
        - System prompts for assistants
        - Instruction templates for tools
        - Response format guidelines
        - Few-shot examples
    """
    _name = "llm.prompt"
    _description = "LLM Prompt Template"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------

    code = fields.Char(
        string="Code",
        required=True,
        tracking=True,
        help="A unique code identifier for the prompt template."
    )

    name = fields.Char(
        string="Name",
        required=True,
        tracking=True,
        help="A human-readable name for the prompt template."
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Whether this prompt template is active."
    )

    # -------------------------------------------------------------------------
    # 2. CONTENT FIELDS
    # -------------------------------------------------------------------------

    prompt_text = fields.Text(
        string="Prompt Text",
        required=True,
        tracking=True,
        help="The template text. Supports placeholders like {name} and {context}."
    )

    description = fields.Text(
        string="Description",
        tracking=True,
        help="A description of what this prompt is used for."
    )

    # -------------------------------------------------------------------------
    # 3. CATEGORISATION
    # -------------------------------------------------------------------------

    category_id = fields.Many2one(
        "llm.prompt.category",
        string="Category",
        ondelete="set null",
        tracking=True,
        help="The category of this prompt template."
    )

    tag_ids = fields.Many2many(
        "llm.prompt.tag",
        string="Tags",
        help="Tags for filtering and organising prompt templates."
    )

    # -------------------------------------------------------------------------
    # 4. VERSIONING
    # -------------------------------------------------------------------------

    version = fields.Char(
        string="Version",
        default="1.0.0",
        tracking=True,
        help="Semantic version of this prompt template."
    )

    parent_id = fields.Many2one(
        "llm.prompt",
        string="Parent Prompt",
        ondelete="set null",
        tracking=True,
        help="The parent prompt this version is derived from."
    )

    # -------------------------------------------------------------------------
    # 5. METADATA
    # -------------------------------------------------------------------------

    is_system_prompt = fields.Boolean(
        string="Is System Prompt",
        default=False,
        tracking=True,
        help="Whether this prompt is intended as a system prompt."
    )

    is_user_prompt = fields.Boolean(
        string="Is User Prompt",
        default=False,
        tracking=True,
        help="Whether this prompt is intended as a user prompt."
    )

    # -------------------------------------------------------------------------
    # 6. CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('name')
    def _check_unique_name(self):
        """
        Ensure that prompt names are unique.

        This is the Odoo 19-compatible version of the constraint.
        It replaces the old _sql_constraints approach that used models.Q.
        """
        for record in self:
            existing = self.search_count([
                ('name', '=', record.name)
            ])
            if existing > 1:
                raise ValidationError(
                    _("Prompt name must be unique.")
                )

    @api.constrains('code')
    def _check_unique_code(self):
        """
        Ensure that prompt codes are unique.

        This is the Odoo 19-compatible version of the constraint.
        """
        for record in self:
            existing = self.search_count([
                ('code', '=', record.code)
            ])
            if existing > 1:
                raise ValidationError(
                    _("Prompt code must be unique.")
                )

    # -------------------------------------------------------------------------
    # 7. HELPER METHODS
    # -------------------------------------------------------------------------

    def render(self, context=None):
        """
        Render the prompt template with the given context.

        Args:
            context (dict): A dictionary of variables to substitute.

        Returns:
            str: The rendered prompt text.

        Example:
            prompt = llm_prompt.browse(1)
            rendered = prompt.render({
                'name': 'Assistant',
                'topic': 'customer service'
            })
        """
        self.ensure_one()

        if context is None:
            context = {}

        # Simple placeholder substitution
        rendered = self.prompt_text
        for key, value in context.items():
            placeholder = "{" + key + "}"
            rendered = rendered.replace(placeholder, str(value))

        return rendered

    def create_version(self, version_name=None):
        """
        Create a new version of this prompt template.

        Args:
            version_name (str): The version name (e.g., '2.0.0').

        Returns:
            LLMPrompt: The new version record.
        """
        self.ensure_one()

        if not version_name:
            # Auto-increment version
            parts = self.version.split('.')
            if len(parts) == 3:
                parts[2] = str(int(parts[2]) + 1)
                version_name = '.'.join(parts)
            else:
                version_name = '1.0.1'

        new_vals = {
            'code': self.code,
            'name': f"{self.name} v{version_name}",
            'prompt_text': self.prompt_text,
            'description': self.description,
            'category_id': self.category_id.id,
            'version': version_name,
            'parent_id': self.id,
            'is_system_prompt': self.is_system_prompt,
            'is_user_prompt': self.is_user_prompt,
        }

        return self.create(new_vals)