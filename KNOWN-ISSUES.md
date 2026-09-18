# Known Issues and Deferred Work

These are things we know about, have made a decision about, and are
deliberately deferring. Do not "fix" them without reading the context.

## Cosmetic / Non-Blocking

### `user.notification` missing not-null constraints

The `nettrades_notifications` module declares `partner_id` and `title`
as required fields, but the database columns allow NULL. This is
because the module was added to the DB before the constraints were
applied, and Odoo does not retroactively add constraints to existing
columns.

**Impact:** New notification records can technically be created without
a partner or title. Runtime validation catches this in the ORM, but
the DB allows it.

**Fix:** A future migration can run `ALTER TABLE user_notification
ALTER COLUMN partner_id SET NOT NULL;` after backfilling any NULL
rows. Low priority.

### Odoo 19 deprecations

Several warnings appear on every module load:

- `_sql_constraints` — superseded by `models.Constraint`. Works but
  is deprecated.
- `@route(type='json')` — superseded by `type='jsonrpc'`. Works but
  is deprecated.
- `attrs="{'invisible': ...}"` — superseded by inline `invisible="..."`.

**Impact:** Warnings only. Not blocking.

**Fix:** A dedicated pass to migrate all three. Approximately 4–6
hours of work. Do it in a single PR; do not mix with functional changes.

## Functional Gaps (Deliberate)

### `nettrades_fairness` — `response_id` is an Integer, not a Many2one

The fairness audit and flag models originally referenced
`llm.assistant.message` as a comodel. That module is not a dependency
and the model doesn't exist there. It was changed to `Integer` because
the field is used as an opaque ID (compared against
`good.answer.vote.answer_id`, which is also an Integer).

**Impact:** You cannot navigate from a fairness flag to the actual
message record in the UI. You can still see the ID.

**Fix:** Decide what the correct reference is (a `good.answer.vote`,
a `llm.message`, or a future unified message model) and change the
field back to a Many2one. Do this when you build the audit-log UI.

### `nettrades_data_collection` — no simulation.session model

The `SimulationDataset` model originally had `session_id` and
`config_id` fields pointing at `simulation.session` and
`simulation.config`. Neither model exists. The fields were removed.

**Impact:** Datasets cannot be linked to a simulation session.

**Fix:** Either build the simulation models (if they're still planned)
or remove the concept entirely. Do not re-add the fields until the
target models exist.

### `nettrades_good_answer` — Fine-tune button on dataset forms

The dataset form originally had a "Fine-tune" button that called
`action_fine_tune()`. The method created a `nettrades_gpu_admin.job`
record. That model does not exist. The button was removed.

**Impact:** You cannot trigger fine-tuning from the dataset form.

**Fix:** The actual fine-tuning pipeline lives in
`ft.training.job` (which does exist). Rewrite `action_fine_tune()` to
create an `ft.training.job` instead, or delete the feature entirely.

### Fine-tuning uses simulated GPU calls

`FTDataset.action_trigger_finetune()` and
`FTTrainingJob` do not actually call a training backend. They log
the job and mark it running.

**Impact:** Fine-tuning is a UI skeleton. No actual training happens.

**Fix:** Implement the pipeline:
1. Export dataset as JSONL (already done — `export_to_jsonl`)
2. Run Data-Juicer (stub exists — `_run_data_juicer_pipeline`)
3. Run DEITA scoring (stub exists — `_run_deita_scoring`)
4. Submit to Unsloth or Axolotl via the training service
5. Poll for completion
6. Deploy the fine-tuned model as an `llm.provider`

See HANDOFF.md §11 for the deprecation warnings list.

## Architectural Debt

### `nettrades_bridge` `_call_local_brain` is a stub

The bridge routing service has a `_call_local_brain` method that
returns a hardcoded `"Processed by local LangGraph agent"` response.
It does not actually call the LangGraph supervisor.

**Impact:** Bridge routing logs usage but does not route.

**Fix:** Replace the stub with an HTTP call to
`http://langgraph-server:8000/invoke`, passing the request through the
graph's API. Handle streaming and errors.

### `connectors/odoo.py` uses a fixed admin user

The Odoo connector authenticates as `admin` for all operations, not
as the requesting user. This breaks tenant isolation.

**Impact:** All agent operations run as admin. Record rules do not
apply. Cross-tenant reads are possible.

**Fix:** Change the connector to accept a per-user session token
(forwarded from the gateway) and authenticate Odoo calls as that user.
See HANDOFF.md §5 (Phase 2) for the plan.


### Also worth a quick check

In the logs it says:
text
```
│    odoo  | 2026-09-17 19:31:07,733 1 WARNING ? odoo.schema: Missing not-null constraint on user.notification.partner_id
│    odoo  | 2026-09-17 19:31:07,733 1 WARNING ? odoo.schema: Missing not-null constraint on user.notification.title
```

Those warnings are from nettrades_notifications and they suggest the module's partner_id and title fields are supposed to be required but the DB column allows NULL. That's a separate issue and not blocking the install, but it means new user.notification records can be created without those fields — which will cause runtime errors later. Flagging it for future development.




## Explicitly Out of Scope

- Live video/audio streaming from spokes
- Multi-region failover for the hub
- On-prem Kubernetes support (single-VM only for now)
- Mobile native apps (PWA is the mobile story)
- Billing integration with Stripe (UI exists, backend stub)