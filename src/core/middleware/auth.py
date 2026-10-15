# -*- coding: utf-8 -*-
# FILE: src/core/middleware/auth.py
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

    # -------------------------------------------------------------------------
    # JWT validation is NOT YET IMPLEMENTED.
    #
    # The previous version of this file contained a placeholder that
    # accepted any Bearer token and set request.state.user = {"sub": "test-user"}.
    # That placeholder was inert only because AUTH_ENABLED defaults to false.
    # If anyone flipped AUTH_ENABLED to true without understanding this, the
    # middleware would accept every request — a complete auth bypass.
    #
    # Fail closed until real validation is implemented:
    #   1. Verify the JWT signature against Odoo's public key
    #   2. Check the exp / iss / aud claims
    #   3. Set request.state.user from the verified payload
    #
    # Until then, raise 501 so operators get a clear signal rather than a
    # silent bypass.
    # -------------------------------------------------------------------------
    raise HTTPException(
        status_code=501,
        detail="JWT validation not implemented. Set AUTH_ENABLED=false or implement token verification.",
    )

    # The following line is unreachable but kept for structural clarity:
    # return await call_next(request)