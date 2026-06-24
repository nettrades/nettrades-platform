import logging
from typing import Any, Union

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMToolRecordUnlinker(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_record_unlinker", "Odoo Record Unlinker")]

    def odoo_record_unlinker_execute(
        self,
        model: str,
        domain: list[list[Union[str, int, bool, float, None]]],
        limit: int = 1,
    ) -> dict[str, Any]:
        """
        Delete records from the specified Odoo model based on the provided domain

        Parameters:
            model: The Odoo model to delete records from
            domain: Domain to identify records to delete
            limit: Maximum number of records to delete (default: 1 for safety)
        """
        _logger.info(
            f"Executing Odoo Record Unlinker with: model={model}, domain={domain}, limit={limit}"
        )

        model_obj = self.env[model]

        # Find records to delete
        records = model_obj.search(domain, limit=limit)

        if not records:
            return {"message": f"No records found matching the domain in {model}"}

        # Store record info before deletion for reporting
        record_info = [
            {"id": record.id, "display_name": record.display_name} for record in records
        ]

        # Count records to be deleted
        count = len(records)

        # Delete the records
        records.unlink()

        # Return information about the deleted records
        result = {
            "deleted_count": count,
            "deleted_records": record_info,
            "message": f"{count} record(s) deleted successfully from {model}",
        }

        return result
