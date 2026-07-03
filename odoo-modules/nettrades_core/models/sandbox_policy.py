# =============================================================================
# FILE: addons/nettrades_core/models/sandbox_policy.py
# =============================================================================
# PURPOSE:
#   Defines sandboxing policies for inference jobs.
#   Administrators can set default trust levels and per_user/ per_job overrides.
# =============================================================================

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class SandboxPolicy(models.Model):
    _name = 'nettrades.sandbox.policy'
    _description = 'Sandbox Policy for Untrusted Code Execution'
    _order = 'sequence'

    name = fields.Char(string="Policy Name", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # === Trust Level ===
    trust_level = fields.Selection([
        ('always_sandbox', 'Always Sandbox'),
        ('never_sandbox', 'Never Sandbox'),
        ('source_based', 'Source-Based (Recommended)'),
    ], string="Trust Level", default='source_based', required=True)

    # === Source_Based Rules ===
    internal_trusted_sources = fields.Many2many(
        'res.users', string="Trusted Internal Users",
        help="Users who can bypass sandbox when running approved code."
    )
    internal_untrusted_sources = fields.Selection([
        ('none', 'None - Always Sandbox'),
        ('downloaded', 'Downloaded Code'),
        ('ai_generated', 'AI Generated Code'),
        ('both', 'Both Downloaded and AI Generated'),
    ], string="Untrusted Sources for Internal Users", default='both')

    external_policy = fields.Selection([
        ('sandbox', 'Always Sandbox'),
        ('block', 'Block External Execution'),
    ], string="External User Policy", default='sandbox')

    # === Runtime Selection ===
    sandbox_runtime = fields.Selection([
        ('gvisor', 'gVisor (CPU)'),
        ('gvisor_gpu', 'gVisor + GPU (nvproxy)'),
        ('none', 'No Sandbox (runc)'),
    ], string="Runtime Class for Sandbox", default='gvisor')

    # === Network & Filesystem ===
    network_egress = fields.Selection([
        ('blocked', 'Block All'),
        ('whitelist', 'Whitelist Only'),
        ('allowed', 'Allow All'),
    ], string="Network Egress Policy", default='whitelist')

    filesystem_policy = fields.Selection([
        ('readonly', 'Read Only'),
        ('workspace', 'Workspace Only'),
        ('full', 'Full Access'),
    ], string="Filesystem Policy", default='workspace')

    # === Helpers ===
    def get_runtime_class(self, user, code_source, requires_gpu):
        """Determine runtime class for a given job."""
        self.ensure_one()
        if self.trust_level == 'always_sandbox':
            return self.sandbox_runtime if self.sandbox_runtime != 'none' else 'gvisor'
        if self.trust_level == 'never_sandbox':
            return 'runc'

        # source_based
        is_internal = user in self.internal_trusted_sources or user.has_group('base.group_user')
        if is_internal:
            # Internal user: check source type
            if code_source in ['downloaded', 'ai_generated'] and self.internal_untrusted_sources in ['both', code_source]:
                return self.sandbox_runtime if self.sandbox_runtime != 'none' else 'gvisor'
            else:
                return 'runc'   # trusted code
        else:
            # External user
            if self.external_policy == 'block':
                raise ValidationError("External execution is blocked by policy.")
            return self.sandbox_runtime if self.sandbox_runtime != 'none' else 'gvisor'

    @api.model
    def get_active_policy(self):
        """Return the first active policy, or create a default one."""
        policy = self.search([('active', '=', True)], limit=1)
        if not policy:
            policy = self.create({
                'name': 'Default Policy',
                'trust_level': 'source_based',
                'internal_trusted_sources': [(4, ref('base.user_root'))],
                'internal_untrusted_sources': 'both',
                'external_policy': 'sandbox',
                'sandbox_runtime': 'gvisor_gpu',  # default to GPU if needed
            })
        return policy