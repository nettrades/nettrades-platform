# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – User Field Reputation model
# =============================================================================
# Tracks a user's reputation points for a single professional field.
# Points are earned through "Good Answer" votes.  When a user's reputation
# reaches a configurable threshold, they unlock the ability to charge for
# their expert sessions (Ask Someone).
#
# AUTONOMOUS CRON JOBS
#   _cron_decay_reputation()        – reduces points for inactive experts.
#   _cron_auto_qualify_by_karma()   – promotes users to Qualified Professional.
#   _cron_auto_adjust_weights()     – automatically adjusts qualified voting
#                                     weights based on community composition.
#
# ADMINISTRATOR CONFIGURATION
#   Thresholds and auto-qualify toggles are set per field in the Professional
#   Field form (nettrades.field), under the "Qualification & Karma" tab.
#   The "Voting Insights" section shows qualified-professional counts and
#   suggests optimal weight values.
#
# FUTURE ENHANCEMENTS
#   - Add a grace period before decay applies (e.g. start after 60 days).
#   - Allow professionals to "boost" their reputation by providing verified
#     credentials (linking to external certification services).
#   - Provide a public reputation history log for transparency.
# =============================================================================
from odoo import fields, models, api

class UserFieldReputation(models.Model):
    _name = 'user.field.reputation'
    _description = 'User reputation per field'

    partner_id = fields.Many2one(
        'res.partner', required=True,
        help="The professional whose reputation is being tracked."
    )
    field_id = fields.Many2one(
        'nettrades.field', required=True,
        help="The professional field this reputation applies to."
    )
    reputation_points = fields.Integer(
        default=0,
        help="Total reputation points earned in this field.  Higher points "
             "unlock charging privileges and improve search ranking."
    )
    can_charge = fields.Boolean(
        default=False,
        help="True when the user has reached the field's "
             "reputation_threshold_for_charging and can set a rate for "
             "Ask Someone sessions."
    )
    updated_at = fields.Datetime(
        default=fields.Datetime.now,
        help="Last time the reputation was modified.  Used for decay calculation."
    )

    # ------------------------------------------------------------------
    # Reputation Decay (1 % per night for inactive 30 days)
    # ------------------------------------------------------------------
    def _cron_decay_reputation(self):
        """
        Runs daily.  Reduces reputation points by 1 % for experts who have
        not received a Good Answer vote in the last 30 days.
        The floor is 0 – reputation never goes negative.
        """
        self.env.cr.execute("""
            UPDATE user_field_reputation
            SET reputation_points = GREATEST(reputation_points * 0.99, 0),
                updated_at = NOW()
            WHERE updated_at < NOW() - INTERVAL '30 days'
        """)

    # ------------------------------------------------------------------
    # Automatic Karma-Based Qualification
    # ------------------------------------------------------------------
    def _cron_auto_qualify_by_karma(self):
        """
        Runs hourly.  For fields where the administrator has enabled
        "Auto-Qualify by Karma", any user whose reputation in that field
        reaches the field's reputation_threshold_for_charging is
        automatically added to the Qualified Professionals list.
        This is NOT intended for regulated fields where credentials must
        be manually verified.
        """
        fields = self.env['nettrades.field'].search([
            ('auto_karma_qualify', '=', True)
        ])
        for field in fields:
            reps = self.search([
                ('field_id', '=', field.id),
                ('reputation_points', '>=', field.reputation_threshold_for_charging),
            ])
            for rep in reps:
                existing = self.env['qualified.professional'].search([
                    ('partner_id', '=', rep.partner_id.id),
                    ('field_id', '=', field.id),
                ], limit=1)
                if not existing:
                    self.env['qualified.professional'].create({
                        'partner_id': rep.partner_id.id,
                        'field_id': field.id,
                        'is_active': True,
                    })

    # ------------------------------------------------------------------
    # Automatic Voting-Weight Adjustment
    # ------------------------------------------------------------------
    def _cron_auto_adjust_weights(self):
        """
        Runs hourly.  For fields where the administrator has enabled
        "Auto-Adjust Weights", the qualified_points_per_vote value is
        automatically set to the suggested_qualified_weight, which is
        calculated from the ratio of qualified professionals to total
        voters in that field.
        This ensures that expert votes have appropriate influence even
        as the community grows.
        """
        fields = self.env['nettrades.field'].search([
            ('auto_adjust_weights', '=', True)
        ])
        for field in fields:
            # Recompute stats to get the latest suggestion
            field._compute_qualified_stats()
            if field.suggested_qualified_weight != field.qualified_points_per_vote:
                field.qualified_points_per_vote = field.suggested_qualified_weight