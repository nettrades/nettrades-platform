## `docs/developer/README.md`

# NETTRADES Developer Documentation

**Audience:** A fresh LLM session or human developer picking up this project with no prior context.

**Purpose:** The authoritative index of NETTRADES developer documentation. Every other document in this directory is a leaf of this index. Everything else in the repository is either historical or superseded.

---

## The three-state model

| State | Document | What it covers |
|---|---|---|
| **Current** | `CURRENT-STATE.md` | What exists today  |
| **Demo** | `DEMO-STATE.md` | The Qatar Foundation target: V100 sub-hub + dynamo, AMD spoke. |
| **Future** | `FUTURE-STATE.md` | The product roadmap beyond the demo: data separation, federation, marketplace, multi-tenancy, certification. |

The bridge documents are:

| Document | Purpose |
|---|---|
| `TRANSITIONS.md` | Numbered checklists for T1 (Current→Demo), T2 (Demo→Future Phase 1), T3 (Future Phase 1→Phase 2+) |
| `ROLES.md` | The four deployment roles and their one-command installers. |
| `FAILOVER-HIERARCHY.md` | The six failover tiers, three VRAM checks, and the routing event ring buffer. |

The current handoff is at the **repository root**, not in this directory:

| Document | Purpose |
|---|---|
| `HANDOFF-YYYY-MM-DD.md` (root) | The current state of work. Which session did what, what is deployed, what is next. |

---

## Reading order

Read in this order, every session:

1. **`HANDOFF-YYYY-MM-DD.md`** at the repository root. The single most current document.
2. **This file.**
3. **`CURRENT-STATE.md`** — what exists right now.
4. **`DEMO-STATE.md`** — the target for the current milestone.
5. **`TRANSITIONS.md`** — the checklist for the current transition.
6. **The specific file named for the work item you are tackling.**

Do not read `ARCHITECTURE-AND-PLAN.md` first. It is superseded by this directory.

Do not read the whole codebase before acting. Read the specific files named for the work item you are tackling.

---

## "What do I want to do?" table

| Goal | Read |
|---|---|
| Know what was done last session | `HANDOFF-YYYY-MM-DD.md` (root) |
| Know what exists today | `CURRENT-STATE.md` |
| Understand the demo architecture | `DEMO-STATE.md` |
| Understand the long-term roadmap | `FUTURE-STATE.md` |
| Know the current milestone's checklist | `TRANSITIONS.md` § T1 |
| Install the V100 sub-hub and dynamo | `scripts/deploy-v100-hub.sh` (one command), then `ROLES.md` § V100 for diagnosis |
| Install the AMD spoke | `scripts/deploy-amd-spoke.sh` (one command), then `ROLES.md` § AMD for diagnosis |
| Understand failover | `FAILOVER-HIERARCHY.md` |
| Find a specific bug | `../../BUG-CATALOG.md` (verify FIXED entries against the code on disk) |
| Find a design decision | `../../DECISIONS.md` |

---

## Path convention

The canonical path for developer docs is `docs/developer/`.

The directory `docs/developers/` (plural) is deprecated. Do not add new files there.

---

## Invariants — never violate without explicit developer direction

1. **Never silently downgrade to a smaller model.** A pinned RPC request that finds the cluster unreachable either routes to a same-model fallback or fails loudly with HTTP 503. Local single-node llama.cpp is not a failover tier.
2. **Fail loudly, not quietly.** `ClusterRecovering` propagates straight to the client and does not open the circuit breaker.
3. **Odoo is the single source of truth for business entities.** `nettrades_infra` (when it exists) holds only operational telemetry.
4. **Administrators control every fallback that could leak data.** `allow_external_api_fallback` is False by default and is opt-in per cluster and per model.
5. **Session affinity preserves KV cache locality.** A conversation pinned to a track stays on that track unless failover is explicitly permitted.
6. **Every externally facing endpoint requires authentication.** No anonymous control-plane endpoints.
7. **No manual steps in the build.** Every artifact the installer depends on is produced by a script that runs as part of the build.

If a design decision is not covered by this directory or by the most recent handoff, ask the developer before implementing.

---

## Anti-patterns to avoid

- **Documentation that drifts from code.** Update the doc in the same commit as the fix.
- **Assuming a service is healthy because the container started.** Run `scripts/test-system.sh`.
- **Treating `.env.example` as authoritative.** The live `.env` plus the code that reads it is authoritative.
- **Hardcoding service names or URLs.** Read from environment variables.
- **Catching broad exceptions to hide failures.** Every `except` clause either handles its specific exception or re-raises.
- **Writing new code before fixing the known bugs.** The handoff's blocker list is the priority queue.
- **Adding features on top of a broken foundation.** Prove the current milestone before extending.

---

## What "done" looks like

| Milestone | Definition of done |
|---|---|
| **Current** | `CURRENT-STATE.md` matches reality. No claim in it is unverified. |
| **Demo** | `scripts/rehearse-demo.sh` exits 0 with all four claims passing in a single session. |
| **Future Phase 1** | `test-swap-erp.sh` proves the database separation is real. |
| **Future Phase 2+** | Federation, marketplace, multi-tenancy, certification — see `FUTURE-STATE.md`. |

---

## Committing to this structure

When you complete work:

1. Update `HANDOFF-YYYY-MM-DD.md` at the repository root with the session summary.
2. If a claim in `CURRENT-STATE.md` changed, update it.
3. If a step in `TRANSITIONS.md` was completed, tick it and record the completion.
4. If a design decision was made, add it to `DECISIONS.md`.

The handoff is the working document. The others are the reference.