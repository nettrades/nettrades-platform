# src/core/supervisor.py - Modified to collect data for the self-improving loop

async def route(self, state: dict) -> dict:
    """Route the request and collect data for the self-improving loop."""
    intent = state.get("intent", "general")
    user_input = state.get("messages", [{}])[-1].get("content", "")

    # Process the request (existing logic)
    result = await self._process_request(state)

    # Collect episode for self-improving loop
    self._collect_episode(
        input_text=user_input,
        output_text=result.get("analysis", ""),
        intent=intent,
        quality_score=result.get("quality_score", 0.0),
    )

    return result

def _collect_episode(self, input_text, output_text, intent, quality_score):
    """Collect an episode for the self-improving loop."""
    # This would call the Odoo data collection service
    pass