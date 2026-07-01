# =============================================================================
# FILE: src/core/security/prompt_injection.py
# =============================================================================
# PURPOSE:
#   Lightweight sanitisation and detection of prompt injection patterns.
#   This module checks user inputs for known adversarial patterns and
#   strips or blocks them before they reach LangGraph agents.
#
#   It is designed to be used as a FastAPI dependency or middleware.
# =============================================================================

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Common injection patterns – can be extended via Odoo admin later
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