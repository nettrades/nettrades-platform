# -*- coding: utf-8 -*-
"""Metrics tracking middleware."""

import time

from prometheus_client import Histogram

REQUEST_DURATION = Histogram(
    'langgraph_request_duration_seconds',
    'Time taken to process a LangGraph request'
)


async def metrics_middleware(request, call_next):
    """Middleware that tracks request duration for Prometheus."""
    start = time.time()
    response = await call_next(request)
    REQUEST_DURATION.observe(time.time() - start)
    return response