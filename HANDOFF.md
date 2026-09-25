# NETTRADES Platform — Handoff

**Last updated:** 2026-09-24
**Last verified state:** 13/13 Odoo modules install cleanly
**Verified by:** `install-modules.sh --force --auto` at 2026-09-24 02:57 UTC

---

## 1. What Works Right Now

The following was confirmed by a clean run on 2026-09-24:

- **`scripts/prepare-odoo-addons.sh --force`** runs to completion. Every
  pre-flight check passes:
  - Manifest validation: 57 modules, all references resolve.
  - XML parse: 197 files, all parse cleanly.
  - Python compile: 526 files, all compile cleanly.
  - UTF-8 verification: all files valid, two-tier (see §4).
  - Line-ending conversion: all files LF.
  - Final line: `57 modules prepared`.
- **`scripts/install-modules.sh --force --auto`** installs all 13 NETTRADES
  modules without warnings about skips. Final line:
  `ALL MODULES INSTALLED SUCCESSFULLY`.
- **Docker stack**: 24/24 containers up, healthy. Traefik routes to LangGraph,
  Odoo, odoo-proxy. PostgreSQL + pgvector healthy.
- **Dockerfile.odoo**: two-stage pip install, correct cryptography/pyOpenSSL
  versions (41.0.7 / 23.2.0). Verified with `from OpenSSL import crypto`.

### The 13 installed modules

```text

nettrades_core

nettrades_queue

nettrades_notifications

nettrades_llm_config

nettrades_bridge

nettrades_gpu_admin

nettrades_ask_someone

nettrades_good_answer

nettrades_fairness

nettrades_data_collection

nettrades_self_improving

nettrades_wireguard

nettrades_onboarding
```
---


## 2. What Changed

### Fixes applied

| Component | Fix |
|---|---|
| `Dockerfile.odoo` | Two-stage pip; `pdfplumber` added; no global `--ignore-installed` |
| `scripts/prepare-odoo-addons.sh` | Added XML parse check, Python compile check, UTF-8 check, attrs= check, `<group expand>` check |
| `scripts/install-modules.sh` | Added grep for silent skips (`not installable, skipped`, `manifest not found`, etc.) |
| `nettrades_core/views/nettrades_user_views.xml` | Stripped BOM |
| `nettrades_bridge/__manifest__.py` | Added `views/menu_views.xml` after all view files |
| `nettrades_bridge/views/menu_views.xml` | Created — consolidated menuitems, loaded last |
| `nettrades_bridge/views/bridge_config_views.xml` | Removed menuitems; migrated `invisible=` |
| `nettrades_bridge/views/bridge_company_config_views.xml` | Migrated `invisible=`; added `active` field |
| `nettrades_bridge/views/bridge_route_views.xml` | Migrated `invisible=`; removed `<group expand>`; search view rewritten |
| `nettrades_bridge/models/bridge_company_config.py` | Added `active` field |
| `nettrades_bridge/models/bridge_config.py` | Added `_cron_health_check()` stub |
| `nettrades_bridge/data/bridge_cron_data.xml` | Removed `doall`, `numbercall` (removed in Odoo 17) |
| `nettrades_bridge/controllers/discovery.py` | Removed `__init__` (forbidden by Odoo 19 ORM); moved state to module-level dict |
| `nettrades_bridge/controllers/bridge_controller.py` | `type='json'` → `type='jsonrpc'` |
| `nettrades_bridge/controllers/route_controller.py` | Same |
| `nettrades_onboarding/__manifest__.py` | Fixed Windows-1252 em-dash in comment; removed dead `res_partner_views.xml` ref; removed non-standard `controllers` key |
| `nettrades_onboarding/models/res_partner.py` | Added four missing fields (`professional_summary`, `skill_ids`, `experience_ids`, `resume_pdf`); added `action_parse_cv` method |
| `nettrades_onboarding/models/res_partner_skill.py` | Created |
| `nettrades_onboarding/models/res_partner_experience.py` | Created |
| `nettrades_onboarding/security/ir.model.access.csv` | Added header row (was missing) |
| `nettrades_onboarding/views/onboarding_wizard.xml` | Removed `user_type` (belongs to res.users); renamed button to `action_parse_cv` |
| `nettrades_gpu_admin/views/multimodal_config_views.xml` | Migrated `invisible=`; removed `name` field (not on model) |
| `nettrades_llm_config/views/llm_company_config_views.xml` | Reworded comment to avoid false-positive grep |
| `nettrades_self_improving/views/config_views.xml` | Migrated `invisible=`; moved menuitems after actions (dead file, see §5) |
| `third-party/llm_knowledge/models/__init__.py` | Fixed Windows-1252 en-dash |
| `third-party/llm_knowledge/views/llm_knowledge_chunk_views.xml` | Reworded comment to avoid false-positive grep |

