import inspect
import json
import logging
from typing import Any, get_type_hints

from pydantic import create_model

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class LLMTool(models.Model):
    _name = "llm.tool"
    _description = "LLM Tool"
    _inherit = ["mail.thread"]

    # Basic tool information
    name = fields.Char(
        required=True,
        tracking=True,
        help="The name of the tool. This will be used by the LLM to call the tool.",
    )
    description = fields.Text(
        required=True,
        tracking=True,
        help="A human-readable description of what the tool does. This will be sent to the LLM.",
    )
    implementation = fields.Selection(
        selection=lambda self: self._selection_implementation(),
        required=True,
        help="The implementation that provides this tool's functionality",
    )
    active = fields.Boolean(default=True)

    # Input schema
    input_schema = fields.Text(
        string="Input Schema",
        help="JSON Schema defining the expected parameters for the tool",
    )

    # Annotations (following the schema specification)
    title = fields.Char(string="Title", help="A human-readable title for the tool")
    read_only_hint = fields.Boolean(
        string="Read Only",
        default=False,
        help="If true, the tool does not modify its environment",
    )
    idempotent_hint = fields.Boolean(
        string="Idempotent",
        default=False,
        help="If true, calling the tool repeatedly with the same arguments will have no additional effect",
    )
    destructive_hint = fields.Boolean(
        string="Destructive",
        default=True,
        help="If true, the tool may perform destructive updates to its environment",
    )
    open_world_hint = fields.Boolean(
        string="Open World",
        default=True,
        help="If true, this tool may interact with an 'open world' of external entities",
    )

    # Implementation-specific fields
    server_action_id = fields.Many2one(
        "ir.actions.server",
        string="Related Server Action",
        help="The specific server action this tool will execute",
    )

    # Function implementation fields
    decorator_model = fields.Char(
        string="Decorator Model",
        readonly=True,
        help="Model name where the decorated method lives (e.g., 'sale.order'). "
        "Set automatically during registration.",
    )
    decorator_method = fields.Char(
        string="Decorator Method",
        readonly=True,
        help="Method name of the decorated tool (e.g., 'create_sales_quote'). "
        "Set automatically during registration.",
    )

    # User consent
    requires_user_consent = fields.Boolean(
        default=False,
        help="If true, the user must consent to the execution of this tool",
    )

    # Default tool flag
    default = fields.Boolean(
        default=False,
        help="Set to true if this is a default tool to be included in all LLM requests",
    )

    # Auto-update flag for function tools
    auto_update = fields.Boolean(
        default=True,
        help="If true, tool metadata will be automatically updated from decorator on Odoo restart. "
        "Set to false to manually manage this tool's configuration.",
    )

    # Tool category for native Odoo Record Rules integration.
    # Keep this Selection minimal and free of optional-module values so the
    # base module installs on any Odoo 19 Community DB. Bridge modules can
    # extend with `_selection_add` — for example a llm_tool_sale module would:
    #     category = fields.Selection(selection_add=[('sales', 'Sales')])
    category = fields.Selection(
        [
            ('general', 'General'),
            ('technical', 'Technical'),
        ],
        string="Tool Category",
        default='general',
        help="Category determines which user groups can access this tool via "
             "Odoo Record Rules. Third-party modules should use "
             "`selection_add` to register additional categories.",
    )

    # Odoo 19: Use models.Constraint instead of _sql_constraints
    _unique_function_tool = models.Constraint(
        "UNIQUE(decorator_model, decorator_method)",
        "A tool for this model and method combination already exists!",
    )
    _unique_tool_name = models.Constraint(
        "UNIQUE(name)",
        "A tool with this name already exists! Tool names must be unique.",
    )

    @api.model
    def _selection_implementation(self):
        """Get all available implementations from tool implementations"""
        implementations = []
        for implementation in self._get_available_implementations():
            implementations.append(implementation)
        return implementations

    @api.model
    def _get_available_implementations(self):
        """Hook method for registering tool services"""
        return [
            ("function", "Function"),
        ]

    def get_pydantic_model_from_signature(self, method):
        """Create a Pydantic model from a method signature"""
        type_hints = get_type_hints(method)
        signature = inspect.signature(method)
        fields = {}

        for param_name, param in signature.parameters.items():
            if param_name == "self":
                continue
            fields[param_name] = (
                type_hints.get(param_name, Any),
                param.default if param.default != param.empty else ...,
            )

        return create_model("DynamicModel", **fields)

    def _get_decorated_method(self):
        """Get the actual decorated method for function tools"""
        self.ensure_one()

        if not self.decorator_model or not self.decorator_method:
            raise ValueError(
                f"Function tool {self.name} missing decorator_model or decorator_method"
            )

        # Get the model (let KeyError propagate if model doesn't exist)
        model_obj = self.env[self.decorator_model]
        model_class = type(model_obj)

        # Check the method exists on the class
        if not hasattr(model_class, self.decorator_method):
            raise AttributeError(
                f"Method {self.decorator_method} not found on model {self.decorator_model}"
            )

        # Return bound method from the instance (not unbound from class)
        return getattr(model_obj, self.decorator_method)

    def get_input_schema(self):
        """Get input schema - from stored field or generate from method signature

        Returns the tool's input schema. Priority:
        1. Use self.input_schema if set (manual override or stored from decorator)
        2. Generate from method signature using MCP SDK
        """
        self.ensure_one()

        # If schema is stored in DB, use it
        if self.input_schema:
            return json.loads(self.input_schema)

        # Generate schema from method signature
        method_func = self._get_implementation_method()

        # Use MCP SDK's func_metadata to generate proper schema
        from mcp.server.fastmcp.utilities.func_metadata import func_metadata

        func_meta = func_metadata(method_func)

        # Get MCP-compatible schema
        schema = func_meta.arg_model.model_json_schema(by_alias=True)
        return schema

    # Note: Tool filtering is now handled by Odoo's native Record Rules
    # based on the 'category' field. No custom filtering needed.

    def execute(self, parameters):
        """Execute this tool with validated parameters"""
        # Get the actual method to execute
        method = self._get_implementation_method()

        # Validate parameters against method signature
        model = self.get_pydantic_model_from_signature(method)
        validated = model(**parameters)

        # Execute the method
        return method(**validated.model_dump())

    def _get_implementation_method(self):
        """Get the actual method for this tool's implementation"""
        self.ensure_one()

        if self.implementation == "function":
            # For decorated tools, get the actual decorated method
            method = self._get_decorated_method()

            # Validate it's actually decorated (optional safety check)
            if not getattr(method, "_is_llm_tool", False):
                _logger.warning(
                    "Method '%s' on model '%s' is not decorated with @llm_tool",
                    self.decorator_method,
                    self.decorator_model,
                )

            return method
        else:
            # For other future implementations, use {implementation}_execute pattern
            impl_method_name = f"{self.implementation}_execute"
            if not hasattr(self, impl_method_name):
                raise NotImplementedError(
                    _("Implementation method %(method)s not found")
                    % {"method": impl_method_name}
                )
            return getattr(self, impl_method_name)

    @api.model
    def _register_hook(self):
        """Scan for @llm_tool decorated methods and auto-register them"""
        super()._register_hook()

        # Track found tools to deactivate missing ones later
        found_tools = set()

        # Scan all models in registry for decorated methods
        for model_name in self.env.registry:
            try:
                model = self.env[model_name]
            except Exception as e:
                # Skip models that can't be accessed (expected for abstract models, etc.)
                _logger.info("Skipping inaccessible model '%s': %s", model_name, e)
                continue

            # Scan class methods directly to avoid triggering property/descriptor access
            # Using type(model) gets the class, avoiding recordset-specific attributes
            model_class = type(model)
            for attr_name in dir(model_class):
                # Skip private attributes and known problematic ones
                if attr_name.startswith("_"):
                    continue

                try:
                    # Get attribute from class, not instance
                    attr = getattr(model_class, attr_name, None)
                    if callable(attr) and getattr(attr, "_is_llm_tool", False):
                        # Found a decorated tool - register it (handles its own errors)
                        self._register_function_tool(model_name, attr_name, attr)
                        # Track that we found this tool
                        found_tools.add((model_name, attr_name))
                except Exception as e:
                    # Some attributes may still fail - log and continue
                    _logger.info(
                        "Skipping attribute '%s' on model '%s': %s",
                        attr_name,
                        model_name,
                        e,
                    )
                    continue

        # Deactivate function tools that no longer exist in code
        self._deactivate_missing_tools(found_tools)

    def _register_function_tool(self, model_name, method_name, method):
        """Create or update tool record for decorated method.

        Handles concurrent registration from multiple workers using Odoo's
        savepoint context manager pattern (same as ir_cron uses).

        If xml_managed=True in the decorator, this method completely skips the tool.
        XML data files have full control over XML-managed tools.
        """
        # Check if tool is XML-managed - if so, skip entirely
        xml_managed = getattr(method, "_llm_tool_xml_managed", False)
        if xml_managed:
            _logger.info(
                "Skipping XML-managed tool %s.%s (controlled by XML data file)",
                model_name,
                method_name,
            )
            return

        # Prepare values from decorator metadata
        tool_name = getattr(method, "_llm_tool_name", method_name)
        values = {
            "name": tool_name,
            "implementation": "function",
            "decorator_model": model_name,
            "decorator_method": method_name,
            "description": getattr(method, "_llm_tool_description", ""),
            "active": True,  # Ensure tool is active (reactivate if previously deactivated)
        }

        # Add metadata if present
        metadata = getattr(method, "_llm_tool_metadata", {})
        if "read_only_hint" in metadata:
            values["read_only_hint"] = metadata["read_only_hint"]
        if "idempotent_hint" in metadata:
            values["idempotent_hint"] = metadata["idempotent_hint"]
        if "destructive_hint" in metadata:
            values["destructive_hint"] = metadata["destructive_hint"]
        if "open_world_hint" in metadata:
            values["open_world_hint"] = metadata["open_world_hint"]

        # Store manual schema if provided via decorator
        if hasattr(method, "_llm_tool_schema"):
            values["input_schema"] = json.dumps(method._llm_tool_schema, indent=2)

        # Use Odoo's savepoint pattern (same as demo data loading in loading.py)
        # If concurrent access fails, savepoint rolls back and we skip gracefully
        try:
            with self.env.cr.savepoint(flush=False):
                # Search for existing tool record (including inactive ones)
                existing = self.with_context(active_test=False).search(
                    [
                        ("decorator_model", "=", model_name),
                        ("decorator_method", "=", method_name),
                    ],
                    limit=1,
                )

                if existing:
                    # Only update if auto_update is enabled
                    auto_update = getattr(existing, "auto_update", True)
                    if auto_update:
                        was_inactive = not existing.active
                        existing.write(values)
                        if was_inactive:
                            _logger.info(
                                "Reactivated function tool '%s' from %s.%s",
                                values["name"],
                                model_name,
                                method_name,
                            )
                        else:
                            _logger.debug(
                                "Updated function tool '%s' from %s.%s",
                                values["name"],
                                model_name,
                                method_name,
                            )
                    else:
                        _logger.debug(
                            "Skipped update for function tool '%s' (auto_update=False)",
                            existing.name,
                        )
                else:
                    # Auto-create the tool
                    self.create(values)
                    _logger.info(
                        "Registered function tool '%s' from %s.%s",
                        values["name"],
                        model_name,
                        method_name,
                    )

        except Exception as e:
            # Concurrent access or other error - skip gracefully (same as Odoo demo data)
            # Tool either already exists or will be registered on next single-worker restart
            _logger.info(
                "Skipped tool registration for %s.%s (concurrent access or already exists): %s",
                model_name,
                method_name,
                e,
            )

    def _deactivate_missing_tools(self, found_tools):
        """Deactivate function tools that no longer exist in code.

        Args:
            found_tools: Set of (model_name, method_name) tuples for tools found during scan

        Uses Odoo's savepoint pattern to handle concurrent deactivation gracefully.
        """
        try:
            # Get all active function tools
            all_function_tools = self.search(
                [("implementation", "=", "function"), ("active", "=", True)]
            )
        except Exception as e:
            # During module upgrade, database might not be ready yet
            _logger.debug("Skipping tool deactivation during upgrade: %s", e)
            return

        for tool in all_function_tools:
            key = (tool.decorator_model, tool.decorator_method)
            if key not in found_tools:
                # Tool no longer exists in code - deactivate it
                try:
                    with self.env.cr.savepoint(flush=False):
                        tool.active = False
                    _logger.info(
                        "Deactivated missing function tool '%s' from %s.%s",
                        tool.name,
                        tool.decorator_model,
                        tool.decorator_method,
                    )
                except Exception:
                    # Concurrent access - skip gracefully
                    _logger.info(
                        "Skipped deactivation for tool '%s' (concurrent access)",
                        tool.name,
                    )

    # API methods for the Tool schema
    def get_tool_definition(self):
        """Returns MCP-compatible tool definition"""
        self.ensure_one()

        # For function tools, use docstring if no description in DB
        description = self.description
        if self.implementation == "function" and not description:
            try:
                method = self._get_decorated_method()
                description = inspect.getdoc(method) or ""
            except (ValueError, AttributeError, KeyError):
                pass  # Could not get method, use empty description

        # Get the input schema (respects stored field or generates)
        input_schema_data = self.get_input_schema()

        # Create MCP ToolAnnotations (only with non-None values)
        from mcp.types import Tool, ToolAnnotations

        # Build annotations dict with only non-None values
        annotations_data = {}
        if self.read_only_hint is not None:
            annotations_data["readOnlyHint"] = self.read_only_hint
        if self.idempotent_hint is not None:
            annotations_data["idempotentHint"] = self.idempotent_hint
        if self.destructive_hint is not None:
            annotations_data["destructiveHint"] = self.destructive_hint
        if self.open_world_hint is not None:
            annotations_data["openWorldHint"] = self.open_world_hint

        tool_annotations = (
            ToolAnnotations(**annotations_data) if annotations_data else None
        )

        # Create and validate MCP Tool instance
        mcp_tool = Tool(
            name=self.name,
            title=self.title
            if self.title
            else self.name,  # title goes to BaseMetadata, not ToolAnnotations
            description=self.description or "",
            inputSchema=input_schema_data,
            annotations=tool_annotations,
        )

        # Return plain dict following 'Models Return Plain Data' pattern
        return mcp_tool.model_dump(exclude_none=True)

    @api.onchange("implementation")
    def _onchange_implementation(self):
        """When implementation changes and input_schema is empty, populate it with the implementation schema"""
        if self.implementation and not self.input_schema:
            schema = self.get_input_schema()
            if schema:
                self.input_schema = json.dumps(schema, indent=2)

    def action_reset_input_schema(self):
        """Reset the input schema to the implementation schema"""
        for record in self:
            # Temporarily clear input_schema to force regeneration
            old_schema = record.input_schema
            record.input_schema = False
            try:
                schema = record.get_input_schema()
                if schema:
                    record.input_schema = json.dumps(schema, indent=2)
                else:
                    # If no schema generated, restore old one
                    record.input_schema = old_schema
            except Exception:
                # If regeneration fails, restore old schema and propagate error
                record.input_schema = old_schema
                raise
        # Return an action to reload the view
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
