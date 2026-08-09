# -*- coding: utf-8 -*-
# =============================================================================
# FILE: odoo-modules/nettrades_gpu_admin/models/gpu_pricing.py
# =============================================================================
# PURPOSE:
#   GPU Pricing model - manages dynamic pricing for GPU nodes.
#   Tracks base price, current price, demand factor, and price history.
#
# UPDATES (2026-08-10):
#   - New model for dynamic pricing
# =============================================================================

from odoo import api, fields, models, _
from datetime import datetime, timedelta
import logging
import json

_logger = logging.getLogger(__name__)


class GpuPricing(models.Model):
    _name = 'gpu.pricing'
    _description = 'GPU Pricing'
    _rec_name = 'node_id'
    _order = 'current_price_per_hour ASC'

    # =========================================================================
    # FIELDS
    # =========================================================================

    node_id = fields.Many2one(
        'gpu.node',
        string='GPU Node',
        required=True,
        help="The GPU node this pricing applies to."
    )

    cluster_id = fields.Many2one(
        'gpu.cluster',
        string='Cluster',
        related='node_id.cluster_id',
        store=True,
        help="The cluster this node belongs to."
    )

    base_price_per_hour = fields.Float(
        string='Base Price per Hour',
        required=True,
        default=1.0,
        help="Base price per hour for this GPU node."
    )

    current_price_per_hour = fields.Float(
        string='Current Price per Hour',
        compute='_compute_current_price',
        store=True,
        help="Current price per hour (base price * demand factor * supply factor)."
    )

    demand_factor = fields.Float(
        string='Demand Factor',
        default=1.0,
        help="Multiplier based on current demand (1.0 = normal)."
    )

    supply_factor = fields.Float(
        string='Supply Factor',
        default=1.0,
        help="Multiplier based on available supply (1.0 = normal)."
    )

    price_history = fields.Text(
        string='Price History',
        help="JSON array of historical prices with timestamps."
    )

    updated_at = fields.Datetime(
        string='Updated At',
        default=fields.Datetime.now,
        help="When the pricing was last updated."
    )

    # =========================================================================
    # COMPUTED FIELDS
    # =========================================================================

    @api.depends('base_price_per_hour', 'demand_factor', 'supply_factor')
    def _compute_current_price(self):
        """Calculate the current price based on factors."""
        for record in self:
            record.current_price_per_hour = (
                record.base_price_per_hour *
                record.demand_factor *
                record.supply_factor
            )

    # =========================================================================
    # METHODS
    # =========================================================================

    def update_demand_factor(self, new_demand_factor):
        """Update the demand factor and record history."""
        self.ensure_one()
        self.demand_factor = new_demand_factor
        self._record_price_history()

    def update_supply_factor(self, new_supply_factor):
        """Update the supply factor and record history."""
        self.ensure_one()
        self.supply_factor = new_supply_factor
        self._record_price_history()

    def _record_price_history(self):
        """Record the current price in the price history."""
        self.ensure_one()
        history = []
        if self.price_history:
            try:
                history = json.loads(self.price_history)
            except json.JSONDecodeError:
                history = []

        # Keep last 100 entries
        history.append({
            'timestamp': datetime.now().isoformat(),
            'price': self.current_price_per_hour,
            'demand_factor': self.demand_factor,
            'supply_factor': self.supply_factor,
        })
        if len(history) > 100:
            history = history[-100:]

        self.price_history = json.dumps(history)
        self.updated_at = fields.Datetime.now()

    @api.model
    def get_or_create_for_node(self, node_id, base_price=1.0):
        """Get or create a pricing record for a node."""
        record = self.search([('node_id', '=', node_id)], limit=1)
        if not record:
            record = self.create({
                'node_id': node_id,
                'base_price_per_hour': base_price,
            })
        return record