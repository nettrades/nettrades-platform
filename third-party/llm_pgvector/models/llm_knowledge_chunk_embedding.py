# -*- coding: utf-8 -*-
# =============================================================================
# LLM Knowledge Chunk Embedding Model (pgvector)
# =============================================================================
# FILE: third-party/odoo_llm/llm_pgvector/models/llm_knowledge_chunk_embedding.py
#
# PURPOSE:
#   This model stores vector embeddings for knowledge chunks using
#   PostgreSQL pgvector. It links a chunk to its embedding vector
#   and the embedding model that generated it.
#
#   The embedding is stored as a vector type in PostgreSQL using the
#   pgvector extension. This allows for efficient similarity search
#   using cosine distance, Euclidean distance, or inner product.
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Import the custom PgVector field from the same module
# This is the custom field type defined in llm_pgvector/fields.py
try:
    from ..fields import PgVector
except ImportError:
    # Fallback: use a text field if the PgVector field is not available
    PgVector = None


class LLMKnowledgeChunkEmbedding(models.Model):
    """
    LLM Knowledge Chunk Embedding.

    This model stores the vector embedding of a knowledge chunk.
    Each chunk can have multiple embeddings if different embedding
    models are used (e.g., for different search purposes).

    The embedding vector is stored as a pgvector array in PostgreSQL.
    """
    _name = "llm.knowledge.chunk.embedding"
    _description = "LLM Knowledge Chunk Embedding"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "chunk_id, embedding_model_id"

    # -------------------------------------------------------------------------
    # 1. RELATIONSHIPS
    # -------------------------------------------------------------------------

    chunk_id = fields.Many2one(
        "llm.knowledge.chunk",
        string="Chunk",
        required=True,
        ondelete="cascade",
        tracking=True,
        help="The knowledge chunk this embedding belongs to."
    )

    embedding_model_id = fields.Many2one(
        "llm.embedding.model",
        string="Embedding Model",
        required=True,
        ondelete="restrict",
        tracking=True,
        help="The embedding model that generated this vector."
    )

    # -------------------------------------------------------------------------
    # 2. VECTOR FIELD (pgvector)
    # -------------------------------------------------------------------------

    # Use the custom PgVector field if available, otherwise use Text
    if PgVector is not None:
        embedding = PgVector(
            string="Embedding",
            help="The vector embedding of the chunk content.",
            required=True
        )
    else:
        # Fallback: store as JSON text if PgVector is not available
        # This allows the module to work without the pgvector extension
        # but loses the ability to do vector similarity searches.
        embedding = fields.Text(
            string="Embedding (JSON)",
            help="The vector embedding stored as a JSON array string.",
            required=True
        )

    # -------------------------------------------------------------------------
    # 3. METADATA
    # -------------------------------------------------------------------------

    dimension = fields.Integer(
        string="Dimension",
        tracking=True,
        help="The dimension of the embedding vector."
    )

    created_at = fields.Datetime(
        string="Created At",
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the embedding was created."
    )

    # -------------------------------------------------------------------------
    # 4. CONSTRAINTS
    # -------------------------------------------------------------------------

    @api.constrains('chunk_id', 'embedding_model_id')
    def _check_unique_chunk_embedding(self):
        """
        Ensure that a chunk can only have one embedding per embedding model.

        This is the Odoo 19-compatible version of the constraint.
        It replaces the old _sql_constraints approach that used models.Q.
        """
        for record in self:
            existing = self.search_count([
                ('chunk_id', '=', record.chunk_id.id),
                ('embedding_model_id', '=', record.embedding_model_id.id)
            ])
            if existing > 1:
                raise ValidationError(
                    _("A chunk can only have one embedding per embedding model.")
                )

    # -------------------------------------------------------------------------
    # 5. HELPER METHODS
    # -------------------------------------------------------------------------

    def get_vector(self):
        """
        Get the embedding as a list of floats.

        Returns:
            list: The embedding vector as a list of floats.

        Example:
            embedding = llm_knowledge_chunk_embedding.browse(1)
            vector = embedding.get_vector()
            # vector is a list of floats like [0.123, 0.456, ...]
        """
        self.ensure_one()
        if PgVector is not None:
            # If using PgVector, it should return a list of floats
            return self.embedding
        else:
            # If using Text fallback, parse the JSON array
            import json
            try:
                return json.loads(self.embedding)
            except (json.JSONDecodeError, TypeError):
                return []

    def get_vector_as_numpy(self):
        """
        Get the embedding as a numpy array.

        Returns:
            numpy.ndarray: The embedding vector as a numpy array.

        Note:
            This requires numpy to be installed.
        """
        self.ensure_one()
        try:
            import numpy as np
            vector = self.get_vector()
            return np.array(vector)
        except ImportError:
            raise ValidationError(_("numpy is not available."))

    def get_vector_as_text(self):
        """
        Get the embedding as a text representation.

        Returns:
            str: The embedding vector as a string (for debugging).
        """
        self.ensure_one()
        return str(self.embedding)

    def find_similar(self, query_vector, limit=10):
        """
        Find similar embeddings using pgvector nearest neighbour search.

        Args:
            query_vector (list): The query vector.
            limit (int): Maximum number of results.

        Returns:
            list: Similar embeddings with distances.
        """
        # This would use pgvector's nearest neighbour operator:
        # SELECT * FROM llm_knowledge_chunk_embedding
        # ORDER BY embedding <-> %s LIMIT %s
        #
        # In practice, this is typically done via a custom search method
        # in the store or knowledge collection model.

        # For now, return an empty list (to be implemented by the store)
        return []

    def set_embedding(self, vector):
        """
        Set the embedding vector.

        Args:
            vector (list): A list of floats.

        Raises:
            ValidationError: If the vector is not a list of floats.
        """
        self.ensure_one()

        if not isinstance(vector, list):
            raise ValidationError(_("Vector must be a list."))

        # Check that all elements are numbers
        for v in vector:
            if not isinstance(v, (int, float)):
                raise ValidationError(_("All vector elements must be numbers."))

        if PgVector is not None:
            self.embedding = vector
        else:
            import json
            self.embedding = json.dumps(vector)

        # Update the dimension
        self.dimension = len(vector)