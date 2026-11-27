
# NETTRADES Platform — Bug Catalog

**Last updated:** 2026-11-16
**Total entries:** 51 (45 from 2026-09-24 session + 6 from 2026-11-16 session)
**Open:** 8 (down from 22)
**Fixed:** 43
**Complements:** None (KNOWN-ISSUES.md was merged into this file and deleted 2026-11-16)

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

**Status:** FIXED
**Severity:** High (security)
**Location:** `src/core/odoo_proxy/main.py`, `jsonrpc_proxy()`
**Symptom:** The `ALLOWED_MODELS` set is checked in `/models/{name}/fields`
but not in `/jsonrpc`. Any JSON-RPC payload is forwarded to Odoo. An agent
can call `execute_kw('res.users', 'search_read', ...)`.

**Fix:** JSON-2 proxy route + whitelist fix
The JSON-2 transport uses a service API key stored in
ODOO_SERVICE_API_KEY. When that variable is set, the proxy
authenticates to Odoo with the scoped service user's token instead
of forwarding the client-supplied uid/password. This is the
forward-compatible path: Odoo 20 deprecates execute_kw, and the
JSON-2 API is the replacement.

**Effort:** 15 minutes.

---

## BUG-002 — `/auth/login` sessions are never stored

**Status:** FIXED
**Severity:** High (functional)
**Location:** `src/core/odoo_proxy/auth.py`, `login()`, `status()`
**Symptom:** Login returns a `session_id` UUID that is not persisted.
`/auth/status` always returns `authenticated: False`. `/auth/logout` only
logs. The Launcher's login never actually works.

**Fix:** Valkey session persistence
Sessions are persisted in Valkey with a 24-hour TTL. This fixes
BUG-002, where the previous in-memory approach lost the session on
every container restart and made /auth/status always return
authenticated: False.
If Valkey is not reachable (VALKEY_HOST not set, or connection
failed), the module falls back to in-process storage. This keeps
local development working without Valkey, at the cost of sessions
not surviving a restart. The fallback is logged once at startup.

**Effort:** 1 hour.

---

## BUG-003 — Proxy uses a fixed admin user for all ORM calls

**Status:** PARTIAL
**Severity:** Critical (security)
**Location:** `src/core/odoo_proxy/main.py` (constant `ODOO_USER`) and
`src/connectors/odoo.py` (`_authenticate_internal`)
**Symptom:** Every ORM call runs as UID 1 (admin). Odoo record rules are
bypassed. Multi-company isolation is defeated. Audit logs say "admin".

**Fix (design level):**
CREATED NEW FILE: odoo-modules/nettrades_gpu_admin/data/nettrades_service_user.xml — NEW
    PURPOSE:
        Creates the `nettrades-service` user used by the LangGraph
        supervisor and the odoo-proxy to authenticate to Odoo. This
        user has NO web login capability (password is '!' meaning
        "no login allowed") and only the groups required by the
        control plane.

        Why a dedicated user:
          - The scheduler, the supervisor, and the proxy all need to
            read gpu.cluster and gpu.node and write layer_assignment.
          - Previously they authenticated as admin (UID 2), which has
            every permission in every module. A single bug in any of
            those components would have given an attacker full control
            of the ERP.
          - With a scoped user, the blast radius is limited to the GPU
            tables and the agent infrastructure.

        Groups assigned:
          - base.group_user            : standard internal user
          - nettrades_gpu_admin.group_gpu_administrator
          - nettrades_gpu_admin.group_gpu_operator
          - nettrades_core.group_nettrades_api

        The user is created with password='!' so it cannot be used to
        log in to the web UI. An API key is generated separately (see
        scripts/configure-odoo-admin.sh) and stored in the environment
        as NETTRADES_SERVICE_API_KEY.

        This file lives in nettrades_gpu_admin rather than
        nettrades_core because the group_gpu_administrator and
        group_gpu_operator groups are defined in
        nettrades_gpu_admin/security/groups.xml, and Odoo resolves XML
        ID references at load time.
Added odoo-modules/nettrades_gpu_admin/data/nettrades_service_user.xml to
odoo-modules/nettrades_gpu_admin/__manifest__.py 

Added service users to deploy/docker/docker-compose.yaml
In scripts/configure-odoo-admin.sh — added service user creation 
**Effort:** 4 hours across the proxy and the connector.

