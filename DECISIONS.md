# Architectural Decisions

Each entry is a decision that has been made, the alternatives considered,
and the reasoning. If a future contributor wants to revisit a decision,
they should read the entry first and understand why it was made.

Format: ADR (Architecture Decision Record), adapted from Michael Nygard.

**Reading order:** ADR-001 through ADR-017 are numbered in the order the
decisions were made. They are not in dependency order. If you are new to
the codebase, read ADR-001, ADR-002, ADR-003, ADR-011, then the rest.

**Status legend:**

* **Accepted** — the decision holds; do not change without an ADR.

* **Accepted — revised** — the original text has been updated; the newer wording is authoritative.

* **Superseded by ADR-XXX** — historical only.
---

## ADR-001 — Business entities live in Odoo ORM; operational state lives in `nettrades_infra`

**Date:** 2026-08
**Revised:** 2026-09-17, 2026-11-05
**Status:** Accepted — revised (2026-11-05)

### Context

The platform stores two distinct kinds of data:

* Business entities — users, companies, partners, projects, reviews, votes, expert sessions, fairness audits, training datasets. These are edited by humans in the Odoo UI. They need record rules, audit trails, multi-company isolation, and field-level security.

* Operational state — GPU heartbeats, RPC topology, session bindings, saga state, idempotency keys, secrets, admin audit, egress audit. These are read and written only by services. They must survive an ERP swap without migrating.

Early prototypes kept parallel raw SQL tables (`nettrades_users`, `nettrades_projects`, etc.) alongside the Odoo ORM tables (`nettrades_user`, `nettrades_project`, etc.) to "decouple from Odoo". This failed: nothing synced them, foreign keys could not cross the boundary, and multi-company rules silently returned zero rows when they compared `res.company` IDs to `nettrades_companies` IDs.

### Decision

There is exactly one storage location per entity:

* Business entities live in Odoo ORM tables. This includes the `nettrades_*` models that must appear in the Odoo UI. Their `_auto` attribute is `True` (the default), so Odoo creates and owns the PostgreSQL table.

* Operational state lives in `nettrades_infra` (see ADR-002).

* LangGraph checkpoints live in their own database (see ADR-003).

* `init-db.sql` contains only extensions (`pgcrypto`, `vector`). It contains no business tables. The previous version of this file contained ~20 `CREATE TABLE nettrades_*` statements that duplicated ORM-managed tables; these are deleted.

### Consequences

* Odoo gives us ACID transactions, record rules, audit trails, multi-company isolation, and field-level security for free.

* Upgrading Odoo requires migrating business data — but `OpenUpgrade` handles this, and that is the standard process.

* An ERP swap (Salesforce, SAP) replaces the connector, not the operational state. The `nettrades_infra` tables stay put.

* The schema for `nettrades_infra` is defined in `init-infra.sql`. Its business schema counterpart is `init-db.sql`, which now only
    creates extensions.

### Alternatives considered

* Raw SQL business tables everywhere — rejected. We would lose security, audit, and transaction guarantees. Reimplementing them is exactly what Odoo exists to avoid.

* Both ORM and raw SQL in parallel — rejected for the reasons documented in the context.

* Move everything out of Odoo into `nettrades_infra` — rejected. Business entities genuinely benefit from Odoo's ORM. The right split is by data kind, not by preference.

## ADR-002 — `nettrades_infra` is the operational system of record

**Date:** 2026-09-17
**Revised:** 2026-11-05
**Status:** Accepted — revised (2026-11-05)

### Context

Agents and services produce operational telemetry that is not business data: GPU heartbeats every 10 seconds, inference job queue entries, saga coordination state, idempotency keys, admin action audit, egress audit, and operator secrets.

### Decision

The following tables live in a separate PostgreSQL database (`nettrades_infra`), not in the Odoo DB:

| Table | Purpose | Added |
| `nettrades_rpc_cluster` | RPC topology snapshots | 2026-09 |
| `nettrades_rpc_node` | RPC worker membership | 2026-09 |
| `nettrades_session_binding` | thread → track pinning | 2026-09 |
| `nettrades_failure_log` | Failover audit trail | 2026-09 |
| `nettrades_saga_log` | Cross-system coordination state | 2026-11 |
| `nettrades_idempotency_keys` | Retry safety | 2026-11 |
| `nettrades_secrets` | Encrypted operator secrets | 2026-11 |
| `nettrades_secrets_audit` | Secret access audit | 2026-11 |
| `nettrades_admin_audit` | Admin console action log | 2026-11 |
| `nettrades_egress_audit` | Outbound connection log | 2026-11 |

The schema is defined in  `init-infra.sql`.

### Consequences

* Odoo upgrades do not touch agent infrastructure.

* The infra DB is unaffected by which CRM/ERP the tenant uses.

* Backups can have different retention policies per database: heartbeats need days, business data needs 90+ days.

* Heartbeat traffic does not compete with Odoo queries for connection pool slots or CPU.

* Secrets are not in `.env` (except bootstrap) and not in `ir.config_parameter` (which is cleartext and included in every database dump).

