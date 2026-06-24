# =============================================================================
# NETTRADES Supervisor – Updated for Bridge Integration
# =============================================================================
# FILE: src/core/supervisor.py
#
# PURPOSE:
#   This file contains the main LangGraph supervisor that orchestrates
#   all AI agents. It classifies user intents, performs medical/legal
#   screening, and routes requests to the appropriate sub-agent.
#
# UPDATED:
#   - Added company_id to state for bridge routing
#   - Added bridge integration point
# =============================================================================

# ... (existing imports) ...

def build_supervisor():
    # ... (existing code) ...

    async def classify(state: dict) -> dict:
        # Get the last user message
        user_msg = state.get("messages", [{}])[-1].get("content", "")
        # Get company_id for bridge routing
        company_id = state.get("company_id")

        # ... (rest of classify) ...

    async def route(state: dict) -> dict:
        # Check if bridge should handle this request
        # The bridge module intercepts requests before they reach the supervisor
        # If the bridge returns a response, use it
        bridge_result = state.get("bridge_result")
        if bridge_result and bridge_result.get("source") != "local":
            return bridge_result

        # ... (existing routing logic) ...

    # ... (rest of supervisor) ...