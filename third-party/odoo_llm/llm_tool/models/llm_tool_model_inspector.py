import inspect
import logging
from typing import Any, Optional

from odoo import api, models

_logger = logging.getLogger(__name__)

# Constants defining the checks (outside the class for better maintainability)
METHOD_TYPE_CHECKS = [
    (lambda mo, ma, iss, isc: ma == "model", "model", "@api.model"),
    (
        lambda mo, ma, iss, isc: ma == "model_create",
        "model_create",
        "@api.model_create_multi/_single",
    ),
    (lambda mo, ma, iss, isc: iss, "static", "@staticmethod"),
    (lambda mo, ma, iss, isc: isc, "class", "@classmethod"),
    (lambda mo, ma, iss, isc: isinstance(mo, staticmethod), "static", "@staticmethod"),
    (lambda mo, ma, iss, isc: isinstance(mo, classmethod), "class", "@classmethod"),
]

OTHER_DECORATOR_CHECKS = [
    (
        lambda mo: hasattr(mo, "_depends"),
        lambda self, mo: f"@api.depends({self._format_depends_info(mo)})",
    ),
    (lambda mo: hasattr(mo, "_constrains"), lambda self, mo: "@api.constrains(...)"),
    (lambda mo: hasattr(mo, "_onchange"), lambda self, mo: "@api.onchange(...)"),
    (lambda mo: getattr(mo, "deprecated", False), lambda self, mo: "@api.deprecated"),
]