### Alternatives considered

* Store all in the Odoo DB — rejected. It couples agent infrastructure to Odoo's schema. A `gpu.node` heartbeat has nothing to do with a sales order; keeping them in the same DB would require coordinating every Odoo migration with every agent schema migration.

* Keep secrets in `.env` — rejected. `.env` is plaintext on disk, copied into images, dumped in backups, and has no access control or rotation story. See ADR-015.

* Keep secrets in `ir.config_parameter` — rejected. It is a cleartext database table readable by any user with Settings access, and it is included in every database dump.

## ADR-003 — LangGraph checkpoints are independent of the ERP

**Date:** 2026-09-17
**Status:** Accepted

### Context

LangGraph persists agent execution state (message history, graph decisions, tool results) to support resumption after failures. Where should this live?

### Decision

Checkpoints live in their own PostgreSQL database (`checkpoints`), managed by `AsyncPostgresSaver`. Tables: `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`.

The checkpointer is instantiated against `checkpoints`, not `odoo`.

### Consequences

* A spoke failure loses only the in-flight generation. The full conversation transcript survives.

* Checkpoints have their own retention policy (default 90 days).

* Checkpoints are encrypted at rest via `LANGGRAPH_AES_KEY`.

* Tenants are isolated by `thread_id` namespacing (e.g. `f"{tenant_id}:{user_thread_id}"`).

An ERP swap does not require migrating checkpoint data.

### Alternatives considered

* Store checkpoints in Odoo tables — rejected. The checkpointer is a database-level concern, not a business concern. Odoo's record rules would apply to checkpoint rows, which makes no sense — checkpoints are the agent's own memory, not business entities.

* Store checkpoints in memory — rejected. A process restart loses all conversation state.

## ADR-004 — The Enterprise Gateway is the single path to any business system

**Date:** 2026-09-17
**Status:** Accepted

### Context

Agents need to read/write business data. Early on, this went directly
to Odoo's JSON-RPC endpoint. When multi-tenancy and vendor neutrality
became requirements, we needed a control point.
Decision

All agent → business-system communication goes through the Enterprise
Gateway (`odoo-proxy`). The gateway:

* validates API keys with rate limiting

* enforces the model whitelist (BUG-001 fix)

* enforces Red/Yellow/Green data-flow mode

* routes to the correct backend per tenant (via `ConnectorRegistry`,
    see ADR-005)

* selects the transport (JSON-2 vs JSON-RPC) per backend version
    (see ADR-012)

* coordinates cross-system sagas

* logs every call

* forwards the session identity to the backend

### Consequences

* One place to enforce policy.

* One place to audit.

* One place to add a new backend.

* The gateway is on the critical path. Its availability matters. It runs as its own container with a healthcheck.

### Alternatives considered

* Direct JSON-RPC from agents — rejected. Every agent would need to know about every backend.

* One gateway per backend — rejected. Saga coordination needs a single coordinator.

## ADR-005 — The connector framework abstracts the API, not the storage

**Date:** 2026-09-17
**Status:** Accepted

### Context

The platform must work with Odoo today and Salesforce/SAP tomorrow. 

How do we make that swap cheap?

### Decision

The `AbstractConnector` interface defines the method surface (`authenticate`, `search`, `create`, `write`, `unlink`, plus domain-specific methods). The gateway holds a `ConnectorRegistry` that resolves a connector class per tenant. Each backend has its own connector implementation.

There is no shared neutral storage layer.

### Consequences

* Adding a backend means writing one adapter, not refactoring the whole platform.

* Agent code is backend-agnostic — it calls `create_project`, not `odoo.jsonrpc.execute_kw`.

* MCP adapters fit the same interface. Future vendor MCP servers plug in without changes to the agent code.

* There is no cross-backend join. If a tenant uses Salesforce for CRM and SAP for ERP, cross-system operations use the saga pattern.

* The connector is version-aware (see ADR-012) so a customer on Odoo 16 is supported alongside a customer on Odoo 20 by the same code.

Alternatives considered

* A shared neutral data model in a separate DB — rejected. This is what the parallel `nettrades_users` tables were trying to do. It duplicates business data, breaks referential integrity, and forces reimplementation of security and audit.

* One connector per backend version — rejected. It multiplies maintenance without improving correctness. One version-aware connector with protocol negotiation is simpler.

## ADR-006 — Hub / Sub-hub / Spoke physical topology

**Date:** 2026-08
**Status:** Accepted

### Context

The platform serves multiple tenants across multiple physical sites. Centralising everything loses data sovereignty; distributing everything loses manageability.

### Decision

Three-tier topology:

* Hub (`nettrades.ai`): cross-tenant federation, marketplace, central management, Dynamo inference for data-centre tenants. Does not hold tenant business data.

* Sub-hub (one per client company or network): local Odoo connector, local policy, local inference master, local admin console, WireGuard controller for its office network.

* Spokes (per computer): `rpc-server` per GPU, heartbeat agent. No Odoo, no PostgreSQL, no LangGraph. ~200 MB RAM.

### Consequences

* Client data stays on client hardware for on-prem workloads.