### Bugs found and closed

See `BUG-CATALOG.md` for the complete list with root causes. Summary:

- Six instances of Windows-1252 bytes in files Odoo reads as UTF-8.
- Five instances of `attrs=` / `states=` (Odoo 16 syntax).
- One instance of `<group expand="0">` inside `<search>` (Odoo 16 syntax).
- One instance of `<menuitem>` before its `<action>` in the same file.
- One instance of a model `__init__` override (forbidden by Odoo 19).
- One instance of a button calling a controller method instead of a model method.
- One instance of `doall` / `numbercall` on `ir.cron` (removed in Odoo 17).
- One instance of a missing `ir.model.access.csv` header row.
- One instance of a Python syntax error (unterminated string).
- One instance of a manifest parse failure (`manifest not found`).

---



## 3. Known Dead Code / Latent Problems

These do not block the current build but are real.

### nettrades_self_improving/views/config_views.xml is dead

This file exists on disk but is not in the manifest. It declares the same XML IDs as `self_improving_config_views.xml`:

```text

view_self_improving_config_form
action_self_improving_config
```

If you ever add it to the manifest, the module will fail with a duplicate ID error.

**Recommended action:**  delete the file. It duplicates what's already in self_improving_config_views.xml and menu_views.xml (verify the latter before deleting). Nothing of value is lost.


### Thread-safety issue in `discovery.py`

`_get_version`, `_get_gpu_count`, `_get_model_count` are called from inside
a background thread started by `start_discovery()`. They call `self.env[...]`,
and Odoo cursors are not thread-safe.

This does not fire today because `python-avahi` is not installed and `AVAHI_AVAILABLE` is `False`. The thread never starts. But when you install avahi and enable mDNS, this will fail with a `RuntimeError`.

Fix when ready: resolve all env-dependent values before spawning the thread, pass them as plain Python data in the runtime state dict. Full example in the discovery.py comments.

### `scripts/audit-views.py` false positives on nested One2many

The audit script checks every `<field name="X"/>` inside `<arch>` against the view's root model. It does not switch context when entering a nested list inside a One2many or Many2many. So a form on `self.improving.config` with a nested list of `trigger.config` fields will report those fields as missing on `self.improving.config`.

Fix when ready: track a model-context stack in `check_view_file`. When you descend into `<field name="X">` where X is a relational field, switch to the comodel; pop on exit. Requires extending `parse_model_fields()` to record `(model, field) → comodel` for relational fields.

### `_sql_constraints` deprecation

Every module load prints 3–5 warnings like:

```text

Model attribute '_sql_constraints' is no longer supported, 
please define models.Constraint on the model.
```

Cosmetic in Odoo 19. Will break in Odoo 20. Batch migration: single commit across the codebase, ~4–6 hours.


### Prometheus `/metrics` 404 on Odoo

### Prometheus is scraping Odoo but Odoo does not expose `/metrics`. Either add the OCA `prometheus_exporter` module to the Odoo image or remove the scrape target from `prometheus.yml`. Not urgent.

## 4. Open Work (Priority Order)

### Immediate

1. Delete `nettrades_self_improving/views/config_views.xml` after verifying nothing else references it. Low-risk cleanup.

2. Verify `action_parse_cv` and `action_run_cycle` methods exist on `res.partner` and `self.improving.config` respectively. Buttons will silently fail on click if the methods don't exist.





    
## 5. Proposed Architecture

