# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Core – Extended res.partner model (MODIFIED)
# =============================================================================
# FILE: odoo-modules/nettrades_core/models/res_partner.py
#
# PURPOSE:
#   This file extends the standard Odoo res.partner with fields for user roles,
#   professional profiles, skills, experience, reviews, geolocation, and the
#   "Good Answer" reputation system.
#
# MODIFICATIONS:
#   - Added fairness evaluation trigger to action_good_answer method.
#   - When a user clicks "Good Answer", the response is evaluated for
#     rationality and bias using the fairness module.
#
# =============================================================================

# ... (existing imports) ...

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # ... (existing fields and methods) ...

    def action_good_answer(self, answer_id, answer_model, answerer_id, field_id):
        """
        Record a 'Good Answer' vote.

        This method is called when a user clicks "Good Answer" on a response.
        It records the vote, updates reputation, and triggers a fairness
        evaluation.

        MODIFIED: Added rationality and bias evaluation using the fairness module.
        """
        # ... (existing code to create the vote record) ...

        # =========================================================================
        # NEW: Trigger fairness evaluation
        # =========================================================================
        try:
            # Check if fairness module is installed
            if 'nettrades.fairness.evaluator' in self.env:
                # Get the original question and answer
                question = self._get_question_for_vote(vote)
                answer = self._get_answer_for_vote(vote)

                # Trigger the fairness evaluation
                evaluator = self.env['nettrades.fairness.evaluator']
                evaluation = evaluator.evaluate_response(
                    question=question,
                    answer=answer,
                    field_id=field_id,
                    response_id=answer_id,
                )

                if evaluation and evaluation.get('rationality_score') is not None:
                    _logger.info(
                        "Fairness evaluation completed for vote %s: "
                        "rationality=%.2f, bias=%.2f",
                        vote.id,
                        evaluation.get('rationality_score'),
                        evaluation.get('bias_score'),
                    )

        except Exception as e:
            # Don't let fairness evaluation break the voting flow
            _logger.error("Fairness evaluation failed for vote %s: %s", vote.id, e)

        # ... (rest of the existing method) ...

    def _get_question_for_vote(self, vote):
        """
        Get the question text for a Good Answer vote.

        This is a helper method that retrieves the original question from
        the vote context.

        Args:
            vote (good.answer.vote): The vote record.

        Returns:
            str: The question text, or empty string if not found.
        """
        # Implementation depends on how questions are stored
        # This is a placeholder that should be implemented based on your data model
        return "User question (retrieved from context)"

    def _get_answer_for_vote(self, vote):
        """
        Get the answer text for a Good Answer vote.

        This is a helper method that retrieves the answer from the vote context.

        Args:
            vote (good.answer.vote): The vote record.

        Returns:
            str: The answer text, or empty string if not found.
        """
        # Implementation depends on how answers are stored
        # This is a placeholder that should be implemented based on your data model
        return "AI answer (retrieved from context)"