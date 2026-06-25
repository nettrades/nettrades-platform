#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI – Tools Package
# =============================================================================
# FILE: src/core/tools/__init__.py
#
# PURPOSE:
#   This file makes the tools directory a Python package so that
#   agent files can import the inference backend and other utilities using:
#       from src.core.tools import get_inference_backend
#
# =============================================================================

# -----------------------------------------------------------------------------
# Import the inference backend and other utilities for public API
# -----------------------------------------------------------------------------
from .inference import get_inference_backend, InferenceBackend

# -----------------------------------------------------------------------------
# Define what is exported when someone does "from src.core.tools import *"
# -----------------------------------------------------------------------------
__all__ = [
    'get_inference_backend',
    'InferenceBackend',
]

# -----------------------------------------------------------------------------
# Package metadata
# -----------------------------------------------------------------------------
__version__ = '1.0.0'
__description__ = 'NETTRADES core tools for inference, LLM, and utilities.'