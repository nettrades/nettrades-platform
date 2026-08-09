# -*- coding: utf-8 -*-
"""Shared helper functions for routes."""

from prometheus_client import Counter

REQUEST_COUNT = Counter(
    'langgraph_requests_total',
    'Total number of requests processed by the LangGraph agent',
    ['intent']
)


def get_graph(app):
    """Get the compiled LangGraph from app state."""
    ml_models = getattr(app.state, "ml_models", {})
    return ml_models.get("graph")


def record_metrics(intent: str):
    """Record request metrics."""
    REQUEST_COUNT.labels(intent=intent).inc()