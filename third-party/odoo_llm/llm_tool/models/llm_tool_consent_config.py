from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class LLMToolConsentConfig(models.Model):
    """Configuration for tool consent messages"""

    _name = "llm.tool.consent.config"
    _description = "LLM Tool Consent Configuration"
    _rec_name = "name"
    name = fields.Char(required=True, default="Default Configuration")
    active = fields.Boolean(default=False)

    # Message to add to tool description
    tool_description_message = fields.Text(
        string="Tool Description Consent Message",
        default="\n\nIMPORTANT: This tool requires explicit user consent before execution. Please ask the user for permission before using this tool.",
    )

    # System message instructions
    system_message_template = fields.Text(
        string="System Message Template",
        default="""The following tools require explicit user consent before execution: {tool_names}.
For these tools, you MUST:
1. Clearly explain to the user what the tool will do
2. Ask for their explicit permission before using the tool
3. Only proceed with using the tool if the user gives clear consent
4. If the user denies consent or doesn't respond clearly, do not use the tool""",
    )

    @api.constrains("active")
    def _check_active_unique(self):
        """Ensure only one configuration is active at a time"""
        for record in self.filtered("active"):
            # Count active records excluding the current one
            active_count = self.search_count(
                [("active", "=", True), ("id", "!=", record.id)]
            )
            if active_count > 0:
                raise ValidationError(
                    _("Only one configuration can be active at a time.")
                )

    @api.model
    def get_active_config(self):
        """Get the active configuration or create default if none exists"""
        config = self.search([("active", "=", True)], limit=1)
        if not config:
            # No active config, try to find any config
            config = self.search([], limit=1)
            if config:
                # Activate the first config found
                config.write({"active": True})
            else:
                # Create a new default config and activate it
                config = self.create({"name": "Default Configuration", "active": True})
        return config
