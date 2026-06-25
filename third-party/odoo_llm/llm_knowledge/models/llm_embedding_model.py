# -*- coding: utf-8 -*-
# =============================================================================
# LLM Embedding Model
# =============================================================================
# FILE: third-party/odoo_llm/llm_knowledge/models/llm_embedding_model.py
#
# PURPOSE:
#   This model represents an embedding model used to generate vector embeddings
#   from text. It stores configuration for different embedding providers
#   such as OpenAI, Hugging Face, or local models.
#
# ODOO 19 COMPATIBILITY:
#   - Uses standard Many2one fields without `ondelete='restrict'` on `ir.model`
#   - Uses `@api.constrains` for uniqueness constraints instead of `models.Q`
#
# =============================================================================

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMEmbeddingModel(models.Model):
    """
    LLM Embedding Model.

    An embedding model is used to convert text into vector embeddings
    for semantic search and RAG (Retrieval-Augmented Generation).
    """
    _name = "llm.embedding.model"
    _description = "LLM Embedding Model"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------

    name = fields.Char(
        string="Name",
        required=True,
        tracking=True,
        help="Name of the embedding model (e.g., 'text-embedding-ada-002')."
    )

    active = fields.Boolean(
        string="Active",
        default=True,
        tracking=True,
        help="Whether this embedding model is active."
    )

    # -------------------------------------------------------------------------
    # 2. PROVIDER CONFIGURATION
    # -------------------------------------------------------------------------

    provider = fields.Selection(
        [
            ("openai", "OpenAI"),
            ("huggingface", "Hugging Face"),
            ("ollama", "Ollama (Local)"),
            ("cohere", "Cohere"),
            ("google", "Google"),
            ("custom", "Custom"),
        ],
        string="Provider",
        required=True,
        default="openai",
        tracking=True,
        help="The provider of this embedding model."
    )

    provider_model = fields.Char(
        string="Provider Model ID",
        required=True,
        tracking=True,
        help="The model ID as recognised by the provider "
             "(e.g., 'text-embedding-ada-002' for OpenAI)."
    )

    # -------------------------------------------------------------------------
    # 3. TECHNICAL CONFIGURATION
    # -------------------------------------------------------------------------

    dimension = fields.Integer(
        string="Dimension",
        required=True,
        default=1536,
        tracking=True,
        help="The dimension of the embedding vector (e.g., 1536 for ada-002)."
    )

    max_tokens = fields.Integer(
        string="Max Tokens",
        default=8191,
        tracking=True,
        help="Maximum number of tokens supported by this embedding model."
    )

    api_base_url = fields.Char(
        string="API Base URL",
        help="Custom API base URL for custom or local providers."
    )

    api_key = fields.Char(
        string="API Key",
        password=True,
        copy=False,
        help="API key for the embedding provider."
    )

    # -------------------------------------------------------------------------
    # 4. CONFIGURATION PARAMETERS
    # -------------------------------------------------------------------------

    config = fields.Json(
        string="Configuration",
        help="Additional configuration parameters as a JSON object."
    )

    # -------------------------------------------------------------------------
    # 5. CONSTRAINTS (Odoo 19 compatible)
    # -------------------------------------------------------------------------

    @api.constrains('provider', 'provider_model')
    def _check_unique_provider_model(self):
        """
        Ensure that the combination of provider and provider_model is unique.
        """
        for record in self:
            existing = self.search_count([
                ('provider', '=', record.provider),
                ('provider_model', '=', record.provider_model)
            ])
            if existing > 1:
                raise ValidationError(
                    _("The combination of provider and provider_model must be unique.")
                )

    # -------------------------------------------------------------------------
    # 6. HELPER METHODS
    # -------------------------------------------------------------------------

    def get_embedding_dimension(self):
        """
        Get the embedding dimension for this model.

        Returns:
            int: The dimension of the embedding vector.
        """
        self.ensure_one()
        return self.dimension

    def get_embedding(self, text):
        """
        Generate an embedding for the given text.

        Args:
            text (str): The text to embed.

        Returns:
            list: The embedding vector as a list of floats.

        Raises:
            UserError: If the provider is not configured properly.
        """
        self.ensure_one()

        # This is a placeholder. In a real implementation, this would call
        # the appropriate embedding API based on the provider.

        # Example provider implementations would go here.

        # For now, we raise a user error.
        from odoo.exceptions import UserError
        raise UserError(
            _("Embedding generation for provider {} is not implemented yet.").format(
                self.provider
            )
        )