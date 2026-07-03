from odoo import http
from odoo.http import request
import json, logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class AskSomeoneController(http.Controller):

    @http.route('/api/v1/ask_someone/request', type='json', auth='user', methods=['POST'])
    def request_expert(self, **kwargs):
        artifact_id = kwargs.get('artifact_id')
        artifact_model = kwargs.get('artifact_model')
        question = kwargs.get('question', '')
        user_lat = kwargs.get('user_lat')
        user_lon = kwargs.get('user_lon')
        partner = request.env.user.partner_id

        field_id = kwargs.get('field_id')
        if not field_id and question:
            field_id = self._infer_field(question)

        if not field_id:
            config = request.env['ir.config_parameter'].sudo()
            field_id = int(config.get_param('ask_someone.default_field_id', 0))
            if not field_id:
                return {'error': 'Could not determine field. Please specify a field.'}

        experts = self._match_experts(field_id, user_lat, user_lon, partner.id)
        if not experts:
            return {'error': 'No experts available at this time.'}

        top_expert = experts[0]
        session = request.env['expert.session'].create({
            'requester_id': partner.id,
            'expert_id': top_expert['id'],
            'field_id': field_id,
            'task_summary': question,
            'rate_per_minute': top_expert.get('charge_rate', 1.0),
            'duration_minutes': 30,
            'status': 'pending',
        })
        return {'session_id': session.session_id, 'expert_name': top_expert['name']}

    def _infer_field(self, question):
        """Use LLM to classify field, fallback to keyword search."""
        # Try LLM provider first
        llm_providers = request.env['llm.provider'].search([('is_enabled', '=', True)], limit=1)
        if llm_providers:
            # Use LangGraph agent to classify (or directly call the provider)
            # For simplicity, we call the LangGraph invoke endpoint
            try:
                import requests
                webhook_url = request.env['ir.config_parameter'].sudo().get_param('langgraph_invoke_url', 'http://langgraph:8000/invoke')
                api_key = request.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
                payload = {
                    "input": {"messages": [{"role": "user", "content": f"Which professional field does this question belong to? Question: {question}"}]}
                }
                headers = {'x-api-key': api_key} if api_key else {}
                resp = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    field_name = data.get('analysis', '').strip().lower()
                    field = request.env['nettrades.field'].search([('name', 'ilike', field_name)], limit=1)
                    if field:
                        return field.id
            except Exception:
                pass
        # Fallback to keyword match
        field = request.env['nettrades.field'].search([], limit=1)
        return field.id if field else None

    def _match_experts(self, field_id, user_lat, user_lon, requester_id):
    
# FIX THIS AND PUT THE TEXT WHERE EVERY IT IS NEEDED
# When the "Ask Someone" button is clicked and the field is restricted (e.g., medicine with only_qualified=True), the matching algorithm in _match_experts applies a hard filter. Only professionals who have been manually verified by an administrator and have an active qualified_professional record for that field are shown as candidates.
# A medical question therefore reaches only verified doctors -- not the general pool of freelancers. If no qualified professional is online, the user receives "No experts available at this time.
#	field = request.env['nettrades.field'].browse(field_id)
#	if field.only_qualified:
#	    qualified_ids = request.env['qualified.professional'].search([
#		('field_id', '=', field_id),
#		('is_active', '=', True),
#	    ]).mapped('partner_id.id')
#	    candidates = candidates.filtered(lambda c: c.id in qualified_ids)


        config = request.env['ir.config_parameter'].sudo()
        distance_weight = float(config.get_param('ask_someone.distance_weight', 0.4))
        reputation_weight = float(config.get_param('ask_someone.reputation_weight', 0.5))
        online_bonus = float(config.get_param('ask_someone.online_bonus', 0.2))
        available_bonus = float(config.get_param('ask_someone.available_bonus', 0.1))
        max_distance = float(config.get_param('ask_someone.max_distance_km', 100))
        rep_threshold = float(config.get_param('ask_someone.reputation_threshold', 100))

        candidates = request.env['res.partner'].search([
            ('user_type', '=', 'freelancer'),
            ('is_online', '=', True),
        ])
        scored = []
        for c in candidates:
            rep = request.env['user.field.reputation'].search([
                ('partner_id', '=', c.id),
                ('field_id', '=', field_id),
            ], limit=1)
            rep_points = rep.reputation_points if rep else 0
            rep_score = min(rep_points / rep_threshold, 1.0)

            # Distance score
            if user_lat and user_lon and c.latitude and c.longitude:
                dist = self._haversine(user_lat, user_lon, c.latitude, c.longitude)
                dist_score = 1 / (1 + dist / max_distance)
            else:
                dist_score = 0.5  # neutral

            in_session = request.env['expert.session'].search_count([
                ('expert_id', '=', c.id),
                ('status', 'in', ['accepted', 'active']),
            ]) > 0
            avail_bonus = available_bonus if not in_session else 0
            online_bonus_val = online_bonus if c.is_online else 0

            score = (distance_weight * dist_score) + (reputation_weight * rep_score) + online_bonus_val + avail_bonus
            scored.append({
                'id': c.id,
                'name': c.name,
                'charge_rate': c.charge_rate,
                'score': score,
            })
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:5]

    def _haversine(self, lat1, lon1, lat2, lon2):
        import math
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    @http.route('/api/v1/ask_someone/session/<session_id>/status', type='json', auth='user', methods=['GET'])
    def session_status(self, session_id):
        session = request.env['expert.session'].search([('session_id', '=', session_id)], limit=1)
        if not session:
            return {'error': 'Session not found'}
        return {
            'status': session.status,
            'expert_id': session.expert_id.id,
            'requester_id': session.requester_id.id,
            'started_at': session.started_at.isoformat() if session.started_at else None,
            'forgejo_repo_url': session.forgejo_repo_url,
        }