class LLMToolModelInspector(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self) -> list[tuple[str, str]]:
        implementations = super()._get_available_implementations()
        return implementations + [
            ("odoo_model_inspector", "Odoo Comprehensive Model Inspector")
        ]

    def odoo_model_inspector_execute(
        self,
        model: str,
        include_fields: bool = True,
        include_methods: bool = True,
        field_limit: int = 30,
        method_limit: int = 20,
        include_private: bool = False,
        method_name_filter: Optional[str] = None,
        method_type_filter: Optional[list[str]] = None,
        field_name_filter: Optional[str] = None,
        field_type_filter: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Comprehensive inspection of an Odoo model including basic information, fields, and methods.

        Parameters:
            model: The Odoo model name to inspect (e.g., res.partner)
            include_fields: Whether to include field information (default: True)
            include_methods: Whether to include method information (default: True)
            field_limit: Maximum number of fields to return (default: 30)
            method_limit: Maximum number of methods to return (default: 20)
            include_private: Whether to include private fields and methods starting with '_' (default: False)
            method_name_filter: Optional filter for methods where name contains this string (case-insensitive)
            method_type_filter: Optional filter for methods by type (e.g., 'instance', 'static', 'model')
            field_name_filter: Optional filter for fields where name contains this string (case-insensitive)
            field_type_filter: Optional filter for fields by type (e.g., 'char', 'many2one', 'integer')
        """
        _logger.info(
            f"Executing Comprehensive Model Inspector with: model={model}, "
            f"include_fields={include_fields}, include_methods={include_methods}"
        )

        # Check if model exists
        if model not in self.env:
            return {"error": f"Model '{model}' not found in Odoo environment"}

        model_obj = self.env[model]

        # 1. Get basic model information from ir.model
        model_info = self._get_model_basic_info(model)
        result = {
            "name": model_info.get("name", model),
            "model": model,
            "description": model_info.get("description", ""),
            "module": model_info.get("module", ""),
            "transient": model_info.get("transient", False),
        }

        # 2. Get inheritance information
        inheritance_info = self._get_inheritance_info(model_obj)
        result["inheritance"] = inheritance_info

        # 3. Get field information if requested
        if include_fields:
            fields_info = self._get_fields_info(
                model_obj,
                limit=field_limit,
                include_private=include_private,
                name_filter=field_name_filter,
                type_filter=field_type_filter,
            )
            result["fields"] = fields_info["fields"]
            result["field_count"] = fields_info["field_count"]
            result["total_fields"] = fields_info["total_fields"]

        # 4. Get method information if requested
        if include_methods:
            methods_info = self._get_methods_info(
                model_obj,
                limit=method_limit,
                include_private=include_private,
                name_filter=method_name_filter,
                type_filter=method_type_filter,
            )
            result["methods"] = methods_info["methods"]
            result["method_count"] = methods_info["returned_count"]
            result["total_methods"] = methods_info["total_found"]

        # 5. Generate a concise summary of the model
        result["summary"] = self._generate_model_summary(result)

        return result

    def _get_model_basic_info(self, model_name: str) -> dict[str, Any]:
        """Get basic information about the model from ir.model."""
        IrModel = self.env["ir.model"]
        model_info = IrModel.search_read(
            [("model", "=", model_name)],
            ["name", "model", "modules", "transient"],
            limit=1,
        )

        if not model_info:
            return {
                "name": model_name,
                "model": model_name,
                "description": f"Model {model_name} not found in ir.model",
                "module": "unknown",
                "transient": False,
            }

        info = model_info[0]
        return {
            "name": info.get("name", model_name),
            "model": info.get("model", model_name),
            "description": info.get("description", ""),
            "module": info.get("modules", ""),
            "transient": info.get("transient", False),
        }

    def _get_inheritance_info(self, model_obj: models.Model) -> dict[str, Any]:
        """Get information about model inheritance."""
        model_cls = model_obj.__class__
        try:
            base_models = []
            if hasattr(model_cls, "_inherit"):
                inherit = model_cls._inherit
                if isinstance(inherit, str):
                    base_models.append(inherit)
                elif isinstance(inherit, (list, tuple)):
                    base_models.extend(inherit)

            base_model = getattr(model_cls, "_name", None)

            return {
                "base_model": base_model,
                "inherited_models": base_models,
                "is_extension": bool(base_models) and base_model in base_models,
            }
        except Exception as e:
            return {"error": f"Error determining inheritance: {str(e)}"}

    def _get_fields_info(
        self,
        model_obj: models.Model,
        limit: int = 30,
        include_private: bool = False,
        name_filter: Optional[str] = None,
        type_filter: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Get detailed information about model fields."""
        fields_info = model_obj.fields_get()
        processed_fields = {}
        total_fields = len(fields_info)
        filtered_fields = {}

        # First filter fields
        for field_name, field_data in fields_info.items():
            # Skip private fields if not included
            if field_name.startswith("_") and not include_private:
                continue

            # Apply name filter if provided
            if name_filter and name_filter.lower() not in field_name.lower():
                continue

            # Apply type filter if provided
            if type_filter and field_data.get("type") not in type_filter:
                continue

            filtered_fields[field_name] = field_data

        # Sort fields by name and apply limit
        field_items = sorted(filtered_fields.items(), key=lambda x: x[0])
        limited_fields = field_items[:limit] if limit > 0 else field_items

        # Process the fields
        for field_name, field_data in limited_fields:
            processed_field = {
                "name": field_name,
                "type": field_data.get("type"),
                "string": field_data.get("string"),
                "help": field_data.get("help", ""),
                "required": field_data.get("required", False),
                "readonly": field_data.get("readonly", False),
                "store": field_data.get("store", True),
            }

            # Add relation info if it's a relational field
            if field_data.get("relation"):
                processed_field["relation"] = field_data.get("relation")
                processed_field["relation_field"] = field_data.get("relation_field", "")

            # Add selection values if it's a selection field
            if field_data.get("selection"):
                # Convert selection to dict for easier consumption
                if isinstance(field_data.get("selection"), list):
                    selection_dict = {
                        key: value for key, value in field_data.get("selection", [])
                    }
                    processed_field["selection"] = selection_dict

            processed_fields[field_name] = processed_field

        return {
            "fields": processed_fields,
            "field_count": len(processed_fields),
            "total_fields": total_fields,
            "limited": limit > 0 and len(filtered_fields) > limit,
        }

    def _get_methods_info(
        self,
        model_obj: models.Model,
        limit: int = 20,
        include_private: bool = False,
        name_filter: Optional[str] = None,
        type_filter: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Get detailed information about model methods."""
        model_cls = model_obj.__class__
        members = inspect.getmembers(model_cls, callable)
        method_details_list = []
        processed_names = set()

        for name, member in members:
            if name in processed_names:
                continue

            # Skip private methods if not included
            if name.startswith("_") and not include_private:
                continue

            # Apply name filter if provided
            if name_filter and name_filter.lower() not in name.lower():
                continue

            details = self._extract_method_details(model_cls, member, name)
            if not details:
                continue

            # Apply type filter if provided
            if type_filter and details.get("method_type") not in type_filter:
                continue

            method_details_list.append(details)
            processed_names.add(name)

        # Sort methods by name and apply limit
        method_details_list.sort(key=lambda x: x["name"])
        total_found = len(method_details_list)
        sliced_results = (
            method_details_list[:limit] if limit > 0 else method_details_list
        )

        return {
            "methods": sliced_results,
            "total_found": total_found,
            "returned_count": len(sliced_results),
            "limited": limit > 0 and total_found > limit,
        }

    def _format_depends_info(self, method_obj):
        """Helper to format the @api.depends decorator string."""
        depends_info = getattr(method_obj, "_depends", {})
        if isinstance(depends_info, (dict, tuple, list)):  # Check if it's iterable
            try:
                # Attempt to create a string representation, handle potential complex structures
                deps_str = (
                    ", ".join(f"'{f}'" for f in depends_info)
                    if isinstance(depends_info, dict)
                    else repr(depends_info)
                )
            except Exception:
                deps_str = "(complex dependencies)"  # Fallback for complex/unrepresentable structures
        else:
            deps_str = repr(depends_info)  # Fallback for non-standard types
        return deps_str

    def _extract_method_details(
        self, model_cls, method_obj, name
    ) -> Optional[dict[str, Any]]:
        """Extract detailed information about a method."""
        details = {
            "name": name,
            "docstring": "",
            "signature": "(Could not determine signature)",
            "method_type": "unknown",
            "decorators": [],
        }

        # 1. Get Docstring
        try:
            doc = inspect.getdoc(method_obj)
            details["docstring"] = doc.strip() if doc else "(No docstring)"
        except Exception as e:
            details["docstring"] = f"(Error getting docstring: {e})"

        # 2. Get Signature
        try:
            sig = inspect.signature(method_obj)
            try:
                signature_str = f"{name}{str(sig)}"
            except Exception:
                signature_str = f"{name}(...)"  # Fallback signature
            details["signature"] = signature_str
        except (ValueError, TypeError):
            details["signature"] = f"{name}(...)"  # Generic representation
        except Exception as e:
            details["signature"] = f"(Error inspecting signature: {e})"

        # --- Use Type and Decorator Logic Patterns ---
        method_type = "unknown"
        decorators_list = []
        type_found = False

        # Gather inputs for checks
        method_api = getattr(method_obj, "_api", None)
        try:
            static_attr = inspect.getattr_static(model_cls, name)
            is_staticmethod_static = isinstance(static_attr, staticmethod)
            is_classmethod_static = isinstance(static_attr, classmethod)
        except AttributeError:
            is_staticmethod_static = False
            is_classmethod_static = False

        # 3. Determine Primary Type and Core Decorator using METHOD_TYPE_CHECKS
        for check_func, type_str, decorator_str in METHOD_TYPE_CHECKS:
            if check_func(
                method_obj, method_api, is_staticmethod_static, is_classmethod_static
            ):
                if not type_found:
                    method_type = type_str
                    type_found = True
                # Add the core decorator if specified and not already present
                if decorator_str and decorator_str not in decorators_list:
                    decorators_list.append(decorator_str)

        if not type_found:
            if hasattr(method_obj, "__get__"):
                method_type = "instance"
            elif inspect.isfunction(method_obj):
                method_type = "function"

        # 4. Collect Other Decorators using OTHER_DECORATOR_CHECKS
        for check_func, formatter_func in OTHER_DECORATOR_CHECKS:
            if check_func(method_obj):
                decorator_str = formatter_func(self, method_obj)
                if decorator_str not in decorators_list:  # Avoid duplicates
                    decorators_list.append(decorator_str)

        details["method_type"] = method_type
        details["decorators"] = decorators_list

        return details

    def _generate_model_summary(self, model_data: dict[str, Any]) -> str:
        """Generate a concise summary of the model."""
        summary_parts = []

        # Basic model info
        summary_parts.append(f"Model: {model_data['name']} ({model_data['model']})")
        if model_data.get("description", {}):
            summary_parts.append(f"Description: {model_data['description']}")

        # Inheritance
        inheritance = model_data.get("inheritance", {})
        if inheritance.get("inherited_models"):
            inherited = ", ".join(inheritance.get("inherited_models", []))
            summary_parts.append(f"Inherits from: {inherited}")

        # Fields summary
        if "fields" in model_data:
            field_types = {}
            for field in model_data["fields"].values():
                field_type = field.get("type", "unknown")
                field_types[field_type] = field_types.get(field_type, 0) + 1

            field_summary = ", ".join(
                [f"{count} {ftype}" for ftype, count in field_types.items()]
            )
            summary_parts.append(
                f"Fields: {model_data.get('field_count', 0)} shown of {model_data.get('total_fields', 0)} total ({field_summary})"
            )

        # Methods summary
        if "methods" in model_data:
            method_types = {}
            for method in model_data["methods"]:
                method_type = method.get("method_type", "unknown")
                method_types[method_type] = method_types.get(method_type, 0) + 1

            method_summary = ", ".join(
                [f"{count} {mtype}" for mtype, count in method_types.items()]
            )
            summary_parts.append(
                f"Methods: {model_data.get('method_count', 0)} shown of {model_data.get('total_methods', 0)} total ({method_summary})"
            )

        return "\n".join(summary_parts)
