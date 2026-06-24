import logging
from typing import Any, Union

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMToolRecordUpdater(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_record_updater", "Odoo Record Updater")]

    def odoo_record_updater_execute(
        self,
        model: str,
        domain: list[list[Union[str, int, bool, float, None]]],
        values: dict[str, Any],
        limit: int = 1,
    ) -> dict[str, Any]:
        """
        Update existing records in the specified Odoo model that match the given domain

        Parameters:
            model: The Odoo model to update records in
            domain: Domain to identify records to update
            values: Dictionary of field values to update
            limit: Maximum number of records to update (default: 1 for safety)
        """
        _logger.info(
            f"Executing Odoo Record Updater with: model={model}, domain={domain}, values={values}, limit={limit}"
        )

        model_obj = self.env[model]

        # Find records to update
        records = model_obj.search(domain, limit=limit)

        if not records:
            return {"error": "No records found matching the domain"}

        # Update the records
        records.write(values)

        # Return information about updated records
        result = {
            "count": len(records),
            "ids": records.ids,
            "message": f"Successfully updated {len(records)} record(s) in {model}",
        }

        return result