* The hub can serve tenants who want cloud deployment.

* Spokes contribute compute without operational complexity.

* The recovery model must work when spokes disappear (see ADR-007).

### Alternatives considered

* Single-tier (everything on the hub) — rejected. Loses data sovereignty.

* Two-tier (hub + spoke, no sub-hub) — rejected. Loses local policy and local admin.

## ADR-007 — Three inference tracks with session affinity and fail-loud failover

**Date:** 2026-09-18
**Status:** Accepted

### Context

Inference hardware spans from data-centre H200s to office PCs that may be switched off. A single inference strategy cannot serve all cases.

### Decision

Four tracks, selected in priority order:

* Dynamo (data centre, tensor parallelism) — primary

* RPC cluster (office PCs, pipeline parallelism) — office fallback

* Local llama.cpp — single-machine fallback

* Remote API — last resort, subject to Red/Yellow/Green mode

Once a conversation starts on a track, it stays there (session affinity). The KV cache is not portable.

On track failure, the supervisor evaluates the six-tier failover

hierarchy:

* Promote a warm spare (model cached, VRAM sufficient)

* Fall back to Dynamo (if `allow_dynamo_fallback`)

* Rebuild RPC with surviving workers (if `allow_rpc_partial_fallback`)

* Route to marketplace (if `allow_marketplace_fallback`)

* Route to external API (if `allow_external_api_fallback`)

* Fail loud — raise `ClusterRecovering`, return HTTP 503 with `Retry-After: 30`

Tier 6 is terminal and cannot be disabled. The platform never silently downgrades to a smaller model. See `FAILOVER-HIERARCHY.md`.

### Consequences

* Conversations cannot be migrated between tracks. This is a hard constraint of the KV cache.

* A spoke power-off loses the in-flight turn, but the conversation transcript survives via the checkpointer.

* The user-visible experience at Tier 6 is: message, then an explicit error with a countdown, then a retry button. The conversation continues from the last completed turn.

* `ClusterRecovering` is not counted by the circuit breaker. If it were, a burst of RPC requests would open the breaker and block Dynamo and local traffic during RPC recovery. See `invoke.py` and `supervisor.py`.

### Alternatives considered

* Round-robin across tracks — rejected. Breaks KV cache locality and requires re-warming on every turn.

* Automatic failover mid-turn — rejected. The partial generation cannot be transferred between backends.

* Silent downgrade to local llama.cpp — rejected. Produces visibly worse answers mid-conversation, which users interpret as a bug.

## ADR-008 — Health monitor in the LangGraph service, not Odoo cron

**Date:** 2026-09-18
**Status:** Accepted

### Context

GPU nodes need continuous health monitoring. Where should the monitor run?

### Decision

The monitor runs as an asyncio task inside the LangGraph service (`src/core/node_health.py`). Two signals:

* Push heartbeat — the spoke agent POSTs every 10 seconds to `POST /nodes/heartbeat` on the LangGraph service. Works behind NAT.

* Pull probe — the monitor HTTP-GETs each node's `/health` every 10 seconds. Only for nodes with HTTP endpoints; bare TCP probes of RPC workers were removed because they left the 1-deep accept queue stuck.

Marks a node unhealthy after 3 consecutive failures (or a heartbeat older than 30 seconds). Restores it after 2 consecutive successes.

Writes durable heartbeats to `nettrades_infra.nettrades_rpc_node`.

### Consequences

