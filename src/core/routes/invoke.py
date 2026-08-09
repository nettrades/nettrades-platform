# -*- coding: utf-8 -*-
"""Main inference endpoint."""

import os
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, status

from supervisor import invoke_supervisor_with_retry
from routes._shared import get_graph, record_metrics

logger = logging.getLogger(__name__)
router = APIRouter(tags=["invoke"])

LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_API_KEY")


@router.post("/invoke")
async def invoke(
    request: Request,
    x_api_key: Optional[str] = Header(None, description="API key for authentication")
):
    """
    Main inference endpoint.

    This endpoint receives a user message, processes it through the LangGraph
    supervisor, and returns the result.

    Authentication:
    - Requires the 'X-API-Key' header with a valid API key.
    - The API key must match the LANGGRAPH_API_KEY environment variable.
    """
    DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() == "true"

    # =========================================================================
    # STEP 1: AUTHENTICATION
    # =========================================================================
    if DISABLE_AUTH:
        logger.warning("Authentication is disabled (DISABLE_AUTH=true) - allowing all requests.")
    else:
        if not LANGGRAPH_API_KEY:
            logger.error("LANGGRAPH_API_KEY is not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="LANGGRAPH_API_KEY is not configured."
            )
        if not x_api_key or x_api_key != LANGGRAPH_API_KEY:
            logger.warning(f"Invalid API key attempt: {x_api_key[:8] if x_api_key else 'None'}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )

    # =========================================================================
    # STEP 2: PARSE REQUEST BODY
    # =========================================================================
    try:
        # Retrieve sanitised body if available, else fallback to original
        if hasattr(request.state, "_sanitised_body"):
            body = request.state._sanitised_body
        else:
            body = await request.json()
        logger.debug(f"Request body: {body}")
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON body: {str(e)}"
        )

    if "input" not in body:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing 'input' field in request body"
        )

    state = body.get("input", {})
    config = body.get("config", {})
    if config.get("configurable", {}).get("thread_id"):
        state["thread_id"] = config["configurable"]["thread_id"]

    # =========================================================================
    # STEP 3: INVOKE THE SUPERVISOR GRAPH
    # =========================================================================
    graph = get_graph(request.app)
    if not graph:
        logger.error("Graph not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graph not initialized. Please check the server logs."
        )

    try:
        result = await invoke_supervisor_with_retry(graph, state, config=config if config else None)

        # Record the intent for metrics
        intent = result.get("intent", "unknown")
        record_metrics(intent)
        logger.info(f"Request completed with intent: {intent}")

        return result
    except Exception as e:
        logger.error(f"Graph invocation failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph invocation failed: {str(e)}"
        )