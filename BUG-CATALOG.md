
# NETTRADES Platform — Bug Catalog

**Last updated:** 2026-09-24
**Total entries:** 45
**Open:** 22
**Fixed:** 23
**Complements:** `KNOWN-ISSUES.md` (older backlog)

---

## Status Legend

- **OPEN** — reproducible, not fixed
- **FIXED** — verified fixed
- **PARTIAL** — partially addressed
- **DEFERRED** — acknowledged, not scheduled
- **FALSE POSITIVE** — reported but the code is actually correct

---

## Session Summary (2026-09-24)

The session that produced this update resolved a chain of failures that had
blocked module installation for over a day. Root causes, in order of discovery:

1. `pdfplumber` pulling an incompatible `cryptography` into the Odoo image,
   breaking `pyOpenSSL`. Fix: two-stage pip install.
2. Windows-1252 em-dash in `nettrades_onboarding/__manifest__.py` causing
   Odoo to report `manifest not found`.
3. Odoo 16 `attrs=` syntax in six view files.
4. `<group expand="0">` inside `<search>` (Odoo 16 syntax).
5. `<menuitem>` before its `<action>` in `bridge_config_views.xml`.
6. `DiscoveryService.__init__` override (forbidden by Odoo 19 ORM).
7. `doall` / `numbercall` on `ir.cron` (removed in Odoo 17).
8. Missing `ir.model.access.csv` header row.
9. Python syntax error (unterminated string) in `res_partner.py`.
10. Buttons on `res.partner` calling controller methods (illegal — buttons
    call model methods).

Result: 13/13 modules install cleanly. See `HANDOFF.md` for the verified state.

---


## BUG-001 — Proxy `/jsonrpc` does not enforce the model whitelist

**Status:** OPEN
**Severity:** High (security)
**Location:** `src/core/odoo_proxy/main.py`, `jsonrpc_proxy()`
**Symptom:** The `ALLOWED_MODELS` set is checked in `/models/{name}/fields`
but not in `/jsonrpc`. Any JSON-RPC payload is forwarded to Odoo. An agent
can call `execute_kw('res.users', 'search_read', ...)`.

**Fix:** Extract `body["params"]["args"][3]` (the model name) and refuse
non-whitelisted models with HTTP 403.

**Effort:** 15 minutes.

---

## BUG-002 — `/auth/login` sessions are never stored

**Status:** OPEN
**Severity:** High (functional)
**Location:** `src/core/odoo_proxy/auth.py`, `login()`, `status()`
**Symptom:** Login returns a `session_id` UUID that is not persisted.
`/auth/status` always returns `authenticated: False`. `/auth/logout` only
logs. The Launcher's login never actually works.

**Fix:** Persist sessions in Valkey (already in the stack) with a TTL.
`/auth/status` reads from Valkey. `/auth/logout` deletes the key.

**Effort:** 1 hour.

---

## BUG-003 — Proxy uses a fixed admin user for all ORM calls

**Status:** OPEN
**Severity:** Critical (security)
**Location:** `src/core/odoo_proxy/main.py` (constant `ODOO_USER`) and
`src/connectors/odoo.py` (`_authenticate_internal`)
**Symptom:** Every ORM call runs as UID 1 (admin). Odoo record rules are
bypassed. Multi-company isolation is defeated. Audit logs say "admin".

**Fix (design level):**
1. The proxy accepts a user session token alongside the API key.
2. The proxy forwards the token as the `uid` in `execute_kw`.
3. The connector accepts a per-user token rather than the fixed admin.

**Effort:** 4 hours across the proxy and the connector.

**Cross-ref:** `KNOWN-ISSUES.md` "P1.5".

---

## BUG-004 — Register node endpoint crashes on first call

