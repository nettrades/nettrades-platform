# -*- coding: utf-8 -*-
# Section A-F - Stores AI-generated match scores between a job and a candidate.
from odoo import fields, models

class NettradesUserMatch(models.Model):
    """
    Each record represents one match result produced by the LangGraph agent.
    It links a job with a user (partner) and stores the computed score and analysis text.
    """
    _name = 'nettrades.user_match'
    _description = 'AI Match between Job and User'

    job_id = fields.Many2one(
        'hr.job', required=True,
        help="The job posting for which the match was calculated."
    )
    user_id = fields.Many2one(
        'res.partner', required=True,
        help="The candidate (job seeker / freelancer) who was matched."
    )
    match_score = fields.Float(
        string="Match Score (0-100)",
        help="Higher values indicate a better fit, as determined by the AI."
    )
    analysis = fields.Text(
        string="AI Analysis",
        help="Natural-language explanation of the match reasoning."
    )
    created_at = fields.Datetime(
        default=fields.Datetime.now,
        help="When the match record was created."
    )