#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# Self-Improving Service - Entry Point
# =============================================================================

import asyncio
import logging
import os
from self_improving_integration import SelfImprovingService

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

async def main():
    """Main entry point for the self-improving service."""
    _logger.info("Starting Self-Improving Service")

    # Get configuration from environment
    odoo_url = os.getenv("ODOO_URL", "http://odoo:8069")
    odoo_api_key = os.getenv("ODOO_API_KEY", "")
    threshold_episodes = int(os.getenv("THRESHOLD_EPISODES", "50"))
    threshold_quality = float(os.getenv("THRESHOLD_QUALITY", "7.0"))

    # Initialise the service
    service = SelfImprovingService(
        threshold_episodes=threshold_episodes,
        threshold_quality=threshold_quality,
    )

    _logger.info(f"Self-Improving Service running with threshold_episodes={threshold_episodes}, threshold_quality={threshold_quality}")

    # Keep the service running
    try:
        while True:
            # Check for new episodes and trigger training if needed
            await service.trigger_training()
            await asyncio.sleep(3600)  # Check every hour
    except KeyboardInterrupt:
        _logger.info("Self-Improving Service stopped")

if __name__ == "__main__":
    asyncio.run(main())