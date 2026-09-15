# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_vote.py
# =============================================================================
# PURPOSE:
#   Defines the nettrades.vote model, which records user votes on
#   NETTRADES Good Answers. This model is referenced in the security
#   rules and is essential for the Good Answer quality scoring system.
#
# RELATIONSHIPS:
#   - answer_id -> nettrades.good_answer (the answer being voted on)
#   - user_id -> nettrades.user (the user who cast the vote)
#
# KEY FEATURES:
#   - Tracks positive and negative votes
#   - Enables quality scoring for self-improving loop
#   - Tenant-isolated via company_id on the related user
# =============================================================================

from odoo import fields, models, api


class NettradesVote(models.Model):
    """
    NETTRADES Vote Model.

    Records a user's vote (positive or negative) on a NETTRADES Good Answer.
    This is used by the self-improving loop to determine which answers
    should be used for fine-tuning.
    """
    _name = 'nettrades.vote'
    _description = 'NETTRADES Vote'
    _rec_name = 'id'
    _order = 'create_date desc'

    # =========================================================================
    # 1. RELATIONSHIPS
    # =========================================================================

    answer_id = fields.Many2one(
        'nettrades.good_answer',
        string='Answer',
        required=True,
        ondelete='cascade',
        help="The Good Answer that this vote relates to."
    )

    user_id = fields.Many2one(
        'nettrades.user',
        string='User',
        required=True,
        ondelete='cascade',
        help="The user who cast this vote."
    )

    # =========================================================================
    # 2. VOTE DATA
    # =========================================================================

    vote_type = fields.Selection(
        [
            ('positive', 'Positive'),
            ('negative', 'Negative'),
        ],
        string='Vote Type',
        required=True,
        default='positive',
        help="Whether the user voted positively or negatively on the answer."
    )

    comment = fields.Text(
        string='Comment',
        help="Optional comment explaining the vote."
    )

    # =========================================================================
    # 3. COMPUTED / RELATED FIELDS
    # =========================================================================

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='user_id.company_id',
        store=True,
        readonly=True,
        help="The company that the voting user belongs to (for tenant isolation)."
    )

    # =========================================================================
    # 4. SQL CONSTRAINTS
    # =========================================================================

    _sql_constraints = [
        (
            'unique_user_answer_vote',
            'UNIQUE(answer_id, user_id)',
            'A user can only vote once per answer.'
        ),
    ]