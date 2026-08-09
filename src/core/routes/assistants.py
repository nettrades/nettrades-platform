# -*- coding: utf-8 -*-
"""Assistants list endpoint for agent-chat-ui compatibility."""

from fastapi import APIRouter

router = APIRouter(tags=["assistants"])


@router.get("/assistants")
async def list_assistants():
    """
    Stub endpoint for agent-chat-ui to list available assistants.

    Returns a single assistant (supervisor) with its ID and name.
    """
    return [{"assistant_id": "supervisor", "name": "Supervisor", "graph_id": "supervisor"}]