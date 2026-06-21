import logging

from odoo import models, tools

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = "mail.message"

    def letta_format_message(self):
        """Provider-specific formatting for Letta."""
        self.ensure_one()
        body = self.body
        if body:
            body = tools.html2plaintext(body)

        if self.is_llm_user_message()[self]:
            formatted_message = {"role": "user"}
            if body:
                formatted_message["content"] = body
            return formatted_message

        elif self.is_llm_assistant_message()[self]:
            formatted_message = {"role": "assistant"}
            formatted_message["content"] = body

            # Note: Letta handles tool calls differently than OpenAI
            # For now, we'll keep it simple and not include tool calls

            return formatted_message

        elif self.is_llm_tool_message()[self]:
            # For Letta, tool messages might need different handling
            # This is a placeholder for future tool integration
            _logger.info(f"Letta: Skipping tool message {self.id} for now")
            return None

        else:
            return None
