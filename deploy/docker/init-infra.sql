-- =============================================================================
-- NETTRADES Agent Infrastructure Database (nettrades_infra)
-- =============================================================================
-- FILE: deploy/docker/init-infra.sql
--
-- PURPOSE:
--   Operational state for the NETTRADES platform: telemetry, coordination,
--   secrets, and audit. This database holds NO tenant business data.
--
--   Business entities (res.partner, sale.order, gpu.node, ...) live in
--   the Odoo database, owned by the ORM (ADR-001).
--   LangGraph checkpoints live in the `checkpoints` database (ADR-003).
--
--   Per ADR-002, keeping operational state in a separate database means:
--     * An Odoo upgrade does not touch agent infrastructure.
--     * Backups have independent retention (heartbeats: days,
--       business data: 90+ days).
--     * Heartbeat traffic does not compete with Odoo queries.
--     * Secrets are not in .env, not in ir.config_parameter, and not
--       in the Odoo database dump (ADR-015).
--
-- IDEMPOTENT: every statement uses CREATE ... IF NOT EXISTS.
--
-- USAGE:
--   Applied by scripts/migrate-phase1-databases.sh on existing deployments,
--   and by /docker-entrypoint-initdb.d/01-create-databases.sh on fresh ones.
-- =============================================================================

