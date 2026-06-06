# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – LLM Feedback model
# =============================================================================
# Each record represents a (question, answer) pair that was positively voted
# by a user.  This data feeds the fine-tuning pipeline.
#
# _fetch_question_and_answer() extracts the actual text from the source
# model.  For AI messages (llm.message), both the user message and the
# assistant response are stored.  For expert sessions, only the expert's
# answer is stored – the patient's original question is intentionally
# omitted to avoid capturing Protected Health Information.
# =============================================================================
from odoo import fields, models, api

class LLMFeedback(models.Model):
    _name = 'llm.feedback'
    _description = 'AI Feedback from Good Answer Votes'

    vote_id = fields.Many2one('good.answer.vote', required=True)
    weight = fields.Float()
    field_id = fields.Many2one('nettrades.field')
    input_text = fields.Text()
    output_text = fields.Text()
    created_at = fields.Datetime()
    processed = fields.Boolean(default=False)

    def _fetch_question_and_answer(self):
        """
        Retrieve the actual question and answer text from the source model.
        
        Supported source models:
          - ai.assistant.message / llm.message → AI chat message
          - expert.session → expert answer (patient question omitted)
        """
        for rec in self:
            vote = rec.vote_id
            model_name = vote.answer_model
            answer_id = vote.answer_id

            # ---- AI chat messages (Apexive LLM / Odoo AI) ----
            if model_name in ('ai.assistant.message', 'llm.message'):
                msg = self.env[model_name].browse(answer_id)
                rec.input_text = msg.user_message
                rec.output_text = msg.assistant_response

            # ---- Expert session answers (Ask Someone) ----
            elif model_name == 'expert.session':
                session = self.env[model_name].browse(answer_id)
                # The expert's answer is in a mail.message linked to the session.
                # We intentionally do NOT store the patient's original question
                # (session.task_summary) to avoid capturing PHI.
                expert_msg = self.env['mail.message'].search([
                    ('model', '=', 'expert.session'),
                    ('res_id', '=', session.id),
                    ('author_id', '=', session.expert_id.id),
                ], order='id desc', limit=1)
                rec.input_text = ''                     # patient question omitted
                rec.output_text = expert_msg.body if expert_msg else ''

            rec.processed = True

    def process_feedback(self):
        """
        Cron job entry point.  Collects unprocessed feedback and exports it
        into a fine-tuning dataset for the corresponding field.
        """
        dataset = self.env['ft.dataset'].search(
            [('name', '=', 'good_answer_feedback')], limit=1)
        if not dataset:
            field = self.env['nettrades.field'].search([], limit=1)
            dataset = self.env['ft.dataset'].create({
                'name': 'good_answer_feedback',
                'description': 'User votes on AI answers',
                'field_id': field.id,
            })

        feedbacks = self.search([('processed', '=', False)])
        for fb in feedbacks:
            fb._fetch_question_and_answer()
            if fb.input_text or fb.output_text:
                # Append to dataset file (simplified: just increment record count)
                dataset.record_count += 1
            fb.processed = True