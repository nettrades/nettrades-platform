# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness - Metrics Calculator
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/models/fairness_metrics.py
#
# PURPOSE:
#   This file implements fairness metrics calculation for the NETTRADES
#   platform. It provides:
#     1. Demographic Parity: Selection rates are similar across groups
#     2. Equal Opportunity: True positive rates are similar across groups
#     3. Disparate Impact: Ratio of selection rates (four-fifths rule)
#
#   These metrics are used to:
#     - Monitor the system for bias over time
#     - Generate compliance reports (NYC Local Law 144)
#     - Identify areas for improvement
#
# LAZY IMPORTS (2026-10-22):
#   pandas and numpy are imported INSIDE the methods that use them, not at
#   module top-level. Importing pandas at top-level pulls in NumPy, which
#   pulls in OpenBLAS, which spawns 64 worker threads during registry load.
#   On containers with a low RLIMIT_NPROC, that produces:
#       OpenBLAS blas_thread_init: pthread_create failed for thread N of 64
#       Resource temporarily unavailable
#   and blocks installation of nettrades_fairness entirely.
#
#   Moving the imports inside the methods means:
#     - Registry load never touches pandas or NumPy.
#     - The first call to a metrics method pays the import cost (~500ms),
#       subsequent calls are free (Python caches imports at module level).
#     - The module installs cleanly even if pandas is absent.
#
#   This is a product-level fix, not a demo hack: it means the fairness
#   module can be installed without requiring pandas/numpy to be present,
#   and the metrics API returns a clear error if they are not.
#
# =============================================================================

