# -*- coding: utf-8 -*-
# =============================================================================
# LLM Store Collection Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_store/models/llm_store_collection.py
#
# PURPOSE:
#   This model represents a collection within a vector store.
#   Collections group vectors by namespace (e.g., by document type,
#   by tenant, by knowledge base).
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMStoreCollection(models.AbstractModel):
    """
    LLM Vector Store Collection.

    A collection is a logical grouping of vectors within a vector store.
    Collections are used to organise embeddings by knowledge domain,
    tenant, or document type.
    """
    _name = "llm.store.collection"
    _description = "LLM Vector Store Collection"
    _inherit = ["mail.thread"]

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------

    name = fields.Char(
        required=True,
        tracking=True,
        help="The name of the collection (unique per store)."
    )

    store_id = fields.Many2one(
        "llm.store",
        string="Vector Store",
        required=True,
        ondelete="restrict",
        tracking=True,
        help="The vector store this collection belongs to."
    )

    dimension = fields.Integer(
        tracking=True,
        help="Dimension of vectors in this collection."
    )

    vector_count = fields.Integer(
        tracking=True,
        help="Number of vectors in this collection."
    )

    metadata = fields.Json(
        string="Collection Metadata",
        help="Additional metadata for this collection."
    )

    description = fields.Text(
        tracking=True,
        help="Optional description of the collection."
    )

    active = fields.Boolean(
        default=True,
        tracking=True,
        help="Whether this collection is active."
    )

    # -------------------------------------------------------------------------
    # 2. CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('store_id', 'name')
    def _check_unique_name(self):
        """
        Ensure collection names are unique per store.

        This is the Odoo 19-compatible version of the constraint.
        It replaces the old _sql_constraints approach.
        """
        for record in self:
            # Count existing collections with the same store_id and name
            existing = self.search_count([
                ('store_id', '=', record.store_id.id),
                ('name', '=', record.name)
            ])
            if existing > 1:
                raise ValidationError(
                    _("Collection names must be unique per store.")
                )

    # -------------------------------------------------------------------------
    # 3. VECTOR OPERATIONS
    # -------------------------------------------------------------------------

    def refresh_stats(self):
        """
        Update statistics about this collection from the store.

        Returns:
            bool: True if successful, False otherwise.
        """
        # To be implemented by specific provider modules
        return True

    def delete_vectors(self, ids=None):
        """
        Remove all vectors from this collection.

        Args:
            ids (list): Optional list of specific vector IDs to delete.

        Returns:
            bool: True if successful, False otherwise.
        """
        if ids is None:
            ids = []

        if self.store_id:
            return self.store_id._delete_vectors(self.id, ids)

        return False

    def search_vectors(self, query_vector, limit=10, filter=None, **kwargs):
        """
        Search for similar vectors in this collection.

        Args:
            query_vector (list): The query vector.
            limit (int): Maximum number of results.
            filter (dict): Optional filter for the search.
            **kwargs: Additional provider-specific parameters.

        Returns:
            list: Search results.
        """
        if self.store_id:
            return self.store_id._search_vectors(
                self.id,
                query_vector,
                limit=limit,
                filter=filter,
                **kwargs
            )

        return []

    def insert_vectors(self, vectors, metadata=None, ids=None, **kwargs):
        """
        Insert vectors into this collection.

        Args:
            vectors (list): List of vectors to insert.
            metadata (list): Optional list of metadata for each vector.
            ids (list): Optional list of IDs for each vector.
            **kwargs: Additional provider-specific parameters.

        Returns:
            list: IDs of the inserted vectors.

        Raises:
            UserError: If no store is configured for this collection.
        """
        if self.store_id:
            return self.store_id._insert_vectors(
                self.id,
                vectors,
                metadata=metadata,
                ids=ids,
                **kwargs
            )
        else:
            raise UserError(
                _("No store configured for this collection.")
            )