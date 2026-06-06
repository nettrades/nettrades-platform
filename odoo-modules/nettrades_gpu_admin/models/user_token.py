# -*- coding: utf-8 -*-
# =============================================================================
# Section H – GPU Node model (nettrades_gpu_admin)
# This file needs to be updated
# =============================================================================

from odoo import fields, models, api, _
from odoo.exceptions import UserError

class AIGPUUserToken(models.Model):
    _name = 'ai.gpu.user_token'
    _description = 'User Token Balance for GPU Sharing'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    free_tokens_remaining = fields.Integer(default=100000)
    gpu_sharing_enabled = fields.Boolean(default=False)
    extra_tokens = fields.Integer(default=0)

    def deduct_tokens(self, tokens):
        self.env.cr.execute("""
            UPDATE ai_gpu_user_token
            SET free_tokens_remaining = free_tokens_remaining - %s,
                updated_at = NOW()
            WHERE id = %s
              AND gpu_sharing_enabled = FALSE
              AND free_tokens_remaining >= %s
            RETURNING free_tokens_remaining
        """, (tokens, self.id, tokens))
        if not self.env.cr.fetchone():
            raise UserError(_(
                "Insufficient free tokens. Enable GPU sharing for unlimited usage."
            ))
        return True