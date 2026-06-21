import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Generate dotted codes for llm.assistant records based on their category hierarchy.
    The code format will be: parent_category.code.subcategory.code.subcategory.code...
    """
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})

        # Get all assistants that don't have a code yet
        assistants = env["llm.assistant"].search(
            ["|", ("code", "=", False), ("code", "=", "")]
        )

        _logger.info(f"Found {len(assistants)} assistants without codes")

        for assistant in assistants:
            # Skip if assistant doesn't have a category
            if not assistant.category_id:
                _logger.warning(
                    f"Assistant '{assistant.name}' (ID: {assistant.id}) has no category"
                )
                continue

            # Build the dotted code from category hierarchy
            code_parts = []
            current_category = assistant.category_id

            # Walk up the category tree collecting codes
            while current_category:
                if current_category.code:
                    code_parts.insert(0, current_category.code)
                else:
                    # If category doesn't have a code, use a sanitized version of its name
                    sanitized_name = current_category.name.lower()
                    sanitized_name = sanitized_name.replace(" ", "_")
                    sanitized_name = "".join(
                        c for c in sanitized_name if c.isalnum() or c == "_"
                    )
                    code_parts.insert(0, sanitized_name)

                current_category = current_category.parent_id

            # Generate the dotted code
            if code_parts:
                new_code = ".".join(code_parts)

                # Check if this code already exists
                existing = env["llm.assistant"].search(
                    [("code", "=", new_code), ("id", "!=", assistant.id)]
                )

                if existing:
                    # Add a suffix to make it unique
                    suffix = 1
                    while existing:
                        test_code = f"{new_code}_{suffix}"
                        existing = env["llm.assistant"].search(
                            [("code", "=", test_code), ("id", "!=", assistant.id)]
                        )
                        if not existing:
                            new_code = test_code
                        suffix += 1

                assistant.code = new_code
                _logger.info(
                    f"Set code '{new_code}' for assistant '{assistant.name}' (ID: {assistant.id})"
                )
            else:
                _logger.warning(
                    f"Could not generate code for assistant '{assistant.name}' (ID: {assistant.id})"
                )

        # Commit the changes
        cr.commit()

        _logger.info(
            "Migration completed: Generated dotted codes for assistants based on category hierarchy"
        )
