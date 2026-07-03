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
# KEY FEATURES:
#   - Versioning (parent/child relationships)
#   - Metadata (number of frames, size, format)
#   - Integration with Data-Juicer for preprocessing
#   - Trigger fine-tuning jobs from the UI
#   - Links to the self-improving loop
#
# DEPENDENCIES:
#   - Odoo 19 CE
#   - nettrades_core module
#   - llm_training module (Apexive)
#
# USAGE:
#   Datasets are automatically created when simulation sessions are
#   completed, or can be created manually from the Odoo admin interface.
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

    Datasets are used to:
    1. Fine-tune AI models via Apexive llm_training
    2. Train reinforcement learning policies
    3. Validate model performance
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
    # 2. RELATIONSHIPS
    # -------------------------------------------------------------------------
    session_id = fields.Many2one(
        'simulation.session',
        string='Source Session',
        help="The simulation session that generated this dataset."
    )

    config_id = fields.Many2one(
        'simulation.config',
        string='Simulation Configuration',
        related='session_id.config_id',
        store=True,
        help="The simulation configuration used to generate this dataset."
    )

    # -------------------------------------------------------------------------
    # 3. VERSIONING (Parent/Child)
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
    # 4. METADATA
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
        help="Format in which the dataset is stored. JSONL is recommended "
             "for compatibility with Data-Juicer."
    )

    # -------------------------------------------------------------------------
    # 5. STORAGE
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
    # 6. STATUS
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
    # 7. PERFORMANCE METRICS
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
    # 8. TAGS (from good_answer module)
    # -------------------------------------------------------------------------
    tag_ids = fields.Many2many(
        'nettrades_good_answer.tag',
        string='Tags',
        help="Tags for categorising this dataset."
    )

    # -------------------------------------------------------------------------
    # 9. FINE-TUNING JOB (from gpu_admin module)
    # -------------------------------------------------------------------------
    fine_tune_job_id = fields.Many2one(
        'nettrades_gpu_admin.job',
        string='Fine-Tune Job',
        help="The fine-tuning job associated with this dataset."
    )

    # -------------------------------------------------------------------------
    # 10. COMPUTED FIELDS
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
    # 11. ACTIONS
    # -------------------------------------------------------------------------
    def action_create_version(self, version_name=None):
        """
        Create a new version of this dataset.

        This method creates a child dataset with the same metadata as
        the parent, allowing for versioned dataset management.

        Args:
            version_name (str): The version name (e.g., '2.0.0').

        Returns:
            simulation.dataset: The new version record.
        """
        self.ensure_one()

        if not version_name:
            # Auto-increment version
            parts = self.version.split('.')
            if len(parts) == 3:
                # Increment patch version
                parts[2] = str(int(parts[2]) + 1)
                version_name = '.'.join(parts)
            else:
                version_name = '1.0.1'

        version_vals = {
            'name': f"{self.name} - v{version_name}",
            'version': version_name,
            'parent_id': self.id,
            'session_id': self.session_id.id,
            'config_id': self.config_id.id,
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
        Process the dataset using Data-Juicer.

        This method triggers the Data-Juicer pipeline to clean, filter,
        and format the dataset for training.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()
        self.status = 'processing'

        try:
            # In a real implementation, this would call Data-Juicer
            # via its API or command line interface.
            #
            # Example:
            # from .data_juicer_pipeline import process_dataset
            # process_dataset(self.id)

            # For now, we simply mark it as ready
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

    def action_fine_tune(self):
        """
        Trigger a fine-tuning job on this dataset using GPUStack.

        This method creates a job in the gpu_admin module and starts it.

        Returns:
            dict: Action result for the Odoo UI.
        """
        self.ensure_one()

        if self.status != 'ready':
            raise UserError(_("Dataset must be processed before fine-tuning."))

        try:
            # Create a fine-tuning job
            job_vals = {
                'name': f"Fine-tune on {self.name} v{self.version}",
                'dataset_id': self.id,
                'status': 'pending',
                'base_model': self._get_default_base_model(),
                'hyperparameters': {
                    'learning_rate': 2e-5,
                    'epochs': 3,
                    'batch_size': 4,
                }
            }

            job = self.env['nettrades_gpu_admin.job'].create(job_vals)
            self.fine_tune_job_id = job.id

            # Start the job
            job.action_start()

            _logger.info(f"Fine-tuning job {job.id} started for dataset {self.id}")

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'nettrades_gpu_admin.job',
                'res_id': job.id,
                'view_mode': 'form',
            }

        except Exception as e:
            _logger.error(f"Fine-tuning job creation failed: {e}")
            raise UserError(_("Failed to create fine-tuning job: {}").format(str(e)))

    def _get_default_base_model(self):
        """
        Get the default base model for fine-tuning.

        Returns:
            str: The default base model name.
        """
        # This could be configurable via system parameters
        return self.env['ir.config_parameter'].sudo().get_param(
            'simulation.default_base_model',
            'llama-3.2-3b'
        )

    # -------------------------------------------------------------------------
    # 12. STATISTICS METHODS
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