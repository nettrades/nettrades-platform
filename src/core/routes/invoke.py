# -*- coding: utf-8 -*-
# FILE: src/core/routes/invoke.py
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.
"""Main inference endpoint."""

import os
import logging
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Request, status

from supervisor import invoke_supervisor_with_retry, ClusterRecovering
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

    Error responses:
    - 400: malformed JSON body
    - 401: missing or invalid API key
    - 422: missing required field
    - 500: unexpected failure inside the graph
    - 503: the pinned inference track is temporarily unreachable
           (see ClusterRecovering below). The response carries a
           Retry-After header so the client can back off and retry.

    CLUSTER RECOVERY POLICY (2026-10):
    When a session is pinned to the RPC track (state["inference_track"]
    == "rpc") and the RPC cluster is temporarily unreachable, the
    supervisor raises ClusterRecovering rather than silently falling
    back to local inference.

    Silent fallback was rejected because:
      - The RPC cluster serves a larger model than the local fallback.
      - Mid-conversation downgrade produces visibly worse answers and
        can introduce factual inconsistencies between turns.
      - Users cannot tell that the backend changed, so they interpret
        the quality drop as a bug.

    Failing loudly is the correct behaviour. The user sees a clear
    message, retries once the cluster has recovered (typically within
    tens of seconds, because the supervisor promotes a warm spare or
    the master restarts with a reduced topology), and the conversation
    continues from the last checkpoint.
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

    # Demo support: allow callers to pin the inference track on the first
    # turn of a session. Subsequent turns inherit the pin from the
    # checkpointed state (session affinity), so this only takes effect
    # for a fresh thread.
    _force = state.pop("_force_track", None)
    if _force and not state.get("inference_track"):
        state["inference_track"] = _force

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
        result = await invoke_supervisor_with_retry(
            graph, state, config=config if config else None
        )

        # Record the intent for metrics
        intent = result.get("intent", "unknown")
        record_metrics(intent)
        logger.info(f"Request completed with intent: {intent}")

        return result

    except ClusterRecovering as e:
        # ---------------------------------------------------------------------
        # FAIL LOUDLY. Do NOT fall back to local inference.
        # ---------------------------------------------------------------------
        # The supervisor has detected that the pinned RPC cluster is
        # temporarily unreachable and has decided, correctly, that
        # silent downgrade is worse than an explicit error. We surface
        # that decision to the client with a 503 and a Retry-After hint.
        #
        # The client UI should:
        #   1. Show the error message to the user.
        #   2. Disable the send button for `Retry-After` seconds.
        #   3. Re-enable it, so the user can retry with the same
        #      thread_id. The checkpointer preserves the full
        #      conversation transcript; the retry continues from the
        #      last completed turn.
        logger.warning(f"Cluster recovering: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
            headers={"Retry-After": "30"},
        )

    except Exception as e:
        # str(e) is sometimes empty (StopIteration, CancelledError, custom
        # exceptions with no message). Log the type and repr along with the
        # full formatted traceback so the real cause is always captured.
        logger.error(
            "Graph invocation failed: %s: %r",
            type(e).__name__,
            e,
        )
        logger.error("Traceback:\n%s", traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
        )
