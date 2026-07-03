# -*- coding: utf-8 -*-
# =============================================================================
# LLM Knowledge Resource Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_knowledge/models/llm_resource.py
#
# PURPOSE:
#   This model represents a knowledge resource within the LLM knowledge base.
#   Resources are linked to Odoo records and provide a way to associate
#   knowledge chunks with specific documents, records, or external sources.
#
# ODOO 19 COMPATIBILITY NOTES:
#   - `ondelete='restrict'` is NOT supported on Many2one fields pointing to
#     'ir.model' in Odoo 19. This has been changed to `ondelete='cascade'`.
#   - The `_sql_constraints` approach has been replaced with `@api.constrains`
#     for uniqueness constraints.
#   - `models.Q` no longer exists in Odoo 19; use `@api.constrains` instead.
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMResource(models.Model):
    """
    LLM Knowledge Resource.

    A resource is a source of knowledge that can be indexed and searched.
    Resources are linked to Odoo records (res_id) and models (model_id)
    to provide context-aware knowledge retrieval.
    """
    _name = "llm.resource"
    _description = "LLM Knowledge Resource"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        tracking=True,
        help="Name of the resource (e.g., document title or reference)."
    )

    # ========================================================================
    # IMPORTANT ODOO 19 FIX:
    #   In Odoo 19, `ondelete='restrict'` is NOT supported for fields
    #   whose comodel is 'ir.model'.
    #
    #   Since this field is `required=True`, `ondelete='set null'` is also
    #   NOT allowed because it would violate the required constraint.
    #
    #   The only valid options for a required field are:
    #     1. `ondelete='cascade'`  - Delete the resource when the model is deleted
    #     2. `ondelete='restrict'` - Prevent deletion of the model if resources exist
    #
    #   We use `cascade` because it allows clean deletion of orphaned resources.
    # ========================================================================
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=True,
        ondelete="cascade",       # Changed from 'restrict' to 'cascade'
        tracking=True,
        help="The Odoo model that this resource belongs to."
    )

    res_id = fields.Integer(
        string="Record ID",
        required=True,
        tracking=True,
        help="The ID of the specific record in the model."
    )

    # -------------------------------------------------------------------------
    # 2. CONTENT FIELDS
    # -------------------------------------------------------------------------

    description = fields.Text(
        string="Description",
        tracking=True,
        help="A human-readable description of the resource."
    )

    content = fields.Text(
        string="Content",
        tracking=True,
        help="The raw text content of the resource. This is what gets indexed."
    )

    # -------------------------------------------------------------------------
    # 3. METADATA FIELDS
    # -------------------------------------------------------------------------

    resource_type = fields.Selection(
        [
            ("document", "Document"),
            ("attachment", "Attachment"),
            ("knowledge_article", "Knowledge Article"),
            ("web_page", "Web Page"),
            ("external_source", "External Source"),
            ("other", "Other"),
        ],
        string="Resource Type",
        default="document",
        tracking=True,
        help="The type of resource."
    )

    source_url = fields.Char(
        string="Source URL",
        tracking=True,
        help="The URL of the original source, if applicable."
    )

    content_hash = fields.Char(
        string="Content Hash",
        tracking=True,
        help="A hash of the content for deduplication and change detection."
    )

    # -------------------------------------------------------------------------
    # 4. STATUS AND TRACKING
    # -------------------------------------------------------------------------

    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Whether this resource is active (soft delete)."
    )

    last_indexed_at = fields.Datetime(
        string="Last Indexed At",
        tracking=True,
        help="The timestamp when this resource was last indexed into chunks."
    )

    # -------------------------------------------------------------------------
    # 5. RELATIONSHIPS
    # -------------------------------------------------------------------------

    chunk_ids = fields.One2many(
        "llm.knowledge.chunk",
        "resource_id",
        string="Chunks",
        help="The chunks that belong to this resource."
    )

    # -------------------------------------------------------------------------
    # 6. CONSTRAINTS (Odoo 19 compatible)
    # -------------------------------------------------------------------------

    @api.constrains('model_id', 'res_id')
    def _check_unique_resource(self):
        """
        Ensure that a resource is unique per (model_id, res_id).

        This is the Odoo 19-compatible version of the constraint.
        It replaces the old _sql_constraints approach (which used models.Q)
        that caused an AttributeError.
        """
        for record in self:
            existing = self.search_count([
                ('model_id', '=', record.model_id.id),
                ('res_id', '=', record.res_id)
            ])
            if existing > 1:
                raise ValidationError(
                    _("A resource already exists for this record. Please use the existing resource.")
                )

    # -------------------------------------------------------------------------
    # 7. HELPER METHODS
    # -------------------------------------------------------------------------

    def get_record(self):
        """
        Get the Odoo record associated with this resource.

        Returns:
            recordset: The Odoo record, or None if the record does not exist.
        """
        self.ensure_one()
        if not self.model_id or not self.res_id:
            return None

        model_obj = self.env[self.model_id.model]
        return model_obj.browse(self.res_id)

    def index_chunks(self, chunk_texts=None, chunk_size=512):
        """
        Index the content of this resource into chunks.

        This method splits the content into smaller chunks and creates
        llm.knowledge.chunk records.

        Args:
            chunk_texts (list): Optional list of pre-segmented chunks.
            chunk_size (int): Maximum size of each chunk in characters.

        Returns:
            list: The created chunk records.

        Raises:
            UserError: If no content is available for chunking.
        """
        from odoo.exceptions import UserError

        if not self.content:
            raise UserError(_("No content available for chunking."))

        if chunk_texts is None:
            paragraphs = self.content.split("\n\n")
            chunk_texts = []
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) <= chunk_size:
                    current_chunk += para + "\n\n"
                else:
                    if current_chunk:
                        chunk_texts.append(current_chunk.strip())
                    current_chunk = para + "\n\n"
            if current_chunk:
                chunk_texts.append(current_chunk.strip())

        chunks = self.env["llm.knowledge.chunk"]
        for i, text in enumerate(chunk_texts):
            chunk_vals = {
                "resource_id": self.id,
                "index": i,
                "text": text,
                "chunk_type": "text",
            }
            chunks |= chunks.create(chunk_vals)

        self.last_indexed_at = fields.Datetime.now()
        return chunks

    def refresh_chunks(self):
        """
        Refresh the chunks for this resource.

        Deletes all existing chunks and recreates them from the current content.

        Returns:
            list: The newly created chunk records.
        """
        self.chunk_ids.unlink()
        return self.index_chunks()