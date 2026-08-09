# -*- coding: utf-8 -*-
"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Liveness and readiness probe for container orchestration.

    This endpoint returns a simple status to indicate that the service is
    running and ready to accept requests.
    """
    return {"status": "ok", "service": "langgraph"}