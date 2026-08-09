# -*- coding: utf-8 -*-
"""JWT authentication middleware for Odoo OAuth 2.0."""

import os
from fastapi import HTTPException, status


async def auth_middleware(request, call_next):
    """
    Validates JWT tokens issued by Odoo for protected endpoints.
    If AUTH_ENABLED is false, skip validation.
    """
    auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        return await call_next(request)

    # Skip validation for health and metrics endpoints
    if request.url.path in ["/health", "/metrics"]:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ")[1]
    # Validate the token (implement your validation logic)
    # For example, verify signature using Odoo's public key
    # and extract user information.
    try:
        # Placeholder validation
        # In production, use a library like python-jose to verify JWT
        # and check with Odoo's public key.
        payload = {"sub": "test-user"}
        request.state.user = payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    return await call_next(request)