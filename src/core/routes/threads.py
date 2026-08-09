# -*- coding: utf-8 -*-
"""Thread management endpoints for agent-chat-ui compatibility."""

import uuid
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Request

from routes._shared import get_graph
from supervisor import invoke_supervisor_with_retry

logger = logging.getLogger(__name__)
router = APIRouter(tags=["threads"])

# In-memory store for thread states (for stub purposes only)
_thread_store: Dict[str, Dict[str, Any]] = {}


@router.post("/threads")
async def create_thread():
    """
    Stub endpoint for agent-chat-ui to create a new conversation thread.

    Generates a new UUID and returns it as thread_id.
    """
    thread_id = str(uuid.uuid4())
    _thread_store[thread_id] = {"messages": [], "state": {}}
    return {"thread_id": thread_id}


@router.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str):
    """
    Stub endpoint for agent-chat-ui to get the current state of a thread.

    Returns the messages stored in the thread (or empty list if not found).
    """
    if thread_id not in _thread_store:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"values": {"messages": _thread_store[thread_id].get("messages", [])}}


@router.post("/threads/{thread_id}/runs")
async def run_thread(thread_id: str, request: Request):
    """
    Stub endpoint for agent-chat-ui to execute a thread run.

    This endpoint forwards the request to the /invoke logic, using the
    thread_id as the configurable thread_id, and stores the response
    in the thread store so that subsequent state requests can retrieve it.

    The UI expects a run_id in response, which we generate.
    """
    if thread_id not in _thread_store:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    state = {
        "messages": body.get("messages", []),
        "thread_id": thread_id,
    }

    graph = get_graph(request.app)
    if not graph:
        raise HTTPException(status_code=503, detail="Graph not ready")

    try:
        config = {"configurable": {"thread_id": thread_id}}
        result = await invoke_supervisor_with_retry(graph, state, config=config)

        assistant_message = {
            "role": "assistant",
            "content": result.get("analysis", "I processed your request.")
        }
        _thread_store[thread_id]["messages"].append(assistant_message)

        run_id = str(uuid.uuid4())
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "messages": [assistant_message],
        }
    except Exception as e:
        logger.error(f"Run thread failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runs")
async def create_run(request: Request):
    """
    Stub endpoint for agent-chat-ui to create a new run without a pre-existing thread.

    This endpoint creates a new thread, runs the supervisor, and returns the
    assistant's response inline. This is the primary endpoint used by the UI.
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    thread_id = str(uuid.uuid4())
    _thread_store[thread_id] = {"messages": body.get("messages", [])}

    state = {
        "messages": body.get("messages", []),
        "thread_id": thread_id,
    }

    graph = get_graph(request.app)
    if not graph:
        raise HTTPException(status_code=503, detail="Graph not ready")

    try:
        config = {"configurable": {"thread_id": thread_id}}
        result = await invoke_supervisor_with_retry(graph, state, config=config)

        assistant_message = {
            "role": "assistant",
            "content": result.get("analysis", "I processed your request.")
        }
        _thread_store[thread_id]["messages"].append(assistant_message)

        run_id = str(uuid.uuid4())
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "messages": [assistant_message],
        }
    except Exception as e:
        logger.error(f"Create run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))