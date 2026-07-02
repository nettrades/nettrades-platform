from odoo import models


class LLMModel(models.Model):
    _inherit = "llm.model"

    def chat(self, messages, stream=False, tools=None, tool_choice="auto", **kwargs):
        """Send chat messages using this model"""
        return self.provider_id.chat(
            messages,
            model=self,
            stream=stream,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )
