# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Bridge – Usage Log Model
# =============================================================================
# FILE: odoo-modules/nettrades_bridge/models/bridge_usage_log.py
#
# PURPOSE:
#   This model tracks all bridge usage for billing and monitoring.
#   Each request routed through the bridge is logged with details about
#   the intent, source, success/failure, and response data.
#
#   This is essential for the commercial model – billing companies for
#   remote brain usage and tracking token consumption.
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class NettradesBridgeUsageLog(models.Model):
    """
    Bridge Usage Log – tracks all routed requests.

    This model stores a record for every request that passes through
    the bridge, enabling usage tracking, billing, and monitoring.
    """
    _name = 'nettrades.bridge.usage.log'
    _description = 'NETTRADES Bridge Usage Log'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # -------------------------------------------------------------------------
    # 1. Company Reference
    # -------------------------------------------------------------------------
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        help="The company that made the request."
    )

    # -------------------------------------------------------------------------
    # 2. Request Details
    # -------------------------------------------------------------------------
    intent = fields.Selection(
        [
            ('recruitment', 'Recruitment'),
            ('freelance', 'Freelance'),
            ('gpu', 'GPU Management'),
            ('vision', 'Vision'),
            ('action', 'Action'),
            ('general', 'General'),
        ],
        string='Intent',
        required=True,
        help="The intent of the request."
    )

    source = fields.Selection(
        [
            ('local', 'Local Brain'),
            ('remote', 'Remote Brain'),
            ('local_fallback', 'Local Brain (Fallback)'),
        ],
        string='Source',
        required=True,
        help="The source that processed the request."
    )

    success = fields.Boolean(
        string='Success',
        default=True,
        help="Whether the request was successful."
    )

    # -------------------------------------------------------------------------
    # 3. Data Storage
    # -------------------------------------------------------------------------
    request_data = fields.Text(
        string='Request Data',
        help="JSON string of the request data."
    )

    response_data = fields.Text(
        string='Response Data',
        help="JSON string of the response data."
    )

    error_message = fields.Text(
        string='Error Message',
        help="Error message if the request failed."
    )

    # -------------------------------------------------------------------------
    # 4. Metrics
    # -------------------------------------------------------------------------
    response_time_ms = fields.Integer(
        string='Response Time (ms)',
        help="Time taken to process the request in milliseconds."
    )

    tokens_used = fields.Integer(
        string='Tokens Used',
        help="Number of tokens consumed by the request (for billing)."
    )

    # -------------------------------------------------------------------------
    # 5. Timestamps
    # -------------------------------------------------------------------------
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the request was logged."
    )

    # -------------------------------------------------------------------------
    # 6. Helper Methods
    # -------------------------------------------------------------------------
    def action_view_details(self):
        """
        Open a form view with detailed information about this log entry.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'nettrades.bridge.usage.log',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }