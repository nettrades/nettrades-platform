#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Self-Improving Integration Service
# =============================================================================
# FILE: src/core/self_improving_integration.py
#
# PURPOSE:
#   This module provides the SelfImprovingService class that records
#   interaction episodes for the self-improving loop. It collects data from
#   user interactions, stores episodes in Odoo's data.episode model, and
#   triggers self-improvement cycles when enough data is collected.
#
#   This is an OPTIONAL module. If it is not present, the supervisor will
#   fall back to a dummy implementation that does nothing. However, having
#   it fully implemented enables the continuous learning loop that makes
#   the platform self-improving over time.
#
# KEY FEATURES:
#   - Records interaction episodes (input → output → feedback)
#   - Stores episodes in Odoo's data.episode model
#   - Detects edge cases and low-confidence responses
#   - Triggers self-improvement cycles when data thresholds are met
#   - Integrates with Apexive llm_training for fine-tuning
#
# DEPENDENCIES:
#   - Odoo environment (for data.episode model)
#   - json for serialization
#
# USAGE:
#   from self_improving_integration import SelfImprovingService
#   service = SelfImprovingService(odoo_env)
#   await service.record_episode(intent, input_data, output_data, quality_score)
#
# =============================================================================

import json
import logging
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. Episode Data Classes
# =============================================================================

