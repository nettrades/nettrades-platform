# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Extended res.partner model
# =============================================================================
# This file extends the standard Odoo res.partner with fields for user roles,
# professional profiles, skills, experience, reviews, geolocation, and the
# "Good Answer" reputation system.
#
# Features added in this file:
#   - user_type field (job_seeker / freelancer / company / partner)
#   - professional profile fields (summary, skills, resume, hourly rate, etc.)
#   - geolocation and online presence
#   - One2many relationships for experience and reviews
#   - action_good_answer() – records a Good Answer vote, updates reputation,
#     creates AI feedback records, and awards indirect reputation to
#     professionals whose expert answers contributed to fine-tuning.
# =============================================================================
import json, logging
from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ---- User role classification ----
    user_type = fields.Selection([
        ('job_seeker', 'Job Seeker'),
        ('freelancer', 'Freelancer'),
        ('company', 'Company'),
        ('partner', 'Partner/Researcher')
    ], string="User Type", help="Determines which features are available on the portal.")

    # ---- Professional profile ----
    professional_summary = fields.Text(string="Professional Summary")
    # Many2many skills instead of Char
    skill_ids = fields.Many2many('nettrades.skill', string="Skills")
    resume_pdf = fields.Binary(string="CV / Resume", attachment=True)
    hourly_rate = fields.Float(string="Hourly Rate",
                               help="Rate charged for 'Ask Someone' sessions.")
    forgejo_username = fields.Char(string="Forgejo Username")
    github_username = fields.Char(string="GitHub Username")
    blog_url = fields.Char(string="Personal Blog / Website")

    # ---- Geolocation & presence (for matching) ----
    latitude = fields.Float()
    longitude = fields.Float()
    is_online = fields.Boolean(default=False)
    last_seen = fields.Datetime()
    charge_rate = fields.Float(help="Per-minute rate for expert sessions (Ask Someone).")

    # ---- Related records ----
    experience_ids = fields.One2many('nettrades.experience', 'partner_id',
                                     string="Work Experience")
    review_ids = fields.One2many('nettrades.review', 'reviewed_partner_id',
                                 string="Reviews")
    average_rating = fields.Float(compute='_compute_average_rating', store=True,
                                  help="Average rating across all received reviews.")

    # ---- Reputation ----
    reputation_points = fields.Integer(default=0)
    can_charge = fields.Boolean(default=False)

    @api.depends('review_ids.rating')
    def _compute_average_rating(self):
        """Compute the average star rating from received reviews."""
        for partner in self:
            ratings = partner.review_ids.mapped('rating')
            partner.average_rating = sum(ratings) / len(ratings) if ratings else 0.0

    # ---- Good Answer voting (integrated into partner for simplicity) ----
    def action_good_answer(self, answer_id, answer_model, answerer_id, field_id):
        """
        Record a 'Good Answer' vote.

        Prevents duplicate votes and awards points based on whether the voter
        is a qualified professional in the relevant field.

        If the answer is AI-generated, creates an llm.feedback record for the
        fine-tuning pipeline.  If the field has expert_answers_trainable enabled
        and the answer comes from an expert session, the expert's answer is also
        captured for training (patient question omitted).

        Additionally, awards indirect reputation points to professionals whose
        expert answers contributed to the fine-tuned model that generated this
        AI answer.
        """
        self.ensure_one()

        # ---- 1. Duplicate check ----
        existing = self.env['good.answer.vote'].search([
            ('user_id', '=', self.id),
            ('answer_id', '=', answer_id),
            ('answer_model', '=', answer_model),
        ])
        if existing:
            raise UserError(_("You have already voted on this answer."))

        # ---- 2. Look up the field ----
        field = self.env['nettrades.field'].browse(field_id)

        # ---- 3. Determine points: higher weight for qualified professionals ----
        qualified = self.env['qualified.professional'].search([
            ('partner_id', '=', self.id),
            ('field_id', '=', field_id),
            ('is_active', '=', True),
        ], limit=1)

        points = (qualified.points_per_vote or field.qualified_points_per_vote
                  if qualified else field.base_points_per_vote)

        # ---- 4. Create vote record ----
        vote = self.env['good.answer.vote'].create({
            'user_id': self.id,
            'answer_id': answer_id,
            'answer_model': answer_model,
            'answerer_id': answerer_id,
            'field_id': field_id,
            'points': points,
            'is_qualified_vote': bool(qualified),
        })

        # ---- 5. Update answerer's per-field reputation ----
        rep = self.env['user.field.reputation'].search([
            ('partner_id', '=', answerer_id),
            ('field_id', '=', field_id),
        ], limit=1)
        if not rep:
            rep = self.env['user.field.reputation'].create({
                'partner_id': answerer_id,
                'field_id': field_id,
            })
        rep.reputation_points += points

        # ---- 6. Record AI feedback (AI answers ALWAYS captured) ----
        if answer_model.startswith(('ai.', 'llm.')):
            self.env['llm.feedback'].sudo().create({
                'vote_id': vote.id,
                'weight': points,
                'field_id': field_id,
                'created_at': fields.Datetime.now(),
            })

        # ---- 7. Record expert feedback (only when field allows it) ----
        elif answer_model == 'expert.session' and field.expert_answers_trainable:
            self.env['llm.feedback'].sudo().create({
                'vote_id': vote.id,
                'weight': points,
                'field_id': field_id,
                'created_at': fields.Datetime.now(),
            })

        # ---- 8. Indirect reputation: reward professionals whose expert answers
        #        were used to fine-tune the AI that generated THIS answer. ----
        if (answer_model.startswith(('ai.', 'llm.'))
                and field.indirect_reputation_points > 0):
            last_job = self.env['ft.training.job'].search([
                ('field_id', '=', field_id),
                ('status', '=', 'completed'),
            ], order='completed_at desc', limit=1)
            if last_job:
                contributions = self.env['ft.dataset.contribution'].search([
                    ('dataset_id', '=', last_job.dataset_id.id),
                ])
                for contrib in contributions:
                    indirect_rep = self.env['user.field.reputation'].search([
                        ('partner_id', '=', contrib.partner_id.id),
                        ('field_id', '=', field_id),
                    ], limit=1)
                    if not indirect_rep:
                        indirect_rep = self.env['user.field.reputation'].create({
                            'partner_id': contrib.partner_id.id,
                            'field_id': field_id,
                        })
                    indirect_rep.reputation_points += field.indirect_reputation_points

        return True


# --- Supporting models ---
class NettradesExperience(models.Model):
    _name = 'nettrades.experience'
    _description = 'Work Experience'

    partner_id = fields.Many2one('res.partner', required=True)
    job_title = fields.Char(required=True)
    company = fields.Char(required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    description = fields.Text()


class NettradesReview(models.Model):
    _name = 'nettrades.review'
    _description = 'User Review'

    reviewer_id = fields.Many2one('res.partner', string="Reviewer", required=True)
    reviewed_partner_id = fields.Many2one('res.partner', string="Reviewed User",
                                           required=True)
    rating = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')],
        required=True, help="1 = poor, 5 = excellent"
    )
    comment = fields.Text()
    project_id = fields.Many2one('project.project')