import json
import logging
from typing import Any, Union

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMToolRecordRetriever(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_record_retriever", "Odoo Record Retriever")]

    def odoo_record_retriever_execute(
        self,
        model: str,
        domain: list[list[Union[str, int, bool, float, None]]] = [],  # noqa: B006
        fields: list[str] = [],  # noqa: B006
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute the Odoo Record Retriever tool

        Parameters:
            model: The Odoo model to retrieve records from
            domain: Domain to filter records (list of lists/tuples like ['field', 'op', 'value'])
            fields: List of field names to retrieve
            limit: Maximum number of records to retrieve
        """
        _logger.info(
            f"Executing Odoo Record Retriever with: model={model}, domain={domain}, fields={fields}, limit={limit}"
        )
        model_obj = self.env[model]

        # Using search_read for efficiency
        if fields:
            result = model_obj.search_read(domain=domain, fields=fields, limit=limit)
        else:
            records = model_obj.search(domain=domain, limit=limit)
            result = records.read()

        # Convert to serializable format
        return json.loads(json.dumps(result, default=str))
