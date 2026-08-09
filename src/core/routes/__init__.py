# -*- coding: utf-8 -*-
"""Route modules for the LangGraph FastAPI application."""

from .health import router as health_router
from .metrics import router as metrics_router
from .invoke import router as invoke_router
from .threads import router as threads_router
from .assistants import router as assistants_router
from .wireguard import router as wireguard_router

__all__ = [
    'health_router',
    'metrics_router',
    'invoke_router',
    'threads_router',
    'assistants_router',
    'wireguard_router',
]