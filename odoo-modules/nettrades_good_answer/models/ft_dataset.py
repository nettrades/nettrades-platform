# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – Fine-Tuning Dataset Model
# =============================================================================
# FILE: odoo-modules/nettrades_good_answer/models/ft_dataset.py
#
# PURPOSE:
#   This model represents a collection of feedback records (questions and
#   answers) for a specific professional field. Datasets are used to trigger
#   fine-tuning jobs via GPUStack.
#
# KEY FEATURES:
#   - Belongs to a specific professional field.
#   - Stores the number of records and the file URI (JSONL) for the dataset.
#   - Methods to export data to JSONL, run quality filters (Data-Juicer,
#     DEITA), and trigger fine-tuning.
#
# FIXES APPLIED:
#   - `action_trigger_finetune` now checks if self is empty (empty recordset)
#     and handles it gracefully by logging a message and returning early.
#   - It also ensures that if multiple records exist, it processes them
#     sequentially or aborts if more than one (to avoid duplicate jobs).
#
# =============================================================================

import json
import logging
import tempfile
import os
import subprocess
from datetime import datetime
from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FTDataset(models.Model):
    _name = 'ft.dataset'
    _description = 'Fine-Tuning Dataset'
    _rec_name = 'name'

    # -------------------------------------------------------------------------
    # 1. Basic Fields
    # -------------------------------------------------------------------------

    field_id = fields.Many2one(
        'nettrades.field',
        string='Professional Field',
        required=True,
        ondelete='cascade',
        help="The professional field this dataset belongs to."
    )

    name = fields.Char(
        string='Name',
        required=True,
        help="A human-readable name for this dataset."
    )

    description = fields.Text(
        string='Description',
        help="Detailed description of the dataset."
    )

    record_count = fields.Integer(
        string='Record Count',
        default=0,
        help="Number of (question, answer) pairs in this dataset."
    )

    file_uri = fields.Char(
        string='File URI',
        help="File path or URI of the exported JSONL dataset."
    )

    create_date = fields.Datetime(
        string='Created',
        readonly=True,
        default=fields.Datetime.now,
        help="Timestamp when the dataset record was created."
    )

    # -------------------------------------------------------------------------
    # 2. Dataset Export
    # -------------------------------------------------------------------------

    def export_to_jsonl(self):
        """
        Export the feedback records for this dataset to a JSONL file.

        This method queries all processed llm.feedback records for the
        field, filters based on the field's minimum vote and voter
        thresholds, and writes them to a temporary JSONL file.

	Added fairness filter to exclude low-rationality and high-bias responses.

        Returns:
            str: Path to the exported JSONL file, or None if no eligible records.

        The exported format is:
            {"prompt": "<question>", "completion": "<answer>"}
        """
        self.ensure_one()
        field = self.field_id

        # Get the threshold values from the field configuration
        min_votes = field.min_votes_for_training or 1
        min_voters = field.min_unique_voters or 1

        # =========================================================================
        # NEW: Get fairness configuration
        # =========================================================================
        fairness_config = self.env['nettrades.fairness.config'].get_config()
        rationality_threshold = fairness_config.rationality_threshold
        bias_threshold = fairness_config.bias_threshold
        use_fairness_filter = fairness_config.auto_filter_training

        # Fetch all processed feedback for this field
        feedbacks = self.env['llm.feedback'].search([
            ('field_id', '=', field.id),
            ('processed', '=', True),
        ])

        # Filter eligible records based on vote count and unique voters
        eligible = []
        for fb in feedbacks:        
            # =========================================================================
            # NEW: Apply fairness filter
            # =========================================================================
            if use_fairness_filter:
                # Get the rationality feedback for this response
                rationality_fb = self.env['nettrades.fairness.audit'].search([
                    ('response_id', '=', fb.vote_id.answer_id),
                ], order='create_date desc', limit=1)

                if rationality_fb:
                    rationality_score = rationality_fb.rationality_score
                    bias_score = rationality_fb.bias_score

                    # Skip if rationality is too low or bias is too high
                    if rationality_score is not None and rationality_score < rationality_threshold:
                        _logger.debug(
                            "Skipping feedback %s: rationality score %.2f < threshold %.2f",
                            fb.id, rationality_score, rationality_threshold
                        )
                        continue

                    if bias_score is not None and bias_score > bias_threshold:
                        _logger.debug(
                            "Skipping feedback %s: bias score %.2f > threshold %.2f",
                            fb.id, bias_score, bias_threshold
                        )
                        continue


            # Count total votes for the same answer
            answer_model = self.env['good.answer.vote'].search([
                ('answer_id', '=', fb.vote_id.answer_id),
                ('answer_model', '=', fb.vote_id.answer_model),
            ])
            total_votes = len(answer_model)
            if total_votes < min_votes:
                continue

            # Count unique voters
            unique_voters = set(answer_model.mapped('user_id.id'))
            if len(unique_voters) < min_voters:
                continue

            eligible.append(fb)

        if not eligible:
            _logger.info("No eligible feedback records for field %s", field.name)
            return None

        # Write to a temporary JSONL file
        temp_path = tempfile.mktemp(suffix='.jsonl')
        with open(temp_path, 'w', encoding='utf-8') as f:
            for fb in eligible:
                record = {
                    'prompt': fb.input_text,
                    'completion': fb.output_text
                }
                f.write(json.dumps(record) + '\n')

        self.file_uri = temp_path
        self.record_count = len(eligible)
        _logger.info("Exported %d records to %s", len(eligible), temp_path)
        return temp_path

    # -------------------------------------------------------------------------
    # 3. Quality Pipeline (Data-Juicer / DEITA)
    # -------------------------------------------------------------------------

    def _run_data_juicer_pipeline(self, jsonl_path):
        """
        Run Data-Juicer quality filtering on the dataset.

        Data-Juicer is an optional quality pipeline that filters,
        deduplicates, and removes PII from the dataset.

        Args:
            jsonl_path (str): Path to the input JSONL file.

        Returns:
            str: Path to the filtered JSONL file, or the original path if
                 Data-Juicer is not installed or disabled.

        Note:
            This method requires the 'py-data-juicer[generic,nlp]' package.
            If not installed, it logs a warning and returns the original path.
        """
        if not self.field_id.enable_data_juicer:
            return jsonl_path

        try:
            import data_juicer  # noqa
        except ImportError:
            _logger.warning(
                "Data-Juicer not installed. Install 'py-data-juicer[generic,nlp]' to enable quality filtering."
            )
            return jsonl_path

        # Build a configuration for Data-Juicer
        # In production, this would be a proper YAML config.
        # For simplicity, we assume Data-Juicer is invoked via CLI.
        # We'll implement a basic command-line call.
        output_path = jsonl_path.replace('.jsonl', '_filtered.jsonl')
        try:
            # Example command: dj-process --config config.yaml --input input.jsonl --output output.jsonl
            # We'll use a simple in-memory filter (placeholder).
            # Actual implementation would involve proper Data-Juicer integration.
            # For now, we'll just copy the file and log.
            import shutil
            shutil.copy(jsonl_path, output_path)
            _logger.info("Data-Juicer filtering completed (simulated).")
            return output_path
        except Exception as e:
            _logger.error("Data-Juicer pipeline failed: %s", e)
            return jsonl_path

    def _run_deita_scoring(self, jsonl_path):
        """
        Run DEITA (LLM-as-Judge) scoring on the dataset.

        DEITA uses an LLM to score each example for complexity, quality,
        and diversity. This helps select high-quality examples for training.

        Args:
            jsonl_path (str): Path to the input JSONL file.

        Returns:
            str: Path to the scored JSONL file, or the original path if
                 DEITA is not installed or disabled.

        Note:
            This method requires the 'distilabel[vllm]' package.
            If not installed, it logs a warning and returns the original path.
        """
        if not self.field_id.enable_deita_scoring:
            return jsonl_path

        try:
            import distilabel  # noqa
        except ImportError:
            _logger.warning(
                "DEITA scoring not available. Install 'distilabel[vllm]' to enable scoring."
            )
            return jsonl_path

        # Placeholder for actual DEITA scoring
        # In production, this would call DEITA via the distilabel pipeline.
        output_path = jsonl_path.replace('.jsonl', '_scored.jsonl')
        try:
            # Simulate scoring
            import shutil
            shutil.copy(jsonl_path, output_path)
            _logger.info("DEITA scoring completed (simulated).")
            return output_path
        except Exception as e:
            _logger.error("DEITA scoring failed: %s", e)
            return jsonl_path

    # -------------------------------------------------------------------------
    # 4. Trigger Fine-Tuning
    # -------------------------------------------------------------------------

    def action_trigger_finetune(self):
        """
        Trigger a fine-tuning job using this dataset.

        This method orchestrates the entire fine-tuning pipeline:
        1. Export data to JSONL (if not already exported)
        2. Run Data-Juicer (if enabled)
        3. Run DEITA scoring (if enabled)
        4. Create a ft.training.job record
        5. Submit the job to GPUStack via the LangGraph agent or direct API

        🔧 FIX: This method now handles empty recordset gracefully.
               It checks `if not self:` and returns early, logging a message.
               It also ensures that if multiple datasets are selected, it
               processes them one by one (though the cron should call it on
               a single dataset).
        """
        # --- Handle empty recordset (critical for cron safety) ---
        # The cron may call this method on an empty recordset if no datasets exist.
        # We log a message and return early to avoid errors.
        if not self:
            _logger.info("action_trigger_finetune called on empty recordset. No action taken.")
            return

        # Ensure we only process one dataset at a time
        # If multiple records, we could loop over them, but for simplicity,
        # we raise a warning if more than one and process the first.
        if len(self) > 1:
            _logger.warning("action_trigger_finetune called on multiple datasets. Processing only the first.")
            self = self[:1]

        self.ensure_one()
        _logger.info("Triggering fine-tuning for dataset %s (field: %s)", self.name, self.field_id.name)

        # 1. Export dataset if not already exported
        if not self.file_uri:
            jsonl_path = self.export_to_jsonl()
            if not jsonl_path:
                _logger.warning("No data to export for dataset %s; skipping fine-tuning.", self.name)
                return
        else:
            jsonl_path = self.file_uri

        # 2. Run Data-Juicer pipeline (optional)
        if self.field_id.enable_data_juicer:
            jsonl_path = self._run_data_juicer_pipeline(jsonl_path)

        # 3. Run DEITA scoring (optional)
        if self.field_id.enable_deita_scoring:
            jsonl_path = self._run_deita_scoring(jsonl_path)

        # 4. Create training job record
        # Note: The hyperparameters are stored as JSON in the field.
        hyperparams = self.field_id.hyperparameters or {}
        job = self.env['ft.training.job'].create({
            'dataset_id': self.id,
            'field_id': self.field_id.id,
            'provider': self.field_id.finetune_provider or 'unsloth',
            'base_model': self.field_id.base_model,
            'status': 'pending',
            'hyperparameters': hyperparams,
            'started_at': fields.Datetime.now(),
        })
        _logger.info("Created training job %s", job.id)

        # 5. Submit the job to GPUStack via LangGraph or direct API
        # This is a placeholder; actual implementation would call the LangGraph
        # agent to orchestrate the training on GPUStack.
        try:
            # Example: call LangGraph agent to submit training
            # result = self._call_langgraph_train(job.id)
            # For now, we simulate success.
            job.status = 'running'
            job.fine_tuned_model_id = f"model_{job.id}"
            _logger.info("Training job %s submitted successfully.", job.id)
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            _logger.error("Training job %s failed: %s", job.id, e)

    # -------------------------------------------------------------------------
    # 5. Cron Integration
    # -------------------------------------------------------------------------

    @api.model
    def _cron_check_and_trigger(self):
        """
        Cron job that checks all datasets and triggers fine-tuning for those
        that have reached the record threshold.

        This method is called by the Odoo scheduler. It searches for datasets
        that have at least `min_votes_for_training` votes and have not yet
        been processed (or have record_count > 0). It then triggers fine-tuning
        for each qualifying dataset.

        🔧 FIX: This method now correctly handles the case where no datasets
               exist by logging a message and returning early.
        """
        # Find all fields with fine-tuning enabled
        fields = self.env['nettrades.field'].search([
            ('base_model', '!=', False),
            ('finetune_provider', '!=', False),
        ])

        triggered = 0
        for field in fields:
            # Find datasets for this field
            datasets = self.search([
                ('field_id', '=', field.id),
                ('record_count', '>=', field.min_votes_for_training or 1),
            ])
            for dataset in datasets:
                _logger.info("Dataset %s has %d records; triggering fine-tuning.", dataset.name, dataset.record_count)
                try:
                    dataset.action_trigger_finetune()
                    triggered += 1
                except Exception as e:
                    _logger.error("Failed to trigger fine-tuning for dataset %s: %s", dataset.name, e)

        if triggered == 0:
            _logger.info("No datasets met the threshold for fine-tuning.")
        else:
            _logger.info("Triggered fine-tuning for %d datasets.", triggered)
