# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES Good Answer – Fine-Tuning Dataset model
# =============================================================================
# Represents a collection of (question, answer) pairs for a single
# professional field.  When enough data has accumulated (≥100 records by
# default), action_trigger_finetune() exports the data to JSONL, runs
# optional quality filters (Data-Juicer / DEITA), records which
# professionals contributed expert answers (for indirect reputation),
# creates a training job record, and calls LangGraph to start the GPUStack
# training job.
#
# ADMINISTRATOR CONFIGURATION
#   All quality and threshold settings are configured per field in the
#   Professional Field form (nettrades.field).  See the "Data-Juicer
#   Quality", "LLM-as-Judge (DEITA)", and "Advanced Training" tabs.
#   Features are OFF by default and must be explicitly enabled.
#
# DEPENDENCIES (optional, only if quality features are enabled)
#   pip install 'py-data-juicer[generic,nlp]'     # Data-Juicer
#   pip install distilabel[vllm]                   # DEITA / LLM-as-Judge
#
# FUTURE ENHANCEMENTS
#   - Benchmark evaluation (enable_benchmark_evaluation field) –
#     implement NeMo Evaluator or a custom benchmark runner that
#     compares new model against a held-out dataset.
#   - GRPO reinforcement learning (enable_grpo_training) – when
#     enough preference pairs exist, trigger Unsloth GRPO training.
#   - A/B shadow testing (enable_ab_testing) – automatic promotion
#     of fine-tuned models if Good Answer rates improve.
# =============================================================================
import json, logging, os, tempfile, requests
from odoo import fields, models, api, _

_logger = logging.getLogger(__name__)


