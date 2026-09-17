# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/nettrades_vote.py
# =============================================================================
# PURPOSE:
#   Records a user's vote (positive or negative) on a NETTRADES Good Answer.
#   Feeds the self-improving loop: answers with many positive votes are
#   prioritised as fine-tuning data.
#
# RELATIONSHIPS:
#   - answer_id  -> nettrades.good_answer (the answer being voted on)
#   - user_id    -> nettrades.user        (the user who cast the vote)
#
# WHY THIS FILE EXISTS:
#   The file was missing from the codebase, but security/nettrades_security.xml
#   contains a record rule that references the model:
#
#       <record id="rule_company_votes" model="ir.rule">
#           <field name="model_id" ref="nettrades_core.model_nettrades_vote"/>
#
#   Odoo auto-generates the XML ID `model_nettrades_vote` from the model's
#   `_name` attribute. Because no model with `_name = 'nettrades.vote'`
#   existed, the XML ID could not be resolved, and the module aborted with:
#
#       ValueError: External ID not found in the system:
#           nettrades_core.model_nettrades_vote
#
#   Because nettrades_core is the root of the NETTRADES module tree, every
#   module that depends on it (10 of the 12) also failed. Adding this one
#   file unblocks all of them.
#
# DESIGN DECISIONS:
#   - `_order = 'create_date desc'` - newest votes first, which is what
#     the UI and the self-improving loop both want.
#   - `_rec_name = 'id'` - a vote has no natural human-readable name, so
#     we use the record ID as its display name.
#   - The unique constraint on (answer_id, user_id) enforces "one vote per
#     user per answer" at the database level. The helper `record_vote()`
#     implements upsert semantics so callers don't have to handle the
#     duplicate case themselves.
# =============================================================================

from odoo import fields, models, api
import logging

_logger = logging.getLogger(__name__)


class NettradesVote(models.Model):
    """
    NETTRADES Vote.

    A single user's positive or negative vote on a single NETTRADES Good
    Answer. Used by the Good Answer agent to compute a quality score, and
    by the self-improving loop to select training data.
    """

    _name = 'nettrades.vote'
    _description = 'NETTRADES Vote'
    _rec_name = 'id'
    _order = 'create_date desc'

    # =========================================================================
    # 1. RELATIONSHIPS
    # =========================================================================

    answer_id = fields.Many2one(
        comodel_name='nettrades.good_answer',
        string='Answer',
        required=True,
        ondelete='cascade',
        index=True,
        help="The Good Answer this vote relates to. Deleting the answer "
             "deletes its votes (cascade).",
    )

    user_id = fields.Many2one(
        comodel_name='nettrades.user',
        string='User',
        required=True,
        ondelete='cascade',
        index=True,
        help="The user who cast the vote.",
    )

    # =========================================================================
    # 2. VOTE DATA
    # =========================================================================

    vote_type = fields.Selection(
        selection=[
            ('positive', 'Positive'),
            ('negative', 'Negative'),
        ],
        string='Vote Type',
        required=True,
        default='positive',
        help="Positive votes add weight to the answer; negative votes "
             "reduce it. Both are recorded for audit purposes.",
    )

    comment = fields.Text(
        string='Comment',
        help="Optional free-text reason for the vote. Useful for the "
             "self-improving loop to distinguish 'this is wrong' from "
             "'this is not what I asked for'.",
    )

    # =========================================================================
    # 3. TENANT ISOLATION (derived, stored for efficient filtering)
    # =========================================================================
    # `company_id` is derived from the voting user. Storing it here means
    # the tenant-isolation record rule can filter directly on this field
    # instead of traversing `user_id.company_id`, which is much faster at
    # scale. It is `readonly=True` because users must not be able to
    # reassign a vote to a different tenant.
    # =========================================================================

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        related='user_id.company_id',
        store=True,
        readonly=True,
        index=True,
        help="Tenant that the voting user belongs to. Derived; do not edit.",
    )

    # =========================================================================
    # 4. SQL CONSTRAINTS
    # =========================================================================
    # A user may change their vote (the helper below does an upsert), but
    # they may not have two votes on the same answer. This is enforced at
    # the database level so it holds even under concurrent writes.
    # =========================================================================

    _sql_constraints = [
        (
            'unique_user_answer_vote',
            'UNIQUE(answer_id, user_id)',
            'A user can only vote once per answer. '
            'Update the existing vote instead of creating a new one.',
        ),
    ]

    # =========================================================================
    # 5. HELPER METHODS
    # =========================================================================

    @api.model
    def record_vote(self, answer_id, user_id, vote_type, comment=None):
        """
        Record or update a vote (upsert).

        This is the only supported way for callers to create or change a
        vote. It handles the duplicate case cleanly, so the caller does
        not need to search first.

        Args:
            answer_id (int): ID of the nettrades.good_answer.
            user_id (int):   ID of the nettrades.user casting the vote.
            vote_type (str): 'positive' or 'negative'.
            comment (str):   Optional free-text comment.

        Returns:
            nettrades.vote: The created or updated vote record.
        """
        Vote = self.env['nettrades.vote']
        existing = Vote.search([
            ('answer_id', '=', answer_id),
            ('user_id', '=', user_id),
        ], limit=1)

        values = {'vote_type': vote_type, 'comment': comment}

        if existing:
            existing.write(values)
            _logger.info(
                "Updated vote %s (answer=%s user=%s -> %s)",
                existing.id, answer_id, user_id, vote_type,
            )
            return existing

        values.update({'answer_id': answer_id, 'user_id': user_id})
        new_vote = Vote.create(values)
        _logger.info(
            "Created vote %s (answer=%s user=%s -> %s)",
            new_vote.id, answer_id, user_id, vote_type,
        )
        return new_vote