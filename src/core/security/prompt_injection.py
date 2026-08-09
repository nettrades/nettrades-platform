# =============================================================================
# FILE: src/core/security/prompt_injection.py
# =============================================================================
# PURPOSE:
#   Lightweight sanitisation and detection of prompt injection patterns.
#   This module checks user inputs for known adversarial patterns and
#   strips or blocks them before they reach LangGraph agents.
#
#   It is designed to be used as a FastAPI dependency or middleware.
#
# UPDATES (2026-08-10):
#   - Added PromptInjectionMiddleware class for FastAPI integration.
#   - Kept existing detect_injection and sanitise_input functions.
# =============================================================================

import re
import logging
from typing import Dict, Any, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Common injection patterns - can be extended via Odoo admin later
INJECTION_PATTERNS = [
    r"(?i)ignore previous instructions",
    r"(?i)forget all previous instructions",
    r"(?i)you are now (.*?) and must",
    r"(?i)disregard (?:all|any) (?:previous|prior) (?:instructions|prompts)",
    r"(?i)you are an AI assistant that has been (?:hacked|compromised)",
    r"(?i)system: you are a (.*?) who will",
    r"(?i)new role: (.*?)",
    r"(?i)from now on, (.*?)",
    r"(?i)your new purpose is to",
    r"(?i)do not (?:follow|obey) (?:the|these) (?:instructions|prompts)",
]


def detect_injection(text: str) -> bool:
    """
    Returns True if any injection pattern is found in the text.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def sanitise_input(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively scans and sanitises strings in the input data.
    If an injection is detected, the offending field is redacted.
    Returns a new dict with sanitised values.
    """
    if isinstance(input_data, dict):
        new_data = {}
        for key, value in input_data.items():
            if isinstance(value, str):
                if detect_injection(value):
                    logger.warning(f"Prompt injection detected in field '{key}'. Redacting.")
                    new_data[key] = "[REDACTED - Potential injection]"
                else:
                    new_data[key] = value
            elif isinstance(value, (list, dict)):
                new_data[key] = sanitise_input(value)  # recurse
            else:
                new_data[key] = value
        return new_data
    elif isinstance(input_data, list):
        return [sanitise_input(item) for item in input_data]
    else:
        return input_data


class PromptInjectionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that sanitises incoming JSON request bodies
    to prevent prompt injection attacks.

    It extracts the request body (if JSON), passes it through sanitise_input(),
    and stores the sanitised version in request.state._sanitised_body.
    This allows downstream handlers to use the cleaned data instead of the raw input.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Intercept POST requests with JSON content, sanitise the body,
        and store it in the request state.
        """
        # Only process POST requests with JSON content
        if request.method == "POST" and request.headers.get("content-type", "").startswith("application/json"):
            try:
                # Read the raw body (this consumes the stream, so we need to store it)
                body = await request.json()
                # Sanitise the data
                sanitised = sanitise_input(body)
                # Attach to request state for later use
                request.state._sanitised_body = sanitised
            except Exception as e:
                logger.warning(f"Failed to sanitise request: {e}")

        # Continue processing the request
        response = await call_next(request)
        return response