# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection - Data Collector Service
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_collector.py
#
# PURPOSE:
#   This service class provides methods for collecting data from various
#   sources and creating data.episode records. It acts as the central
#   entry point for the Monitor phase of the self-improving loop.
#
# USAGE:
#   collector = request.env['data.collector']
#   collector.collect_good_answer(vote_id)
#   collector.collect_expert_session(session_id)
#   collector.collect_langgraph_interaction(data)
#
#   The collector handles the creation of data.episode records and
#   their associated annotations, feedback, and metrics.
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class DataCollector(models.TransientModel):
    """
    Data Collector Service - Collects data from various sources.

    This service provides methods for collecting interaction data from
    different parts of the platform and creating data.episode records.
    """
    _name = 'data.collector'
    _description = 'Data Collector Service'
    _transient = True

    # =========================================================================
    # 1. COLLECT FROM GOOD ANSWER VOTES
    # =========================================================================

    @api.model
    def collect_good_answer(self, vote_id):
        """
        Collect data from a Good Answer vote.

        This method is called when a user clicks "Good Answer" on an
        AI-generated response. It creates a data.episode record with
        the question and answer, and a data.feedback record with the vote.

        Args:
            vote_id (int): The ID of the good.answer.vote record.

        Returns:
            data.episode: The created episode record.
        """
        vote = self.env['good.answer.vote'].browse(vote_id)

        if not vote.exists():
            _logger.warning("Good Answer vote %s not found", vote_id)
            return None

        # Get the question and answer from the vote
        # This assumes the vote is linked to an AI answer
        input_text = self._get_question_for_vote(vote)
        output_text = self._get_answer_for_vote(vote)

        if not input_text or not output_text:
            _logger.warning("Could not retrieve question/answer for vote %s", vote_id)
            return None

        # Calculate quality score from vote points
        # Vote points are typically 1-5, scale to 2-10
        quality_score = vote.points * 2

        # Create the episode
        episode = self.env['data.episode'].create({
            'source': 'good_answer',
            'source_id': str(vote.id),
            'input_text': input_text,
            'output_text': output_text,
            'quality_score': quality_score,
            'vote_count': 1,
            'partner_id': vote.user_id.id,
            'field_id': vote.field_id.id,
            'context_data': {
                'vote_id': vote.id,
                'is_qualified_vote': vote.is_qualified_vote,
            },
        })

        # Create feedback record
        self.env['data.feedback'].create({
            'episode_id': episode.id,
            'feedback_type': 'good_answer',
            'value': vote.points,
            'user_id': vote.user_id.id,
            'field_id': vote.field_id.id,
        })

        # Auto-qualify if quality_score meets threshold
        # The threshold is configured in the admin settings
        threshold = self.env['ir.config_parameter'].sudo().get_param(
            'data_collection.min_quality_score', 5.0
        )

        if quality_score >= float(threshold):
            episode.action_qualify()

        _logger.info("Collected episode %s from Good Answer vote %s", episode.id, vote_id)
        return episode

    # =========================================================================
    # 2. COLLECT FROM EXPERT SESSIONS
    # =========================================================================

    @api.model
    def collect_expert_session(self, session_id):
        """
        Collect data from an Ask Someone expert session.

        This method is called when an expert session is completed.
        It creates a data.episode record with the expert's answer.

        Args:
            session_id (int): The ID of the expert.session record.

        Returns:
            data.episode: The created episode record.
        """
        session = self.env['expert.session'].browse(session_id)

        if not session.exists():
            _logger.warning("Expert session %s not found", session_id)
            return None

        # Create the episode
        episode = self.env['data.episode'].create({
            'source': 'ask_someone',
            'source_id': str(session.id),
            'input_text': session.question,
            'output_text': session.answer,
            'quality_score': session.rating_by_requester * 2,  # Scale 1-5 to 2-10
            'is_qualified': True,  # Expert answers are automatically qualified
            'partner_id': session.expert_id.id,
            'field_id': session.field_id.id,
            'context_data': {
                'session_id': session.id,
                'duration_minutes': session.duration_minutes,
                'rate_per_minute': session.rate_per_minute,
            },
        })

        _logger.info("Collected episode %s from expert session %s", episode.id, session_id)
        return episode

    # =========================================================================
    # 3. COLLECT FROM LANGGRAPH AGENTS
    # =========================================================================

    @api.model
    def collect_langgraph_interaction(self, input_text, output_text, intent, partner_id=None, field_id=None):
        """
        Collect data from a LangGraph agent interaction.

        This method is called by the LangGraph supervisor when it processes
        a request. It creates a data.episode record with the interaction.

        Args:
            input_text (str): The user's query.
            output_text (str): The AI's response.
            intent (str): The intent of the request (recruitment, freelance, etc.).
            partner_id (int, optional): The user ID.
            field_id (int, optional): The field ID.

        Returns:
            data.episode: The created episode record.
        """
        episode = self.env['data.episode'].create({
            'source': 'langgraph',
            'input_text': input_text,
            'output_text': output_text,
            'partner_id': partner_id,
            'field_id': field_id,
            'context_data': {
                'intent': intent,
                'timestamp': fields.Datetime.now().isoformat(),
            },
        })

        _logger.info("Collected episode %s from LangGraph interaction", episode.id)
        return episode

    # =========================================================================
    # 4. COLLECT FROM CHATBOT
    # =========================================================================

    @api.model
    def collect_chatbot_interaction(self, message, response, partner_id=None, field_id=None):
        """
        Collect data from a chatbot interaction.

        Args:
            message (str): The user's message.
            response (str): The chatbot's response.
            partner_id (int, optional): The user ID.
            field_id (int, optional): The field ID.

        Returns:
            data.episode: The created episode record.
        """
        episode = self.env['data.episode'].create({
            'source': 'chatbot',
            'input_text': message,
            'output_text': response,
            'partner_id': partner_id,
            'field_id': field_id,
            'context_data': {
                'timestamp': fields.Datetime.now().isoformat(),
            },
        })

        _logger.info("Collected episode %s from chatbot interaction", episode.id)
        return episode

    # =========================================================================
    # 5. COLLECT FROM ROS 2 / ROBOTICS
    # =========================================================================

    @api.model
    def collect_ros2_interaction(self, topic, data, success, partner_id=None):
        """
        Collect data from a ROS 2 / robotics interaction.

        This method is called by the ROS 2 tools when a robotic action is
        performed. It creates a data.episode record with the action data.

        Args:
            topic (str): The ROS 2 topic.
            data (dict): The action data.
            success (bool): Whether the action was successful.
            partner_id (int, optional): The user ID.

        Returns:
            data.episode: The created episode record.
        """
        episode = self.env['data.episode'].create({
            'source': 'ros2',
            'input_text': f"Action on {topic}: {json.dumps(data)}",
            'output_text': f"Success: {success}",
            'quality_score': 10.0 if success else 0.0,
            'is_qualified': success,
            'partner_id': partner_id,
            'context_data': {
                'topic': topic,
                'data': data,
                'timestamp': fields.Datetime.now().isoformat(),
            },
        })

        _logger.info("Collected episode %s from ROS 2 interaction", episode.id)
        return episode

    # =========================================================================
    # 6. HELPER METHODS
    # =========================================================================

    def _get_question_for_vote(self, vote):
        """
        Get the question text for a Good Answer vote.

        This method retrieves the original question from the vote context.

        Args:
            vote (good.answer.vote): The vote record.

        Returns:
            str: The question text, or empty string if not found.
        """
        # This is a placeholder implementation
        # In production, this would retrieve the question from the
        # linked answer record (e.g., llm.assistant.message)
        return "User question (retrieved from context)"

    def _get_answer_for_vote(self, vote):
        """
        Get the answer text for a Good Answer vote.

        This method retrieves the answer from the vote context.

        Args:
            vote (good.answer.vote): The vote record.

        Returns:
            str: The answer text, or empty string if not found.
        """
        # This is a placeholder implementation
        # In production, this would retrieve the answer from the
        # linked answer record (e.g., llm.assistant.message)
        return "AI answer (retrieved from context)"

    # =========================================================================
    # 7. CRON JOBS
    # =========================================================================

    @api.model
    def _cron_collect_unprocessed(self):
        """
        Scheduled cron job to collect unprocessed data.

        This method runs periodically to collect data from various sources
        that haven't been processed yet. It checks for:
          - New Good Answer votes
          - Completed expert sessions
          - New LangGraph interactions

        The cron runs every hour by default.
        """
        _logger.info("Running data collection cron job...")

        # Collect from Good Answer votes
        votes = self.env['good.answer.vote'].search([
            ('processed_for_ai', '=', False),
        ])

        count = 0
        for vote in votes:
            self.collect_good_answer(vote.id)
            vote.processed_for_ai = True
            count += 1

        _logger.info("Collected %s episodes from Good Answer votes", count)

        # Collect from completed expert sessions
        sessions = self.env['expert.session'].search([
            ('status', '=', 'completed'),
            ('collected_for_training', '=', False),
        ])

        count = 0
        for session in sessions:
            self.collect_expert_session(session.id)
            session.collected_for_training = True
            count += 1

        _logger.info("Collected %s episodes from expert sessions", count)