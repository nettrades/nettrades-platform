from odoo import models


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "llm.assistant.action.mixin"]

    def action_process_with_ai(self):
        """
        Parse invoice with AI assistant.
        Creates a fresh thread every time (no context carryover).
        Frontend opens AI chat for OCR parsing and follow-up questions.
        """
        return self.action_open_llm_assistant(
            "odoo_invoice_data_entry_assistant", force_new_thread=True
        )
