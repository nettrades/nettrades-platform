#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Agents Package
# =============================================================================
# FILE: src/core/agents/__init__.py
#
# PURPOSE:
#   This file makes the agents directory a Python package so that
#   supervisor.py can import the agent factory functions using:
#       from .agents.recruitment_agent import create_recruitment_agent
#
#   It also exposes the public API of the agents package for cleaner imports.
#
# USAGE:
#   Instead of importing each agent separately, you can now do:
#       from src.core.agents import create_recruitment_agent
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

# -----------------------------------------------------------------------------
# Define what is exported when someone does "from src.core.agents import *"
# -----------------------------------------------------------------------------
__all__ = [
    'create_recruitment_agent',
    'create_freelance_agent',
    'create_lead_gen_agent',
    'create_gpu_management_agent',
    'create_vision_agent',
    'create_action_agent',
]

# -----------------------------------------------------------------------------
# Package metadata
# -----------------------------------------------------------------------------
__version__ = '1.0.0'
__description__ = 'NETTRADES LangGraph sub-agents for recruitment, freelance, lead generation, GPU management, vision, and action.'