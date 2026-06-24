# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection – Data Metric Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_metric.py
#
# PURPOSE:
#   This model stores performance metrics for the self-improving system.
#   Metrics are collected from various sources and used for trigger detection.
#
#   Metrics include:
#     - Quality scores (average rationality, bias)
#     - Success rates (task completion, user satisfaction)
#     - Performance (latency, throughput)
#     - GPU utilisation
#
# =============================================================================

from odoo import fields, models, api, _
import logging

_logger = logging.getLogger(__name__)


class DataMetric(models.Model):
    """
    Data Metric – performance metrics for the self-improving system.

    Each metric record stores a single measurement at a point in time.
    """
    _name = 'data.metric'
    _description = 'Data Metric'
    _order = 'create_date DESC'
    _rec_name = 'id'

    # =========================================================================
    # 1. Basic Fields
    # =========================================================================
    metric_type = fields.Selection(
        [
            ('quality_avg', 'Average Quality Score'),
            ('rationality_avg', 'Average Rationality Score'),
            ('bias_avg', 'Average Bias Score'),
            ('success_rate', 'Task Success Rate'),
            ('latency_p50', 'Latency P50 (ms)'),
            ('latency_p95', 'Latency P95 (ms)'),
            ('latency_p99', 'Latency P99 (ms)'),
            ('gpu_utilisation', 'GPU Utilisation (%)'),
            ('episode_count', 'Episode Count'),
            ('flag_count', 'Flag Count'),
            ('cycle_count', 'Cycle Count'),
        ],
        string='Metric Type',
        required=True,
        help="The type of metric being measured."
    )

    metric_value = fields.Float(
        string='Metric Value',
        required=True,
        help="The numeric value of the metric."
    )

    # =========================================================================
    # 2. Context
    # =========================================================================
    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        help="The field this metric applies to. If empty, applies globally."
    )

    metadata = fields.Json(
        string='Metadata',
        help="Additional context for the metric (e.g., time window, sample size)."
    )

    # =========================================================================
    # 3. Timestamps
    # =========================================================================
    create_date = fields.Datetime(
        string='Created At',
        default=fields.Datetime.now,
        readonly=True,
        help="Timestamp when the metric was recorded."
    )

    # =========================================================================
    # 4. Helper Methods
    # =========================================================================
    @api.model
    def record_metric(self, metric_type, value, field_id=None, metadata=None):
        """
        Record a new metric.

        Args:
            metric_type (str): The metric type.
            value (float): The metric value.
            field_id (int, optional): The field ID.
            metadata (dict, optional): Additional metadata.

        Returns:
            DataMetric: The created metric record.
        """
        return self.create({
            'metric_type': metric_type,
            'metric_value': value,
            'field_id': field_id,
            'metadata': metadata or {},
        })