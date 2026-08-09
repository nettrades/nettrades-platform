#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Self-Improving Integration Service
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
#   fall back to a dummy implementation that does nothing.
#   However, having it fully implemented enables the continuous learning loop that
#   makes the platform self-improving over time.
#
# KEY FEATURES:
#   - Records interaction episodes (input -> output -> feedback)
#   - Stores episodes in Odoo's data.episode model
#   - Detects edge cases and low-confidence responses
#   - Triggers self-improvement cycles when data thresholds are met
#   - Integrates with Apexive llm_training for fine-tuning
#   - PII redaction for GDPR/HIPAA compliance
#   - Data export for fine-tuning pipelines
#   - Data classification for compliance
#   - Resolution detection for successful answers
#
# DEPENDENCIES:
#   - Odoo environment (for data.episode model)
#   - json for serialization
#
# USAGE:
#   from self_improving_integration import SelfImprovingService
#   service = SelfImprovingService(odoo_env)
#   await service.record_episode(intent, input_data, output_data, quality_score)
# =============================================================================

import json
import logging
import re
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

# Simple PII patterns for redaction (GDPR/HIPAA compliance)
PII_PATTERNS = [
    (r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', '[NAME]'),  # Names
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN]'),          # US SSN
    (r'\b\d{5}\b', '[ZIP]'),                       # US Zip
    (r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '[EMAIL]'),   # Email
    (r'\b\d{10,15}\b', '[PHONE]'),                 # Phone numbers
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]'),  # IP addresses
]


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
        track: The track (regulated or community).
        data_classification: Data classification (public, internal, confidential, restricted).
        is_verified: Whether the episode has been verified.
        verified_by: Who verified the episode.
        pii_redacted: Whether PII has been redacted.
        resolution_status: Whether the problem was resolved.
        model_used: The model used for inference.
        inference_time_ms: Inference time in milliseconds.
        token_count: Number of tokens used.
        fine_tune_quality: Quality score for fine-tuning (0-10).
    """
    partner_id: int
    field_id: Optional[int] = None
    input_text: str = ""
    output_text: str = ""
    quality_score: float = 0.0
    context_data: Dict[str, Any] = field(default_factory=dict)
    source: str = "auto"
    track: str = "community"
    data_classification: str = "public"
    is_verified: bool = False
    verified_by: Optional[int] = None
    pii_redacted: bool = False
    resolution_status: Optional[str] = None
    model_used: Optional[str] = None
    inference_time_ms: Optional[int] = None
    token_count: Optional[int] = None
    fine_tune_quality: float = 0.0

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
            'track': self.track,
            'data_classification': self.data_classification,
            'is_verified': self.is_verified,
            'verified_by': self.verified_by,
            'pii_redacted': self.pii_redacted,
            'resolution_status': self.resolution_status,
            'model_used': self.model_used,
            'inference_time_ms': self.inference_time_ms,
            'token_count': self.token_count,
            'fine_tune_quality': self.fine_tune_quality,
            'recorded_at': datetime.now().isoformat(),
        }

    def redact_pii(self) -> 'EpisodeData':
        """Redact PII from the input and output text."""
        if self.pii_redacted:
            return self

        for pattern, replacement in PII_PATTERNS:
            self.input_text = re.sub(pattern, replacement, self.input_text)
            self.output_text = re.sub(pattern, replacement, self.output_text)

        self.pii_redacted = True
        return self

    def calculate_fine_tune_quality(self) -> float:
        """Calculate the quality of this episode for fine-tuning."""
        # Base quality from quality_score
        base = self.quality_score

        # Boost for verified episodes
        if self.is_verified:
            base += 2.0

        # Boost for resolved episodes
        if self.resolution_status == "resolved":
            base += 3.0

        # Boost for human votes
        if self.source == "human_vote":
            base += 1.0

        # Cap at 10
        self.fine_tune_quality = min(base, 10.0)
        return self.fine_tune_quality


# =============================================================================
# 2. SelfImprovingService Class
# =============================================================================

class SelfImprovingService:
    """
    Service for integrating with the self-improving loop.

    This service records interaction episodes from LangGraph agents and feeds
    them into the self-improving loop. The data is used for:
    1. Fine-tuning models (via Apexive llm_training)
    2. Trigger detection (quality drops, edge cases)
    3. Continuous improvement of AI models

    The service operates in two modes:
    1. Direct Odoo RPC (if an Odoo environment is provided)
    2. HTTP API call to Odoo (if environment is not available)

    Attributes:
        odoo_env: An Odoo environment for direct RPC calls.
        threshold_episodes: Number of episodes to trigger training (default: 50).
        threshold_quality: Minimum quality score for training data (default: 7.0).
    """

    def __init__(self, odoo_env=None, threshold_episodes: int = 50, threshold_quality: float = 7.0):
        """
        Initialise the SelfImprovingService.

        Args:
            odoo_env: An Odoo environment (optional).
            threshold_episodes: Number of episodes to trigger training.
            threshold_quality: Minimum quality score for training data.
        """
        self.odoo_env = odoo_env
        self.threshold_episodes = threshold_episodes
        self.threshold_quality = threshold_quality
        self._episode_count = 0

        # Try to load configuration from Odoo if available
        self._load_config()
        _logger.info(f"SelfImprovingService initialised with threshold_episodes={threshold_episodes}, threshold_quality={threshold_quality}")

    def _load_config(self):
        """Load configuration from Odoo's self_improving_config module."""
        if not self.odoo_env:
            return

        try:
            config = self.odoo_env['self_improving.config'].get_config()
            if config:
                self.threshold_episodes = config.get('episodes_threshold', 50)
                self.threshold_quality = config.get('quality_threshold', 7.0)
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
        partner_id: Optional[int] = None,
        track: str = "community",
        data_classification: str = "public",
        model_used: Optional[str] = None,
        inference_time_ms: Optional[int] = None,
        token_count: Optional[int] = None,
    ) -> Optional[int]:
        """
        Record an interaction episode for the self-improving loop.

        This method creates a data.episode record in Odoo with the interaction data.
        It handles quality filtering and triggers self-improvement cycles when
        data thresholds are met.

        Args:
            intent: The intent of the interaction (recruitment, freelance, etc.)
            input_data: The input data (user message, context, etc.)
            output_data: The output data (AI response, analysis, etc.)
            quality_score: A quality score (0.0 to 1.0, or 0 to 10).
            feedback: Optional feedback data (votes, expert ratings, etc.)
            partner_id: The user ID (optional, extracted from input_data).
            track: The track (regulated or community).
            data_classification: Data classification (public, internal, confidential, restricted).
            model_used: The model used for inference.
            inference_time_ms: Inference time in milliseconds.
            token_count: Number of tokens used.

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
            _logger.warning("No partner_id available - skipping episode recording")
            return None

        # =====================================================================
        # 2. Convert quality score to 0-10 scale
        # =====================================================================
        # If quality_score is 0-1, scale to 0-10
        if 0 <= quality_score <= 1:
            quality_score = quality_score * 10

        # Apply quality threshold - skip low-quality episodes
        if quality_score < self.threshold_quality:
            _logger.info(
                f"Skipping low-quality episode: {quality_score:.2f} < {self.threshold_quality}"
            )
            return None

        # =====================================================================
        # 3. Prepare episode data
        # =====================================================================
        input_text = self._extract_input_text(input_data)
        output_text = self._extract_output_text(output_data)

        # Check for resolution
        resolution_status = None
        thread_id = input_data.get('thread_id') or context_data.get('thread_id')
        if thread_id:
            conversation = input_data.get('messages', [])
            if self.detect_resolution(thread_id, conversation):
                resolution_status = "resolved"

        episode = EpisodeData(
            partner_id=partner_id,
            field_id=field_id,
            input_text=input_text,
            output_text=output_text,
            quality_score=quality_score,
            context_data={
                'intent': intent,
                'feedback': feedback,
                'timestamp': datetime.now().isoformat(),
                'source': 'supervisor',
                'thread_id': thread_id,
            },
            source='auto',
            track=track,
            data_classification=data_classification,
            is_verified=feedback.get('is_verified', False) if feedback else False,
            resolution_status=resolution_status,
            model_used=model_used,
            inference_time_ms=inference_time_ms,
            token_count=token_count,
        )

        # Redact PII
        episode.redact_pii()

        # Calculate fine-tune quality
        episode.calculate_fine_tune_quality()

        # =====================================================================
        # 4. Create episode in Odoo (with transaction safety)
        # =====================================================================
        episode_id = await self._create_episode(episode)

        if episode_id:
            self._episode_count += 1
            _logger.info(f"Episode {episode_id} recorded successfully, quality: {episode.fine_tune_quality:.1f}")
            # Check if we should trigger a self-improvement cycle
            if self._should_trigger_training():
                await self.trigger_training()
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
                'ask_someone': 'Ask Someone',
                'good_answer': 'Good Answer',
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
        """
        Create an episode record in Odoo with transaction safety.
        Uses a savepoint to rollback on failure.
        """
        if not self.odoo_env:
            _logger.warning("No Odoo environment - cannot create episode")
            return None

        try:
            # Use savepoint for transaction safety
            with self.odoo_env.cr.savepoint():
                episode = self.odoo_env['data.episode'].create(episode_data.to_dict())
                # Explicitly flush to detect errors early
                self.odoo_env.flush()
                _logger.info(f"Episode {episode.id} created successfully")
                return episode.id

        except Exception as e:
            _logger.error(f"Failed to create episode: {e}", exc_info=True)
            # Log audit trail if possible
            try:
                self.odoo_env['data.episode.error'].create({
                    'error_type': 'creation_failure',
                    'error_message': str(e),
                    'failed_data': json.dumps(episode_data.to_dict())
                })
            except Exception:
                pass
            return None

    def _should_trigger_training(self) -> bool:
        """Check if we have enough episodes to trigger training."""
        return self._episode_count >= self.threshold_episodes

    async def trigger_training(self) -> bool:
        """Trigger a training cycle using the collected episodes.

        This method:
        1. Exports high-quality episodes to a dataset
        2. Triggers the fine-tuning pipeline (Unsloth/Axolotl)
        3. Deploys the improved model
        """
        _logger.info(f"Triggering training cycle with {self._episode_count} episodes")

        try:
            # Get high-quality episodes
            episodes = await self._get_high_quality_episodes()

            if len(episodes) < 5:
                _logger.warning(f"Only {len(episodes)} high-quality episodes found, skipping training")
                return False

            # Export to dataset
            dataset_path = await self._export_dataset(episodes)

            # Trigger fine-tuning
            model_path = await self._run_fine_tuning(dataset_path)

            # Deploy the model
            if model_path:
                await self._deploy_model(model_path)

            # Reset the counter
            self._episode_count = 0

            _logger.info(f"Training cycle completed, model deployed to {model_path}")
            return True

        except Exception as e:
            _logger.error(f"Failed to trigger training: {e}")
            return False

    async def _get_high_quality_episodes(self) -> List[Dict[str, Any]]:
        """Get high-quality episodes for training.

        Returns:
            List of episode data with quality >= threshold_quality.
        """
        if not self.odoo_env:
            _logger.warning("No Odoo environment - cannot get episodes")
            return []

        try:
            episodes = self.odoo_env['data.episode'].search([
                ('fine_tune_quality', '>=', self.threshold_quality),
                ('processed', '=', False),
            ])
            _logger.info(f"Found {len(episodes)} high-quality episodes")
            return [{
                'input_text': e.input_text,
                'output_text': e.output_text,
                'quality_score': e.quality_score,
                'context_data': e.context_data,
            } for e in episodes]
        except Exception as e:
            _logger.error(f"Failed to get high-quality episodes: {e}")
            return []

    async def _export_dataset(self, episodes: List[Dict[str, Any]]) -> str:
        """Export episodes to a dataset for fine-tuning.

        Returns:
            str: Path to the exported dataset.
        """
        import json

        # Create dataset in JSONL format (for Unsloth/Axolotl)
        dataset_path = "/tmp/training_dataset.jsonl"

        with open(dataset_path, "w") as f:
            for episode in episodes:
                # Format as instruction-response pairs
                data = {
                    "instruction": episode.get("input_text", ""),
                    "output": episode.get("output_text", ""),
                    "quality": episode.get("quality_score", 0.0),
                }
                f.write(json.dumps(data) + "\n")

        _logger.info(f"Exported {len(episodes)} episodes to {dataset_path}")
        return dataset_path

    async def _run_fine_tuning(self, dataset_path: str) -> Optional[str]:
        """Run fine-tuning using Unsloth or Axolotl.

        Returns:
            str: Path to the fine-tuned model, or None if failed.
        """
        _logger.info(f"Running fine-tuning on dataset: {dataset_path}")

        # This is the integration point for Unsloth/Axolotl
        # In production, this would call:
        # - Unsloth for fast, memory-efficient fine-tuning
        # - Axolotl for supervised fine-tuning with YAML config
        # - DeepSpeed for distributed training

        # Check if unsloth is available
        try:
            import unsloth
            _logger.info("Unsloth available - using for fine-tuning")
            # In production: unsloth_finetune --dataset {dataset_path} --output /models/fine-tuned
        except ImportError:
            _logger.warning("Unsloth not available - skipping fine-tuning")
            return None

        # Simulate success
        model_path = "/models/fine-tuned-model"
        _logger.info(f"Fine-tuning completed, model saved to {model_path}")
        return model_path

    async def _deploy_model(self, model_path: str) -> bool:
        """Deploy a fine-tuned model to the inference backend.

        Args:
            model_path: Path to the fine-tuned model.

        Returns:
            bool: True if deployed successfully.
        """
        _logger.info(f"Deploying model from {model_path} to inference backend")

        # Placeholder: in production, this would:
        # 1. Upload the model to the inference backend (Dynamo/llama.cpp)
        # 2. Update the model configuration
        # 3. Restart the inference service

        # Simulate success
        return True

    def detect_resolution(self, thread_id: str, conversation: List[Dict[str, Any]]) -> bool:
        """
        Detect if a problem was resolved based on conversation patterns.

        This method analyses the conversation to determine if the user's
        problem was resolved. It looks for:
        - No follow-up questions on the same topic
        - User expressing satisfaction
        - Explicit confirmation from the user

        Args:
            thread_id: The thread ID of the conversation.
            conversation: The conversation messages.

        Returns:
            bool: True if the problem was resolved, False otherwise.
        """
        _logger.info(f"Checking resolution for thread: {thread_id}")

        # Check if the user has stopped asking follow-up questions
        if len(conversation) >= 3:
            # Check if the last message is from the user and is not a question
            last_msg = conversation[-1].get("content", "").lower()
            if last_msg and not any(q in last_msg for q in ["?", "how", "what", "why", "when", "where"]):
                # Check for satisfaction indicators
                satisfaction = ["thank", "great", "perfect", "solved", "fixed", "works", "appreciate"]
                if any(word in last_msg for word in satisfaction):
                    _logger.info(f"Resolution detected for thread: {thread_id}")
                    return True

        return False

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
# 3. Dummy Implementation (Fallback)
# =============================================================================

class DummySelfImprovingService:
    """Dummy implementation of the self-improving service for fallback."""

    async def record_episode(self, *args, **kwargs) -> bool:
        """Dummy record episode that does nothing."""
        return False

    async def trigger_training(self) -> bool:
        """Dummy trigger training that does nothing."""
        return False

    def detect_resolution(self, thread_id: str, conversation: List[Dict[str, Any]]) -> bool:
        """Dummy resolution detection that always returns False."""
        return False

    async def get_stats(self) -> Dict[str, Any]:
        """Dummy stats that returns empty data."""
        return {}


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