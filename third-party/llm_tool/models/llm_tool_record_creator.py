import logging
from typing import Any

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMToolRecordCreator(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_record_creator", "Odoo Record Creator")]

    def odoo_record_creator_execute(
        self,
        model: str,
        fields: dict[str, Any] = None,
        records: list[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create one or multiple new records in the specified Odoo model

        Parameters:
            model: The Odoo model to create record(s) in
            fields: Dictionary of field values for a single record creation
            records: List of dictionaries for multiple records creation
        """
        if fields is None and records is None:
            raise ValueError("Either 'fields' or 'records' must be provided")

        if fields is not None and records is not None:
            raise ValueError("Only one of 'fields' or 'records' should be provided")

        _logger.info(
            f"Executing Odoo Record Creator with: model={model}, "
            f"fields={fields}, records={records}"
        )

        model_obj = self.env[model]

        if fields is not None:
            # Handle single record creation
            new_record = model_obj.create(fields)
            result = {
                "id": new_record.id,
                "display_name": new_record.display_name,
                "message": f"Record created successfully in {model}",
            }
        else:
            # Handle multiple records creation
            new_records = model_obj.create(records)
            records_data = [
                {
                    "id": record.id,
                    "display_name": record.display_name,
                }
                for record in new_records
            ]

            result = {
                "records": records_data,
                "count": len(records_data),
                "message": f"{len(records_data)} records created successfully in {model}",
            }

        return result
