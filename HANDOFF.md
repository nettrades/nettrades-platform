# NETTRADES Platform — Handoff to Next Context Window

**Created:** 2026-09-18
**Branch:** `dev-deployment1`
**Repository:** https://github.com/nettrades/nettrades-platform
**Current state:** 10 of 12 Odoo modules install. 2 remaining failures diagnosed.

---

## 1. Current Deployment State

### Installed and Working

| # | Module | Notes |
|---|---|---|
| 1 | `nettrades_core` | Core tables, users, companies, fields, reviews |
| 2 | `nettrades_queue` | Job queue adapter |
| 3 | `nettrades_notifications` | User notifications |
| 4 | `nettrades_llm_config` | Provider configuration (`nettrades.llm.company.config`) |
| 5 | `nettrades_ask_someone` | Expert sessions, qualified professionals |
| 6 | `nettrades_good_answer` | Voting, feedback, fine-tuning pipeline |
| 7 | `nettrades_fairness` | Rationality/bias scoring (syntax fixed) |
| 8 | `nettrades_data_collection` | Episodes, annotations, metrics |
| 9 | `nettrades_loop` | Self-improving cycle orchestration |
| 10 | `nettrades_self_improving_config` | Config UI |

### Still Failing

| Module | Blocker | Where to Look |
|---|---|---|
| `nettrades_gpu_admin` | `AssertionError: is_model_definition(model_def)` during model load | `models/*.py` — probably a class with conflicting `_name`/`_inherit` |
| `nettrades_bridge` | Cascades from `nettrades_gpu_admin` (it's a dependency) | Fix gpu_admin first |

### Not Yet Attempted

- `nettrades_onboarding`
- `nettrades_trigger` (partially there — this context didn't finish diagnosing)
- `nettrades_wireguard`
- `nettrades_recruitment` (planned)
- `nettrades_project` (planned)
- `nettrades_crm` (planned)
- `nettrades_marketplace` (planned)

---

## 2. Proposed Architecture

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

## 3. Instructions for the Next Context Window

### Immediate Priorities

1. **Fix `nettrades_gpu_admin`'s `AssertionError`.** This is the last hard blocker. Everything downstream (including `nettrades_bridge`) depends on it.
2. **Get all 12 modules installing** cleanly on a fresh DB.
3. **Rebuild the Launcher** and verify the Modules tab shows all 12 installed.

### How to Diagnose the gpu_admin AssertionError

The error is:
```
File "/usr/lib/python3/dist-packages/odoo/orm/model_classes.py", line 157, in add_to_registry
assert is_model_definition(model_def)
AssertionError
```


This fires when a class in a module's namespace inherits a base model but has an invalid `_name` / `_inherit` combination. Run these in order:

**Step A — Get the real traceback:**

```bash
cd ~/nettrades-platform
LATEST=$(ls -t logs/install-modules-*.log | head -1)
LINE=$(grep -n "nettrades_gpu_admin reinstall failed" "$LATEST" | head -1 | cut -d: -f1)
START=$((LINE - 150))
sed -n "${START},${LINE}p" "$LATEST"

```

Look for the class name in the frames just above add_to_registry. That names the offending model.

**Step B — Enumerate every model class in the module:**

```bash

cd ~/nettrades-platform
for f in odoo-modules/nettrades_gpu_admin/models/*.py; do
    echo "=== $f ==="
    grep -nE "^\s*class |^\s*_name|^\s*_inherit" "$f"
done
```

**Step C — Check for the known patterns that trigger the assertion:**

| Pattern | How to detect | Fix |
|---|---|---|
| `scripts/nettrades-setup.sh` | Master orchestrator (phases 0–5) | |

		
| Model defined twice (same `_name` in two files) | Duplicate `_name = '...'` across the module | Delete one, or change one to `_inherit` |
| Class `inherits models.Model, models.TransientModel` | Multiple bases | Choose one base |
| _inherit is a class object, not a string | `_inherit = SomeClass` | Change to `_inherit = 'model.name'` |
| Class inherits `models.AbstractModel` but declares `_name` matching an existing model | Grep model names | Rename or remove `_name` |
| A controller file contains a class inheriting from `models.Model` | `grep -rn "class.*models.Model" controllers/` | Move the model to `models/`, or change to a plain class |

**Step D — Check for cross-module clashes:**


```bash

cd ~/nettrades-platform
# Every _name declared anywhere in the codebase
for f in odoo-modules/*/models/*.py; do
    grep -H "_name = " "$f" 2>/dev/null
done | sed -E "s/.*_name = ['\"]([^'\"]+)['\"].*/\1/" | sort | uniq -d
```

Any output is a duplicate. Fix it.

## Known Issues That Are Already Fixed (Do Not Re-Fix)

Do NOT touch these — they're working:

* `nettrades_core` menu parent references (`menu_nettrades_root`)

* `nettrades_good_answer` CSV headers (`model_id:id`)

* `nettrades_fairness` `res.groups` `category_id` (removed)

* `nettrades_fairness` `_compute_status_fields` syntax (fixed)

* `nettrades_fairness` `response_id` type (`Integer` not `Many2one('llm.assistant.message')`)

* `nettrades_data_collection` `simulation.session` references (removed)

* `nettrades_data_collection` CSV (`model_simulation_dataset`)

* `nettrades_ask_someone` controller indentation on `return experts`

* `nettrades_loop` `company_id` (added)

* All `__init__.py` files — verified against actual folders

* All non-UTF-8 characters (normalized to ASCII)

* All CDATA in help fields (removed)

* All `res.groups` `category_id` references (removed)

Files That Are Sacred — Do Not Delete

* `scripts/prepare-odoo-addons.sh` — the fail-loud validator. Recently hardened.

* `scripts/install-modules.sh` — the ordered installer. Recently fixed.

* `odoo-modules/nettrades_core/models/nettrades_vote.py` — was missing; unblocks 10 modules.

* `odoo-modules/nettrades_ask_someone/security/nettrades_ask_someone_security.xml` — moved from core.

## 4. Troubleshooting Playbook for Remaining Modules

Use this when a module fails to install. The classes of error are finite; each has a signature.

### Error Class 1 — `No matching record found for external id 'model_xxx'`

**Symptom:**

```text

Exception: Module loading <mod> failed: file <mod>/security/ir.model.access.csv could not be processed:
No matching record found for external id 'model_xxx'

```

**Cause:** The CSV's `model_id:id` column references a model that doesn't exist, or the model's _name doesn't match.

**Fix:**

1.     Grep for the actual `_name` values in the module:
```bash

    grep -hE "^\s*_name\s*=" odoo-modules/<mod>/models/*.py | sed -E "s/.*'([a-z_.]+)'.*/\1/"
```
2. For each, the correct XML ID is `model_<name_with_underscores>`.

3. Update the CSV accordingly.

Recent examples fixed: `nettrades_good_answer`, `nettrades_data_collection`, `nettrades_llm_config`.

### Error Class 2 — `Field "X" does not exist in model "Y"`

**Symptom:**

```text

odoo.tools.convert.ParseError: while parsing .../views/<file>.xml
Error while validating view near:
    <field name="X"/>
Field "X" does not exist in model "Y"
```

**Cause:** A view references a field that the model doesn't declare.

**Fix — three options:**

1. **Rename in the view** — the field exists under a different name:

```bash

    grep -n "def _name\|= fields\." odoo-modules/<mod>/models/<model>.py | grep -i "keyword"
```

2. **Add the field to the model** if it's genuinely needed.

3. **Remove the field from the view** if it's obsolete.

**Recent examples fixed:** `last_audit_date` on `nettrades.fairness.config` (added as computed field), `response_id` on `nettrades.fairness.audit` (changed to Integer).

### Error Class 3 — `AssertionError: Field X with unknown comodel_name 'Y'`

**Symptom:**

```text

File ".../fields_relational.py", line 93, in setup_nonrelated
    assert self.comodel_name in model.pool, \
AssertionError: Field <model>.<field> with unknown comodel_name '<comodel>'

```

**Cause:** A Many2one, One2many, or Many2many field points at a model that isn't loaded.

**Fix — two options:**

1. **Add the module containing the comodel to** `depends`:

```bash

    grep -rn "_name = '<comodel>'" odoo-modules/

```

That tells you which module owns it. Add that module to depends.

2. **Change the comodel** to a model that's already loaded, or remove the field.

**Recent examples fixed:** `simulation.session` in `nettrades_data_collection`, `llm.assistant.message` in `nettrades_fairness`.


### Error Class 4 — `AssertionError` (bare) in `add_to_registry`

**Symptom:**

```text

File ".../model_classes.py", line 157, in add_to_registry
    assert is_model_definition(model_def)
AssertionError
```


**Cause:** A class in the module's namespace inherits a base model with an invalid _name / _inherit combination. **This is what's currently blocking** nettrades_gpu_admin.

**Fix:** See section 3 above for the full diagnostic flow. The most common causes:

* Model declared with _name twice

* Class inheriting both models.Model and models.TransientModel

* _inherit set to a Python class rather than a string

* Model name clashes with an already-loaded module

### Error Class 5 — ValueError: Invalid field 'X' in 'model'

**Symptom:**

```text

File ".../odoo/orm/models.py", line 4660, in create
    raise ValueError(f"Invalid field {field_name!r} in {self._name!r}")
ValueError: Invalid field 'X' in 'model'

```

**Cause:** Usually in an XML data file — a <record> or <field> that references a nonexistent field on the model. In res.groups specifically, Odoo 19 removed category_id.

**Fix:** Remove the invalid field reference from the XML.

**Recent example fixed:** `category_id` in `nettrades_fairness/security/fairness_security.xml` (three occurrences).

### Error Class 6 — Syntax errors

**Symptom:**

```text

SyntaxError: 'return' outside function
```

or

```text

SyntaxError: invalid syntax
```

**Cause:** Editing accidents — a `def` line was deleted, indentation was wrong, or a stray character crept in.

**Fix:** Run Python's parser on the file:

```bash

python3 -c "import ast; ast.parse(open('<file>').read())"
```

That gives you the exact line number.

Recent examples fixed: `nettrades_ask_someone/controllers/main.py`, `nettrades_fairness/models/fairness_config.py`.

### Error Class 7 — XML schema / RNG validation

**Symptom:**

```text

odoo.tools.convert: The XML file '<file>' does not fit the required schema!
AssertionError: Element odoo has extra content: <tag>, line N
```

**Cause:** The XML has a construct that Odoo 19's RelaxNG schema rejects. Common culprits:

    CDATA blocks in `<field name="help">` (must be plain XML)

    Deprecated `<tree>` tag (use `<list>` in Odoo 17+)

    Unescaped `<`, `>`, `&` inside attribute values (use `&lt;`, `&gt;`, `&amp;`)

**Fix:** Reorder, escape, or remove.

**Recent examples fixed:** `nettrades_core` view files (CDATA removed, `<tree>` → `<list>`).

### Error Class 8 — Duplicate XML ID

**Symptom:**

```text

Duplicate id '<xmlid>' in module <module>
```

**Cause:** Two files in the same module declare the same id on a <record>, <menuitem>, etc.

**Fix:**

```bash

grep -rn 'id="<xmlid>"' odoo-modules/<module>/
```

Remove one of them.

Recent example fixed: `menu_fairness_audit_log` declared in both `fairness_dashboard_views.xml` and `fairness_config_views.xml`.

### Error Class 9 — Non-UTF-8 characters

**Symptom:**

```text

UnicodeDecodeError: 'utf-8' codec can't decode byte 0x97 in position NNN
```

or

```text

grep: <file>: binary file matches
file: <file>: Non-ISO extended-ASCII text
```

**Cause:** A file was saved with Windows-1252 encoding instead of UTF-8. Usually from pasting from a browser or Word.

**Fix:** Run the normalization script (see scripts/normalize-encoding.py if it exists; otherwise re-save the file from WSL VS Code):

```bash

python3 -c "
from pathlib import Path
p = Path('<file>')
text = p.read_bytes().decode('cp1252', errors='replace')
for a, b in [('\u2014', '-'), ('\u2019', \"'\"), ('\u201c', '\"'), ('\u201d', '\"'), ('\u00d7', 'x')]:
    text = text.replace(a, b)
p.write_text(text, encoding='utf-8')
print('Fixed:', p)
"
```

### Error Class 10 — `Module not found` for a dependency

**Symptom:**

```text

module <mod>: <dep> is not installed
```

or the module silently fails with no visible error.

**Cause:** The depends list references a module that isn't installed and isn't in the install order.

**Fix:** Check install-modules.sh:

```bash

grep -A15 "MODULES=(" scripts/install-modules.sh
```

Add the missing dependency before the module that needs it.

## 5. Daily Workflow

Every time you edit a module and want to test:

```bash

cd ~/nettrades-platform

# 1. Verify the file parses (Python)

python3 -c "import ast; ast.parse(open('odoo-modules/<mod>/models/<file>.py').read())" && echo "OK"

# 2. Verify the file parses (XML)

python3 -c "import xml.etree.ElementTree as ET; ET.parse('odoo-modules/<mod>/views/<file>.xml')" && echo "OK"

# 3. Verify no non-ASCII crept in

grep -nP '[^\x00-\x7F]' odoo-modules/<mod>/models/<file>.py odoo-modules/<mod>/views/<file>.xml

# 4. Rebuild the deploy tree (validator will fail loudly if manifests drift)

./scripts/prepare-odoo-addons.sh --force

# 5. Restart Odoo (bind mounts must be re-attached after prepare)

cd deploy/docker
docker compose stop odoo && docker compose rm -f odoo && docker compose up -d odoo
sleep 12
cd ../..

# 6. Install just the module you changed

./scripts/install-modules.sh --force --auto --modules=<mod> 2>&1 | tail -30

# 7. If it fails, read the log

LATEST=$(ls -t logs/install-modules-*.log | head -1)
LINE=$(grep -n "Traceback\|AssertionError\|ValueError\|ParseError" "$LATEST" | head -1 | cut -d: -f1)
sed -n "$((LINE - 20)),$((LINE + 40))p" "$LATEST"

```


**Critical:** Always use `docker compose stop/rm/up`, not docker compose restart. The bind mount to `deploy/docker/odoo-modules/` references an inode. After `prepare-odoo-addons.sh` deletes and recreates the directory, the old inode is gone and `restart` doesn't re-attach. Stop/rm/up forces a fresh mount.

## 6. Key Files and Their Purpose

	

| Path | Purpose |
|---|---|
| `scripts/nettrades-setup.sh` | Master orchestrator (phases 0–5) |
| `scripts/prepare-odoo-addons.sh` | Copies modules to Docker build context, validates manifests (fails loudly) |
| `scripts/install-modules.sh` | Installs modules one at a time in dependency order |
| `scripts/audit-views.py` | Scans views for field-reference errors |
| `odoo-modules/` | Source of truth for Odoo modules |
| `deploy/docker/odoo-modules/` | Copy used by the Odoo container (rebuilt by prepare-odoo-addons.sh) |
| `deploy/docker/docker-compose.yaml` | Full stack definition |
| `deploy/docker/.env` | Generated secrets, domains, ports |
| `src/core/` | LangGraph supervisor, checkpointing, node health |
| `src/core/odoo_proxy/` | Enterprise gateway (connectors) |
| `installer/` | Electron launcher |
| `logs/install-modules-*.log` | Per-run install logs |


## 7. Launcher Notes

The Launcher (Electron app in `installer/`) has a **Modules** tab that reads module state from Odoo's `ir.module.module` table. If it shows modules as "Available" instead of "Installed", that's because the module install failed. Fix the module in Odoo, and the Launcher will show it correctly.

The Launcher's **System Check** tab runs `install-modules.sh` in the background. When it succeeds, all modules in the install list will be green.

The Launcher's **Deploy** tab offers five profiles (Sovereign in a Box, Sovereign AI Router, Production, Kubernetes, Custom). All current deployments use the first profile.

## 8. What to Do First in the Next Context

1. Read this file.

2. Run `git log --oneline -10` on `dev-deployment1` to see recent commits.

3. Fix the `nettrades_gpu_admin` `AssertionError` using section 3's diagnostic flow.

4. Get `nettrades_gpu_admin` and `nettrades_bridge` installing.

5. Try `nettrades_trigger`, `nettrades_onboarding`, `nettrades_wireguard` — they haven't been attempted.

6. Run the full 15-module install and confirm zero failures.

7. Rebuild the Launcher (`cd installer && npm run build:linux && npm start`) and verify all modules show green.

## 9. Contact Points for Deep-Dive Questions

| Topic | Where to Look |
|---|---|
| Odoo module structure | `docs/developer/building-odoo-modules.md` |
| Bridge architecture | `docs/developer/bridge-architecture.md` |
| LangGraph supervisor | `src/core/supervisor.py, docs/developer/langgraph-supervisor-state-machine.md` |
| Enterprise gateway | `src/core/odoo_proxy/main.py, src/connectors/*.py` |
| Hub/spoke topology | `docs/operations/deployment-perspective-network-diagram.md` |
| GPU admin | `odoo-modules/nettrades_gpu_admin/, docs/developer/nvidia-dynamo-integration.md` |
| Self-improving loop | `docs/developer/self-improving-loop.md` |


## 10. Fairness Module Fixes (2026-09-18)

The `nettrades_fairness` module has been the hardest to stabilise. Six
distinct issues have been fixed in this session:

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

## 11. Deprecation Warnings Being Ignored

The following warnings appear on every module load and are NOT causing
failures. Do not "fix" them unless you have a spare weekend:

  • `Model attribute '_sql_constraints' is no longer supported` —
    Odoo 19 renamed this to `models.Constraint`. The old form still
    works. Migration is a separate, low-priority task.

  • `@route(type='json') is a deprecated alias to @route(type='jsonrpc')` —
    In Odoo 19, `type='json'` still works but should become `type='jsonrpc'`.
    Fix in a future cleanup pass.

  • `Field nettrades.fairness.config.custom_evaluation_api_key: unknown
    parameter 'password'` — already fixed in this session by removing
    `password=True`. Will not appear after the next install.

  • `Missing not-null constraint on qualified_professional.verification_status` —
    Cosmetic. Add `required=True` to the field eventually. Not blocking.

  • `The model ask.someone.config has no _description` — Cosmetic.
    Add `_description` to the model class in `nettrades_ask_someone`.

---

## 12. Order to Install Modules (do not reorder)

The `scripts/install-modules.sh` file contains the correct order. The key
constraint: a module must come AFTER everything it depends on.

Verified dependency edges:

  nettrades_core          → (none)
  nettrades_queue         → (none)
  nettrades_notifications → nettrades_core
  nettrades_llm_config    → nettrades_core, llm
  nettrades_ask_someone   → nettrades_core, payment, mail
  nettrades_good_answer   → nettrades_core, llm, mail
  nettrades_fairness      → nettrades_core, nettrades_good_answer
  nettrades_data_collection → nettrades_core, nettrades_good_answer,
                              nettrades_ask_someone
  nettrades_loop          → nettrades_core, nettrades_data_collection
  nettrades_self_improving_config → nettrades_core,
                                     nettrades_data_collection,
                                     nettrades_loop
  nettrades_gpu_admin     → nettrades_core
  nettrades_bridge        → nettrades_core, nettrades_gpu_admin
  nettrades_trigger       → nettrades_data_collection
  nettrades_wireguard     → nettrades_core
  nettrades_onboarding    → nettrades_core

If you add a new module, add it to this list after all its dependencies.
