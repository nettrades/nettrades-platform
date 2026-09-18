# Architectural Decisions

Each entry is a decision that has been made, the alternatives considered,
and the reasoning. If a future contributor wants to revisit a decision,
they should read the entry first and understand why it was made.

Format: ADR (Architecture Decision Record), adapted from Michael Nygard.

---

## ADR-001 — Odoo ORM is the single source of truth for business data

**Date:** 2026-08 (revised 2026-09-17)
**Status:** Accepted

### Context
The platform stores business entities (users, companies, projects,
reviews, votes, expert sessions, fairness audits, training datasets).
Early prototypes kept parallel raw SQL tables (`nettrades_users`,
`nettrades_projects`, etc.) alongside the Odoo ORM tables
(`nettrades_user`, `nettrades_project`, etc.) to "decouple from Odoo".

### Decision
Business entities live ONLY in Odoo's ORM tables. The parallel raw SQL
tables are deleted from `init-db.sql` and never reintroduced.

### Consequences
- We get ACID transactions, record rules, audit trails, multi-company
  isolation, and field-level security for free.
- Upgrading Odoo requires migrating business data. But `OpenUpgrade`
  handles this — it is the standard process.
- Switching to Salesforce/SAP later requires re-implementing the ORM
  operations in an adapter. That is the correct place for vendor
  neutrality — at the API, not the storage.

### Alternatives considered
- **Raw SQL everywhere** — rejected because we would lose security,
  audit, and transaction guarantees. Reimplementing them is exactly
  what Odoo exists to avoid.
- **Both ORM and raw SQL in parallel** — rejected because nothing syncs
  them, foreign keys can't cross the boundary, and multi-company rules
  silently return zero rows when they compare `res.company` IDs to
  `nettrades_companies` IDs.

---

## ADR-002 — Agent infrastructure lives in a separate PostgreSQL database

**Date:** 2026-09-17
**Status:** Accepted

### Context
Agents produce operational telemetry: GPU heartbeats every 10 seconds,
inference job queue entries, PWA caches, saga coordination state,
idempotency keys. This data is not business data.

### Decision
The following tables live in a separate PostgreSQL database
(`nettrades_infra`), not in the Odoo DB:

    nettrades_gpu_nodes        — heartbeats, telemetry
    nettrades_queue_tasks      — inference job queue
    nettrades_pwa_cache        — offline agent cache
    nettrades_saga_log         — cross-system coordination state
    nettrades_compensation_registry — saga rollback actions
    nettrades_idempotency_keys — retry safety

### Consequences
- Odoo upgrades do not touch agent infrastructure.
- The agent infra DB is unaffected by which CRM/ERP the tenant uses.
- Backups can have different retention policies (heartbeats don't need
  90 days; business data does).
- Heartbeat traffic does not compete with Odoo queries.

### Alternatives considered
- **Store all in the Odoo DB** — rejected because it couples agent
  infrastructure to Odoo's schema. A `nettrades_gpu_nodes` table has
  nothing to do with a sales order; keeping them in the same DB would
  require coordinating every Odoo migration with every agent schema
  migration.

---

## ADR-003 — LangGraph checkpoints are separate from business data

**Date:** 2026-09-17
**Status:** Accepted

### Context
LangGraph persists agent execution state (message history, graph
decisions, tool results) to support resumption after failures. Where
should this live?

### Decision
Checkpoints live in their own PostgreSQL tables (`checkpoints`,
`checkpoint_writes`, `checkpoint_blobs`) managed by `PostgresSaver`.
They are not business data, and they are not routed through the
Enterprise Gateway.

### Consequences
- A spoke failure loses only the in-flight generation. The full
  conversation transcript survives.
- Checkpoints have their own retention policy (default 90 days).
- Checkpoints are encrypted at rest via `LANGGRAPH_AES_KEY`.
- Tenants are isolated by `thread_id` namespacing (e.g.
  `f"{tenant_id}:{user_thread_id}"`).

### Alternatives considered
- **Store checkpoints in Odoo tables** — rejected because the
  checkpointer is a database-level concern, not a business concern.
  Odoo's record rules would apply to checkpoint rows, which makes no
  sense — checkpoints are the agent's own memory, not business entities.
- **Store checkpoints in memory** — rejected because a process
  restart loses all conversation state.

---

## ADR-004 — The Enterprise Gateway is the single path to any business system

**Date:** 2026-09-17
**Status:** Accepted

### Context
Agents need to read/write business data. Early on, this went directly
to Odoo's JSON-RPC endpoint. When multi-tenancy and vendor neutrality
became requirements, we needed a control point.

### Decision
All agent → business-system communication goes through the Enterprise
Gateway (evolved from `odoo_proxy`). The gateway:

- validates API keys
- enforces rate limits
- enforces Red/Yellow/Green data flow mode
- routes to the correct backend per tenant
- forwards user identity (session token) to the backend
- coordinates cross-system sagas
- logs every call

### Consequences
- One place to enforce policy.
- One place to audit.
- One place to add new backends.
- The gateway is a critical path component. Its availability matters.

### Alternatives considered
- **Direct JSON-RPC from agents** — rejected because every agent would
  need to know about every backend.
- **One gateway per backend** — rejected because the saga coordination
  needs a single coordinator.

---

## ADR-005 — The Connector framework abstracts the API, not the storage

**Date:** 2026-09-17
**Status:** Accepted

### Context
The platform must work with Odoo today and Salesforce/SAP tomorrow.
How do we make that swap cheap?

