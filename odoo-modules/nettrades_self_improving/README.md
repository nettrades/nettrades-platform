# NETTRADES Self-Improving

Consolidated module that merges `nettrades_trigger`, `nettrades_loop`,
and `nettrades_self_improving_config` into one cohesive unit.

## Architecture

Three design decisions make this module future-proof:

### 1. Quality signals live as fields on `data.episode`

Instead of scattering quality metrics across modules, all signals are
fields on the shared `data.episode` model:

- `quality_score`       — from Good Answer votes (existing)
- `fairness_score`      — from the fairness evaluator (new)
- `hallucination_score` — reserved for future hallucination detection
- `user_satisfaction`   — reserved for future survey integration

Any consumer writes to these fields; the training pipeline reads them
via declarative filters in `training.pipeline.dataset_config`.

Adding a new quality signal = adding a field + adding a filter entry.
No pipeline code changes.

### 2. Training backend is configurable

`training.pipeline.training_config['backend']` selects the backend:
'unsloth', 'axolotl', or 'dynamo'. `submit_training_job()` dispatches
to the corresponding `_submit_<backend>()` method.

Adding a new backend = adding a method + adding the backend name to
`SUPPORTED_BACKENDS`.

### 3. Orchestrator is a resumable state machine

`loop.cycle.status` is the state. `loop.orchestrator._drive_cycle()`
advances through states until a terminal state (completed, failed,
skipped) is reached. States that wait for external work (e.g. training)
leave the cycle in that state; a cron job picks them up later.

Adding a new stage = adding a state value + a handler method.

## Required dependencies

- `nettrades_core`
- `nettrades_data_collection` (owns `data.episode`)
- `llm_training` (owns `llm.training.dataset`, `llm.training.job`, `llm.provider`)
- `queue_job`, `mail`, `web`, `base`

## Migration from the three old modules

1. Back up the database.
2. Uninstall `nettrades_loop`, then `nettrades_trigger`, then
   `nettrades_self_improving_config` (in that order).
3. Delete the three module directories.
4. Copy this module into `odoo-modules/nettrades_self_improving/`.
5. Update `scripts/install-modules.sh` to reference only the merged name.
6. Run `./scripts/prepare-odoo-addons.sh --force`.
7. Restart Odoo and install the merged module.

## Integration with `nettrades_fairness`

`nettrades_fairness` writes to `data.episode.fairness_score` if the
field exists. It does NOT need a dependency on this module:

```python
if 'fairness_score' in self.env['data.episode']._fields:
    self.env['data.episode'].browse(response_id).write({
        'fairness_score': rationality_score - bias_score,
    })

```

## Integration with future quality signals

Any module can write to hallucination_score or user_satisfaction
following the same pattern. The training pipeline reads them via
declarative filters in dataset_config['filters'].
