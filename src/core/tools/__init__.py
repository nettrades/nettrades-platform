#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI - Tools Package
# =============================================================================
# FILE: src/core/tools/__init__.py
#
# PURPOSE:
#   This file makes the tools directory a Python package so that
#   agent files can import the inference backend and other utilities using:
#       from tools import get_inference_backend
#
# =============================================================================

# -----------------------------------------------------------------------------
# Import the inference backend for public API
# The backend detection is now unified in inference.py, which provides
# a zero-latency health-checked dictionary-returning function.
# -----------------------------------------------------------------------------
from .inference import get_inference_backend

# -----------------------------------------------------------------------------
# Define what is exported when someone does "from tools import *"
# -----------------------------------------------------------------------------
__all__ = [
    'get_inference_backend',
]

# -----------------------------------------------------------------------------
# Package metadata
# -----------------------------------------------------------------------------
__version__ = '1.0.0'
__description__ = 'NETTRADES core tools for inference, LLM, and utilities.'