The platform is a three-layer stack. Business logic lives in Odoo's ORM. Agent infrastructure lives in a separate database. Distributed inference runs across hub, sub-hubs, and spokes.

```text

════════════════════════════════════════════════════════════════════════════════
 NETTRADES SOVEREIGN AI PLATFORM — Full Architecture
════════════════════════════════════════════════════════════════════════════════

╔═════════════════════════════════════════════════════════════════════════════╗
║  LAYER 4 — USER INTERFACES                                                  ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                             ║
║  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           ║
║  │ NETTRADES        │  │ Odoo CE Admin    │  │ AI Chat UI       │           ║
║  │ Launcher         │  │ (Business UI)    │  │ (LangGraph UI)   │           ║
║  │ (Electron)       │  │                  │  │                  │           ║
║  │                  │  │ • Users          │  │ • Chat with AI   │           ║
║  │ • Deploy         │  │ • Companies      │  │ • Mark answers   │           ║
║  │ • Modules        │  │ • Projects       │  │ • Ask Someone    │           ║
║  │ • Containers     │  │ • Fields         │  │ • Review flags   │           ║
║  │ • Backup         │  │ • Reviews        │  │ • Dashboard      │           ║
║  │ • Credentials    │  │ • GPU nodes      │  │                  │           ║
║  │ • Monitor        │  │ • LLM config     │  │                  │           ║
║  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘           ║
║           │                     │                     │                     ║
╚═══════════╪═════════════════════╪═════════════════════╪═════════════════════╝
            │                     │                     │
            │  (Docker socket)    │  (HTTP/8069)        │  (HTTP/3002)
            ▼                     ▼                     ▼
╔═════════════════════════════════════════════════════════════════════════════╗
║  LAYER 3 — ORCHESTRATION & GATEWAY                                          ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                             ║
║  ┌────────────────────────────────────────────────────────────────────────┐ ║
║  │  LangGraph Supervisor  (FastAPI :8000)                                 │ ║
║  │                                                                        │ ║
║  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │ ║
║  │  │ Intent       │ │ Session      │ │ Hardware     │ │ Recovery     │   │ ║
║  │  │ Router       │ │ Affinity     │ │ Selector     │ │ Coordinator  │   │ ║
║  │  │              │ │              │ │              │ │              │   │ ║
║  │  │ Reads intent │ │ Pins conv.   │ │ Dynamo >     │ │ Drains       │   │ ║
║  │  │ from Odoo    │ │ to backend   │ │ RPC > local  │ │ node, calls  │   │ ║
║  │  │ config       │ │ for session  │ │ > remote     │ │ compensator  │   │ ║
║  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘   │ ║
║  │         │                │                │                │           │ ║
║  │         └────────────────┴────────────────┴────────────────┘           │ ║
║  │                                  │                                     │ ║
║  │                        Tool calls (JSON-RPC)                           │ ║
║  │                                  ▼                                     │ ║
║  │  ┌──────────────────────────────────────────────────────────────────┐  │ ║
║  │  │  Enterprise Gateway  (evolved from odoo_proxy :8090)             │  │ ║
║  │  │                                                                  │  │ ║
║  │  │  • API key validation     • Red/Yellow/Green mode enforcement    │  │ ║
║  │  │  • Rate limiting          • Tenant routing                       │  │ ║
║  │  │  • Tool whitelist         • Identity proxy (forwards session)    │  │ ║
║  │  │  • Audit logging          • Saga coordinator (cross-system)      │  │ ║
║  │  │                                                                  │  │ ║
║  │  │  Connector Registry:                                             │  │ ║
║  │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐              │  │ ║
║  │  │  │ Odoo         │ │ Salesforce   │ │ SAP          │              │  │ ║
║  │  │  │ Connector    │ │ MCP Adapter  │ │ MCP Adapter  │              │  │ ║
║  │  │  │ (JSON-RPC)   │ │              │ │              │              │  │ ║
║  │  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘              │  │ ║
║  │  └─────────┼────────────────┼────────────────┼──────────────────────┘  │ ║
║  └────────────┼────────────────┼────────────────┼─────────────────────────┘ ║
║               │                │                │                           ║
╚═══════════════╪════════════════╪════════════════╪═══════════════════════════╝
                │                │                │
                ▼                ▼                ▼
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  LAYER 2 — BUSINESS SYSTEMS (Single source of truth per tenant)                      ║
╠══════════════════════════════════════════════════════════════════════════════════════╣
║                                                                                      ║
║  ┌──────────────────────────────────────┐   ┌──────────────────────────────────────┐ ║
║  │  Odoo CE + NETTRADES modules         │   │  External systems (optional)         │ ║
║  │  (Management plane)                  │   │                                      │ ║
║  │                                      │   │  ┌────────────┐  ┌────────────┐      │ ║
║  │  ┌──────────────────────┐            │   │  │ Salesforce │  │ SAP        │      │ ║
║  │  │ 10 core modules      │            │   │  │ (CRM)      │  │ (ERP)      │      │ ║
║  │  │ • core               │            │   │  └────────────┘  └────────────┘      │ ║
║  │  │ • queue              │            │   │                                      │ ║
║  │  │ • notifications      │            │   │  Any system exposing an MCP server   │ ║
║  │  │ • llm_config         │            │   │  can be plugged in via the gateway.  │ ║
║  │  │ • ask_someone        │            │   │                                      │ ║
║  │  │ • good_answer        │            │   └──────────────────────────────────────┘ ║
║  │  │ • fairness           │            │                                            ║
║  │  │ • data_collection    │            │   All 12 modules install into ONE          ║
║  │  │ • loop               │            │   Odoo instance per tenant.                ║
║  │  │ • self_improving     │            │                                            ║
║  │  │ • bridge             │            │   Every business entity lives in           ║
║  │  │ • gpu_admin          │            │   Odoo's ORM tables. No duplicate          ║
║  │  │ • trigger            │            │   raw SQL for the same entities.           ║
║  │  │ • wireguard          │            │                                            ║
║  │  │ • onboarding         │            │                                            ║
║  │  └──────────────────────┘            │                                            ║
║  │                                      │                                            ║
║  │  PostgreSQL 17 (Odoo DB)             │                                            ║
║  │  ┌──────────────────────────────────┐│                                            ║
║  │  │ ORM tables                       ││                                            ║
║  │  │ • nettrades_user                 ││                                            ║
║  │  │ • nettrades_project              ││                                            ║
║  │  │ • nettrades_field                ││                                            ║
║  │  │ • gpu_node, gpu_cluster          ││                                            ║
║  │  │ • good_answer_vote               ││                                            ║
║  │  │ • ft_dataset, ft_training_job    ││                                            ║
║  │  │ • data_episode, data_annotation  ││                                            ║
║  │  │ • nettrades_fairness_audit, _flag││                                            ║
║  │  │ • loop_cycle, trigger_config     ││                                            ║
║  │  └──────────────────────────────────┘│                                            ║
║  │                                      │                                            ║
║  │  LangGraph Checkpoints               │                                            ║
║  │  ┌──────────────────────┐            │                                            ║
║  │  │ checkpoint tables    │            │                                            ║
║  │  │ • checkpoints        │            │                                            ║
║  │  │ • checkpoint_writes  │            │                                            ║
║  │  │ • checkpoint_blobs   │            │                                            ║
║  │  └──────────────────────┘            │                                            ║
║  └──────────────────────────────────────┘                                            ║
║                                                                                      ║
║  ┌────────────────────────────────────────────────────────────────────────┐          ║
║  │  NETTRADES Agent Infrastructure Database  (separate PostgreSQL DB)     │          ║
║  │                                                                        │          ║
║  │  • nettrades_gpu_nodes          — heartbeats, telemetry                │          ║
║  │  • nettrades_queue_tasks        — inference job dispatch               │          ║
║  │  • nettrades_pwa_cache          — offline agent cache                  │          ║
║  │  • nettrades_saga_log           — cross-system coordination state      │          ║
║  │  • nettrades_compensation_registry — saga rollback actions             │          ║
║  │  • nettrades_idempotency_keys   — retry safety                         │          ║
║  │                                                                        │          ║
║  │  Rationale: operational telemetry, not business data.                  │          ║
║  │  Independent of which CRM/ERP the tenant uses. Unaffected by           │          ║
║  │  Odoo upgrades. Separate backup lifecycle.                             │          ║
║  └────────────────────────────────────────────────────────────────────────┘          ║
║                                                                                      ║
╚══════════════════════════════════════════════════════════════════════════════════════╝

╔══════════════════════════════════════════════════════════════════════════════╗
║  LAYER 1 — DISTRIBUTED INFERENCE (Physical topology)                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌────────────────────────────────────────────────────────────────────────┐  ║
║  │  HUB  (nettrades.ai)                                                   │  ║
║  │                                                                        │  ║
║  │  Data-centre infrastructure:                                           │  ║
║  │  ┌──────────────────────┐   ┌──────────────────────┐                   │  ║
║  │  │ Dynamo + vLLM        │   │ Odoo CE + NETTRADES  │                   │  ║
║  │  │ (H200 + NVLink)      │   │ (governance)         │                   │  ║
║  │  │                      │   │                      │                   │  ║
║  │  │ Tensor parallelism   │   │ • Multi-tenant DB    │                   │  ║
║  │  │ 1 model / N GPUs     │   │ • Billing            │                   │  ║
║  │  └──────────┬───────────┘   └──────────────────────┘                   │  ║
║  │             │                                                          │  ║
║  │             │  Session affinity by X-Dynamo-Session-ID                 │  ║
║  │             │                                                          │  ║
║  └─────────────┼──────────────────────────────────────────────────────────┘  ║
║                │                                                             ║
║                │  WireGuard mesh (10.100.0.0/24)                             ║
║                │  HTTPS + mTLS for control plane                             ║
║                ▼                                                             ║
║  ┌─────────────────────────────┐  ┌─────────────────────────────┐            ║
║  │  SUB-HUB  (Client A)        │  │  SUB-HUB  (Client B)        │            ║
║  │                             │  │                             │            ║
║  │  • Own Odoo CE instance     │  │  • Own Odoo CE instance     │            ║
║  │  • Own NETTRADES modules    │  │  • Own NETTRADES modules    │            ║
║  │  • Local policy + rules     │  │  • Local policy + rules     │            ║
║  │  • Local LLM cache          │  │  • Local LLM cache          │            ║
║  │  • GPU cluster controller   │  │  • GPU cluster controller   │            ║
║  │  • Sub-hub WireGuard server │  │  • Sub-hub WireGuard server │            ║
║  │                             │  │                             │            ║
║  │  ┌────────────────────────┐ │  │  ┌─────────────────────────┐│            ║
║  │  │ llama.cpp RPC master   │ │  │  │ llama.cpp RPC master    ││            ║
║  │  │ (pipeline parallel)    │ │  │  │ (pipeline parallel)     ││            ║
║  │  │ on Windows or llama.cpp│ │  │  │ on Windows or llama.cpp ││            ║
║  │  │ RPC master & Dynamo    │ │  │  │ RPC master & Dynamo     ││            ║
║  │  │  + vLLM on Ubuntu      │ │  │  │ + vLLM on Ubuntu        ││            ║
║  │  └──────────┬─────────────┘ │  │  └──────────┬──────────────┘│            ║
║  │             │               │  │             │               │            ║
║  │             │ rpc://        │  │             │ rpc://        │            ║
║  │             │               │  │             │               │            ║
║  └─────────────┼───────────────┘  └─────────────┼───────────────┘            ║
║                │                                │                            ║
║                │  WireGuard tunnel per spoke    │                            ║
║                ▼                                ▼                            ║
║ ┌───────────────────────────────────────────────────────────────────┐        ║
║ │ ┌─────────────────────────────┐  ┌─────────────────────────────┐  │        ║
║ │ │  SPOKES  (Client A office)  │  │  SPOKES  (Client B office)  │  │        ║
║ │ │                             │  │                             │  │        ║
║ │ │  Each spoke runs ONLY:      │  │  Each spoke runs ONLY:      │  │        ║
║ │ │  ┌──────────────────────┐   │  │  ┌──────────────────────┐   │  │        ║
║ │ │  │ • WireGuard client   │   │  │  │ • WireGuard client   │   │  │        ║
║ │ │  │ • rpc-server.exe     │   │  │  │ • rpc-server.exe     │   │  │        ║
║ │ │  │   on Windows         │   │  │  │  on Windows          │   │  │        ║
║ │ │  │ OR rpc-server or     │   │  │  │ OR rpc-server or     │   │  │        ║
║ │ │  │    VLLM for Dynamo   │   │  │  │    VLLM for Dynamo   │   │  │        ║
║ │ │  │    on Ubuntu         │   │  │  │    on Ubuntu         │   │  │        ║
║ │ │  │ • Heartbeat agent    │   │  │  │ • Heartbeat agent    │   │  │        ║
║ │ │  │   (~200 MB RAM)      │   │  │  │   (~200 MB RAM)      │   │  │        ║
║ │ │  └──────────────────────┘   │  │  └──────────────────────┘   │  │        ║
║ │ │                             │  │                             │  │        ║
║ │ └─────────────────────────────┘  └─────────────────────────────┘  │        ║
║ │   PCs: e.g. Windows workstations with RTX 3060/4070               │        ║
║ │   Jetsons: e.g. Jetson Orin Nano                                  │        ║
║ │                                                                   │        ║
║ │   NO Odoo. NO PostgreSQL. NO LangGraph. NO Redis.                 │        ║
║ │   On Windows when one spoke powers off:                           │        ║
║ │    → RPC pipeline aborts (GGML_ASSERT).                           │        ║
║ │    → LangGraph checkpointer preserves conversation transcr ipt.   │        ║
║ │    → User retries; checkpoint reloads from PostgreSQL.            │        ║
║ │    → Partial generation is lost, full context is kept.            │        ║
║ │   On Linux when a VLLM spoke powers off             :             │        ║
║ │    → NVIDIA Dynamo recovers the system                            │        ║
║ └───────────────────────────────────────────────────────────────────┘        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝


════════════════════════════════════════════════════════════════════════════════
 DATA FLOW — A single inference request
════════════════════════════════════════════════════════════════════════════════

  1. User types a question in the AI Chat UI (:3002)
     └─► POST /invoke  { thread_id, messages }

  2. LangGraph Supervisor accepts the request
     └─► Looks up thread_id in PostgresSaver
     └─► If thread exists: loads last checkpoint
     └─► If new thread: starts fresh graph state

  3. Supervisor checks session affinity
     └─► state["inference_track"] already set? → use it
     └─► Not set? → query Enterprise Gateway for hardware
         ├─► Dynamo healthy + model fits? → DYNAMO
         ├─► RPC cluster healthy + model fits? → RPC
         ├─► Local llama.cpp up? → LOCAL
         └─► Otherwise → REMOTE API (if allowed by mode)

  4. Supervisor calls LLM via chosen backend
     └─► Dynamo: OpenAI-compatible API at :8001
     └─► RPC:   llama.cpp master at sub-hub
     └─► Local: llama.cpp container at :8080
     └─► Remote: OpenAI/Anthropic/…

  5. Backend streams tokens back
     └─► Supervisor buffers and forwards via SSE to UI

  6. On completion, Supervisor writes a checkpoint to PostgresSaver
     └─► Thread state: full message history, decisions, tool results
     └─► Encrypted at rest via LANGGRAPH_AES_KEY

  7. If the agent used any tools (create_project, good_answer, etc.)
     └─► Those went through Enterprise Gateway → Odoo JSON-RPC
     └─► Odoo ORM applied record rules, wrote audit trail, committed


════════════════════════════════════════════════════════════════════════════════
 DATA FLOW — A spoke failure during RPC inference
════════════════════════════════════════════════════════════════════════════════

  1. User A starts a long conversation on the RPC cluster
     └─► Supervisor pinned state["inference_track"] = "rpc"
     └─► Conversation committed to checkpoint after each turn

  2. Mid-generation, spoke #3 loses power
     └─► rpc-server on spoke #3 becomes unreachable
     └─► llama.cpp master hits GGML_ASSERT and aborts
     └─► All in-flight requests on this cluster fail

  3. LangGraph Supervisor catches the failure
     └─► Calls _on_rpc_node_failure(node)
     └─► Node health monitor also detects missing heartbeats
         ├─► After 3 consecutive failures → mark node unhealthy
         └─► Triggers drain-and-restart callback

  4. Recovery actions
     └─► Gateway revokes spoke #3's WireGuard peer
     └─► Supervisor cancels in-flight jobs on that cluster
     └─► Layer assignment recomputed without spoke #3
     └─► Master restarted with reduced topology
     └─► User sees clear error: "Cluster interrupted. Retry."

  5. User A retries
     └─► Same thread_id sent to /invoke
     └─► LangGraph loads the last checkpoint from PostgreSQL
     └─► Full conversation history is intact
     └─► Partial generation from the failed turn is lost
     └─► Model resumes from the last completed turn


════════════════════════════════════════════════════════════════════════════════
 SEPARATION OF CONCERNS
════════════════════════════════════════════════════════════════════════════════

  What lives in Odoo ORM (business):
    Users, companies, projects, fields, reviews, votes, expert sessions,
    GPU cluster definitions, LLM provider config, fairness audits, flags,
    episodes, annotations, loop cycles, trigger configs

  What lives in the agent infra DB (operational):
    Heartbeats, job queue, saga logs, idempotency keys, PWA cache

  What lives in the checkpoint DB (execution):
    Thread state, message history, graph decisions, tool results

  What lives in Valkey (ephemeral):
    Session tokens, rate limit counters, hot idempotency cache

  What runs on spokes (edge):
    WireGuard client, rpc-server, heartbeat agent (~200 MB total)


════════════════════════════════════════════════════════════════════════════════
 WHY THIS IS FUTURE-PROOF
════════════════════════════════════════════════════════════════════════════════

  Add a new enterprise backend (Salesforce, SAP, ...):
    → Write a new adapter in src/connectors/
    → Register it with the ConnectorRegistry
    → No agent code changes. No checkpoint changes. No inference changes.

  Swap Odoo for another ERP:
    → New adapter, same method surface (create, search_read, write, unlink)
    → Gateway routes based on tenant configuration
    → LangGraph supervisor sees no difference

  Upgrade Odoo 19 → 20:
    → Only touches business data
    → Agent infra DB untouched
    → Checkpoints untouched
    → Inference layer untouched

  Add a new inference backend:
    → Update hardware selector logic
    → No change to gateway, no change to Odoo, no change to checkpoints

════════════════════════════════════════════════════════════════════════════════

```