**Status:**  CHECK IF STILL OPEN
**Severity:** Critical (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/controllers/main.py`,
`register_node()`
**Symptom:** `node_vals` omits `partner_id`, which is `required=True` on
`gpu.node`. Every registration attempt raises `ValidationError`.

**Fix:** Add `partner_id` to the create dict. The natural value is
`token.created_by.partner_id.id`.

**Effort:** 5 minutes.

---

## BUG-005 — Register node endpoint references non-existent field

**Status:** OPEN
**Severity:** High (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/controllers/main.py`,
`_generate_node_wireguard_config()`
**Symptom:** Reads `cluster.dns_servers`. `gpu.cluster` has no such field.
`AttributeError` fires after BUG-004 is fixed.

**Fix:** Remove the reference. The platform does not need to dictate DNS
for the WireGuard mesh.

**Effort:** 2 minutes.

---

## BUG-006 — `drain_and_restart_for_node` does not exist on `gpu.cluster`

**Status:** OPEN
**Severity:** High (functional)
**Location:** Called in `src/core/supervisor.py` (`_on_rpc_node_failure`),
defined nowhere
**Symptom:** Every health-monitor-detected node failure raises
`AttributeError` when the callback fires. The drain-and-restart cycle
never completes.

**Fix:** Add the method to `gpu.cluster`. It marks the node offline,
revokes the WireGuard peer, and recomputes `layer_assignment`. It does
**not** relaunch the master container — that belongs in
`src/core/rpc_scheduler.py`.

**Effort:** 45 minutes.

---

## BUG-007 — `gpu.cluster` lacks `recompute_layers`, `layer_assignment`, `llama_rpc_cluster`

**Status:** OPEN
**Severity:** High (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py`
**Symptom:** Three things missing for the distributed inference design:
- `recompute_layers()` method does not exist.
- `layer_assignment` JSON field does not exist.
- `llama_rpc_cluster` is not one of the `trust_mode` options.

**Fix:**
1. Add `('llama_rpc_cluster', 'llama.cpp RPC Cluster')` to `trust_mode`.
2. Add `layer_assignment = fields.Json()`.
3. Add `recompute_layers()` — see `ARCHITECTURE-FUTURE.md` and
   `ARCHITECTURE-AND-PLAN.md` §4.5 for the algorithm.
4. Update `_compute_payment_mode` to treat `llama_rpc_cluster` as
   trusted (internal payment mode).

**Effort:** 1 hour.

---

## BUG-008 — `gpu.node` lacks `inference_capability` and `compute_profile`

**Status:** OPEN
**Severity:** Medium (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/models/gpu_node.py`
**Symptom:** No way to mark a node as an RPC worker vs a local-only node.
No place to store the compute profile reported by the spoke agent.

**Fix:**
1. Add `inference_capability = fields.Selection([...])`.
2. Add `compute_profile = fields.Json()`.

**Effort:** 20 minutes.

---

## BUG-009 — `gpu_registration_token_views.xml` references non-existent field

**Status:** CHECK IF STILL OPEN
**Severity:** Medium (install-time)
**Location:** `odoo-modules/nettrades_gpu_admin/views/gpu_registration_token_views.xml`
**Symptom:** The form references `cluster_id` on `gpu.registration.token`.
The model has no such field.

**Fix:** Remove `cluster_id` from the view.

**Effort:** 2 minutes.

**Note:** The file is currently commented out of the manifest. Fix this
before enabling.

---

## BUG-010 — `gpu_node_views.xml` has duplicate notebook pages

**Status:**  CHECK IF STILL OPEN
**Severity:** Medium (install-time)
**Location:** `odoo-modules/nettrades_gpu_admin/views/gpu_node_views.xml`
**Symptom:** The form has two `<page string="GPUs">`, two
`<page string="Network">`, two `<page string="Economics">`. Odoo rejects
duplicate page names.

**Fix:** Remove the duplicates. Keep the more detailed version of each.

**Effort:** 15 minutes.

**Note:** The file is currently commented out of the manifest. Fix this
before enabling.

---

## BUG-011 — Three view files reference wrong field names

**Status:**  CHECK IF STILL OPEN
**Severity:** Medium (install-time)
**Location:**
- `views/gpu_schedule_views.xml` — references `node_id`, `enabled`. Model has `cluster_id`, `is_enabled`.
- `views/gpu_token_economics_views.xml` — references `node_id`, `tokens_earned`, `tokens_spent`, `balance`, `last_transaction`. Model has `earn_rate_per_1k_tokens`, etc.
- `views/multimodal_config_views.xml` — references `vision_enabled`, `vision_model_name`, `robotics_enabled`, `mqtt_broker_url`, `edge_enabled`. Model uses `enable_multimodal`, `multimodal_vlm_model`, `enable_robotics`, `iot_mqtt_broker`, `enable_edge_deployment`. Also uses Odoo 16 `attrs=` syntax.

**Fix:** Rewrite each view against the actual model fields.

**Effort:** 2 hours.

**Note:** All three files are commented out of the manifest. Fix before
enabling.

---

## BUG-012 — `menu_items.xml` uses removed `<act_window>` and duplicates `menu_gpu_root`

**Status:** OPEN
**Severity:** Low (install-time)
**Location:** `odoo-modules/nettrades_gpu_admin/views/menu_items.xml`
**Symptom:** Uses `<act_window>` (removed in Odoo 17). Also defines
`menu_gpu_root` which is now also defined in `gpu_cluster_views.xml`.

**Fix:** Either remove the file (the definitions exist elsewhere) or
rewrite using `<record model="ir.actions.act_window">`. If keeping it,
remove the duplicate `menu_gpu_root`.

**Effort:** 30 minutes.

---

## BUG-013 — Owl JS components call methods that don't exist

**Status:** OPEN
**Severity:** Medium (runtime)
**Location:**
- `static/src/js/dashboard.js` — calls `gpu.cluster.start_finetune()` and `gpu.cluster.deploy_finetuned_model()` (neither method exists).
- `static/src/js/wireguard_manager.js` — calls `get_wireguard_peers()` and `revoke_wireguard_peer()` as ORM methods. The model has `get_peers_for_wireguard()` (different name) and `_revoke_wireguard_peer()` (private).
- `static/src/js/node_manager.js` — reads `pool` instead of `gpu_pool`; uses `env.user.companyId` in a way that doesn't work in Owl.

**Fix:**
1. Add public wrappers on `gpu.cluster`: `action_revoke_wireguard_peer`,
   `action_start_finetune`, `action_deploy_finetuned_model`.
2. Fix the JS field names.
3. Fix the Owl env access.

**Effort:** 1 hour.

---

## BUG-014 — `gpu_scanner.py` is an Odoo model living outside Odoo

**Status:** OPEN
**Severity:** Medium (functional)
**Location:** `src/core/discovery/gpu_scanner.py`
**Symptom:** Uses `from odoo import api, fields, models`. Cannot import
`odoo` from `src/core/`, which runs in a Python container without Odoo.

**Fix (two options):**
1. Rewrite as a plain Python module that calls Odoo via the proxy.
2. Move it into the Odoo module (`odoo-modules/nettrades_gpu_admin/models/`)
   and call it from the container's HTTP controller.

**Recommendation:** Option 1. Keeps the code outside Odoo, matches the
`src/core/` design principle.

**Effort:** 2 hours.

---

## BUG-015 — `ros2_tools.py` uses `self.env` outside a model

**Status:** OPEN
**Severity:** Low (not currently called)
**Location:** `src/core/tools/ros2_tools.py`
**Symptom:** The class `ROS2Tools` uses `self.env['data.episode']` as if
it were an Odoo model. It is not.

**Fix:** Rewrite as a plain client that posts to the proxy API. Match
the pattern in `src/core/tools/odoo_tools.py`.

**Effort:** 1 hour.

---

## BUG-016 — `main.py` `_get_available_hardware` blocks the event loop

**Status:**  CHECK IF STILL OPEN
**Severity:** Medium (performance)
**Location:** `src/core/supervisor.py`, `_get_available_hardware()`
**Symptom:** Uses `requests.post` inside an `async def`. Under concurrent
load, requests serialize.

**Fix:** Replace with `httpx.AsyncClient`. Pattern already exists in
`app.py` and `odoo_tools.py`.

**Effort:** 20 minutes.

---

## BUG-017 — `_on_rpc_node_failure` blocks the event loop

**Status:**  CHECK IF STILL OPEN
**Severity:** Medium (performance)
**Location:** `src/core/supervisor.py`, `_on_rpc_node_failure()`
**Symptom:** Same as BUG-016.

**Fix:** Same as BUG-016.

**Effort:** 15 minutes.

---

## BUG-018 — Node inventory not refreshed

**Status:** OPEN
**Severity:** Low (operational)
**Location:** `src/core/app.py`, lifespan
**Symptom:** `_load_node_inventory_into_monitor()` is called once at
startup. A node added to Odoo after LangGraph starts is invisible until
restart.

**Fix:** Add an asyncio background task that calls the function every
60 seconds.

**Effort:** 30 minutes.

---

## BUG-019 — `mode.py` uses `__import__('datetime')`

**Status:**  CHECK IF STILL OPEN
**Severity:** Cosmetic
**Location:** `src/core/odoo_proxy/mode.py`
**Symptom:** Uses `__import__('datetime').datetime.now()` inline.
Functionally correct, but confusing.

**Fix:** Add `from datetime import datetime` at the top.

**Effort:** 2 minutes.

---

## BUG-020 — `mode.py` imports `requests` but never uses it

**Status:**  CHECK IF STILL OPEN
**Severity:** Cosmetic
**Location:** `src/core/odoo_proxy/mode.py`
**Symptom:** Unused import.

**Fix:** Remove the import.

**Effort:** 1 minute.

---

## BUG-021 — `ft.dataset` writes to `llm.training.dataset` with wrong fields

**Status:** PARTIAL
**Severity:** High (functional)
**Location:** `odoo-modules/nettrades_good_answer/models/ft_dataset.py`
**Symptom:** `export_to_jsonl()` and `action_trigger_finetune()` reference
`llm.training.dataset` fields (`record_count`, `data`, `status`, `field_id`)
that don't exist. Only `name`, `description`, `attachment_ids`,
`example_count`, `file_count` exist.

**Fix:** Refactor `ft.dataset` to store its output as an
`llm.training.dataset` via a new `training_dataset_id = fields.Many2one('llm.training.dataset')`.
The `export_to_jsonl()` method creates an `ir.attachment` and an
`llm.training.dataset` in one call.

**Status detail:** `training.pipeline.create_dataset()` in
`nettrades_self_improving` was rewritten in this session to do this
correctly. The `ft.dataset` version is unused but not deleted.

**Effort:** 3 hours.

**Cross-ref:** `KNOWN-ISSUES.md` "Open — `ft.dataset` vs `llm.training.dataset`".

---

## BUG-022 — `self_improving_integration` writes to `data.episode` fields that didn't exist

**Status:** FIXED (2026-09-21)
**Severity:** High (functional)
**Location:** `src/core/self_improving_integration.py`
**Fix:** Added the missing fields to `data.episode`:
`track`, `data_classification`, `is_verified`, `verified_by`,
`resolution_status`, `model_used`, `inference_time_ms`, `token_count`,
`fine_tune_quality`, `recorded_at`.

---

## BUG-023 — `self_improving_integration` had a `NameError`

**Status:** FIXED (2026-09-21)
**Location:** `src/core/self_improving_integration.py`, `_create_episode()`
**Fix:** Replaced the reference to undefined `context_data` with a direct
read from `input_data.get('thread_id')`.

---

## BUG-024 — `data_collector.py` had four bugs

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_data_collection/models/data_collector.py`
**Fixes:**
1. Added `import json`.
2. Removed `field_id` from `data.feedback.create()` in `collect_good_answer`.
3. Changed `session.question` → `session.task_summary` in `collect_expert_session`.
4. Removed the `collected_for_training` block from `_cron_collect_unprocessed`.

---

## BUG-025 — `good_answer_vote.create()` wrote a bad foreign key

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_good_answer/models/good_answer_vote.py`
**Fix:** Removed the write to `data.feedback` with `episode_id=vote.answer_id`
(an Integer, not an episode ID).

---

## BUG-026 — `expert_session.action_complete_session()` wrote a bad foreign key

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_ask_someone/models/expert_session.py`
**Fix:** Writes `episode_id=episode.id` (the ID of the just-created episode)
instead of `self.id` (the session ID).

---

## BUG-027 — `loop.orchestrator` used an instance attribute for wait signalling

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_self_improving/models/loop_orchestrator.py`
**Fix:** Replaced `self._should_wait = True` with `return 'wait'` from the
state handler. Odoo 19 recordsets do not reliably support arbitrary
instance attributes.

---

## BUG-028 — `loop.cycle.dataset_record_count` related field was invalid

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_self_improving/models/loop_cycle.py`
**Fix:** Removed the field. Count is tracked on `loop.cycle.episode_count`
directly.

---

## BUG-029 — `data_episode.action_export_to_training_dataset` wrote to non-existent fields

**Status:** FIXED (2026-09-21)
**Location:** `odoo-modules/nettrades_data_collection/models/data_episode.py`
**Fix:** Method removed entirely. Superseded by
`training.pipeline.create_dataset()`.

---

## BUG-030 — `llm_training` view used `<group string="Group By">` inside `<search>`

**Status:** FIXED (2026-09-21)
**Location:** `third-party/llm_training/views/llm_training_job_views.xml`
**Fix:** Removed the wrapper. Filters with `context="{'group_by': ...}"`
appear under "Group By" automatically.

**Note:** This is a local patch to a third-party module. **Re-apply if
`third-party/llm_training` is re-vendored.**

---


### BUG-031 — Dockerfile `--ignore-installed` broke OpenSSL

**Status:** FIXED (2026-09-24)
**Severity:** Critical (infrastructure)
**Symptom:**


AttributeError: module 'lib' has no attribute 'GEN_EMAIL'
text

Every Odoo module failed on load. Only `nettrades_core` needed `base` + `mail`;
those modules failed too, so the failure was not module-specific.

**Root cause:** `pip3 install --ignore-installed` in `Dockerfile.odoo` forced
pip to upgrade `cryptography` to version 50.x, which is incompatible with the
Debian-provided `pyOpenSSL 23.2.0`. The mismatch was silent because
`cryptography` was importable in isolation; the failure only surfaced when
something imported `OpenSSL.crypto`.

**Fix:** Two-stage pip install in `Dockerfile.odoo`. Stage 1 pre-installs
`typing-extensions`, `idna`, `charset-normalizer` with `--ignore-installed`
(they need to shadow Debian). Stage 2 installs the rest without
`--ignore-installed`.

**Verified by:**

docker compose exec -T odoo python3 -c
"from OpenSSL import crypto; print('OpenSSL OK')"
→ OpenSSL OK
text


### BUG-032 — Windows-1252 bytes in files Odoo reads as UTF-8

**Status:** FIXED (multiple instances)
**Severity:** Critical (install-blocking)
**Symptom:** `ValueError: External ID not found` or `manifest not found`
with no obvious cause.

**Root cause:** Python 3 reads files as UTF-8 by default. A file containing
Windows-1252 bytes (em-dashes `0x97`, en-dashes `0x96`, curly quotes
`0x91`–`0x94`, `0x96`–`0x97`) fails to decode. `cat` and `md5sum` don't
reveal this.

**Instances fixed:**
- `nettrades_onboarding/__manifest__.py` (em-dash in comment)
- `third-party/llm_knowledge/models/__init__.py` (en-dash in comment)

**Diagnostic that found it:**
```python
import ast
with open(path, 'rb') as f:
    content = f.read()
ast.literal_eval(content.decode('utf-8'))
```

Prevention: Two-tier UTF-8 check added to prepare-odoo-addons.sh.
Hard error on nettrades_*, warning on vendored files.


### BUG-033 — <menuitem> before <action> in bridge_config_views.xml

**Status:** FIXED
**Severity:** High (install-blocking)
**Symptom:**
text

ValueError: External ID not found in the system:
nettrades_bridge.action_bridge_config

**Root cause:** Odoo resolves <menuitem action="X"/> immediately at parse
time. The three menuitems in bridge_config_views.xml referenced actions
defined either below them in the same file or in files loaded later.

**Fix:** Consolidated all menuitems into a new views/menu_views.xml, listed
last in the manifest's data array. Removed menuitems from individual view
files.

Note: Same pattern existed in nettrades_self_improving/views/config_views.xml
(moved menuitems after actions) — but that file is dead code (see BUG-041).


### BUG-034 — <menuitem> before <action> in config_views.xml

**Status:** FIXED (but the file is dead — see BUG-041)
**Severity:** High (would be install-blocking if enabled)
Same pattern as BUG-033.


### BUG-035 — doall / numbercall on ir.cron (removed in Odoo 17)

**Status:** FIXED
**Severity:** High (install-blocking)
**Symptom:** ValueError: Invalid field 'doall' in 'ir.cron'
**Location:** nettrades_bridge/data/bridge_cron_data.xml
**Fix:** Removed both fields. They were deprecated in Odoo 17 and are gone
in 19.


### BUG-036 — attrs= syntax (Odoo 16, removed in Odoo 17)

**Status:** FIXED (all instances)
**Severity:** High (install-blocking)
**Symptom:** ParseError: Since 17.0, the "attrs" and "states" attributes are no longer used.
Instances fixed:

    nettrades_bridge/views/bridge_config_views.xml

    nettrades_bridge/views/bridge_company_config_views.xml

    nettrades_bridge/views/bridge_route_views.xml

    nettrades_gpu_admin/views/multimodal_config_views.xml

    nettrades_self_improving/views/config_views.xml (dead file)

    nettrades_llm_config/views/llm_company_config_views.xml

**Fix:** Migrated all attrs="{'invisible': [('X', '=', False)]}" to
invisible="not X". Simple conditions:

    [('X', '=', False)] → not X

    [('X', '=', True)] → X

    [('X', '!=', 'value')] → X != 'value'

    required → separate required="X" attribute.

Prevention: Pre-flight check for attrs= / states=, but softened to a
warning because Odoo 19 still tolerates it (deprecation only).


### BUG-037 — <group expand="0"> inside <search> (Odoo 16, removed in Odoo 17)

**Status:** FIXED
**Severity:** High (install-blocking)
**Symptom:** RELAXNGV:RELAXNG_ERR_INVALIDATTR: Invalid attribute expand for element group
**Location:** nettrades_bridge/views/bridge_route_views.xml
**Fix:** Removed the <group expand="0" string="Group By"> wrapper. Group-by
filters are now top-level <filter> elements with context="{'group_by':...}";
Odoo groups them automatically.


### BUG-038 — DiscoveryService.__init__ override forbidden by Odoo 19

**Status:** FIXED
**Severity:** High (install-blocking)
**Symptom:**
text

WARNING odoo odoo.models: The method DiscoveryService.__init__ doesn't match the new signature
AttributeError: 'nettrades_bridge.discovery' object has no attribute '_discovery_thread'

**Root cause:** Odoo 19's ORM instantiates model classes itself; arbitrary
instance attributes set in __init__ are discarded. The ORM calls
__init__ with no arguments on a fresh recordset, so any self._x = ...
assignment appears to work but is lost.

**Fix:** Removed __init__. Runtime state (thread handle, running flag,
peer cache) now lives in a module-level dict keyed by database name
(_DISCOVERY_STATE[dbname]). Helper _get_runtime(env) returns the state
for the current database.

Latent issue (still open): The discovery thread calls
self.env['...'] from inside the background thread. This will fail when
avahi is installed. See BUG-043.


### BUG-039 — pdfplumber in single-stage pip install

**Status:** FIXED
**Severity:** High (build-blocking)
**Symptom:** pdfplumber pulls pdfminer.six, which pulls cryptography.
With --ignore-installed, this broke the OpenSSL stack (see BUG-031).
Without it, pip tried to uninstall Debian-provided typing_extensions and
failed with RECORD file not found.
**Fix:** Two-stage install. Stage 1 shadows Debian packages. Stage 2 installs
pdfplumber without --ignore-installed.


### BUG-040 — Windows-1252 em-dash in onboarding manifest

**Status:** FIXED
**Severity:** Critical (install-blocking)
**Symptom:** module nettrades_onboarding: manifest not found even though
the file existed and passed md5sum matching.
**Root cause:** Windows-1252 byte 0x97 in a comment. Python 3 failed to
decode the file. Odoo caught the exception and reported "manifest not found".
**Fix:** Rewrote the manifest with ASCII-only comments.


### BUG-041 — Duplicate XML IDs across config_views.xml and self_improving_config_views.xml

**Status:** OPEN (harmless today)
**Severity:** Medium (would break if enabled)
**Symptom:** Both files declare:
text

view_self_improving_config_form
action_self_improving_config

config_views.xml is not in the manifest, so the duplicate is harmless.
If it's added to the manifest, the module will fail with a duplicate ID
error.

**Fix:** Delete config_views.xml after verifying that
self_improving_config_views.xml and menu_views.xml provide complete
coverage.


### BUG-042 — audit-views.py false positive on nested One2many fields

**Status:** OPEN
**Severity:** Low (diagnostic tool only)
**Symptom:** Files like self_improving_config_views.xml are flagged for
referencing name, trigger_type, threshold_value on
self.improving.config — but those fields are inside a nested <list>
for the trigger_ids One2many, so they refer to trigger.config, not
self.improving.config.
**Fix:** Track model context in check_view_file. When descending into a
relational field, switch to the comodel. Requires extending
parse_model_fields() to record (model, field) → comodel.


### BUG-043 — Discovery thread calls self.env from a background thread

**Status:** OPEN (latent)
**Severity:** Medium (will break when avahi is installed)
**Location:** nettrades_bridge/controllers/discovery.py
**Symptom:** _get_version, _get_gpu_count, _get_model_count are called
from inside _discovery_loop, which runs in a background thread. Odoo
cursors are not thread-safe.
Why it doesn't fire now: python-avahi is not installed, so
AVAHI_AVAILABLE is False and _discovery_loop never runs.
Fix when ready: Resolve env-dependent values before spawning the
thread, pass them as plain Python data in the runtime state dict.
Example already in the file as a comment.


### BUG-044 — Onboarding res_partner.py syntax error (unterminated string)

**Status:** FIXED
**Severity:** Critical (install-blocking)
**Location:** nettrades_onboarding/models/res_partner.py
**Symptom:**
text

SyntaxError: unterminated string literal (detected at line 25)

**Fix:** Added the missing closing quote on the help= argument.


### BUG-045 — Onboarding button calls a controller method

**Status:** FIXED
**Severity:** High (runtime)
**Location:** nettrades_onboarding/views/onboarding_wizard.xml
**Symptom:** parse_cv is not a valid action on res.partner
**Root cause:** The button called name="parse_cv", which existed only on
the HTTP controller. Odoo buttons invoke model methods.
**Fix:** Added action_parse_cv method to res.partner. Renamed the button.


### BUG-046 — Missing ir.model.access.csv header row

**Status:** FIXED
**Severity:** High (install-blocking)
**Location:** nettrades_onboarding/security/ir.model.access.csv
**Symptom:** ValueError: Invalid field name 'access_res_partner_user'
**Fix:** Added the header row:
text

id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink



## Summary of still-relevant entries:

BUG-021 (ft.dataset vs llm.training.dataset) — PARTIAL, see notes.

BUG-022 through BUG-030 — FIXED in prior sessions.



## Open Bugs (by priority)

Security — High Priority

#### BUG-001 — Proxy /jsonrpc doesn't enforce the model whitelist

src/core/odoo_proxy/main.py. ALLOWED_MODELS is checked in

/models/{name}/fields but not in /jsonrpc. **Fix:** extract

body["params"]["args"][3] and refuse non-whitelisted models with 403.

Effort: 15 min.


#### BUG-002 — /auth/login sessions are never stored
src/core/odoo_proxy/auth.py. Login returns a session_id UUID that is
not persisted. **Fix:** persist in Valkey. Effort: 1 hour.

#### BUG-003 / P1.5 — Proxy runs all ORM calls as admin (UID 1)
src/core/odoo_proxy/main.py, src/connectors/odoo.py. Every ORM call
runs as admin. Record rules bypassed. Audit logs say "admin".
Fix (design level): proxy accepts a user session token alongside the API
key, forwards it as uid in execute_kw. Effort: 4 hours.
Functional — Medium Priority

#### BUG-005 — _generate_node_wireguard_config reads cluster.dns_servers
Field doesn't exist. **Fix:** remove the reference. Effort: 2 min.

#### BUG-006 — drain_and_restart_for_node is called but undefined
Supervisor calls gpu.cluster.drain_and_restart_for_node(node_external_id).
The method doesn't exist. **Fix:** add it. Effort: 45 min.

#### BUG-007 — gpu.cluster missing recompute_layers, layer_assignment, llama_rpc_cluster
Needed for distributed inference. Effort: 1 hour.

#### BUG-008 — gpu.node missing inference_capability, compute_profile
Needed to mark nodes as RPC workers. Effort: 20 min.

#### BUG-012 — menu_items.xml uses <act_window> (removed in Odoo 17)
Also duplicates menu_gpu_root. Effort: 30 min.

#### BUG-013 — Owl JS components call non-existent methods
dashboard.js, wireguard_manager.js, node_manager.js. **Fix:** add public
wrappers. Effort: 1 hour.

#### BUG-014 — gpu_scanner.py is an Odoo model living outside Odoo
Uses from odoo import api, fields, models but runs in a Python container.
**Fix:** rewrite as a plain Python module that calls the proxy. Effort: 2 hours.

#### BUG-015 — ros2_tools.py uses self.env outside a model
Same class of problem as BUG-014. Effort: 1 hour.

#### BUG-018 — Node inventory not refreshed
app.py lifespan loads node inventory once. **Fix:** asyncio background task.
Effort: 30 min.

#### BUG-021 — ft.dataset writes to llm.training.dataset with wrong fields
PARTIAL. training.pipeline.create_dataset() was rewritten correctly; the
ft.dataset version is unused but not deleted. Decision required: wire
ft.dataset to llm.training.dataset or retire it. Effort: 3 hours.

#### BUG-041 — Duplicate XML IDs in config_views.xml
See above. Effort: 5 min (delete).

#### BUG-042 — Audit script false positive on nested One2many
Effort: 40 min.

#### BUG-043 — Discovery thread calls self.env from background thread
Effort: 30 min (when avahi is ready).
Low Priority / Cosmetic

    _sql_constraints deprecation (5 warnings per module load).

    website_sale_marketplace missing author key.

    Prometheus /metrics 404 on Odoo.

    discovery.py thread-safety (BUG-043, latent).

Bug Summary Table


| ID | Status | Severity | Category | Effort |
|---|---|---|---|---|
| BUG-001 | OPEN | High | Security | 15 min |
| BUG-002 | OPEN | High | Security | 1 h |
| BUG-003 | OPEN | Critical | Security | 4 h |
| BUG-004 | - | Critical |  | 5 min |
| BUG-005 | OPEN | High | Functional | 2 min |
| BUG-006 | OPEN | High | Functional | 45 min |
| BUG-007 | OPEN | High | Functional | 1 h |
| BUG-008 | OPEN | Medium | Functional | 20 min |
| BUG-009 | - | Medium |  | 2 min |
| BUG-010 | - | Medium |  | 15 min |
| BUG-011 | - | Medium |  | 2 h |
| BUG-012 | OPEN | Low | Install | 30 min |
| BUG-013 | OPEN | Medium | Runtime | 1 h |
| BUG-014 | OPEN | Medium | Functional | 2 h |
| BUG-015 | OPEN | Low | Functional | 1 h |
| BUG-016 | - | Medium |  | 20 min |
| BUG-017 | - | Medium |  | 15 min |
| BUG-018 | OPEN | Low | Operational | 30 min |
| BUG-019 | - | Cosmetic |  | 2 min |
| BUG-020 | - | Cosmetic |  | 1 min |
| BUG-021 | PARTIAL | High | Functional | 3 h |
| BUG-022 | FIXED | High | - | — |
| BUG-023 | FIXED | High | - | — |
| BUG-024 | FIXED | High | - | — |
| BUG-025 | FIXED | High | - | — |
| BUG-026 | FIXED | High | - | — |
| BUG-027 | FIXED | High | - | — |
| BUG-028 | FIXED | High | - | — |
| BUG-029 | FIXED | High | - | — |
| BUG-030 | FIXED | High | - | — |
| BUG-031 | FIXED | Critical | Infra | — |
| BUG-032 | FIXED | Critical | Encoding | — |
| BUG-033 | FIXED | High | Install | — |
| BUG-034 | FIXED | High | Install | — |
| BUG-035 | FIXED | High | Install | — |
| BUG-036 | FIXED | High | Install | — |
| BUG-037 | FIXED | High | Install | — |
| BUG-038 | FIXED | High | Install | — |
| BUG-039 | FIXED | High | Build | — |
| BUG-040 | FIXED | Critical | Encoding | — |
| BUG-041 | OPEN | Medium | Maintenance | 5 min |
| BUG-042 | OPEN | Low | Diagnostic | 40 min |
| BUG-043 | OPEN | Medium | Latent | 30 min |
| BUG-044 | FIXED | Critical | Syntax | — |
| BUG-045 | FIXED | High | Runtime | — |
| BUG-046 | FIXED | High | Install | — |

Total open effort: ~21 hours.
Total fixed this session: 14 bugs.
Recommended Sequence

The thread-safety issue in discovery.py — latent (avahi not installed)
    
    
BUG-041 (5 min) — delete the dead file.

BUG-005 (2 min) — remove the dangling field reference.

BUG-001, BUG-002 (1 h 15 min) — proxy security fixes.

BUG-007, BUG-008 (1 h 20 min) — data structure for distributed inference.

BUG-006 (45 min) — supervisor callback.

BUG-003 (4 h) — the big one.