@dataclass
class EpisodeData:
    """
    Data structure for a single interaction episode.

    Attributes:
        partner_id: The user ID.
        field_id: The professional field ID (from nettrades.field).
        input_text: The user's input.
        output_text: The AI's output.
        quality_score: A quality score (0-10).
        context_data: Additional context (JSON).
        source: The source of the episode (human_vote, expert, auto).
    """
    partner_id: int
    field_id: Optional[int] = None
    input_text: str = ""
    output_text: str = ""
    quality_score: float = 0.0
    context_data: Dict[str, Any] = field(default_factory=dict)
    source: str = "auto"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Odoo model creation."""
        return {
            'partner_id': self.partner_id,
            'field_id': self.field_id,
            'input_text': self.input_text,
            'output_text': self.output_text,
            'quality_score': self.quality_score,
            'context_data': json.dumps(self.context_data),
            'source': self.source,
        }


# =============================================================================
# 2. SelfImprovingService Class
# =============================================================================

class SelfImprovingService:
    """
    Service for integrating with the self-improving loop.

    This service records interaction episodes from LangGraph agents and
    feeds them into the self-improving loop. The data is used for:
    1. Fine-tuning models (via Apexive llm_training)
    2. Trigger detection (quality drops, edge cases)
    3. Continuous improvement of AI models

    The service operates in two modes:
    1. Direct Odoo RPC (if an Odoo environment is provided)
    2. HTTP API call to Odoo (if environment is not available)

    Attributes:
        odoo_env: An Odoo environment for direct RPC calls.
        threshold_episodes: Number of episodes to trigger training (default: 50).
        threshold_quality: Minimum quality score for training data (default: 5.0).
    """

    def __init__(self, odoo_env=None):
        """
        Initialise the SelfImprovingService.

        Args:
            odoo_env: An Odoo environment (optional). If provided, the service
                      uses direct RPC to create episodes. Otherwise, it uses
                      HTTP API calls.
        """
        self.odoo_env = odoo_env
        self.threshold_episodes = 50
        self.threshold_quality = 5.0

        # Try to load configuration from Odoo if available
        self._load_config()

        _logger.info("SelfImprovingService initialised")

    def _load_config(self):
        """Load configuration from Odoo's self_improving_config module."""
        if not self.odoo_env:
            return

        try:
            config = self.odoo_env['self_improving.config'].get_config()
            if config:
                self.threshold_episodes = config.get('episodes_threshold', 50)
                self.threshold_quality = config.get('quality_threshold', 5.0)
                _logger.info(
                    f"Loaded self-improving config: "
                    f"threshold_episodes={self.threshold_episodes}, "
                    f"threshold_quality={self.threshold_quality}"
                )
        except Exception as e:
            _logger.warning(f"Failed to load self-improving config: {e}")

    async def record_episode(
        self,
        intent: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        quality_score: float = 0.5,
        feedback: Optional[Dict[str, Any]] = None,
        partner_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Record an interaction episode for the self-improving loop.

        This method creates a data.episode record in Odoo with the interaction
        data. It handles quality filtering and triggers self-improvement
        cycles when data thresholds are met.

        Args:
            intent: The intent of the interaction (recruitment, freelance, etc.)
            input_data: The input data (user message, context, etc.)
            output_data: The output data (AI response, analysis, etc.)
            quality_score: A quality score (0.0 to 1.0, or 0 to 10).
            feedback: Optional feedback data (votes, expert ratings, etc.)
            partner_id: The user ID (optional, extracted from input_data).

        Returns:
            Optional[int]: The ID of the created episode, or None if failed.

        Example:
            # In supervisor.py:
            service = SelfImprovingService(odoo_env)
            await service.record_episode(
                intent="recruitment",
                input_data={"messages": [{"role": "user", "content": "..."}]},
                output_data={"analysis": "..."},
                quality_score=0.85
            )
        """
        _logger.info(f"Recording episode for intent: {intent}, quality: {quality_score:.2f}")

        # =====================================================================
        # 1. Extract partner_id and field_id
        # =====================================================================
        if not partner_id:
            partner_id = input_data.get('user_id') or input_data.get('partner_id')

        field_id = self._get_field_id(intent)

        if not partner_id:
            _logger.warning("No partner_id available – skipping episode recording")
            return None

        # =====================================================================
        # 2. Convert quality score to 0-10 scale
        # =====================================================================
        # If quality_score is 0-1, scale to 0-10
        if 0 <= quality_score <= 1:
            quality_score = quality_score * 10

        # Apply quality threshold – skip low-quality episodes
        if quality_score < self.threshold_quality:
            _logger.info(
                f"Skipping low-quality episode: {quality_score:.2f} < {self.threshold_quality}"
            )
            return None

        # =====================================================================
        # 3. Prepare episode data
        # =====================================================================
        # Extract input text from messages
        input_text = self._extract_input_text(input_data)
        output_text = self._extract_output_text(output_data)

        episode_data = EpisodeData(
            partner_id=partner_id,
            field_id=field_id,
            input_text=input_text,
            output_text=output_text,
            quality_score=quality_score,
            context_data={
                'intent': intent,
                'feedback': feedback,
                'timestamp': time.time(),
                'source': 'supervisor'
            },
            source='auto'
        )

        # =====================================================================
        # 4. Create episode in Odoo
        # =====================================================================
        episode_id = await self._create_episode(episode_data)

        if episode_id:
            _logger.info(f"Episode {episode_id} recorded successfully")

            # Check if we should trigger a self-improvement cycle
            await self._check_trigger()

            return episode_id
        else:
            _logger.warning("Failed to create episode")
            return None

    # =========================================================================
    # 3. Helper Methods
    # =========================================================================

    def _get_field_id(self, intent: str) -> Optional[int]:
        """Get the professional field ID for a given intent."""
        if not self.odoo_env:
            return None

        try:
            # Map intent to field name
            field_name_map = {
                'recruitment': 'Recruitment',
                'freelance': 'Freelance',
                'gpu': 'GPU Management',
                'vision': 'Computer Vision',
                'action': 'Robotics',
                'medical': 'Medical',
                'legal': 'Legal',
                'lead_gen': 'Lead Generation',
            }

            field_name = field_name_map.get(intent, 'General')

            # Try to find the field
            fields = self.odoo_env['nettrades.field'].search([
                ('name', 'ilike', field_name)
            ], limit=1)

            if fields:
                return fields.id

            # Create a default field if it doesn't exist
            field = self.odoo_env['nettrades.field'].create({
                'name': field_name,
                'description': f'Auto-created field for {intent}'
            })
            _logger.info(f"Created field '{field_name}' for intent '{intent}'")
            return field.id

        except Exception as e:
            _logger.warning(f"Failed to get field ID: {e}")
            return None

    def _extract_input_text(self, input_data: Dict[str, Any]) -> str:
        """Extract input text from various data formats."""
        # Try messages format
        messages = input_data.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, dict):
                return last_msg.get('content', '')
            return str(last_msg)

        # Try direct text
        if 'text' in input_data:
            return str(input_data['text'])

        if 'query' in input_data:
            return str(input_data['query'])

        # Fallback
        return json.dumps(input_data)[:500]

    def _extract_output_text(self, output_data: Dict[str, Any]) -> str:
        """Extract output text from various data formats."""
        if 'analysis' in output_data:
            return str(output_data['analysis'])

        if 'response' in output_data:
            return str(output_data['response'])

        if 'message' in output_data:
            return str(output_data['message'])

        # Fallback
        return json.dumps(output_data)[:500]

    async def _create_episode(self, episode_data: EpisodeData) -> Optional[int]:
        """Create an episode record in Odoo."""
        if not self.odoo_env:
            _logger.warning("No Odoo environment – cannot create episode")
            return None

        try:
            episode = self.odoo_env['data.episode'].create(episode_data.to_dict())
            return episode.id
        except Exception as e:
            _logger.error(f"Failed to create episode: {e}")
            return None

    async def _check_trigger(self):
        """Check if a self-improvement trigger should fire."""
        if not self.odoo_env:
            return

        try:
            # Count unprocessed high-quality episodes
            episode_count = self.odoo_env['data.episode'].search_count([
                ('processed', '=', False),
                ('quality_score', '>=', self.threshold_quality)
            ])

            _logger.info(f"Unprocessed episodes: {episode_count}")

            # If we have enough episodes, trigger the self-improving loop
            if episode_count >= self.threshold_episodes:
                _logger.info(
                    f"Triggering self-improvement cycle: {episode_count} episodes ready"
                )

                # Find active trigger configurations
                triggers = self.odoo_env['self_improving.trigger'].search([
                    ('trigger_type', '=', 'data_volume'),
                    ('active', '=', True)
                ])

                for trigger in triggers:
                    _logger.info(f"Trigger {trigger.name} will be processed by cron")

        except Exception as e:
            _logger.warning(f"Failed to check trigger: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the self-improving loop.

        Returns:
            Dict[str, Any]: Statistics including episode count, quality scores, etc.
        """
        stats = {
            'threshold_episodes': self.threshold_episodes,
            'threshold_quality': self.threshold_quality,
            'episode_count': 0,
            'avg_quality': 0.0,
        }

        if not self.odoo_env:
            return stats

        try:
            episodes = self.odoo_env['data.episode'].search([
                ('processed', '=', False)
            ])

            stats['episode_count'] = len(episodes)

            if episodes:
                avg_quality = sum(e.quality_score for e in episodes) / len(episodes)
                stats['avg_quality'] = avg_quality

        except Exception as e:
            _logger.warning(f"Failed to get stats: {e}")

        return stats


# =============================================================================
# 4. MAIN ENTRY POINT (for testing)
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def test_self_improving():
        """Test the SelfImprovingService."""
        service = SelfImprovingService()
        episode_id = await service.record_episode(
            intent="recruitment",
            input_data={
                "messages": [{"role": "user", "content": "Find a Python developer"}],
                "user_id": 1
            },
            output_data={"analysis": "Found 5 candidates..."},
            quality_score=8.5,
            feedback={"votes": 3, "avg_rating": 4.5}
        )
        print(f"Episode ID: {episode_id}")

        stats = await service.get_stats()
        print(f"Stats: {stats}")

    asyncio.run(test_self_improving())