# -*- coding: utf-8 -*-
"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, REGISTRY

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    This endpoint exposes all Prometheus metrics for scraping by a Prometheus
    server. It includes request counts, durations, and any other metrics
    registered with the Prometheus registry.
    """
    return Response(content=generate_latest(REGISTRY), media_type="text/plain")