### Decision
The `AbstractConnector` interface defines the method surface
(`authenticate`, `search`, `create`, `write`, `unlink`, plus
domain-specific methods). The gateway holds a `ConnectorRegistry`
that resolves a connector class per tenant. Each backend has its own
connector implementation. There is no shared storage layer.

### Consequences
- Adding a backend means writing one adapter, not refactoring the
  whole platform.
- The agent code is backend-agnostic — it calls `create_project`, not
  `odoo.jsonrpc.execute_kw`.
- MCP adapters fit the same interface. Future vendor MCP servers plug
  in without changes to the agent code.
- There is no "cross-backend join" — if a tenant uses Salesforce for
  CRM and SAP for ERP, cross-system operations use the saga pattern.

### Alternatives considered
- **A shared neutral data model in a separate DB** — rejected. This
  is what the parallel `nettrades_users` tables were trying to do.
  It duplicates business data, breaks referential integrity, and
  forces reimplementation of security and audit.

---

## ADR-006 — Hub / Sub-hub / Spoke physical topology

**Date:** 2026-08
**Status:** Accepted

### Context
The platform serves multiple tenants across multiple physical sites.
Centralising everything loses data sovereignty; distributing everything
loses manageability.

### Decision
Three-tier topology:

- **Hub** (`nettrades.ai`): central management, global marketplace,
  multi-tenant Odoo, Dynamo inference for data-centre tenants.
- **Sub-hub** (one per client company or network): local Odoo instance,
  local policy, WireGuard controller for its office, local RPC
  inference master.
- **Spokes** (per computer): WireGuard client, `rpc-server` (or a
  heartbeat agent), ~200 MB RAM. No Odoo, no PostgreSQL, no LangGraph.

### Consequences
- Client data stays on client hardware for on-prem workloads.
- The hub can serve tenants who want cloud deployment.
- Spokes contribute compute without needing operational complexity.
- The recovery model must work when spokes disappear (see ADR-007).

---

## ADR-007 — Three inference tracks with session affinity

**Date:** 2026-09-18
**Status:** Accepted

### Context
Inference hardware spans from data-centre H200s to office PCs that
may be switched off. A single inference strategy cannot serve all cases.

### Decision
Three tracks, selected in priority order:

1. **Dynamo** (data centre, tensor parallelism) — primary
2. **RPC cluster** (office PCs, pipeline parallelism) — office fallback
3. **Local llama.cpp** — single-machine fallback
4. **Remote API** — last resort, subject to Red/Yellow/Green mode

Once a conversation starts on a track, it stays there (session
affinity). The KV cache is not portable.

On track failure: **return an error, let the user retry**. LangGraph's
checkpointer preserves the conversation; only the partial generation
from the failed turn is lost.

### Consequences
- Conversations cannot be migrated between tracks. This is a hard
  constraint of the KV cache.
- A spoke power-off kills the whole RPC cluster's in-flight work.
  This is a known limitation of llama.cpp's RPC backend (it hard-aborts
  with `GGML_ASSERT`, no graceful recovery).
- The user-visible experience is: message, then an error, then a retry
  button. The full conversation is intact.

### Alternatives considered
- **Round-robin across tracks** — rejected because it would break
  KV cache locality and require re-warming on every turn.
- **Automatic failover mid-turn** — rejected because the partial
  generation cannot be transferred between backends.

---

## ADR-008 — Health monitor in LangGraph, not Odoo cron

**Date:** 2026-09-18
**Status:** Accepted

### Context
GPU nodes need continuous health monitoring. Where should the monitor
run?

### Decision
The monitor runs as an asyncio task inside the LangGraph service
(`src/core/node_health.py`). Probes every 10 seconds, marks unhealthy
after 3 consecutive failures, requires 2 successes to restore.

### Consequences
- Real-time detection (10s vs Odoo cron's 1-minute minimum).
- Health monitoring does not depend on Odoo being up.
- Probe traffic does not compete with business queries for Odoo
  resources.
- The monitor must coordinate with the supervisor's recovery callbacks.

### Alternatives considered
- **Odoo cron** — rejected for latency and coupling reasons.
- **A separate service** — rejected as over-engineering; the LangGraph
  service already runs continuously and has DB access.

---

## ADR-009 — WireGuard for all hub ↔ sub-hub ↔ spoke traffic

**Date:** 2026-08
**Status:** Accepted

### Context
The platform needs secure communication across untrusted networks
(public internet, office LANs).

### Decision
WireGuard, configured in three physically separate networks:

- Admin VPN: 10.10.0.0/24
- Internal RPC: 10.100.0.0/24
- Control plane: 10.200.0.0/24

The `nettrades_wireguard` module and `nettrades_bridge` module manage
peers from Odoo. The `wireguard-manager.sh` script is the source of
truth for the config on the hub.

### Consequences
- Spoke keys are generated on the spoke; private keys never leave.
- Registration is token-authenticated (`gpu.registration.token`).
- Peer revocation on node failure is a single API call.

---

## ADR-010 — Modules install in dependency order, one at a time

**Date:** 2026-09-17
**Status:** Accepted

### Context
Odoo module installation fails in confusing ways when dependencies are
missing. A batch install hides which module caused the failure.

### Decision
`install-modules.sh` installs one module at a time in a hardcoded
order (see HANDOFF.md §12). Each install has a 120-second timeout.
On failure, the script logs and continues (with `--auto`).

### Consequences
- Failures are isolated to one module.
- The log clearly shows which module failed and why.
- Adding a new module requires updating the order in the script.