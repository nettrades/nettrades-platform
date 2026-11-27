# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/inference_model_policy.py
# =============================================================================
# PURPOSE:
#   Per-model failover policy override.
#
#   The cluster-level policy (fields on gpu.cluster) is the default for every
#   model routed through that cluster. This model provides an OPTIONAL
#   per-model exception.
#
#   Use case: a university lab has an H200 node running a 70B model and an
#   RTX 4090 node running a 7B model in the same RPC cluster. The admin wants
#   the 7B model to fail over to Dynamo (cheap, fast) but wants the 70B model
#   to fail loudly (quality-critical, expensive). A cluster-level policy
#   cannot express this. A per-model override can.
#
# RESOLUTION SEMANTICS:
#   If a record exists for (cluster_id, model_name), it COMPLETELY REPLACES
#   the cluster default for that model. There is no field-by-field merge.
#   Replace semantics are deliberate: they keep the routing decision
#   unambiguous and the admin screen trivial to reason about.
#
# ODOO 20 COMPATIBILITY:
#   - Uses models.Constraint (the new API). _sql_constraints is removed in
#     Odoo 20 and silently ignored if present.
#   - No deprecated fields.
#   - The unique constraint is enforced at the database level so concurrent
#     creates cannot produce two policies for the same (cluster, model).
# =============================================================================

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class InferenceModelPolicy(models.Model):
    """
    Per-model failover policy override.

    One record per (cluster, model_name) pair. When present, it replaces
    the cluster-level defaults for the named model.
    """

    _name = 'inference.model.policy'
    _description = 'Per-Model Inference Failover Policy'
    _rec_name = 'model_name'
    _order = 'cluster_id, model_name'

    # =========================================================================
    # 1. IDENTIFICATION
    # =========================================================================

    cluster_id = fields.Many2one(
        'gpu.cluster',
        string='Cluster',
        required=True,
        ondelete='cascade',
        index=True,
        help="The cluster this policy applies to. Deleting the cluster "
             "deletes its model policies.",
    )

    model_name = fields.Char(
        string='Model Name',
        required=True,
        index=True,
        help="The model identifier exactly as it appears in the MODEL_NAME "
             "environment variable and in the supervisor's state. For "
             "example: 'deepseek-r1-distill-qwen-7b-q4_k_m'. The match is "
             "case-sensitive.",
    )

    active = fields.Boolean(
        string='Active',
        default=True,
        help="Uncheck to temporarily disable this policy. When disabled, "
             "the cluster default applies.",
    )

    description = fields.Text(
        string='Notes',
        help="Free-text notes. Useful for recording why this model needs "
             "a different policy from the cluster default.",
    )

    # =========================================================================
    # 2. FAILOVER TIER TOGGLES (same names as gpu.cluster for consistency)
    # =========================================================================

    allow_dynamo_fallback = fields.Boolean(
        string='Allow Dynamo Fallback',
        default=True,
        help="If the RPC cluster is unavailable, allow routing this model to "
             "a Dynamo cluster. The SAME model is served.",
    )

    allow_rpc_partial_fallback = fields.Boolean(
        string='Allow Partial RPC Fallback',
        default=False,
        help="If the RPC cluster loses workers, allow rebuilding it with the "
             "remaining healthy nodes. The model identity is unchanged.",
    )

    allow_marketplace_fallback = fields.Boolean(
        string='Allow GPU Marketplace Fallback',
        default=False,
        help="If no local cluster is available, rent GPUs from the NETTRADES "
             "marketplace. The SAME model is served on rented hardware.",
    )

    allow_external_api_fallback = fields.Boolean(
        string='Allow External API Fallback',
        default=False,
        help="LAST RESORT. Send prompts and responses to an external API "
             "provider. This leaves your network. Only enable if your data "
             "governance policy permits it.",
    )

    external_api_provider = fields.Selection(
        [
            ('openai', 'OpenAI'),
            ('anthropic', 'Anthropic'),
            ('custom', 'Custom (OpenAI-compatible)'),
        ],
        string='External API Provider',
        default='openai',
    )

    external_api_model = fields.Char(
        string='External API Model',
        default='gpt-4o',
        help="The model name to request from the external provider.",
    )

    # =========================================================================
    # 3. SQL CONSTRAINTS
    # =========================================================================
    # models.Constraint is the modern API and works on both Odoo 19 and
    # Odoo 20. It replaces the legacy `_sql_constraints` list, which is
    # deprecated in Odoo 19 (silently ignored — Odoo logs
    # "Model attribute '_sql_constraints' is no longer supported") and
    # removed entirely in Odoo 20.
    #
    # Do not add a `_sql_constraints = [...]` block "for compatibility".
    # Odoo 19 will warn and ignore it; Odoo 20 will refuse to load the
    # module. Use models.Constraint unconditionally.

    _unique_cluster_model = models.Constraint(
        'UNIQUE(cluster_id, model_name)',
        'Only one failover policy can exist per (cluster, model) pair. '
        'Edit the existing policy instead of creating a second one.',
    )
    
    # =========================================================================
    # 4. HELPERS
    # =========================================================================

    @api.model
    def resolve_policy(self, cluster_id: int, model_name: str) -> dict:
        """
        Return the effective failover policy for a (cluster, model) pair.

        Called by the LangGraph supervisor via the odoo-proxy. Returns a
        plain dict so the supervisor does not need an Odoo ORM session.

        Resolution:
          1. Look up an active per-model policy for (cluster, model_name).
          2. If found, return its six fields.
          3. If not found, return the cluster's six default fields.

        Args:
            cluster_id: the gpu.cluster id.
            model_name: the model identifier string.

        Returns:
            dict with keys:
                allow_dynamo_fallback
                allow_rpc_partial_fallback
                allow_marketplace_fallback
                allow_external_api_fallback
                external_api_provider
                external_api_model
                source: 'per_model' or 'cluster_default'
        """
        if not cluster_id:
            return self._empty_policy()

        # 1. Per-model override
        if model_name:
            per_model = self.sudo().search([
                ('cluster_id', '=', cluster_id),
                ('model_name', '=', model_name),
                ('active', '=', True),
            ], limit=1)
            if per_model:
                return {
                    'allow_dynamo_fallback': per_model.allow_dynamo_fallback,
                    'allow_rpc_partial_fallback': per_model.allow_rpc_partial_fallback,
                    'allow_marketplace_fallback': per_model.allow_marketplace_fallback,
                    'allow_external_api_fallback': per_model.allow_external_api_fallback,
                    'external_api_provider': per_model.external_api_provider,
                    'external_api_model': per_model.external_api_model,
                    'source': 'per_model',
                }

        # 2. Cluster default
        cluster = self.env['gpu.cluster'].sudo().browse(cluster_id)
        if not cluster.exists():
            return self._empty_policy()

        return {
            'allow_dynamo_fallback': cluster.allow_dynamo_fallback,
            'allow_rpc_partial_fallback': cluster.allow_rpc_partial_fallback,
            'allow_marketplace_fallback': cluster.allow_marketplace_fallback,
            'allow_external_api_fallback': cluster.allow_external_api_fallback,
            'external_api_provider': cluster.external_api_provider,
            'external_api_model': cluster.external_api_model,
            'source': 'cluster_default',
        }

    @api.model
    def _empty_policy(self) -> dict:
        """Return the safe default when nothing is configured."""
        return {
            'allow_dynamo_fallback': False,
            'allow_rpc_partial_fallback': False,
            'allow_marketplace_fallback': False,
            'allow_external_api_fallback': False,
            'external_api_provider': 'openai',
            'external_api_model': 'gpt-4o',
            'source': 'none',
        }