-- pgcrypto for AES-256-GCM secret encryption (ADR-015)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- 1. RPC cluster topology snapshots
-- =============================================================================
-- Written by src/core/rpc_scheduler.py whenever the RPC cluster topology
-- changes. The operator-visible configuration lives in Odoo (gpu.cluster);
-- this table holds the scheduler's own view of what it last launched, so
-- the scheduler can restart with a known topology even if Odoo is briefly
-- unavailable.
CREATE TABLE IF NOT EXISTS nettrades_rpc_cluster (
    id               SERIAL PRIMARY KEY,
    odoo_cluster_id  INTEGER NOT NULL UNIQUE,
    name             TEXT,
    health_status    TEXT DEFAULT 'unknown',
    layer_assignment JSONB,
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- 2. RPC worker membership + last heartbeat
-- =============================================================================
-- Durable copy of the health monitor's per-node state. The in-memory
-- NodeHealth objects in src/core/node_health.py are authoritative for
-- routing decisions; this table survives a LangGraph container restart
-- and gives the operator a durable history.
CREATE TABLE IF NOT EXISTS nettrades_rpc_node (
    id              SERIAL PRIMARY KEY,
    odoo_node_id    INTEGER NOT NULL UNIQUE,
    cluster_id      INTEGER REFERENCES nettrades_rpc_cluster(id) ON DELETE CASCADE,
    hostname        TEXT,
    wg_ip           TEXT,
    contribution    TEXT DEFAULT 'active',
    last_heartbeat  TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rpc_node_last_heartbeat
    ON nettrades_rpc_node(last_heartbeat DESC);

-- =============================================================================
-- 3. Session -> inference track binding (session affinity)
-- =============================================================================
-- Per ADR-007, once a conversation starts on an inference track, it stays
-- on that track until the track becomes unavailable. This table is the
-- durable form of the pin; the checkpointer also persists it in LangGraph
-- state, so this table is a fallback for the case where the checkpoint has
-- been pruned but the operator wants to audit recent bindings.
CREATE TABLE IF NOT EXISTS nettrades_session_binding (
    id              SERIAL PRIMARY KEY,
    thread_id       TEXT NOT NULL UNIQUE,
    inference_track TEXT NOT NULL,
    cluster_id      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_session_binding_expires
    ON nettrades_session_binding(expires_at);

-- =============================================================================
-- 4. Failover audit trail
-- =============================================================================
-- Written by src/core/supervisor.py::_select_inference_track when a
-- failover tier fires. The in-memory ring buffer (get_routing_events) is
-- for the Launcher; this is the post-hoc audit.
CREATE TABLE IF NOT EXISTS nettrades_failure_log (
    id              SERIAL PRIMARY KEY,
    node_id         INTEGER,
    cluster_id      INTEGER,
    failure_type    TEXT,
    details         JSONB,
    recovery_action TEXT,
    occurred_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_failure_log_occurred_at
    ON nettrades_failure_log(occurred_at DESC);

-- =============================================================================
-- 5. Saga coordination state (ADR-004)
-- =============================================================================
-- Cross-system operations (e.g. create-project-then-create-invoice) are
-- coordinated through the saga pattern. One row per saga, steps array
-- records progress. A saga left in state='running' for more than an hour
-- is a signal that the coordinator failed mid-operation.
CREATE TABLE IF NOT EXISTS nettrades_saga_log (
    id           SERIAL PRIMARY KEY,
    saga_id      UUID NOT NULL UNIQUE,
    saga_type    VARCHAR(64) NOT NULL,
    state        VARCHAR(32) NOT NULL,
    steps        JSONB,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    outcome      VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS idx_saga_log_state
    ON nettrades_saga_log(state)
    WHERE state IN ('pending', 'running');

-- =============================================================================
-- 6. Idempotency keys (ADR-004, retry safety)
-- =============================================================================
-- Before performing a state-changing operation, the gateway looks up its
-- idempotency key. If it exists, the stored response is returned; otherwise
-- the operation proceeds and the response is stored. TTL is set by the
-- caller (typically 24 hours).
CREATE TABLE IF NOT EXISTS nettrades_idempotency_keys (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(255) NOT NULL UNIQUE,
    response   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires_at
    ON nettrades_idempotency_keys(expires_at);

-- =============================================================================
-- 7. Encrypted operator secrets (ADR-015)
-- =============================================================================
-- AES-256-GCM encrypted with NETTRADES_SECRETS_KEY (a bootstrap secret kept
-- in .env). Nonce stored alongside the ciphertext; key not stored.
--
-- Per ADR-015, operator-configurable secrets (backup credentials, storage
-- keys, LLM provider keys) live here. Bootstrap secrets (POSTGRES_PASSWORD,
-- NETTRADES_SECRETS_KEY, LANGGRAPH_API_KEY, PROXY_API_KEY) stay in .env
-- because they are needed before the database is up.
CREATE TABLE IF NOT EXISTS nettrades_secrets (
    id          SERIAL PRIMARY KEY,
    key         VARCHAR(255) NOT NULL UNIQUE,
    value       BYTEA NOT NULL,
    nonce       BYTEA NOT NULL,
    description TEXT,
    created_by  VARCHAR(255),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version     INTEGER NOT NULL DEFAULT 1
);

-- =============================================================================
-- 8. Secret access audit
-- =============================================================================
CREATE TABLE IF NOT EXISTS nettrades_secrets_audit (
    id           SERIAL PRIMARY KEY,
    secret_key   VARCHAR(255) NOT NULL,
    action       VARCHAR(32) NOT NULL,
    performed_by VARCHAR(255),
    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_secrets_audit_performed_at
    ON nettrades_secrets_audit(performed_at DESC);

-- =============================================================================
-- 9. Admin console action log (ADR-013)
-- =============================================================================
-- One row per state-changing action performed from the admin console.
-- Written by nettrades-ui's /admin router after the action completes or
-- fails. Includes the before/after state so a restore can be audited.
CREATE TABLE IF NOT EXISTS nettrades_admin_audit (
    id           SERIAL PRIMARY KEY,
    actor        VARCHAR(255) NOT NULL,
    action       VARCHAR(128) NOT NULL,
    target       VARCHAR(255),
    before_state JSONB,
    after_state  JSONB,
    outcome      VARCHAR(32) NOT NULL,
    ip           INET,
    performed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_performed_at
    ON nettrades_admin_audit(performed_at DESC);

-- =============================================================================
-- 10. Egress audit (ADR-004)
-- =============================================================================
-- One row per outbound connection the platform makes to a system outside
-- the tenant's network. Written by the Enterprise Gateway whenever an
-- external-API or marketplace track fires. Required for GDPR compliance
-- (data subject access requests need to know where data went).
CREATE TABLE IF NOT EXISTS nettrades_egress_audit (
    id             SERIAL PRIMARY KEY,
    destination    VARCHAR(255) NOT NULL,
    port           INTEGER,
    protocol       VARCHAR(32),
    bytes_sent     BIGINT,
    bytes_received BIGINT,
    initiated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    initiated_by   VARCHAR(255),
    failed         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_egress_audit_initiated_at
    ON nettrades_egress_audit(initiated_at DESC);