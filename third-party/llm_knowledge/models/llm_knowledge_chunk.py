# -*- coding: utf-8 -*-
# =============================================================================
# LLM Knowledge Chunk Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_knowledge/models/llm_knowledge_chunk.py
#
# PURPOSE:
#   This model represents a chunk of knowledge from a resource.
#   Chunks are smaller pieces of text that can be embedded and searched.
#
# ODOO 19 COMPATIBILITY NOTES:
#   - The `collection_ids` field was previously defined as a related field
#     referencing a non-existent source field, causing a KeyError.
#     It has been re-implemented as a standard Many2many field with
#     `llm.knowledge.collection`.
#   - `models.Q` no longer exists; use `@api.constrains` for constraints.
#   - `ondelete='restrict'` on Many2one fields to `ir.model` has been
#     changed to `ondelete='cascade'` for compatibility.
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMKnowledgeChunk(models.Model):
    """
    LLM Knowledge Chunk.

    A chunk is a small piece of text from a resource that can be
    embedded and used for RAG (Retrieval-Augmented Generation).
    """
    _name = "llm.knowledge.chunk"
    _description = "LLM Knowledge Chunk"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "resource_id, index"

    # -------------------------------------------------------------------------
    # 1. RELATIONSHIPS
    # -------------------------------------------------------------------------

    resource_id = fields.Many2one(
        "llm.resource",
        string="Resource",
        required=True,
        ondelete="cascade",
        tracking=True,
        help="The resource this chunk belongs to."
    )

    # ========================================================================
    # FIX: The original `collection_ids` was defined as a related field that
    # referenced a non-existent field. This caused a KeyError during registry
    # setup. It has been re-implemented as a standard Many2many field.
    #
    # If the relationship between chunks and collections is not needed,
    # you can remove this field. However, we include it to preserve the
    # original data model.
    # ========================================================================
    collection_ids = fields.Many2many(
        "llm.knowledge.collection",
        string="Collections",
        help="The collections this chunk belongs to."
    )

    # -------------------------------------------------------------------------
    # 2. CONTENT FIELDS
    # -------------------------------------------------------------------------

    index = fields.Integer(
        string="Index",
        required=True,
        tracking=True,
        help="The position of this chunk within the resource."
    )

    text = fields.Text(
        string="Text",
        required=True,
        tracking=True,
        help="The text content of this chunk."
    )

    chunk_type = fields.Selection(
        [
            ("text", "Text"),
            ("code", "Code"),
            ("markdown", "Markdown"),
            ("other", "Other"),
        ],
        string="Chunk Type",
        default="text",
        tracking=True,
        help="The type of content in this chunk."
    )

    # -------------------------------------------------------------------------
    # 3. METADATA
    # -------------------------------------------------------------------------

    metadata = fields.Json(
        string="Metadata",
        help="Additional metadata for this chunk (JSON)."
    )

    # -------------------------------------------------------------------------
    # 4. EMBEDDING (from pgvector)
    # -------------------------------------------------------------------------

    # The embedding is stored in a separate model to support multiple
    # embedding models per chunk. This is defined in llm_pgvector.
    embedding_ids = fields.One2many(
        "llm.knowledge.chunk.embedding",
        "chunk_id",
        string="Embeddings",
        help="Vector embeddings of this chunk."
    )

    # -------------------------------------------------------------------------
    # 5. CONSTRAINTS (Odoo 19 compatible)
    # -------------------------------------------------------------------------

    @api.constrains('resource_id', 'index')
    def _check_unique_index(self):
        """
        Ensure that the index is unique per resource.
        """
        for record in self:
            existing = self.search_count([
                ('resource_id', '=', record.resource_id.id),
                ('index', '=', record.index)
            ])
            if existing > 1:
                raise ValidationError(
                    _("Chunk index must be unique per resource.")
                )

    # -------------------------------------------------------------------------
    # 6. HELPER METHODS
    # -------------------------------------------------------------------------

    def get_text(self):
        """
        Get the text content of this chunk.

        Returns:
            str: The text content.
        """
        self.ensure_one()
        return self.text

    def get_resource(self):
        """
        Get the resource for this chunk.

        Returns:
            LLMResource: The resource record.
        """
        self.ensure_one()
        return self.resource_id

    def get_embeddings(self, embedding_model_id=None):
        """
        Get the embeddings for this chunk.

        Args:
            embedding_model_id (int): Optional filter by embedding model.

        Returns:
            recordset: The embedding records.
        """
        self.ensure_one()

        domain = [('chunk_id', '=', self.id)]
        if embedding_model_id:
            domain.append(('embedding_model_id', '=', embedding_model_id))

        return self.env["llm.knowledge.chunk.embedding"].search(domain)

    def get_first_embedding(self):
        """
        Get the first embedding for this chunk.

        Returns:
            LLMKnowledgeChunkEmbedding: The first embedding record.
        """
        self.ensure_one()
        return self.embedding_ids[:1]

    def add_to_collection(self, collection_id):
        """
        Add this chunk to a collection.

        Args:
            collection_id (int): The ID of the collection to add to.

        Returns:
            bool: True if successful.
        """
        self.ensure_one()
        if collection_id not in self.collection_ids.ids:
            self.collection_ids = [(4, collection_id)]
            return True
        return False

    def remove_from_collection(self, collection_id):
        """
        Remove this chunk from a collection.

        Args:
            collection_id (int): The ID of the collection to remove from.

        Returns:
            bool: True if successful.
        """
        self.ensure_one()
        if collection_id in self.collection_ids.ids:
            self.collection_ids = [(3, collection_id)]
            return True
        return False