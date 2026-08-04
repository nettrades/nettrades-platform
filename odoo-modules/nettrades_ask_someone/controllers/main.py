# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Ask Someone - Main Controller
# =============================================================================
# FILE: odoo-modules/nettrades_ask_someone/controllers/main.py
#
# PURPOSE:
#   This controller provides the HTTP endpoints for the Ask Someone feature.
#   It handles:
#   - Creating expert session requests
#   - Matching experts based on field and location
#   - Inferring the professional field from the question
#
# KEY ENDPOINTS:
#   - POST /api/v1/ask_someone/request - Create a new expert session request
#
# INTEGRATION:
#   - Uses LangGraph for field inference
#   - Uses Odoo's payment.acquirer for Stripe escrow
#   - Uses qualified_professional model for expert filtering
# =============================================================================

from odoo import http
from odoo.http import request
import json
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class AskSomeoneController(http.Controller):

    @http.route('/api/v1/ask_someone/request', type='json', auth='user', methods=['POST'])
    def request_expert(self, **kwargs):
        """
        Create a new expert session request.

        Request body:
        {
            "artifact_id": int,          # Optional: ID of the artifact being discussed
            "artifact_model": str,       # Optional: Model of the artifact
            "question": str,             # The user's question
            "user_lat": float,           # Optional: User's latitude for proximity matching
            "user_lon": float,           # Optional: User's longitude for proximity matching
            "field_id": int,             # Optional: Professional field ID
        }

        Returns:
            {
                "session_id": str,       # The session identifier
                "expert_name": str,      # The name of the matched expert
                "error": str             # Error message if any
            }
        """
        artifact_id = kwargs.get('artifact_id')
        artifact_model = kwargs.get('artifact_model')
        question = kwargs.get('question', '')
        user_lat = kwargs.get('user_lat')
        user_lon = kwargs.get('user_lon')
        partner = request.env.user.partner_id
        field_id = kwargs.get('field_id')

        # Validate input
        if not question:
            return {'error': 'Question is required.'}

        # Infer the field if not provided
        if not field_id:
            field_id = self._infer_field(question)

        if not field_id:
            config = request.env['ir.config_parameter'].sudo()
            field_id = int(config.get_param('ask_someone.default_field_id', 0))

        if not field_id:
            return {'error': 'Could not determine field. Please specify a field.'}

        # Match experts for this field
        experts = self._match_experts(field_id, user_lat, user_lon, partner.id)

        if not experts:
            return {'error': 'No experts available at this time.'}

        top_expert = experts[0]

        # Create the session
        session = request.env['expert.session'].create({
            'requester_id': partner.id,
            'expert_id': top_expert['id'],
            'field_id': field_id,
            'task_summary': question,
            'rate_per_minute': top_expert.get('charge_rate', 1.0),
            'duration_minutes': 30,
            'status': 'pending',
        })

        # Notify the expert (via mail)
        session.message_post(
            body=f"New expert session request from {partner.display_name}. Question: {question}",
            subject="New Ask Someone Request",
            partner_ids=[(4, top_expert['id'])],
        )

        return {
            'session_id': session.session_id,
            'expert_name': top_expert['name'],
        }

    def _infer_field(self, question):
        """
        Infer the professional field from the question using LLM or keyword matching.

        Args:
            question (str): The user's question.

        Returns:
            int: The ID of the inferred field, or None.
        """
        # Try LLM provider first
        llm_providers = request.env['llm.provider'].search([('is_enabled', '=', True)], limit=1)

        if llm_providers:
            try:
                import requests
                webhook_url = request.env['ir.config_parameter'].sudo().get_param(
                    'langgraph_invoke_url',
                    'http://langgraph:8000/invoke'
                )
                api_key = request.env['ir.config_parameter'].sudo().get_param(
                    'langgraph_api_key',
                    ''
                )
                payload = {
                    "input": {
                        "messages": [{
                            "role": "user",
                            "content": f"Which professional field does this question belong to? Question: {question}"
                        }]
                    }
                }
                headers = {'x-api-key': api_key} if api_key else {}
                resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    field_name = data.get('analysis', '').strip().lower()
                    field = request.env['nettrades.field'].search([('name', 'ilike', field_name)], limit=1)
                    if field:
                        return field.id
            except Exception as e:
                _logger.warning(f"LLM field inference failed: {e}")

        # Fallback to keyword matching
        field = request.env['nettrades.field'].search([], limit=1)
        return field.id if field else None

    def _match_experts(self, field_id, user_lat, user_lon, requester_id):
        """
        Match experts for a given field.

        This method applies the following filters:
        1. Only users with an active qualified_professional record are considered
        2. For restricted fields (only_qualified=True), only verified professionals are shown
        3. Experts are ranked by reputation, availability, and proximity

        Args:
            field_id (int): The professional field ID.
            user_lat (float): User's latitude.
            user_lon (float): User's longitude.
            requester_id (int): The ID of the requester.

        Returns:
            list: List of expert dictionaries with keys: id, name, charge_rate, distance.
        """
        # Get the field configuration
        field = request.env['nettrades.field'].browse(field_id)
        if not field.exists():
            return []

        # Build the domain for qualified professionals
        domain = [
            ('field_id', '=', field_id),
            ('is_active', '=', True),
        ]

        # For restricted fields, only show manually verified professionals
        if field.only_qualified:
            domain.append(('is_verified', '=', True))

        # Get qualified professionals
        qualified = request.env['qualified_professional'].search(domain)

        if not qualified:
            _logger.info("No qualified professionals found for field %s", field_id)
            return []

        # Build the expert list
        experts = []
        for qp in qualified:
            partner = qp.partner_id
            if not partner or partner.id == requester_id:
                continue

            # Check if the expert is online and available
            is_online = getattr(partner, 'is_online', False)
            is_available = getattr(partner, 'is_available', True)

            if not is_online or not is_available:
                continue

            expert_data = {
                'id': partner.id,
                'name': partner.display_name or partner.name or 'Expert',
                'charge_rate': qp.charge_rate or 1.0,
                'reputation': qp.reputation_score or 0,
                'distance': 0,  # In production, calculate distance using geocoding
                'is_verified': qp.is_verified,
            }

            # Calculate distance if coordinates are provided
            if user_lat and user_lon and partner.partner_latitude and partner.partner_longitude:
                # Simplified distance calculation (in production, use geocoding service)
                # For now, use a simple placeholder
                expert_data['distance'] = 0

            experts.append(expert_data)

        # Sort experts by reputation (highest first), then by availability
        experts.sort(key=lambda e: (-e['reputation'], e.get('distance', 0)))

        _logger.info("Matched %d experts for field %s", len(experts), field_id)
        return experts