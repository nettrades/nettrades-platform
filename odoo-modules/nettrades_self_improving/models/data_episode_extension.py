# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Self-Improving - data.episode Extension
# FILE: odoo-modules/nettrades_self_improving/models/data_episode_extension.py
# =============================================================================
# Adds quality-signal fields to data.episode. Any module that produces a
# quality signal writes to these fields; the training pipeline reads them.
#
# Safe to extend here because this module declares nettrades_data_collection
# as a dependency, so data.episode is registered before this file loads.
# =============================================================================

from odoo import fields, models


class DataEpisode(models.Model):
    _inherit = 'data.episode'

    fairness_score = fields.Float(
        string='Fairness Score',
        default=0.0,
        index=True,
        help="Composite score: rationality_score - bias_score. "
             "Range -10 (worst) to +10 (best). Written by nettrades_fairness "
             "if installed; otherwise stays at 0.0 and is ignored by filters.",
    )

    hallucination_score = fields.Float(
        string='Hallucination Score',
        default=0.0,
        index=True,
        help="Reserved for future hallucination detection. "
             "Range 0 (factual) to 10 (fabricated).",
    )

    user_satisfaction = fields.Float(
        string='User Satisfaction',
        default=0.0,
        index=True,
        help="Reserved for future user satisfaction signals. "
             "Range 0 (unhappy) to 10 (delighted).",
    )