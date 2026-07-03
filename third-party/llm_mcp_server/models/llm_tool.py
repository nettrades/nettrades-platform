import logging

from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from odoo import _, api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMTool(models.Model):
    _inherit = "llm.tool"

    @api.model
    def get_mcp_tools_list(self, params=None):
        """Handle MCP tools/list request - return MCP ListToolsResult

        Returns only tools that the current user has permission to access.
        Filtering is handled by Odoo's native Record Rules based on 'category' field.
        """
        # search() without sudo() respects ACL and Record Rules automatically
        active_tools = self.search([("active", "=", True)])

        mcp_tools = []
        for tool in active_tools:
            # Get tool definition as dict
            tool_definition = tool.get_tool_definition()
            # Convert to MCP Tool object
            mcp_tool = Tool(**tool_definition)
            mcp_tools.append(mcp_tool)

        return ListToolsResult(tools=mcp_tools)

    @api.model
    def execute_mcp_tool(self, params=None):
        """Handle MCP tools/call request - return MCP CallToolResult"""
        if not params:
            raise UserError(_("Missing parameters for tool call"))

        tool_name = params.get("name")
        if not tool_name:
            raise UserError(_("Missing tool name in parameters"))

        tool_arguments = params.get("arguments", {})

        # Find the tool by name
        tool = self.search([("name", "=", tool_name), ("active", "=", True)], limit=1)
        if not tool:
            raise UserError(_("Tool '%s' not found or inactive") % tool_name)

        try:
            # Execute the tool
            result = tool.execute(tool_arguments)

            # Return MCP CallToolResult
            content = [
                TextContent(type="text", text=str(result) if result is not None else "")
            ]
            return CallToolResult(content=content, isError=False)
        except Exception as e:
            _logger.exception(f"Error executing tool {tool_name}")
            # Return error result
            error_content = [
                TextContent(type="text", text=f"Tool execution failed: {str(e)}")
            ]
            return CallToolResult(content=error_content, isError=True)