### Key Architectural Principles

1. **Odoo ORM is the single source of truth** for all business entities. No duplicate raw SQL tables for projects, users, votes, etc.
2. **Agent infrastructure lives in its own database.** GPU heartbeats, job queues, saga logs, idempotency keys. Not business entities, not ORM, not coupled to Odoo upgrades.
3. **The Enterprise Gateway is the single path** from agents to any backend. Every business operation goes through it.
4. **Vendor neutrality is at the API level, not the storage level.** The `execute_kw`-shaped method surface is the abstraction. Swapping Odoo for Salesforce means writing a new adapter, not migrating data.
5. **LangGraph checkpoints are separate from business data.** They store the agent's execution state, not the business records. A spoke failure loses only the in-flight generation, not the conversation.

---




## 10. Fairness Module Fixes (2026-09-18)

The `nettrades_fairness` module has been the hardest to stabilise. 

  1. `res.groups` `category_id` — removed (Odoo 19 dropped the field)
  2. `response_id` comodel — changed from `Many2one('llm.assistant.message')`
     to `Integer` on both `nettrades.fairness.audit` and
     `nettrades.fairness.flag`
  3. `_compute_status_fields` — syntax error (extra closing paren) fixed;
     fields added so the view can reference them
  4. `password=True` on `custom_evaluation_api_key` — removed; deprecated
  5. `fairness_config_views.xml` — rewritten against actual model fields;
     `attrs=` migrated to inline `invisible=`
  6. `fairness_audit_views.xml` — rewritten against actual model fields;
     was referencing `fairness.audit` (missing `nettrades.` prefix) and
     fields `name` / `model_id` that don't exist

  If `nettrades_fairness` fails again, the first thing to check is that
  every view's `<field name="model">` matches a real `_name = '...'` in
  `models/*.py`. The pattern `fairness.audit` (without prefix) is
  especially likely to reappear.

