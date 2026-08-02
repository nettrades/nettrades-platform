#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# AGENTS MODULE – NETTRADES LangGraph Sub-Agents
# =============================================================================
# FILE: src/core/agents/__init__.py
#
# PURPOSE:
#   This module exports all LangGraph sub-agents used by the supervisor.
#   Each sub-agent is a compiled LangGraph graph that handles a specific
#   business domain.
#
#   This file makes the agents directory a Python package so that
#   supervisor.py can import the agent factory functions using:
#       from .agents.recruitment_agent import create_recruitment_agent
#
#   It also exposes the public API of the agents package for cleaner imports.
#
# AGENTS:
#   - recruitment_agent: Handles job recruitment and candidate search
#   - freelance_agent: Handles freelance project matching
#   - lead_gen_agent: Handles lead generation from external feeds
#   - gpu_management_agent: Handles GPU cluster health and scaling
#   - vision_agent: Handles image analysis (VLM)
#   - action_agent: Handles robotic action control (VLA)
#   - ask_someone_agent: Handles expert marketplace (NEW)
#   - good_answer_agent: Handles quality scoring and verification (NEW)
#   - gpu_marketplace_agent: Handles GPU booking and marketplace (NEW)
#
# USAGE:
#   Instead of importing each agent separately, you can now do:
#       from agents import create_recruitment_agent
#
# =============================================================================

# -----------------------------------------------------------------------------
# Import agent factory functions for public API
# -----------------------------------------------------------------------------
from .recruitment_agent import create_recruitment_agent
from .freelance_agent import create_freelance_agent
from .lead_gen_agent import create_lead_gen_agent
from .gpu_management_agent import create_gpu_management_agent
from .vision_agent import create_vision_agent
from .action_agent import create_action_agent
from .ask_someone_agent import create_ask_someone_agent
from .good_answer_agent import create_good_answer_agent
from .gpu_marketplace_agent import create_gpu_marketplace_agent

# -----------------------------------------------------------------------------
# Define what is exported when someone does "from agents import *"
# -----------------------------------------------------------------------------
__all__ = [
    'create_recruitment_agent',
    'create_freelance_agent',
    'create_lead_gen_agent',
    'create_gpu_management_agent',
    'create_vision_agent',
    'create_action_agent',
    "create_ask_someone_agent",
    "create_good_answer_agent",
    "create_gpu_marketplace_agent",
]

# -----------------------------------------------------------------------------
# Package metadata
# -----------------------------------------------------------------------------
__version__ = '1.0.0'
__description__ = 'NETTRADES LangGraph sub-agents for recruitment, freelance, lead generation, GPU management, vision, and action.'