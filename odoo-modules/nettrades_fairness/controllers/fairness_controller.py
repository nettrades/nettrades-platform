# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Fairness - REST API Controller
# =============================================================================
# FILE: odoo-modules/nettrades_fairness/controllers/fairness_controller.py
#
# PURPOSE:
#   This controller provides REST API endpoints for the fairness system.
#   It enables external tools and services to interact with the fairness
#   module programmatically.
#
# ENDPOINTS:
#   - GET /api/fairness/health - Health check
#   - POST /api/fairness/evaluate - Evaluate a response
#   - GET /api/fairness/audit - Get audit logs
#   - GET /api/fairness/metrics - Get fairness metrics
#   - POST /api/fairness/flag/review - Review a flag
#
# =============================================================================

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError
import json
import logging

_logger = logging.getLogger(__name__)


class FairnessController(http.Controller):

    # =========================================================================
    # 1. Health Check
    # =========================================================================

    @http.route('/api/fairness/health', type='json', auth='public', methods=['GET'], csrf=False)
    def health_check(self):
        """
        Health check endpoint for the fairness system.

        Returns:
            dict: Health status.
        """
        return {
            'status': 'healthy',
            'version': '1.0.0',
            'timestamp': fields.Datetime.now().isoformat(),
        }

    # =========================================================================
    # 2. Evaluate Response
    # =========================================================================

    @http.route('/api/fairness/evaluate', type='json', auth='user', methods=['POST'], csrf=False)
    def evaluate_response(self):
        """
        Evaluate an AI response for rationality and bias.

        Request format:
        {
            "question": "What is the capital of France?",
            "answer": "The capital of France is Paris.",
            "field_id": 1  # optional
        }

        Returns:
            dict: Evaluation results.
        """
        params = request.json or {}
        question = params.get('question')
        answer = params.get('answer')
        field_id = params.get('field_id')

        if not question or not answer:
            return {
                'status': 'error',
                'message': 'Missing question or answer',
            }

        evaluator = request.env['nettrades.fairness.evaluator']
        result = evaluator.evaluate_response(question, answer, field_id)

        return {
            'status': 'success',
            'data': result,
        }

    # =========================================================================
    # 3. Get Audit Logs
    # =========================================================================

    @http.route('/api/fairness/audit', type='json', auth='user', methods=['GET'], csrf=False)
    def get_audit_logs(self):
        """
        Get fairness audit logs.

        Query parameters:
            - limit: Maximum number of records (default 100)
            - offset: Pagination offset (default 0)
            - field_id: Filter by field ID

        Returns:
            dict: Audit log entries.
        """
        params = request.params or {}

        domain = []
        field_id = params.get('field_id')
        if field_id:
            domain.append(('field_id', '=', field_id))

        limit = int(params.get('limit', 100))
        offset = int(params.get('offset', 0))

        logs = request.env['nettrades.fairness.audit'].search(
            domain,
            order='create_date DESC',
            limit=limit,
            offset=offset,
        )

        return {
            'status': 'success',
            'data': [{
                'id': log.id,
                'rationality_score': log.rationality_score,
                'bias_score': log.bias_score,
                'rationale': log.rationale,
                'is_passed': log.is_passed,
                'create_date': log.create_date.isoformat() if log.create_date else None,
            } for log in logs],
            'total': request.env['nettrades.fairness.audit'].search_count(domain),
        }

    # =========================================================================
    # 4. Get Fairness Metrics
    # =========================================================================

    @http.route('/api/fairness/metrics', type='json', auth='user', methods=['GET'], csrf=False)
    def get_metrics(self):
        """
        Get fairness metrics for the system.

        Query parameters:
            - field_id: Filter by field ID
            - protected_attr: Protected attribute to check (default 'gender')

        Returns:
            dict: Fairness metrics.
        """
        params = request.params or {}
        field_id = params.get('field_id')
        protected_attr = params.get('protected_attr', 'gender')

        metrics = request.env['nettrades.fairness.metrics']
        result = metrics.run_audit(field_id, protected_attr)

        return {
            'status': 'success',
            'data': result,
        }

    # =========================================================================
    # 5. Review a Flag
    # =========================================================================

    @http.route('/api/fairness/flag/review', type='json', auth='user', methods=['POST'], csrf=False)
    def review_flag(self):
        """
        Review a fairness flag.

        Request format:
        {
            "flag_id": 1,
            "status": "accepted",
            "notes": "This response is fine."
        }

        Returns:
            dict: Review result.
        """
        params = request.json or {}
        flag_id = params.get('flag_id')
        status = params.get('status', 'reviewed')
        notes = params.get('notes', '')

        if not flag_id:
            return {
                'status': 'error',
                'message': 'Missing flag_id',
            }

        flag = request.env['nettrades.fairness.flag'].browse(flag_id)

        if not flag.exists():
            return {
                'status': 'error',
                'message': 'Flag not found',
            }

        flag.action_review(notes, status)

        return {
            'status': 'success',
            'message': f'Flag {flag_id} reviewed with status {status}',
        }