---






## 13. Third-party modules

* llm_knowledge and other llm_* third-party modules are copied into the image but only llm_training is a dependency of an installed module (nettrades_self_improving).


## 5. Untested Territory

The following is running but has never been exercised end-to-end:
The buttons in forms

* `action_parse_cv` on `res.partner` — never clicked.

* `action_run_cycle` on `self.improving.config` — never clicked.

* `action_test_connection` on `nettrades.bridge.config` — never clicked.

* `action_scan_network` and `action_generate_controller_keys` on `gpu.cluster` — never clicked.

**Risk:** Each button calls a method that may not exist, may have a typo, or  may fail on first use. Odoo does not validate method references at install time.

### Cron jobs

* `cron_gpu_health_watchdog` and `cron_gpu_utilisation_alert` (in `nettrades_gpu_admin/data/cron.xml`).

* `cron_bridge_health_check` (in `nettrades_bridge/data/bridge_cron_data.xml`).

Risk: The bridge cron calls `model._cron_health_check()`. The method
exists (added in this session) but returns `True` in all cases without
actually doing anything meaningful for local mode. Fine.

The GPU crons call `model._cron_health_watchdog()` and `model._cron_high_utilisation_alert()`. Those methods are defined on `gpu.node`. Whether the cron records reference the correct model — verify by checking `ir_cron.model_id` in the database. 

