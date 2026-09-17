# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Data Collection - Dataset Model
# =============================================================================
# FILE: odoo-modules/nettrades_data_collection/models/data_dataset.py
#
# PURPOSE:
#   This model manages datasets generated from simulation sessions.
#   Datasets are versioned and can be used to fine-tune AI models
#   via the Apexive llm_training module and GPUStack.
#
# UPDATES (2026-09-17):
#   - Removed `session_id` (Many2one to simulation.session) and
#     `config_id` (related through session_id). Neither simulation.session
#     nor simulation.config is defined in this codebase, so the fields
#     caused an AssertionError at install:
#       Field simulation.dataset.session_id with unknown comodel_name
#       'simulation.session'
#   - Removed the same references from action_create_version().
#   - If session/config models are reintroduced later, restore these fields
#     and the corresponding logic in action_create_version().
#
# KEY FEATURES:
#   - Versioning (parent/child relationships)
#   - Metadata (number of frames, size, format)
#   - Trigger fine-tuning jobs from the UI
#   - Links to the self-improving loop
#
# =============================================================================

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SimulationDataset(models.Model):
    """
    Simulation Dataset Model.

    This model stores datasets generated from simulation sessions.
    Each dataset can be versioned (parent/child relationships) and
    contains metadata about the data it contains.
    """
    _name = 'simulation.dataset'
    _description = 'Simulation Dataset'
    _order = 'create_date DESC'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # -------------------------------------------------------------------------
    # 1. BASIC FIELDS
    # -------------------------------------------------------------------------
    name = fields.Char(
        string='Name',
        required=True,
        help="A descriptive name for this dataset."
    )

    version = fields.Char(
        string='Version',
        default='1.0.0',
        help="Semantic version for this dataset (e.g., 1.0.0, 1.1.0)."
    )

    description = fields.Text(
        string='Description',
        help="Detailed description of the dataset contents."
    )

    # -------------------------------------------------------------------------
    # 2. VERSIONING (Parent/Child)
    # -------------------------------------------------------------------------
    parent_id = fields.Many2one(
        'simulation.dataset',
        string='Parent Dataset',
        help="The parent dataset this version was derived from."
    )

    child_ids = fields.One2many(
        'simulation.dataset',
        'parent_id',
        string='Children',
        help="Child datasets derived from this dataset."
    )

    # -------------------------------------------------------------------------
    # 3. METADATA
    # -------------------------------------------------------------------------
    num_episodes = fields.Integer(
        string='Number of Episodes',
        help="Total number of episodes in this dataset."
    )

    num_frames = fields.Integer(
        string='Number of Frames',
        help="Total number of frames/samples in this dataset."
    )

    total_size_gb = fields.Float(
        string='Total Size (GB)',
        help="Total storage size of the dataset in gigabytes."
    )

    data_format = fields.Selection(
        [
            ('jsonl', 'JSONL'),
            ('parquet', 'Parquet'),
            ('coco', 'COCO'),
            ('kitti', 'KITTI'),
        ],
        string='Data Format',
        default='jsonl',
        help="Format in which the dataset is stored."
    )

    # -------------------------------------------------------------------------
    # 4. STORAGE
    # -------------------------------------------------------------------------
    storage_path = fields.Char(
        string='Storage Path',
        help="Local or network path where the dataset files are stored."
    )

    s3_bucket = fields.Char(
        string='S3 Bucket',
        help="If using cloud storage, the S3 bucket name."
    )

    s3_key = fields.Char(
        string='S3 Key',
        help="S3 object key prefix for the dataset."
    )

    # -------------------------------------------------------------------------
    # 5. STATUS
    # -------------------------------------------------------------------------
    status = fields.Selection(
        [
            ('collecting', 'Collecting'),
            ('processing', 'Processing'),
            ('ready', 'Ready'),
            ('error', 'Error'),
        ],
        string='Status',
        default='collecting',
        help="Current status of the dataset."
    )

    # -------------------------------------------------------------------------
    # 6. PERFORMANCE METRICS
    # -------------------------------------------------------------------------
    avg_fps = fields.Float(
        string='Average FPS',
        help="Average frames per second during collection."
    )

    avg_sensor_freq = fields.Float(
        string='Average Sensor Frequency',
        help="Average sensor reading frequency."
    )

    total_training_time = fields.Float(
        string='Total Training Time (s)',
        help="Total time spent training on this dataset."
    )

    # -------------------------------------------------------------------------
    # 7. COMPUTED FIELDS
    # -------------------------------------------------------------------------
    has_children = fields.Boolean(
        compute='_compute_has_children',
        store=False,
        help="Whether this dataset has child versions."
    )

    @api.depends('child_ids')
    def _compute_has_children(self):
        """Compute whether the dataset has child versions."""
        for record in self:
            record.has_children = bool(record.child_ids)

    # -------------------------------------------------------------------------
    # 8. ACTIONS
    # -------------------------------------------------------------------------
    def action_create_version(self, version_name=None):
        """
        Create a new version of this dataset.

        Args:
            version_name (str): The version name (e.g., '2.0.0').

        Returns:
            dict: An act_window action to open the new version.
        """
        self.ensure_one()

        if not version_name:
            parts = self.version.split('.')
            if len(parts) == 3:
                parts[2] = str(int(parts[2]) + 1)
                version_name = '.'.join(parts)
            else:
                version_name = '1.0.1'

        version_vals = {
            'name': f"{self.name} - v{version_name}",
            'version': version_name,
            'parent_id': self.id,
            'num_episodes': self.num_episodes,
            'num_frames': self.num_frames,
            'data_format': self.data_format,
            'storage_path': self.storage_path,
            's3_bucket': self.s3_bucket,
            's3_key': self.s3_key,
            'status': 'collecting',
        }

        new_version = self.create(version_vals)

        _logger.info(f"Created new version {version_name} of dataset {self.name}")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'simulation.dataset',
            'res_id': new_version.id,
            'view_mode': 'form',
        }

    def action_process(self):
        """
        Process the dataset (mark as ready).

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()
        self.status = 'processing'

        try:
            self.status = 'ready'
            _logger.info(f"Dataset {self.id} processed successfully")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Dataset Processed'),
                    'message': _('The dataset has been processed and is ready for training.'),
                    'type': 'success',
                    'sticky': False,
                }
            }

        except Exception as e:
            self.status = 'error'
            _logger.error(f"Dataset processing failed: {e}")
            raise UserError(_("Dataset processing failed: {}").format(str(e)))

    # -------------------------------------------------------------------------
    # 9. STATISTICS METHODS
    # -------------------------------------------------------------------------
    def action_view_children(self):
        """
        Open a list view of child datasets.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'simulation.dataset',
            'view_mode': 'tree,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id},
        }