* Real-time detection (10s vs Odoo cron's 1-minute minimum).

* Health monitoring does not depend on Odoo being up.

* Probe traffic does not compete with business queries for Odoo resources.

* The monitor coordinates with the supervisor's recovery callbacks via `_on_rpc_node_failure`.

### Alternatives considered

* Odoo cron — rejected for latency and coupling reasons.

* A separate service — rejected as over-engineering. LangGraph already runs continuously and has DB access.

* TCP probes of RPC workers — rejected after the 2026-10-28 incident. The bare TCP connect never sends the ggml handshake, so the worker blocks in `recv()` and the accept queue fills with phantom connections.

## ADR-009 — WireGuard for all cross-network traffic

**Date:** 2026-08
**Status:** Accepted

Context

The platform needs secure communication across untrusted networks (public internet, office LANs).

### Decision

WireGuard, configured in three physically separate networks:

* Admin VPN: `10.10.10.0/24` (operator SSH access)

* Internal RPC: `10.100.0.0/24` (RPC master ↔ spoke)

* Control plane: `10.200.0.0/24` (heartbeat, admin API)

Spoke private keys are generated on the spoke and never leave. Registration is token-authenticated (`gpu.registration.token`). Peer revocation on node failure is a single API call.

The Windows service implements the tunnel via the official `tunnel.dll` embeddable service (`WireGuardTunnel$NETTRADES`).

### Consequences

* Secure communication across untrusted networks.

* Peer management is scriptable from Odoo or the admin console.

* The `nettrades_wireguard` Odoo module is optional; the `wireguard-manager.sh` script is the source of truth on the hub.

### Alternatives considered

* SSH tunnels — rejected. Not mesh; not designed for multi-peer.

* Tailscale / ZeroTier — rejected. External coordination server conflicts with the sovereign requirement.

## ADR-010 — Modules install in dependency order, one at a time

**Date:** 2026-09-17
**Revised:** 2026-11-05
**Status:** Accepted — revised (2026-11-05)

### Context

Odoo module installation fails in confusing ways when dependencies are missing. A batch install hides which module caused the failure.

### Decision

`install-modules.sh` installs one module at a time in a hardcoded order. Each install has a 120-second timeout.

On failure, the script exits non-zero. The previous behaviour — log and continue, then exit 0 — made a broken install look like a success to any caller that checked the exit code. That was the direct cause of the "14 modules failed but the script said OK" bug in October 2026.

The --auto flag suppresses the interactive prompt. It does not suppress failure propagation.

No third-party module is required for the platform to boot (see ADR-011 and ADR-012). If `llm_openai` or `queue_job` fails to install, the platform runs on env-var config for LLM and on a `src/core` job queue. The module is installed later, or not at all.

### Consequences

* Failures are isolated to one module.

* The exit code reflects reality.

* Adding a new module requires updating the order in the script.

* A missing third-party module degrades a feature, not the platform.

### Alternatives considered

* Continue on failure — rejected. It hid bugs.

* Batch install — rejected. It cannot isolate the failing module.

## ADR-011 — Odoo is a connector, not the platform core

**Date:** 2026-11-05
**Status:** Accepted

### Context

Odoo 20 introduced AI features that run through Odoo's IAP servers (`iap.odoo.com`) on a metered credit model, even for on-premise customers. The "bring your own key" escape hatch that Odoo 19 offered was removed. Odoo's own partner programme pays recurring commission on Enterprise subscriptions. If NETTRADES is built "inside Odoo", every customer conversation becomes a conversation about Odoo Enterprise, Odoo IAP credits, and Odoo's AI roadmap.

The platform's differentiators are not in the ERP layer. They are in:

* Sovereign inference (customer's own GPUs, no meter, no data egress).

* Fail-loud failover across heterogeneous hardware.

* Multi-ERP orchestration (Odoo, Salesforce, SAP in the same tenant).

None of those require Odoo to be the core.

### Decision

Odoo is the default business-document connector, not the platform core. The platform core is:

* `src/core` — supervisor, scheduler, health monitor, routing, connectors, secrets, admin API

* `nettrades_infra` — operational state

* `nettrades-ui` — chat, admin, backup/restore

* The inference fabric — Dynamo, RPC, local, remote

A tenant may run Odoo 16, Odoo 19, Odoo 20, Salesforce, or SAP. The supervisor's routing decisions do not change.

### Consequences

* The platform can be sold without requiring Odoo.

* Odoo's AI monetisation does not become NETTRADES' AI monetisation.

* The connector layer is the product surface for ERP integration.

* Odoo upgrades affect only the connector, not the platform.

* Future ERP features that Odoo ships natively (agents that create records, MCP, AI Fields) become optional enhancements, not blockers.

### Alternatives considered

* Stay "inside Odoo" — rejected. The platform becomes a funnel for Odoo's paid tiers, and inherits Odoo's release cadence and pricing.

* Drop Odoo entirely — rejected. Odoo gives us real business documents (partners, invoices, HR, projects) with security and audit for free. The right move is to demote it, not delete it.

## ADR-012 — Version-aware Odoo connector with protocol detection

**Date:** 2026-11-05
**Status:** Accepted (implementation pending)

### Context

Odoo has shipped one major version per year for eleven years. The
External API has changed:

* `/xmlrpc` and `/xmlrpc/2` — legacy, removed in Odoo 20

* `/jsonrpc` with `execute_kw` — supported through Odoo 21, removed in Odoo 22 (fall 2028) and Online 21.1 (winter 2027)

* `/json/2/{model}/{method}` — introduced in Odoo 19, the forward path

A connector that assumes one protocol will break at a fixed date. Customers will not all upgrade on the same day. Both must be supported for the foreseeable future.

### Decision

A single `OdooConnector` detects the server version on first contact via `/web/webclient/version_info` (unauthenticated, always available), then selects the transport:

* Odoo 19+ → JSON-2: `POST /json/2/{model}/{method}` with Bearer API key, named arguments only.

* Odoo 8–18 → JSON-RPC: `POST /jsonrpc` with `execute_kw`.

* Odoo < 8 → XML-RPC.

The detected protocol is cached on the profile. On a version-mismatch error, it re-detects.

Multi-instance profiles are supported: each profile has its own URL, database, credentials, and protocol. A customer running Odoo 16 for HR and Odoo 20 for finance can connect to both.

New development always targets JSON-2.

### Consequences

* One connector codebase supports Odoo 8–20.

* A customer on Odoo 16 is not forced to migrate to be supported.

* The Odoo 22 deadline is a transport change, not a module rewrite.

* The odoo-proxy gains a `/json/2/{model}/{method}` endpoint that forwards to Odoo using `ODOO_SERVICE_API_KEY` (already present in `main.py`).

* Every call site in `rpc_scheduler.py`, `supervisor.py`, and `odoo_tools.py` migrates to the connector.

### Alternatives considered

* One connector per version — rejected. Multiplies maintenance without improving correctness.

* JSON-RPC only until Odoo 22 — rejected. It defers the change rather than making it. The customer will still pay for it at the deadline.

* JSON-2 only — rejected. It breaks every customer on Odoo ≤ 18.

## ADR-013 — Admin console in `nettrades-ui` with step-up auth and audit

**Date:** 2026-11-05
**Status:** Accepted (implementation partially complete)

### Context

The Electron Launcher cannot run on a headless sub-hub. A separate `web-launcher` container was proposed; it duplicates authentication, has its own session store, and cannot share the audit trail.

`nettrades-ui` already exists, already has session handling (via `odoo-proxy/auth.py` with Valkey-backed sessions), and is already routed through Traefik.

### Decision

The admin console is an `/admin` router in `nettrades-ui`, not a separate container. It:

* requires `session['user']` and membership of `nettrades_gpu_admin.group_gpu_administrator`

* reuses the Electron Launcher's Backup tab HTML/JS; `window.api.*` is replaced by `fetch('/admin/api/*'`)

* requires step-up re-authentication (fresh password or passkey assertion, server-enforced) for destructive actions: restore, module install, container removal. Container restart does not require it.

* writes exactly one row per action to `nettrades_infra.nettrades_admin_audit`: actor, action, target, before state, after state, outcome, IP, timestamp

* uses secure session cookies (`HttpOnly`, `Secure`, `SameSite=Strict`)

* enforces CSRF protection on all state-changing endpoints

* is gated by `ADMIN_WEB_ENABLED` in `.env` (default `true` on sub-hubs, false on spokes)

### Consequences

* One authentication system, one audit trail, no duplicated auth.

* A compromised browser session cannot perform a destructive action without the second factor.

* The Electron Launcher and the web admin share the same backend. The logic is written once and mounted twice.

* The `web-launcher` container is not built. If a future requirement needs a separate surface (e.g., a customer portal), it reuses the same router rather than duplicating auth.

### Alternatives considered

* Separate `web-launcher` container — rejected. Duplicated auth, wrong OAuth endpoints (OCA `auth_oidc` paths not present in standard Odoo), missing CSRF, missing template. Reviewed and discarded 2026-11-03.

* Reuse the Odoo web UI for admin — rejected. Odoo's UI is ERP-shaped; the platform admin surface (cluster, tokens, backup, audit) does not map to it.

## ADR-014 — Backup via restic, extended in place

**Date:** 2026-11-05
**Status:** Accepted (implementation complete, destination not yet configured)

### Context

The existing `backup.sh` writes a compressed archive to the same filesystem as the database. If that filesystem fails, both the database and its backup are lost. The local tar is also unencrypted: 
it contains `.env` (all secrets) and the database dump (all business data, and for a medical customer, all PHI).

Mature backup products (BombVault, OpenPanel) expose a destination wizard: a type selector (S3-compatible / SFTP / WebDAV / SMB / local or network folder / rclone remote), the credential fields for that type, and a "Test Connection" step before scheduling. A network folder is just a mounted path to restic.

### Decision

Extend the existing scripts; do not create a parallel `backup-offhost.sh`.

* `backup.sh --remote` uploads to `BACKUP_REPOSITORY` via restic after the local backup completes. If `BACKUP_REPOSITORY` is empty, `--remote` is a no-op with a warning.

* `restore.sh --from-remote [--snapshot=<id>]` downloads a snapshot from `BACKUP_REPOSITORY` into a temp directory, then runs the existing restore path with the downloaded file.

* `BACKUP_REPOSITORY` is a generic restic URL. No vendor is baked in.

* `BACKUP_PASSWORD` is generated by phase-env.sh alongside the other secrets, displayed once with an explicit loss warning.

* `backup.sh` writes a Prometheus textfile metric `nettrades_backup_last_success_timestamp` on every successful local backup. The `BackupTooOld` alert fires if it goes stale by 24 hours.

* The UI (Electron Backup tab and web `/admin` backup view) exposes the destination type selector, credential fields, "Test Connection", and a snapshot list. Both surfaces share the same HTML/JS.

### Consequences

* One backup code path, one restore code path.

* The customer can point backups at their own storage, including a network folder (which is just a mounted path to restic).

* Backups are client-side encrypted. A copy of the archive does not reveal its contents.

* Losing `BACKUP_PASSWORD` means losing the remote backups. This is stated in the UI, in `phase-env.sh`, and in     `docs/developer/runbook-postgres.md`.

* Local backups remain unencrypted by default. Excluding .env from the local tar is a future refinement.

### Alternatives considered

* New `backup-offhost.sh` script — rejected. Duplicates logic, produces two cron entries, two retention policies, two places to fix when a bug is found.

* `rsync` to a remote — rejected. No encryption, no deduplication, no incremental metadata.

* `s3 cp` — rejected. No encryption at rest beyond what the provider offers, no deduplication, no retention policy.

* Backblaze B2 hardcoded — rejected. Customer's storage is unknown; the repository URL is a configuration, not a default.

## ADR-015 — Secrets in encrypted `nettrades_infra`, not `.env` or `ir.config_parameter`

**Date:** 2026-11-05
**Status:** Accepted (implementation pending)

### Context

`.env` is unencrypted plaintext on disk, copied into images, dumped in backups, and has no access control, no rotation mechanism, and no audit trail. It is appropriate for development and for bootstrap secrets that must exist before the database, but not for operator secrets that change over time.

Odoo's `ir.config_parameter` is a cleartext database table, readable by any user with Settings access, and included in every database dump. It is worse than `.env`, not better.

The industry split is:

* Full secret manager (HashiCorp Vault, AWS Secrets Manager) — enterprise-grade, requires infrastructure.

* Database encryption with a key outside the database (Archestra, OCA `data_encryption`) — pragmatic middle ground.

### Decision

* .env holds bootstrap secrets only: `POSTGRES_PASSWORD`, `NETTRADES_SECRETS_KEY`, `LANGGRAPH_API_KEY`, `PROXY_API_KEY`.

* Operator-configurable secrets (backup credentials, storage keys, LLM provider keys, mode config) live in `nettrades_infra.nettrades_secrets`, AES-256-GCM encrypted with `NETTRADES_SECRETS_KEY`.

* `ir.config_parameter` is never used for secrets.

* A future Vault connector stores a reference in `nettrades_infra` and fetches the value from Vault on demand. Vault is optional; it is not a dependency.

* `nettrades_secrets_audit` logs every read and write.

### Consequences

* A database dump alone does not reveal the secrets.

* `.env` shrinks to four values.

* Secret rotation is a write to `nettrades_secrets`, not a file edit and container restart.

* The encryption key is a single point of failure. Losing `NETTRADES_SECRETS_KEY` means losing the ability to decrypt any secrets stored in the database. Rotation is a documented procedure (rewrap all values under the new key, then discard the old).

### Alternatives considered

* Keep everything in `.env` — rejected. It is worse than `ir.config_parameter` only by degree.

* Keep everything in `ir.config_parameter` — rejected. Cleartext and included in every backup.

* Vault as a hard dependency — rejected. It is a heavy infrastructure requirement for the demo and for the first hundred customers. The Vault connector is a future enhancement.

## ADR-016 — Source-Available (`BUSL-1.1` → `Open RAIL-S`) plus commercial license, with ethical override and mandatory CLA

**Date:** 2026-11-05
**Revised:** 2026-11-27
**Status:** Accepted — revised (2026-11-27)

### Context

The project requires a licensing structure that achieves four objectives simultaneously:
1. **Unconditional Ethical Governance:** `ETHICAL-STATEMENT.md` must legally override all public and commercial uses, automatically revoking rights upon prohibited or harmful deployment (which `AGPL-3.0` legally forbids).
2. **Frictionless Adoption for Individuals, SMEs & Public Educational Institutions and Hospitals:** Households, developers, small businesses (up to 1 Sub-Hub and 5 Spokes), schools, colleges, universities, charities and hospitals must be able to run the platform locally at zero cost without copyleft contamination.
3. **Commercial Protection Against Cloud Free-Riding:** Large enterprises (> 5 Spokes) and commercial cloud/SaaS providers must not be able to host or rescale the platform commercially without a paid Commercial License.
4. **Long-Term Openness with Permanent Ethics:** After 4 years, older releases transition to a permissive, responsible AI license rather than a copyleft license that strips ethical restrictions.

Dual/multi-tier licensing requires **NETTRADES LIMITED (UK Company No. 08160657)** to hold full relicensing rights over every contribution via a mandatory Contributor License Agreement (`Contributor-License-Agreement.md`).

### Decision

* **Master License (`LICENSE.txt`):** All original code is licensed under **NETTRADES Source-Available License 1.0 (based on `BUSL-1.1`)**, strictly conditioned upon continuous compliance with `ETHICAL-STATEMENT.md` and prohibiting unauthorized AI model scraping/training.
* **Free Additional Use Grant:** Production use is permitted free of charge for:
  * Households, independent developers, and small businesses operating up to **1 Sub-Hub and 5 Spokes** (including internal Odoo, Salesforce, and SAP integrations).
  * Accredited schools, colleges, universities, registered charities, non-profit research institutes, and public/non-profit hospitals (including NHS bodies) at **unlimited scale**.
  * Independent developers building and packaging AI agents for the official NETTRADES Marketplace.
* **4-Year Transition (`Change License`):** Four (4) years after each version's public release, it transitions to the **AI Pubs Open RAIL-S License v1.0** (incorporating `ETHICAL-STATEMENT.md` as mandatory Attachment A) alongside NETTRADES LIMITED's ongoing Commercial License offering, ensuring ethical restrictions remain permanently binding.
* **Commercial License (`COMMERCIAL-LICENSE.md`):** Large enterprises (> 5 Spokes) and commercial hosted/SaaS providers require a paid Commercial EULA from **NETTRADES LIMITED**.
* **Mandatory CLA:** Every contributor must sign `Contributor-License-Agreement.md` (enforced via CLA Assistant in CI) before any PR is merged.
* **Patent Strategy (`LEGAL/PATENTS.md`):** Patent applications are filed by **NETTRADES LIMITED** prior to public disclosure (protecting absolute-novelty jurisdictions such as the UK and EU). Public `BUSL-1.1` / `Open RAIL-S` users receive only a narrow, revocable conditional patent license strictly bound to their permitted scope and `ETHICAL-STATEMENT.md`.
* **Claimed Mechanisms:** VRAM-proportional layer assignment with a hard fail-loud threshold; heterogeneous vendor pinning with per-GPU RPC workers and HSA override; warm-spare promotion with pipeline-parallel capacity matching; session-pinned inference with checkpointed recovery and draining heartbeat.

### Consequences

* `ETHICAL-STATEMENT.md` legally overrides all public, institutional, and commercial deployments—closing the AGPL-3.0 ethical loophole.
* Hospitals, universities, and SMEs can adopt NETTRADES without AGPL network-copyleft compliance blockers.
* Cloud giants cannot resell NETTRADES as a competing managed service for 4 years without a Commercial License.
* All IP ownership, patent filings, and CLA assignments are unified under **NETTRADES LIMITED (UK Company No. 08160657)** under the laws of England and Wales.

### Alternatives considered

* **GNU AGPL-3.0 (superseded):** Rejected. AGPL-3.0 legally prohibits adding ethical use restrictions (Sections 7 and 10), allows cloud providers to host unmodified code commercially without paying and triggers automatic corporate/hospital legal bans due to network copyleft.
* **MIT or Apache-2.0:** Rejected. Permits closed-source SaaS competition with no ethical enforcement or commercial protection.
* **Pure Closed-Source:** Rejected. Eliminates community hardware testing and slows bottom-up adoption among SMEs, universities, and hospitals.


## ADR-017 — Stay on Odoo 19 through 2027; upgrade only after the dependency is removed

**Date:** 2026-11-05
**Status:** Accepted

### Context

Odoo 19 has standard support through September 2028. Odoo 20 shipped in September 2026; support runs through September 2029.

We will try to migrate as much of the functionality in the Nettrades Odoo modules into the Nettrades launcher, the Nettrades UI and the other Nettrades Platform code, like the src folder as possible so that we could reduce the reliance on Odoo and make Odoo upgrade easy. Currently the system is under development and there are no live users therefore it is easier to make these changes as no data has to be migrated as we make these changes. 

The custom-module migration surface is larger than usual for migrating to Odoo 20:

* `_sql_constraints` → `models.Constraint` / `UniqueIndex`

* `ir.model.access` + `ir.rule` → `ir.access` (`security/ir.access.csv`)

* `fields.Binary` → `BinaryValue`

* OWL 2 → OWL 3

* `get_param` / `set_param` → typed accessors

* Python 3.12 base

Those are all module-level rewrites, and they land at once if the upgrade is done today. The `llm_openai` and `queue_job` modules do not have 20.0 branches.


### Decision

* Deploy on Odoo 19 and stabilise the baseline.

* Execute ADR-011 through ADR-015 (connector, operational state, admin console, secrets, backup) before considering the upgrade.

* Upgrade to Odoo 20 only when:

* `nettrades_core` is the only mandatory NETTRADES module.

* `llm_openai` and `queue_job` are not on the boot path.

* The version-aware `OdooConnector` (ADR-012) is in place.

* Operational state lives in `nettrades_infra` (ADR-002).

* The upgrade is then a connector exercise plus a `models.Constraint` / `ir.access.csv` rewrite in one or two modules, not a 195-module port.

### Consequences

* The platform is stable and supported for two years while the dependency is removed.

* The Odoo 20 migration is uneventful rather than existential.

* The platform's own features (inference, failover, admin, backup) do not wait for Odoo 20.

* The team is not pulled into a migration while the platform is still finding its product-market fit.

### Alternatives considered

* Upgrade now — rejected. We want to move as much functionality as possible from the Odoo nettrades modules out as possible into the Nettrades launcher, the Nettrades UI and the other Nettrades Platform code, like the src folder first. 

* Stay on Odoo 19 until 2028 — rejected. Odoo 19 support ends September 2028; leaving no buffer for the eventual migration.

* Drop Odoo entirely and use only connectors from day one — rejected. Odoo's business documents (partners, invoices, HR, projects) are genuinely useful, and 15M+ existing Odoo users are a market to sell to, not a liability to move.

---

## ADR-018 — The hub does not detect hardware locally

**Date:** 2026-11-16
**Status:** Accepted

### Context

`src/core/hardware_detection.py` was written to detect hardware from inside
the LangGraph container. Containers do not have `/sys/class/drm` access, do
not have `nvidia-smi` bind-mounted, and do not have the vendor tooling.
Every detection call therefore returned zero GPUs.
`supervisor.py::_get_available_hardware()` used
`local_profile.total_vram_mb` to decide whether a model fit "locally" — a
value that was always 0 — so the `local` branch of
`_select_inference_track` was dead code. It was deleted 2026-11-16.

The question it was trying to answer — "does this model fit on hardware
the platform can route to?" — is already answered by the health monitor,
which reads from `gpu.node` in Odoo (populated by spoke registrations and
`configure-hub-for-spokes.sh`) plus `deploy/docker/hub-manifest.json`
(written by `phase-deploy.sh` from `scripts/lib/detect.py` on the host,
mounted read-only into the container).

### Decision

The hub has exactly two sources of hardware truth:

1. **Odoo records** — `gpu.node` rows for every registered spoke or hub
   inference endpoint. Populated by spokes (`POST /api/v1/gpu/register`)
   and by `configure-hub-for-spokes.sh`.
2. **Hub manifest** — `deploy/docker/hub-manifest.json`, generated by
   `scripts/lib/detect.py` on the host during `phase-deploy.sh`, mounted
   read-only into `langgraph-server` at `/app/hub-manifest.json`. When a
   `gpu.node` row's hostname or endpoint matches the local machine,
   `app.py::_load_node_inventory_into_monitor()` overrides the row's
   `gpus`, `vram_total_mb`, `gpu_count`, `role`, and `hostname` from the
   manifest. This gives the hub a self-description that survives without
   privileged access.

`supervisor.py` reads only from the health monitor. It never calls a local
detector.

### Consequences

- The hub can only route to hardware that is either registered as a
  `gpu.node` or written into the manifest. Unregistered hardware is
  unreachable. This is the correct security posture.
- Any new inference track that wants to be routable must either register
  with the hub or be added to the manifest. This is a deliberate gate.
- `hardware_detection.py` is gone. The two remaining detection
  implementations (`scripts/lib/detect.py` + `scripts/vendor/*` and
  `scripts/spoke-agent.py::detect_gpus()`) are documented in ADR-019.

### Alternatives considered

- **Bind-mount `/sys/class/drm` and `/dev/nvidia*` into the LangGraph
  container.** Rejected. It gives the AI orchestration service privileged
  host access, breaks the container isolation model, and does not help on
  WSL2 (where `/sys/class/drm` does not expose NVIDIA cards).
- **Run detection in a sidecar that the container queries.** Rejected as
  over-engineering. The manifest file is simpler and does not add a
  service.

---

## ADR-019 — Two detection implementations, one data shape

**Date:** 2026-11-16
**Status:** Accepted (consolidation into a shared package is a future ADR)

### Context

Two detection implementations remain after ADR-018:

- `scripts/lib/detect.py` + `scripts/vendor/*` — installer-time. Runs on
  the host. Writes the hub manifest. Has `hardware-matrix.yaml` lookup
  and the two-phase PCI/software diagnostic.
- `scripts/spoke-agent.py::detect_gpus()` — runtime. Runs on the spoke.
  Assigns per-GPU `rpc_port`, computes `HSA_OVERRIDE_GFX_VERSION` per
  GPU, has the Windows WMI fallback and the Apple Metal path.

These differ for real reasons:

- The installer must succeed on a **bare OS** before any driver is
  installed. The spoke runs **after** drivers are installed.
- The installer produces a schema-compliant manifest. The spoke produces
  GPU pinning env vars.
- The spoke has observed hardware failure modes (HSA override, WMI VRAM
  saturation) that do not apply to the installer.

### Decision

Keep two implementations. Do not consolidate them into one function. Instead:

- Extract a shared `packages/nettrades-hardware/` package that both import.
- Keep the **schema** in that package (`GPUInfo`,
  `CapabilityManifest`) so a future "add a fourth detector" is a wiring
  change not a schema change.
- Keep the **behaviour** (manifest writing, HSA computation, Windows WMI)
  inside each consumer.

The consolidation plan is a separate ADR when executed.

### Consequences

- The two implementations must be kept in sync on schema changes. The
  `GPUInfo` dataclass is duplicated today (once in
  `scripts/lib/capability.py::GPUCapability`, once in
  `scripts/spoke-agent.py::GPUInfo`). When a field is added to one, it
  must be added to the other, or the package is created first.
- `spoke-agent.py::detect_gpus()` is authoritative for runtime behaviour.
  Any fix to a runtime detection bug goes there, not in `vendor/*`.
- `scripts/lib/detect.py` is authoritative for the manifest schema. Any
  fix to a manifest bug goes there.
- The two must be tested together: `install-spoke.sh` writes a manifest;
  the spoke reads it. If they diverge, the spoke silently falls back to
  its own detection, which is correct but masks the divergence. A
  round-trip test is needed.

### Alternatives considered

- **One detector, one process.** Rejected. It would need either
  privileged container access (rejected in ADR-018) or a separate service
  (rejected as over-engineering), and it would lose the bare-OS Phase 1
  / Phase 2 split that catches "hardware present, driver missing".
- **One detector, two entry points, no schema.** Rejected. The manifest
  is a wire format between the installer and the hub; without a stable
  schema, future changes break the round-trip silently.