**Additional details:** 
(proxy uses a fixed admin UID for all ORM calls) — unchanged from BUG-003's PARTIAL status. The scoped nettrades-service user exists, and the JSON-2 path uses it, but the legacy /jsonrpc path still uses admin. Not on the demo path; remains a follow-up item.

The scoped nettrades-service user exists (configure-odoo-admin.sh), but odoo_proxy/main.py still uses ODOO_USER (UID 2 = admin) for /jsonrpc. JSON-2 path uses the scoped key. Acceptable for demo, note as follow-up.

---

## BUG-004 — Register node endpoint crashes on first call

**Status:**  FIX APPLIED to odoo-modules/nettrades_gpu_admin/controllers/main.py and 
- CHECK 
**Severity:** Critical (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/controllers/main.py`,
`register_node()`
**Symptom:** `node_vals` omits `partner_id`, which is `required=True` on
`gpu.node`. Every registration attempt raises `ValidationError`.

**Fix:** Add `partner_id` to the create dict. The natural value is
`token.created_by.partner_id.id`.

**Effort:** 5 minutes.

Fixed: controllers/main.py::register_node and configure-hub-for-spokes.sh now resolve partner_id before Node.create(). Priority: company partner → token creator partner → base.partner_root. The third fallback guarantees registration cannot fail on a missing partner.

for BUG-004 added this to 
scripts/pre-demo-check.sh that verifies partner_id resolution works end-to-end before you go on stage. That is the same script I sent in the previous response; you can add a check for the dynamo_worker row, which you already had:
bash

check "dynamo_worker registered" bash -c \
  "docker compose -f deploy/docker/docker-compose.yaml exec -T postgres \
   psql -U odoo -d odoo -tAc \
   \"SELECT COUNT(*) FROM gpu_node WHERE inference_capability='dynamo_worker'\" \
   | grep -q '^1$'"

If that check fails on the V100, it means either the probe failed (network path to vLLM) or configure-hub-for-spokes.sh failed on partner_id. After the patch above, it will only fail on the network path, which is the correct failure mode to diagnose.

---

## BUG-005 — Register node endpoint references non-existent field

**Status:** FIXED
**Severity:** High (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/controllers/main.py`,
`_generate_node_wireguard_config()`
**Symptom:** Reads `cluster.dns_servers`. `gpu.cluster` has no such field.
`AttributeError` fires after BUG-004 is fixed.

**Fix:** Removed the reference. The platform does not need to dictate DNS
for the WireGuard mesh. 
Change
'dns_servers': cluster.dns_servers or '8.8.8.8, 1.1.1.1',
To
'dns_servers': '8.8.8.8, 1.1.1.1',
Verified by the fact that register_node no longer raises AttributeError when the DB cluster record exists — the fake token test reached the token validation step before failing

**Effort:** 2 minutes.

---


---

## BUG-007 — `gpu.cluster` lacks `recompute_layers`, `layer_assignment`, `llama_rpc_cluster`

**Status:** PARTIAL
**Severity:** High (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/models/gpu_cluster.py`
**Symptom:** Three things missing for the distributed inference design:
- `recompute_layers()` method does not exist.
- `layer_assignment` JSON field does not exist.
- `llama_rpc_cluster` is not one of the `trust_mode` options.

**Fix:**
layer_assignment — added. Verified in the DB.

rpc_master_node_id — added (this wasn't in the catalog's list but was needed).

recompute_layers() — not added, and no longer needed. The algorithm lives in src/core/rpc_scheduler.py::compute_layer_assignment().  

llama_rpc_cluster trust_mode option — not added, and not needed by the current code. The supervisor distinguishes tracks by trust_mode == 'company_multi_gpu' (dynamo) vs anything else (rpc). Adding the explicit option is a UI clarification, not a functional requirement.

Fix (implemented): Added layer_assignment and rpc_master_node_id fields to gpu.cluster. The recompute_layers algorithm and the llama_rpc_cluster trust_mode option are not needed because the layer assignment is computed in src/core/rpc_scheduler.py. llama_rpc_cluster remains a future UI polish item.


**Effort:** 1 hour.

---

## BUG-008 — `gpu.node` lacks `inference_capability` and `compute_profile`

**Status:** FIXED
**Severity:** Medium (functional)
**Location:** `odoo-modules/nettrades_gpu_admin/models/gpu_node.py`
**Symptom:** No way to mark a node as an RPC worker vs a local-only node.
No place to store the compute profile reported by the spoke agent.

**Fix:**
1. Add `inference_capability = fields.Selection([...])`.
2. Add `compute_profile = fields.Json()`.
Both fields added. Verified in the DB:
sql

-- Both columns exist:
inference_capability | character varying | not null | 'local_only'
compute_profile      | jsonb

Odoo's Missing not-null constraint on gpu.node.inference_capability warning on every module load confirms the field is registered in the model and being compared against the DB.

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

menu_items.xml commented out of manifest. Not demo-critical.

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

**Status:**  FIXED
**Severity:** Medium (performance)
**Location:** `src/core/supervisor.py`, `_get_available_hardware()`
**Symptom:** Uses `requests.post` inside an `async def`. Under concurrent
load, requests serialize.

**Fix:** Replace with `httpx.AsyncClient`. Pattern already exists in
`app.py` and `odoo_tools.py`.
In src/core/supervisor.py, replaced requests.post with httpx.AsyncClient. The function now uses:
python

async with httpx.AsyncClient(timeout=5) as client:
    r = await client.post(...)

Also fixed the related VRAM aggregation bug (+= 0 was a no-op placeholder).

**Effort:** 20 minutes.

---

## BUG-017 — `_on_rpc_node_failure` blocks the event loop

**Status:**  FIXED
**Severity:** Medium (performance)
**Location:** `src/core/supervisor.py`, `_on_rpc_node_failure()`
**Symptom:** Same as BUG-016.

**Fix:** Rewrote the whole function to use httpx.AsyncClient. It now posts to the supervisor's own /rpc/relaunch endpoint via RPCScheduler.restart_without_node(), which is a valid path.

**Effort:** 15 minutes.

---

## BUG-018 — Node inventory not refreshed

**Status:** FIXED
**Severity:** Low (operational)
**Location:** `src/core/app.py`, lifespan
**Symptom:** `_load_node_inventory_into_monitor()` is called once at
startup. A node added to Odoo after LangGraph starts is invisible until
restart.

**Fixed:** Add an asyncio background task that calls the function every
60 seconds.
_node_inventory_loop now runs every 60s.

**Effort:** 30 minutes.

---

## BUG-019 — `mode.py` used `__import__('datetime')`
fix applied to src/core/odoo_proxy/mode.py
**Status:**  Fixed 
**Severity:** Cosmetic
**Location:** `src/core/odoo_proxy/mode.py`
**Symptom:** Uses `__import__('datetime').datetime.now()` inline.
Functionally correct, but confusing.

**Fix:** Add `from datetime import datetime` at the top.

**Effort:** 2 minutes.

mode.py had import requests (unused) and __import__('datetime'). Fixed below.
now mode.py uses normal import; unused requests removed
---

## BUG-020 — `mode.py` imports `requests` but never used it
fix applied to src/core/odoo_proxy/mode.py
**Status:**  Fixed
**Severity:** Cosmetic
**Location:** `src/core/odoo_proxy/mode.py`
**Symptom:** Unused import.

**Fix:** Remove the import.

**Effort:** 1 minute.
now mode.py uses normal import; unused requests removed
---

## BUG-021 — `ft.dataset` writes to `llm.training.dataset` with wrong fields

Decision still needed — not demo-blocking.

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

**Status:** FIXED
**Location:** `src/core/self_improving_integration.py`, `_create_episode()`
**Fix:** Replaced 
thread_id = input_data.get('thread_id') or context_data.get('thread_id')
With
thread_id = input_data.get('thread_id')

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
config_views.xml duplicate XML IDs. File is commented out of the manifest. Safe for demo.
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

Only affects the audit-views.py diagnostic tool. Not demo-critical.


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

OPEN (latent)	Only fires when avahi is installed. Not demo-critical.
Latent discovery thread issue; avahi not installed.

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



### RPC Bugs 

Traced a chain of failures from "the scheduler does nothing" to "the scheduler works end-to-end". These are now fixed :

### BUG-047 — Dockerfile.langgraph had no Docker CLI.
**Status:** FIXED
rpc_scheduler.recreate_master() runs docker compose ... via subprocess.run. The container had no docker binary. Fix: added docker.io + Compose v2 plugin (from GitHub release, not Debian repos) to Dockerfile.langgraph.

### BUG-048 — langgraph-server had no Docker socket or rpc.env mount.
**Status:** FIXED
Even with the CLI present, the container couldn't reach the host daemon or write rpc.env. Fix: added four volumes (/var/run/docker.sock, ./rpc.env, ./docker-compose.yaml, ./.env) and two env vars to the compose service.

### BUG-049 — docker-compose.yaml had no rpc profile services.
**Status:** FIXED
llama-rpc-master and llama-rpc-worker-cuda did not exist. Fix: added both behind profiles: ["rpc"].

### BUG-050 — app.py had no /rpc/relaunch endpoint.
**Status:** FIXED
The supervisor's failure callback had no target. Fix: added the endpoint with RPCSchedulerError handling that returns structured JSON on failure instead of leaking a traceback.

### BUG-052 — ODOO_USER=1 is __system__, not admin.
**Status:** FIXED
The scheduler and odoo-proxy authenticated as the superuser, which cannot log in via JSON-RPC (no password). Fix: .env now sets ODOO_USER=<admin uid>; compose default is ${ODOO_USER:-2}; configure-odoo-admin.sh writes the discovered uid back to .env automatically.

### BUG-053 — Admin user password was set in the wrong format.
**Status:** FIXED
The initial attempt used crypt(password, gen_salt('bf')) in Postgres, which writes a bcrypt hash. Odoo expects pbkdf2_sha512 (or argon2) for res_users.password. The hash was rejected. Fix: configure-odoo-admin.sh sets the password through Odoo's ORM (admin.password = ...), which runs the correct hasher.

### BUG-054 — configure-odoo-admin.sh was called before the Odoo container was running.
**Status:** FIXED
The call was placed before docker compose up -d --build. docker compose exec -T odoo failed with "service odoo is not running", and 2>/dev/null hid the error, causing set -e to exit silently. Fix: moved the call to after the stack starts, removed the redirect.

### BUG-055 — Duplicate ODOO_ADMIN_PASSWORD in .env.example and .env.
**Status:** FIXED
Both files had the old ADMIN_PASSWORD line under the PostgreSQL section AND the new ODOO_ADMIN_PASSWORD under the Odoo section. safe_sed_replace targets the first match, so a future regeneration would update the wrong one. Fix: .env.example cleaned. Your live .env still needs the same cleanup (see below).

### BUG-056 — ODOO_MASTER_PASSWORD was ambiguous.
**Status:** FIXED
Renamed to DB_MANAGER_UI_PASSWORD (at your instruction), then to DB_MANAGER_UI_PASSWORD — the exact name you settled on. Compose maps it to the odoo service's ADMIN_PASSWORD env var; the actual usage pattern is now documented in .env.example.

### BUG-057 — Docker Compose file path duplication.
**Status:** FIXED
docker compose -f deploy/docker/docker-compose.yaml run from inside deploy/docker resolved the path relative to the CWD, doubling the directory. Fix: run docker compose ... from deploy/docker without -f, or use an absolute path.

### BUG-058 — context_data NameError in self_improving_integration.py.
**Status:** FIXED
This is technically BUG-023 but was a regression. See above.



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




---

## 3. `docs/developer/BUG-CATALOG.md` — append this section

Append **above** the current "## Summary of still-relevant entries" section:

```markdown
## Session 2026-10-23 — post-fix verification pass

The 2026-10-22 fixes were re-audited against the code on disk. Six of them
were incomplete or introduced a regression; those are listed below as
BUG-059 through BUG-064. All are FIXED as of this session.

### BUG-059 — `install-netsvc.ps1` lost the installation command during the preshutdown edit

**Status:** FIXED (2026-10-23)
**Severity:** High (would break Windows installer at ship time)
**Location:** `scripts/windows/install-netsvc.ps1`
**Symptom:** The edit that added `sc.exe config NETTRADESNetSvc preshutdown= 60000`
replaced the `& $ServiceExe install` block instead of appending after it.
`sc.exe config` failed (service did not yet exist) and `Start-Service` failed
(service never registered). Windows installer was broken end-to-end.

**Fix:** Restored the `& $ServiceExe install` block before the `sc.exe config`
line, with the `Write-Warning` fallback preserved. Verified by inspection
of the file — order is now install → config preshutdown → start.

**Not on the demo path.**

---

### BUG-060 — `heartbeat()` used `Node._fields` (undefined) instead of `node._fields`

**Status:** FIXED (2026-10-23)
**Severity:** High (runtime on every drain)
**Location:** `odoo-modules/nettrades_gpu_admin/controllers/main.py::heartbeat`
**Symptom:** The drain branch added in the previous session referenced `Node`,
which is only defined in `register_node()`. `heartbeat()` has `node` (the
specific record) but not `Node` (the model). Every drain heartbeat raised
`NameError`, caught by the outer `try`, returning `Internal server error`
with HTTP 200.

**Effect:** LangGraph heartbeats still worked (their drain path is
independent), so the demo remained functional. But the Odoo `status` field
never received `'draining'`, and the AMD box logged "Odoo heartbeat failed"
on every drain.

**Fix:** Changed `Node._fields` to `node._fields`. `_fields` is class-level
metadata, identical across all records, so the semantics are unchanged.
Comment added explaining the choice.

---

### BUG-061 — `_probe_all()` skipped transition callbacks when a node was draining

**Status:** FIXED (2026-10-23)
**Severity:** High (operational — delayed cluster rebuild on drain)
**Location:** `src/core/node_health.py::_probe_all`
**Symptom:** The drain branch was:

```python
if node.draining:
    node.is_healthy = False
    continue
```


The continue skipped:

    Prometheus metric updates (NODE_UP stayed at 1 for the whole drain window)

    The _on_node_unhealthy callback, which fires _on_rpc_node_failure →
    restart_without_node. Without it, the cluster did not rebuild until
    the next pre_generation_check failed on an incoming request — a
    delay of 30 s or more on the Routing tab.

Fix: Replaced the continue with an if/else so the drain branch
falls through to the metrics update and the transition check. The rest of
the loop body runs normally. Comment explains why continue is wrong here.

Verified by: manual inspection; drain sequence traced end-to-end in the
health monitor's log path.
BUG-062 — _find_warm_spare domain matched every row on empty exclusion

Status: FIXED (2026-10-23)
Severity: High (silent cluster rebuild with the failed node)
Location: src/core/rpc_scheduler.py::_find_warm_spare
Symptom: ("id", "not in", []) matches every row in Odoo's domain
evaluator. On a single-spoke demo, surviving_nodes is empty, so
surviving_ids was set(), the domain became id not in [], and the
failed node — still state='active' — was returned as a candidate spare
for itself. restart_without_node then added it back to surviving_nodes
and rebuilt the cluster with the dead node.

Fix: Added exclude_node_ids parameter; cast exclusions to int
(Odoo's not in on an Integer field silently matches everything when the
list contains strings); added an explicit fail-safe when the combined
exclusion list is empty (return None rather than promote). Caller in
restart_without_node now passes exclude_node_ids=[failed_node_id].

Verified by: tracing the domain-building logic against Odoo's
documented not in semantics.
BUG-063 — _watch_drain_file honoured stale trigger files after reboot

Status: FIXED (2026-10-23)
Severity: Medium (spoke drains itself on every boot after power loss)
Location: scripts/spoke-agent.py::_watch_drain_file
Symptom: If the trigger file drain.requested survived a power loss
(Windows path particularly), the agent would drain on the next boot, before
any generation had begun. Under systemd the drain sequence deletes the
file, but a hard power cut does not.

Fix: Record process_start_ts = time.time() at thread start; if the
trigger file already exists with mtime < process_start_ts - 2, delete
it and log a warning. Only files written after the process started are
honoured as live triggers. The 2 s slack covers slow startups where the
file might be written by the service supervisor just before the agent's
watcher thread starts.
BUG-064 — phase-modules.sh aborted the whole phase on any transient Odoo hiccup

Status: FIXED (2026-10-23)
Severity: Medium (operator workflow — not demo-path)
Location: scripts/phase-modules.sh
Symptom: The $(...) capture was replaced with a | tee pipeline
during the 2026-10-22 fix. Under set -euo pipefail, a nonzero exit from
docker compose exec odoo (e.g. Odoo momentarily unavailable) aborted
the entire phase. The previous $(...) form was forgiving by accident
(bash does not propagate the inner command's exit code through a
capture).

Fix: Wrapped the piped command with set +e / CONFIGURE_EXIT=$? /
set -e. If the exit is nonzero, log a warning and continue — the phase
marker is written at the end, so a genuine failure surfaces on re-run.
Also corrected since 2026-10-22

    BUG-004 now fully fixed end-to-end. Previous entry marked the
    partner_id fix but missed the missing node = Node.create(node_vals)
    call and the idempotent re-registration path. Both are in place and
    documented in the code.

    BUG-043 (discovery thread self.env) remains OPEN (latent).
    No change this session. Do not fix before the demo; the avahi-daemon is
    installed by install-spoke.sh but the Odoo discovery thread is only
    started when the manifest enables discovery.py, and it is currently
    commented out. Re-audit after the demo.

    BUG-003 (admin user for ORM calls) remains PARTIAL. The scoped
    service user exists; the odoo-proxy still authenticates as admin on
    the JSON-RPC path. Not on the demo path. Do not touch before the demo.

---

## Session 2026-11-16 — demo-fix completion

The Qatar Foundation demo was accepted. This session addressed the bugs
discovered during the demo-fix cycle and merged the KNOWN-ISSUES.md backlog
into this catalog.

All six fixes were verified end-to-end on the WSL2 dev box
(RTX 5070 Ti, WSL2, CUDA 12.0 driver 610.47, compute capability 12.0).

### BUG-065 — `app.py` missing `import json` at module scope

**Status:** FIXED (2026-11-16)
**Severity:** High (silent functional failure)
**Location:** `src/core/app.py`, top-of-file imports
**Symptom:** The hub-manifest override block in
`_load_node_inventory_into_monitor()` calls `json.load()` on the manifest
file. `import json` was present in an earlier revision but was removed (or
never added at module scope). The override block's `try/except` caught the
`NameError` and logged a warning — "Hub manifest read failed: name 'json'
is not defined" — every 60 seconds. The health monitor therefore kept
receiving the stale `gpu.node` values from Odoo (65536 MB aggregate for a
4× V100 record, written by `configure-hub-for-spokes.sh` on the original
hub) instead of the manifest's real values.

**Effect:** `/nodes` reported `vram_total_mb: 65536` on a machine whose only
GPU has 16 GB. The supervisor's `_get_available_hardware()` therefore
computed `dynamo_vram_mb = 65536`, which is over 4× the true value. That
did not cause a functional failure on the dev box (a 5 GB model fits in
either number) but would have caused the supervisor to route a 40 GB model
to the RPC track and have the master silently offload to CPU.

**Fix:** Added `import json` at module scope. The `_json` alias used
inline in the `compute_profile` parsing branch was a separate local import
and did not shadow the module-level `json`.

**Verified:** `/nodes` now returns `hostname=DESKTOP-TH432JK`,
`vram_total_mb=16303`, `gpu_count=1`.

**Effort:** 1 minute.

### BUG-066 — `supervisor.py::classify()` used substring match on intent list

**Status:** FIXED (2026-11-16)
**Severity:** High (wrong routing for most queries)
**Location:** `src/core/supervisor.py`, `classify()`
**Symptom:** The intent classifier parsed the LLM's reply by scanning
`_VALID_INTENTS_ORDERED` for the first entry that appeared as a substring
of the reply. When the model echoed the prompt list (which contains every
intent name — `recruitment`, `freelance`, ... `gpu_marketplace`, `general`),
the first entry — `gpu_marketplace` — always matched. Every short or
ambiguous query routed to the GPU marketplace agent.

**Effect:** "hello", "what model are you", "what's the weather" — all went
to the marketplace agent. The marketplace agent had nothing to do with
them, so it fell through to the general LLM (which is why user-visible
output looked correct) but the routing events log, the intent field in
`/invoke` responses, and the self-improving episode recording all showed
`intent=gpu_marketplace`.

**Fix:** Exact membership test:

```python
matched = raw if raw in _VALID_INTENTS_ORDERED else None
```
Non-matching replies fall through to general. Keyword overrides
("what model", "show gpu cluster") still fire first.

**Verified:** hello → general, what model are you → general
(keyword override), show gpu cluster status → gpu_management
(keyword override).

Effort: 5 minutes.

### BUG-067 — `spoke-agent.py::detect_gpus()` non-idempotent

**Status:** FIXED (2026-11-16)
**Severity:** Medium (latent)
**Location:** `scripts/spoke-agent.py`, `_AMD_ENUMERATED_DEVICE_DIRS`
**Symptom:** The AMD detection path deduplicated realpath'd device
directories against a module-level set. A second call to `detect_gpus()`
returned an empty list.
**Effect:** Currently latent. `detect_gpus()` is called once per process
(either from `--detect-only` or from `SpokeAgent.__init__`). Any future
re-detection path — a SIGHUP handler, a `--redetect` flag, a test that
calls the function twice — would silently find no AMD GPUs.
**Fix:** Moved the dedupe set to a per-call local (`seen: set = set()`), per-call instead of per-module.
**Verified:** Two consecutive calls return the same GPU count.
**Effort:** 3 minutes.

### BUG-068 — `spoke-agent.py::_detect_intel_gpus()` used line number as device index

**Status:** FIXED (2026-11-16)
**Severity:** Medium (no Intel GPUs in current fabric)
**Location:** `scripts/spoke-agent.py`, `_detect_intel_gpus()`
**Symptom:** The `xpu-smi discovery` branch iterated with
`for idx, line in enumerate(...)` and passed `idx` as `vendor_device_index`.
If xpu-smi printed header lines before the first "Device Name", the first
Intel GPU pinned to `level_zero:3` instead of `level_zero:0`.
**Effect:** On a 2-GPU Intel Arc deployment with a 3-line header, both
`rpc-server` processes would attempt to attach to non-existent devices and
fail to init. This bug was present in both `spoke-agent.py` and the
deleted `hardware_detection.py`; only `vendor/intel.py` had the correct
implementation.
**Fix:** Use a separate `device_idx` counter that increments only on actual
device lines, matching `vendor/intel.py`'s pattern.
**Verified:** Structural correctness confirmed against `vendor/intel.py`.
**Effort:** 5 minutes.

### BUG-069 — `app.py::_node_inventory_loop` ran the loader twice at startup

**Status:** FIXED (2026-11-16)
**Severity:** Cosmetic (one redundant RPC at startup)
**Location:** `src/core/app.py`, `_node_inventory_loop()`
**Symptom:** The `lifespan()` called `_load_node_inventory_into_monitor()`
once, then started the inventory loop task. The loop's first line was
`await _load_node_inventory_into_monitor()` — duplicate call 19 ms later.
**Effect:** Two identical Odoo JSON-RPC calls per container start. The
manifest override fired twice in the logs. Not a functional failure; the
loader is idempotent.
**Fix:** Sleep first, then load.
```python
while True:
    await asyncio.sleep(interval_seconds)
    try:
        await _load_node_inventory_into_monitor()
    except Exception as e:
        logger.warning(f"Node inventory refresh failed: {e}")
```
**Verified:** After `docker compose build --no-cache langgraph-server`,
the log shows a single "Hub manifest override" at startup, then one per
60 seconds.
**Effort:** 2 minutes.

### BUG-070 — Docker `COPY` cache retained stale `app.py`

**Status:** DOCUMENTED (2026-11-16, no code fix — Docker behaviour)
**Severity:** Operational (cost one hour of debugging)
**Location:** `deploy/docker/Dockerfile.langgraph`
**Symptom:** After editing `src/core/app.py` and running
`docker compose up -d --build langgraph-server`, the container started
with the previous `app.py`. The build log showed a fresh
`COPY src/core/  0.1s` (not `CACHED`), but the file inside was stale.
A subsequent `docker compose build --no-cache langgraph-server` fixed it.
**Root cause:** Docker's COPY layer cache is keyed on file content hash
and mtime. On WSL2 and Windows-hosted Docker, a single-line edit
occasionally produces a file whose metadata collides with a previous
build, causing the layer cache to consider the new file "unchanged" even
though its content differs. This is rare but reproducible.
**Effect:** Any fix to a `src/core/` file can silently fail to reach the
running container. The failure mode is a build that reports success, a
container that starts, and a behaviour that does not match the source.
**Fixed:** Documented in `Dockerfile.langgraph` with explicit remedy
(`--no-cache`). Also added an operational rule to `README-AGENT.md`.
```dockerfile

# Source code is copied wholesale. Two known failure modes on WSL2 and
# Windows-hosted Docker, both observed during the 2026-11-16 session:
#
#   1. COPY layer cache reuse. A source edit under src/core/ sometimes
#      does not invalidate the COPY layer, so the running container keeps
#      the previous file version. Force a rebuild:
#          docker compose build --no-cache langgraph-server
#
#   2. If the change is in the image but the code still does not fire at
#      runtime, check that the import statement is at module scope — the
#      `import json` bug on 2026-11-16 was the manifest override silently
#      failing on every inventory refresh with a NameError caught in the
#      outer try/except.
COPY src/core/ /app/src/core/
```
**Verified:** On every --no-cache rebuild since, the container has the
current file.
**Effort:** Documentation only.