from odoo import fields, models, api, _
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class FairnessMetrics(models.TransientModel):
    """
    Fairness Metrics Calculator - computes fairness metrics for the system.
    """
    _name = 'nettrades.fairness.metrics'
    _description = 'Fairness Metrics Calculator'
    _transient = True

    # =========================================================================
    # 0. Lazy import helper
    # =========================================================================
    @api.model
    def _require_numeric_stack(self):
        """
        Return (pd, np) with lazy import.

        Raises UserError with an actionable message if pandas or numpy are
        not installed. This is better than an opaque ImportError from a
        top-level import, which would break the entire module's registry
        load.
        """
        try:
            import pandas as pd  # noqa: F401
            import numpy as np   # noqa: F401
        except ImportError as e:
            raise UserError(_(
                "Fairness metrics require pandas and numpy. "
                "Install them on the Odoo container with: "
                "pip3 install --break-system-packages pandas numpy\n"
                "Original error: %s"
            ) % str(e))
        return pd, np

    # =========================================================================
    # 1. Metric Calculation Methods
    # =========================================================================

    @api.model
    def calculate_demographic_parity(self, candidate_ids, protected_attr,
                                     score_field='ai_match_score', threshold=0.7):
        """
        Calculate demographic parity: selection rates are similar across groups.

        Demographic parity requires that the proportion of positive outcomes
        is roughly equal across groups.

        Args:
            candidate_ids (list): List of candidate record IDs.
            protected_attr (str): The protected attribute field name (e.g., 'gender').
            score_field (str): The field name for the prediction score.
            threshold (float): The threshold for a positive outcome.

        Returns:
            dict: Demographic parity metrics.
        """
        pd, np = self._require_numeric_stack()

        # Fetch candidate data
        candidates = self.env['hr.applicant'].browse(candidate_ids)
        if not candidates:
            return {'error': 'No candidates found'}

        # Build DataFrame
        data = []
        for candidate in candidates:
            protected_value = getattr(candidate, protected_attr, None)
            if protected_value is None:
                continue
            score = getattr(candidate, score_field, 0) or 0
            data.append({
                'protected': protected_value,
                'score': float(score),
                'positive': float(score) >= threshold,
            })

        if not data:
            return {'error': 'No valid data'}

        df = pd.DataFrame(data)

        # Calculate selection rates per group
        group_rates = df.groupby('protected')['positive'].mean().to_dict()

        # Calculate demographic parity ratio
        rates = list(group_rates.values())
        if len(rates) < 2:
            return {
                'group_rates': group_rates,
                'parity_ratio': 1.0,
                'passed': True,
                'message': 'Only one group found'
            }

        min_rate = min(rates)
        max_rate = max(rates)
        parity_ratio = min_rate / max_rate if max_rate > 0 else 1.0

        # Four-fifths rule: parity_ratio >= 0.8 is considered fair
        passed = parity_ratio >= 0.8

        return {
            'group_rates': group_rates,
            'parity_ratio': parity_ratio,
            'passed': passed,
            'message': f'Demographic parity ratio: {parity_ratio:.3f} {"(Passed)" if passed else "(Failed)"}',
        }

    @api.model
    def calculate_equal_opportunity(self, candidate_ids, protected_attr,
                                    outcome_attr='hired', score_field='ai_match_score',
                                    threshold=0.7):
        """
        Calculate equal opportunity: true positive rates are similar across groups.

        Equal opportunity requires that the model has similar true positive
        rates across groups.

        Args:
            candidate_ids (list): List of candidate record IDs.
            protected_attr (str): The protected attribute field name.
            outcome_attr (str): The field name for the actual outcome.
            score_field (str): The field name for the prediction score.
            threshold (float): The threshold for a positive prediction.

        Returns:
            dict: Equal opportunity metrics.
        """
        pd, np = self._require_numeric_stack()

        candidates = self.env['hr.applicant'].browse(candidate_ids)
        if not candidates:
            return {'error': 'No candidates found'}

        # Build DataFrame
        data = []
        for candidate in candidates:
            protected_value = getattr(candidate, protected_attr, None)
            if protected_value is None:
                continue
            score = getattr(candidate, score_field, 0) or 0
            actual_outcome = getattr(candidate, outcome_attr, False) or False
            predicted_positive = float(score) >= threshold
            data.append({
                'protected': protected_value,
                'score': float(score),
                'actual': bool(actual_outcome),
                'predicted': predicted_positive,
            })

        if not data:
            return {'error': 'No valid data'}

        df = pd.DataFrame(data)

        # Calculate true positive rates per group
        def tpr(group):
            actual_pos = group[group['actual']]
            if len(actual_pos) == 0:
                return 0.0
            true_pos = len(actual_pos[actual_pos['predicted']])
            return true_pos / len(actual_pos)

        group_tpr = df.groupby('protected').apply(tpr).to_dict()

        # Calculate equal opportunity ratio
        rates = list(group_tpr.values())
        if len(rates) < 2:
            return {
                'group_tpr': group_tpr,
                'eo_ratio': 1.0,
                'passed': True,
                'message': 'Only one group found'
            }

        min_rate = min(rates)
        max_rate = max(rates)
        eo_ratio = min_rate / max_rate if max_rate > 0 else 1.0
        passed = eo_ratio >= 0.8

        return {
            'group_tpr': group_tpr,
            'eo_ratio': eo_ratio,
            'passed': passed,
            'message': f'Equal opportunity ratio: {eo_ratio:.3f} {"(Passed)" if passed else "(Failed)"}',
        }

    @api.model
    def calculate_disparate_impact(self, candidate_ids, protected_attr,
                                   score_field='ai_match_score', threshold=0.7):
        """
        Calculate disparate impact (four-fifths rule).

        Delegates to calculate_demographic_parity so it inherits the lazy
        pandas import.
        Args:
            candidate_ids (list): List of candidate record IDs.
            protected_attr (str): The protected attribute field name.
            score_field (str): The field name for the prediction score.
            threshold (float): The threshold for a positive outcome.

        Returns:
            dict: Disparate impact metrics.
        """
        result = self.calculate_demographic_parity(
            candidate_ids, protected_attr, score_field, threshold,
        )
        result['metric_name'] = 'disparate_impact'
        result['threshold'] = 0.8
        result['rule'] = 'four-fifths'
        return result

    # =========================================================================
    # 2. Automated Audit
    # =========================================================================

    @api.model
    def run_audit(self, field_id=None, protected_attr='gender'):
        """
        Run a comprehensive fairness audit for a field.

        This method calculates all fairness metrics and creates an audit record.

        Args:
            field_id (int, optional): The professional field to audit.
            protected_attr (str): The protected attribute to check.

        Returns:
            dict: Audit results.
        """
        domain = []
        if field_id:
            domain.append(('field_id', '=', field_id))

        candidates = self.env['hr.applicant'].search(domain)
        if not candidates:
            return {'error': 'No candidates found for audit'}

        # Calculate metrics
        dp_result = self.calculate_demographic_parity(candidates.ids, protected_attr)
        eo_result = self.calculate_equal_opportunity(candidates.ids, protected_attr)
        di_result = self.calculate_disparate_impact(candidates.ids, protected_attr)

        # Create audit record
        audit = self.env['nettrades.fairness.audit'].create({
            'field_id': field_id,
            'question_text': f'Automated audit for {protected_attr}',
            'response_text': (
                f'Demographic Parity: {dp_result.get("parity_ratio", 0):.3f}\n'
                f'Equal Opportunity: {eo_result.get("eo_ratio", 0):.3f}\n'
                f'Disparate Impact: {di_result.get("parity_ratio", 0):.3f}'
            ),
            'rationale': dp_result.get('message', '') + '\n' + eo_result.get('message', ''),
            'evaluation_model': 'automated_audit',
            'protected_attributes': protected_attr,
        })

        return {
            'audit_id': audit.id,
            'demographic_parity': dp_result,
            'equal_opportunity': eo_result,
            'disparate_impact': di_result,
            'overall_passed': dp_result.get('passed', False) and eo_result.get('passed', False),
        }