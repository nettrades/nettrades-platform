-- =============================================================================
-- NETTRADES Database Initialisation (odoo database)
-- =============================================================================
-- Extensions only, per ADR-001. Business entities are created by the
-- Odoo ORM; operational state lives in nettrades_infra; LangGraph
-- checkpoints live in `checkpoints`.
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;