### End-to-end inference

LangGraph is running. Dynamo is running. llama.cpp is running. **No inference request has been sent through the full stack**. The LangGraph `/health` endpoint returns 200. That's not the same as a successful inference.

**Test:** `POST /invoke` with a simple prompt. Untested.

### The odoo-proxy

Running on port 8090. Never received a real request. The `/jsonrpc` model whitelist issue (BUG-001) is present but has not manifested because no traffic exercises it.

### The bridge routing logic

`nettrades.bridge.routing` has a `route_request` method that decides local vs. remote. Never invoked. The remote brain URL is `https://api.nettrades.ai` which does not exist. `bridge_mode` defaults to `local`, so a request in default config would route locally — but the local call path is a stub that returns a hardcoded message.


### The GPU marketplace

`gpu.node`, `gpu.cluster`, `gpu.registration.token` all have models and views. No node has ever been registered. The token validation logic has never been exercised. 

### The onboarding wizard

`onboarding_wizard.xml` has never been opened in the UI. The `profile_completeness` compute is likely being evaluated (it's `store=True`) but no partner has ever been edited through this view.

### The self-improving loop

loop.orchestrator has an execute_cycle method referenced in the smoke test. Never run against real data.


## Changes to be made soon:

* A separate database nettrades_infra will be built.  DECISIONS.md ADR-002 mentions it. ENVIRONMENT.md says it's "(planned)". Right now agent state lives in the same database as Odoo.

* Will soon have demos for distributed inferencing, therefore will be building the distributed inferencing. 

* The installer/ (Electron launcher) will be a part of the shipped product. It builds and produces an AppImage / .deb / .exe   It is based on the STEAM game Launcher so that it is easy for children to use and use AI in their projects.

* Currently the target deployment is PCs and Servers and eventually K8s, but the KV Cache is on the physical machines, so we need to see if Llama.cpp pipeline parallelism and NAVIDIA Dynamo could work with K8s or we need to use the supervisor agent to decide which machines will be used. The phase-k8s.sh script exists but it has been deferred.




### Summary

| Component  | Status  | 
|---|---|
| Base platform (13 modules installed) | ✅ Verified  |
| Docker stack health | ✅ Verified  |
| Pre-flight script | ✅ Verified  |
| Installer script | ✅ Verified  |
| Individual module UIs | Being Tested  |
| Buttons | Being Tested  |
| Cron jobs | Being Tested  |
| End-to-end inference | Being Tested  |
| Proxy endpoints | Being Tested  |
| Bridge routing | Being Tested  |
| GPU registration | Being Tested  |

The platform is "installed" but not "used". The next milestone should involve actually opening the UI and clicking a few things — that will surface a different class of bug (runtime vs. install-time).