class FTDataset(models.Model):
    _name = 'ft.dataset'
    _description = 'Fine-tuning Dataset'

    field_id = fields.Many2one(
        'nettrades.field', required=True,
        help="The professional field this dataset belongs to."
    )
    name = fields.Char(required=True)
    description = fields.Text()
    file_uri = fields.Char(
        help="Path to the exported JSONL file on the server filesystem."
    )
    record_count = fields.Integer(
        default=0,
        help="Number of (question, answer) pairs currently in the dataset."
    )
    created_at = fields.Datetime(default=fields.Datetime.now)

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    def export_to_jsonl(self):
        """
        Write all processed feedback for this field to a temporary JSONL file.
        Feedback records that do not meet the field's minimum vote and
        unique-voter thresholds are silently excluded.
        Each line is a JSON object with 'prompt' and 'completion'.
        """
        field = self.field_id
        min_votes = field.min_votes_for_training or 1
        min_voters = field.min_unique_voters or 1

        feedbacks = self.env['llm.feedback'].search([
            ('field_id', '=', field.id),
            ('processed', '=', True),
        ])

        # Apply per-record vote thresholds (see Advanced Training tab)
        eligible = []
        for fb in feedbacks:
            vote = fb.vote_id
            # Count total votes on the same answer
            total_votes = self.env['good.answer.vote'].search_count([
                ('answer_id', '=', vote.answer_id),
                ('answer_model', '=', vote.answer_model),
            ])
            if total_votes < min_votes:
                continue
            # Count distinct voters
            distinct_voters = len(set(
                self.env['good.answer.vote'].search([
                    ('answer_id', '=', vote.answer_id),
                    ('answer_model', '=', vote.answer_model),
                ]).mapped('user_id.id')
            ))
            if distinct_voters < min_voters:
                continue
            eligible.append(fb)

        if not eligible:
            _logger.info("No eligible feedback records for dataset '%s' after threshold filters.", self.name)
            return None

        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False)
        for fb in eligible:
            if fb.input_text or fb.output_text:
                tmp.write(json.dumps({
                    "prompt": fb.input_text or '',
                    "completion": fb.output_text or '',
                }) + "\n")
        tmp.close()
        return tmp.name

    # ------------------------------------------------------------------
    # Inference endpoint resolution for quality pipelines
    # ------------------------------------------------------------------
    def _get_inference_endpoint(self, field):
        """
        Resolve the LLM endpoint for quality scoring based on the field's
        configuration.  Returns (api_base, api_key) for an OpenAI-compatible
        API call.
        """
        endpoint_type = field.data_juicer_endpoint_type or 'field_llm'

        if endpoint_type == 'gpustack':
            config = self.env['ir.config_parameter'].sudo()
            return (
                config.get_param('gpustack_server_url', 'http://gpustack:80') + '/v1-openai',
                config.get_param('gpustack_api_key', 'dummy'),
            )
        elif endpoint_type == 'local_vllm':
            config = self.env['ir.config_parameter'].sudo()
            return (
                config.get_param('vllm_base_url', 'http://vllm:8000/v1'),
                config.get_param('vllm_api_key', 'dummy'),
            )
        else:
            provider = field.default_llm_provider_id
            if provider:
                return (provider.api_base, provider.api_key or 'dummy')
            config = self.env['ir.config_parameter'].sudo()
            return (
                config.get_param('gpustack_server_url', 'http://gpustack:80') + '/v1-openai',
                'dummy',
            )

    # ------------------------------------------------------------------
    # Data-Juicer quality pipeline
    # ------------------------------------------------------------------
    def _run_data_juicer_pipeline(self, jsonl_path):
        """
        Run Data-Juicer quality filtering on the exported dataset.

        Returns (filtered_path, stats_dict).  If Data-Juicer is not
        enabled or not installed, returns the original path with a
        status message.

        If Data-Juicer rejects too many samples (exceeding the configured
        max_rejection_rate), the field's Data-Juicer is auto-disabled.
        """
        field = self.field_id

        if not field.enable_data_juicer:
            return jsonl_path, {'status': 'disabled'}

        _logger.info("Running Data-Juicer quality pipeline for field '%s'...", field.name)

        api_base, api_key = self._get_inference_endpoint(field)

        # Build Data-Juicer configuration
        operators = []
        if field.data_juicer_enable_dedup:
            operators.append({'deduplicator': {}})
        if field.data_juicer_enable_pii:
            operators.append({'remove_non_string_columns_filter': {}})
        operators.append({
            'llm_quality_score_filter': {
                'api_model': 'gpt-4o-mini',
                'api_endpoint': api_base,
                'api_key': api_key,
                'min_score': field.data_juicer_min_quality_score,
                'text_key': 'prompt',
            }
        })

        config = {
            'project_name': f'nettrades_field_{field.id}',
            'dataset_path': jsonl_path,
            'export_path': f'/tmp/dj_filtered_{self.id}.jsonl',
            'process': operators,
        }

        import yaml, subprocess
        config_path = os.path.join(tempfile.gettempdir(), f'dj_config_{self.id}.yaml')
        filtered_path = os.path.join(tempfile.gettempdir(), f'dj_filtered_{self.id}.jsonl')

        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        try:
            result = subprocess.run(
                ['dj-process', '--config', config_path],
                capture_output=True, text=True, timeout=1800   # 30-minute timeout
            )
            if result.returncode != 0:
                _logger.error("Data-Juicer failed: %s", result.stderr)
                return jsonl_path, {'status': 'error', 'error': result.stderr[:500]}
        except FileNotFoundError:
            _logger.error(
                "Data-Juicer (dj-process) not found.  "
                "Install: pip install 'py-data-juicer[generic,nlp]'"
            )
            return jsonl_path, {'status': 'error', 'error': 'Data-Juicer not installed'}
        except subprocess.TimeoutExpired:
            _logger.error("Data-Juicer timed out (30 min).")
            return jsonl_path, {'status': 'error', 'error': 'Timeout'}

        # Calculate rejection statistics
        try:
            with open(jsonl_path, 'r') as f:
                original_count = sum(1 for _ in f)
            with open(filtered_path, 'r') as f:
                filtered_count = sum(1 for _ in f)
        except FileNotFoundError:
            return jsonl_path, {'status': 'error', 'error': 'Output file not found'}

        rejection_rate = 1.0 - (filtered_count / max(original_count, 1))

        stats = {
            'original_count': original_count,
            'filtered_count': filtered_count,
            'rejection_rate': round(rejection_rate, 3),
            'status': 'completed',
        }

        # Auto-disable if rejection rate too high
        if (field.data_juicer_auto_disable
                and field.data_juicer_max_rejection_rate > 0
                and rejection_rate > field.data_juicer_max_rejection_rate):
            field.write({
                'enable_data_juicer': False,
                'data_juicer_status': 'auto_disabled',
            })
            _logger.warning(
                "Data-Juicer auto-disabled for field '%s': rejection rate %.1f%% > max %.1f%%.",
                field.name, rejection_rate * 100, field.data_juicer_max_rejection_rate * 100
            )
            field.activity_schedule(
                'mail.mail_activity_data_warning',
                summary=f"Data-Juicer auto-disabled for {field.name}",
                note=(
                    f"Rejection rate: {rejection_rate*100:.1f}% "
                    f"(maximum: {field.data_juicer_max_rejection_rate*100:.1f}%).\n"
                    f"Original samples: {original_count}\n"
                    f"Surviving samples: {filtered_count}\n\n"
                    f"Review the Data-Juicer settings or check the training data "
                    f"quality.  Re-enable Data-Juicer when ready."
                ),
            )

        field.write({
            'data_juicer_last_run': fields.Datetime.now(),
            'data_juicer_last_stats': stats,
        })

        _logger.info(
            "Data-Juicer complete for field '%s': %d→%d samples (%.1f%% rejected).",
            field.name, original_count, filtered_count, rejection_rate * 100
        )

        return filtered_path, stats

    # ------------------------------------------------------------------
    # DEITA / LLM-as-Judge scoring
    # ------------------------------------------------------------------
    def _run_deita_scoring(self, jsonl_path):
        """
        Run DEITA (LLM-as-Judge) quality scoring via distilabel.

        Returns (filtered_path, stats_dict).  If DEITA is not enabled
        or not installed, returns the original path with a status message.
        """
        field = self.field_id

        if not field.enable_deita_scoring:
            return jsonl_path, {'status': 'disabled'}

        _logger.info("Running DEITA scoring for field '%s'...", field.name)

        api_base, api_key = self._get_inference_endpoint(field)

        try:
            from distilabel.llms import OpenAILLM
            from distilabel.steps.tasks import QualityScorer, ComplexityScorer
            from distilabel.pipeline import Pipeline
        except ImportError:
            _logger.error(
                "distilabel not installed. Install: pip install distilabel[vllm]"
            )
            return jsonl_path, {'status': 'error', 'error': 'distilabel not installed'}

        filtered_path = os.path.join(tempfile.gettempdir(), f'deita_filtered_{self.id}.jsonl')

        try:
            llm = OpenAILLM(
                model="gpt-4o-mini",
                api_key=api_key,
                base_url=api_base,
            )

            with Pipeline(name=f"nettrades_deita_field_{field.id}") as pipeline:
                complexity = ComplexityScorer(
                    llm=llm,
                    input_mappings={"instruction": "prompt"},
                    output_mappings={"score": "complexity_score"},
                )
                quality = QualityScorer(
                    llm=llm,
                    input_mappings={"instruction": "prompt", "response": "completion"},
                    output_mappings={"score": "quality_score"},
                )
                complexity.connect(quality)

            distiset = pipeline.run(dataset_path=jsonl_path)

            df = distiset['default'].to_pandas()
            original_count = len(df)

            if field.deita_min_complexity > 0:
                df = df[df['complexity_score'] >= field.deita_min_complexity]
            if field.deita_min_quality > 0:
                df = df[df['quality_score'] >= field.deita_min_quality]

            filtered_count = len(df)
            df.to_json(filtered_path, orient='records', lines=True)

            rejection_rate = 1.0 - (filtered_count / max(original_count, 1))

            stats = {
                'original_count': original_count,
                'filtered_count': filtered_count,
                'rejection_rate': round(rejection_rate, 3),
                'avg_complexity': round(float(df['complexity_score'].mean()), 3) if filtered_count > 0 else 0,
                'avg_quality': round(float(df['quality_score'].mean()), 3) if filtered_count > 0 else 0,
                'status': 'completed',
            }

        except Exception as e:
            _logger.error("DEITA scoring failed: %s", e)
            return jsonl_path, {'status': 'error', 'error': str(e)[:500]}

        # Auto-disable if configured (using the same max_rejection_rate field for consistency)
        if (field.deita_auto_disable
                and field.data_juicer_max_rejection_rate > 0
                and rejection_rate > field.data_juicer_max_rejection_rate):
            field.write({
                'enable_deita_scoring': False,
                'deita_status': 'auto_disabled',
            })
            field.activity_schedule(
                'mail.mail_activity_data_warning',
                summary=f"DEITA auto-disabled for {field.name}",
                note=(
                    f"Rejection rate: {rejection_rate*100:.1f}%.\n"
                    f"Review DEITA thresholds or training data quality."
                ),
            )

        field.write({
            'deita_last_run': fields.Datetime.now(),
            'deita_last_stats': stats,
        })

        return filtered_path, stats

    # ------------------------------------------------------------------
    # Main trigger – called by cron when enough records have accumulated
    # ------------------------------------------------------------------
    def action_trigger_finetune(self):
        """
        Called by cron when record_count reaches a configurable threshold.
        1. Export eligible feedback to JSONL.
        2. Run Data-Juicer quality pipeline (if enabled).
        3. Run DEITA scoring (if enabled).
        4. Record which professionals contributed expert answers (indirect rep).
        5. Create a training job record.
        6. Call LangGraph to start GPUStack training.
        """
        self.ensure_one()
        field = self.field_id

        # Determine if we have enough data (use field-level threshold or default 100)
        min_records = field.min_votes_for_training or 100
        if self.record_count < min_records:
            _logger.info("Not enough data for fine-tuning (have %d, need %d)", self.record_count, min_records)
            return False

        # ---- 1. Export data ----
        try:
            filepath = self.export_to_jsonl()
        except Exception as e:
            _logger.error("Export to JSONL failed: %s", e)
            return False

        if filepath is None:
            _logger.info("No eligible feedback records to export for dataset '%s'.", self.name)
            return False

        self.file_uri = filepath

        # ---- 2. Data-Juicer quality pipeline ----
        if field.enable_data_juicer:
            try:
                filtered_path, dj_stats = self._run_data_juicer_pipeline(filepath)
                if dj_stats.get('status') == 'completed':
                    self.file_uri = filtered_path
                elif dj_stats.get('status') == 'error':
                    _logger.warning("Data-Juicer error: %s. Using unfiltered dataset.", dj_stats.get('error'))
            except Exception as e:
                _logger.warning("Data-Juicer pipeline failed: %s. Using unfiltered dataset.", e)

        # ---- 3. DEITA scoring ----
        if field.enable_deita_scoring:
            try:
                deita_path, deita_stats = self._run_deita_scoring(self.file_uri)
                if deita_stats.get('status') == 'completed':
                    self.file_uri = deita_path
                elif deita_stats.get('status') == 'error':
                    _logger.warning("DEITA error: %s.", deita_stats.get('error'))
            except Exception as e:
                _logger.warning("DEITA scoring failed: %s. Using current dataset.", e)

        # ---- 4. Record which professionals contributed expert answers ----
        # (This feeds the indirect reputation system.)
        feedbacks = self.env['llm.feedback'].search([
            ('field_id', '=', field.id),
            ('processed', '=', True),
        ])
        experts_seen = set()
        for fb in feedbacks:
            if fb.vote_id.answer_model == 'expert.session':
                session = self.env['expert.session'].browse(fb.vote_id.answer_id)
                if session and session.expert_id:
                    if session.expert_id.id not in experts_seen:
                        self.env['ft.dataset.contribution'].create({
                            'dataset_id': self.id,
                            'partner_id': session.expert_id.id,
                            'points_contributed': fb.weight,
                        })
                        experts_seen.add(session.expert_id.id)

        # ---- 5. Create training job ----
        job = self.env['ft.training.job'].create({
            'dataset_id': self.id,
            'field_id': field.id,
            'provider': field.finetune_provider or 'unsloth',
            'base_model': field.base_model or 'deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B',
            'status': 'pending',
        })

        # ---- 6. Call LangGraph agent (direct, no n8n) ----
        url = self.env['ir.config_parameter'].sudo().get_param(
            'langgraph_invoke_url', 'http://langgraph:8000/invoke')
        api_key = self.env['ir.config_parameter'].sudo().get_param('langgraph_api_key', '')
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['x-api-key'] = api_key

        try:
            resp = requests.post(url, json={
                "input": {"messages": [{"role": "user", "content": json.dumps({
                    "action": "start_finetune",
                    "job_id": job.id,
                    "dataset_id": self.id,
                    "file_path": self.file_uri,
                    "field_id": field.id,
                    "base_model": field.base_model,
                    "training_config": 'unsloth_single_gpu',
                })}]}
            }, headers=headers, timeout=30)
            resp.raise_for_status()
            job.status = 'running'
            _logger.info("Fine-tuning job %d started.", job.id)
        except requests.Timeout:
            job.status = 'failed'
            job.error_message = 'Fine-tuning trigger timed out.'
            _logger.error("Fine-tuning trigger timed out for dataset %s", self.id)
        except requests.ConnectionError:
            job.status = 'failed'
            job.error_message = 'Cannot reach LangGraph.'
            _logger.error("Fine-tuning trigger connection error for dataset %s", self.id)
        except requests.HTTPError as e:
            job.status = 'failed'
            job.error_message = f'LangGraph returned HTTP {e.response.status_code}'
            _logger.error("Fine-tuning trigger HTTP error: %s", e)
        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            _logger.error("Fine-tuning trigger failed for dataset %s: %s", self.id, e)

        return True