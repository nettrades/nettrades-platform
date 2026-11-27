## `docs/developer/FAILOVER-HIERARCHY.md` — full replacement

# Failover Hierarchy

**Purpose:** The six tiers evaluated when a pinned RPC session finds its cluster unreachable. This is the design that makes "never silently downgrade to a smaller model" true.

**Source of truth:**
- `src/core/supervisor.py::_select_inference_track`
- `src/core/rpc_scheduler.py::_find_warm_spare` (async as of 2026-10-20; dispatches the Odoo query via `asyncio.to_thread`)
- `src/core/rpc_scheduler.py::pre_generation_check`
- `src/core/rpc_scheduler.py::restart_without_node`

**Status:** Designed and testable. No tier has yet fired on the current hardware. Do not say "works" until the rehearsal exercises each tier.

**Last updated:** 2026-10-20 — `_find_warm_spare` is async and dispatches the Odoo query via `asyncio.to_thread` so it does not block the event loop; Tier 2 prerequisite (LAN IP in `LLM_BASE_URL`) documented; the WSL sub-hub has been retired from the demo path.

---

## The six tiers

When a session is pinned to the `rpc` track and the pre-generation health check finds the cluster unreachable, the supervisor evaluates these tiers in order:

| Tier | Condition | Action |
|---|---|---|
| **1. Warm spare** | A node in the cluster has the model cached AND the resulting topology has sufficient VRAM | Promote the spare, rebuild the layer assignment, restart the master |
| **2. Dynamo fallback** | `allow_dynamo_fallback=True` AND `dynamo_vram_mb > 0` | Route to the V100 vLLM endpoint (same model, different hardware) |
| **3. Partial RPC** | `allow_rpc_partial_fallback=True` AND at least one healthy worker remains | Rebuild the cluster with fewer workers, same model |
| **4. Marketplace** | `allow_marketplace_fallback=True` | Rent a GPU that serves the same model |
| **5. External API** | `allow_external_api_fallback=True` | Route to OpenAI/Anthropic (opt-in only; leaves the network) |
| **6. Fail loud** | Always on | Raise `ClusterRecovering`, return HTTP 503 with `Retry-After: 30` |

---

## The three VRAM sufficiency checks

The failover hierarchy is only safe because of three VRAM checks. Understanding them is required to reason about the hierarchy.

### Check A — `_find_warm_spare` (Tier 1)

Before promoting a spare, the scheduler verifies:

1. The candidate is online, in the same cluster, has `model_cached=True`, and is not in the active topology.
2. `spare_vram_mb >= failed_vram_mb`. **The spare must be at least as large as the node it replaces.** This is the pipeline-parallelism requirement — the spare takes the failed node's share of the model.
3. `surviving_vram_mb + spare_vram_mb >= required_vram_mb`, where `required_vram_mb = (MODEL_SIZE_BYTES / 1MB) * 1.15` (15% headroom).

If condition 1 holds but 2 or 3 fails, the spare is skipped with a warning, and the supervisor falls through to Tier 2.

`MODEL_SIZE_BYTES` is an environment variable. Default is `4683073248` (DeepSeek-R1-7B-Q4_K_M). Set it in `.env` to match the served model.

**Async note (2026-10-20).** `_find_warm_spare` is an `async` method. It dispatches the Odoo query for candidate spares to a worker thread via `asyncio.to_thread(self._odoo_rpc_sync_search, ...)`, so the synchronous `httpx.Client` inside `_odoo_rpc_sync_search` does not block the LangGraph event loop. A 15-second synchronous Odoo call inside an `async def` would freeze every other request served by the container for the duration of the call. That would be especially damaging during a demo failover, because the Launcher health probe and any in-flight chat request would stall for the same period. `restart_without_node` awaits `_find_warm_spare`.

### Check B — `pre_generation_check` (before every pinned RPC request)

Before routing any pinned RPC request, the supervisor calls `RPCScheduler.pre_generation_check(cluster_id)`. This does two things:

1. **TCP-probes every worker** in the cluster at the RPC worker port. If any is unreachable, the check fails.
2. **Sums the VRAM** of every worker. If the total is below `required_vram_mb`, the check fails.

The check runs under `asyncio.wait_for(..., timeout=RPC_PREFLIGHT_TIMEOUT)`. As of 2026-10-20, `RPC_PREFLIGHT_TIMEOUT = 5.0`. Prior to that it was `3.0`, which was too tight for the six-GPU AMD rig on the same LAN as the sub-hub — healthy clusters were producing spurious `preflight_fail` events. On the current demo topology (V100 sub-hub at `192.168.1.212`, AMD rig on the same LAN) 5.0 has not produced spurious failures. If a different topology is used, raise it further.

If the check fails, `_select_inference_track` proceeds to the failover policy tiers (2 through 6).

### Check C — `restart_without_node` (before rebuilding a reduced cluster)

When a worker fails and no warm spare is available, the scheduler must decide whether to rebuild the cluster with the surviving workers. It verifies:

1. `sum(vram of surviving workers) >= required_vram_mb`.

If the survivors cannot hold the model, the scheduler:

- Stops the master.
- Writes an empty `RPC_BACKENDS` to `rpc.env`.
- Does NOT rebuild.
- Returns `{"undersized": True, "vram_available_mb": ..., "vram_required_mb": ...}`.

The next request fails `pre_generation_check` and the supervisor applies the failover policy.

**Why all three checks exist:** each catches a different case. Check A catches an undersized spare. Check B catches a cluster that lost a worker but still passes the TCP probe. Check C catches the case where rebuilding with survivors would produce a cluster too small to hold the model.

---

## Tier 6 — the fail-loud guarantee

Tier 6 is terminal. It cannot be disabled. If nothing else is available, the request fails.

The supervisor raises `ClusterRecovering`. This exception:

- **Propagates straight to the client.** It is NOT caught by the circuit breaker.
- **Does NOT open the circuit breaker.** `SupervisorCircuitBreaker` only trips on `ConnectionError`, `TimeoutError`, and `asyncio.TimeoutError`. `ClusterRecovering` is a deliberate, transient condition.
- **Results in HTTP 503 with `Retry-After: 30`.**

```python
# src/core/routes/invoke.py
except ClusterRecovering as e:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(e),
        headers={"Retry-After": "30"},
    )
```

The client receives a clear signal: the platform is temporarily recovering, retry in 30 seconds. The checkpointer has preserved the conversation; the retry continues from the last completed turn.

### Circuit breaker interaction

| Failure type | Counts toward breaker | Action |
|---|---|---|
| `ConnectionError` (network) | Yes | After 5 failures, breaker opens for 30s |
| `TimeoutError` (upstream slow) | Yes | Same |
| `asyncio.TimeoutError` | Yes | Same |
| `ClusterRecovering` | No | Straight to client |
| Any other exception | No | Logged and re-raised |

The reason `ClusterRecovering` is excluded: it is a normal, transient condition. During RPC recovery, requests to other tracks (dynamo, local, remote) must continue to be served. If the breaker counted `ClusterRecovering` failures, a burst of RPC requests would open the breaker and block ALL traffic for 30 seconds.

### The routing event ring buffer

The supervisor publishes every routing decision to a 200-entry in-memory ring buffer (`_ROUTING_EVENTS` in `supervisor.py`). The Launcher polls `/routing/events` to show a live failover timeline.

Two event-emission refinements applied 2026-10-16:

* pinned events are deduplicated per thread. The `record_routing_event("pinned", ...)` call is guarded by `state["_pin_recorded"]`. The flag is persisted by the LangGraph checkpointer, so it survives across turns. Without the guard, a ten-message conversation on a pinned thread would emit ten `pinned` events and push the interesting `failover_tier*` events off the back of the ring buffer before the operator could see them.

* `preflight_ok` / `preflight_fail` events are always emitted. They are not deduplicated — every preflight is a real signal. If you see a wall of `preflight_fail` on a healthy cluster, `RPC_PREFLIGHT_TIMEOUT` is too low.

### Testing each tier

Test scripts live in `scripts/tests/failover/`. Each one exercises one tier. `run-all.sh` runs them all and reports pass/fail.




#### Tier 1 — warm spare promotion

```bash

# Setup: two spokes registered, one active and one warm spare with model_cached=True
# Kill the active spoke
# Send a request pinned to rpc
# Expect: master log shows "Found viable warm spare: <name>"
# Expect: master rebuilds with the spare and the request succeeds
```

#### Tier 2 — Dynamo fallback

Prerequisite for Tier 2 firing. The V100's `.env` must set `LLM_BASE_URL=http://<V100-LAN-IP>:8001/v1` (the host's LAN IP), not `http://localhost:8001/v1`. `configure-hub-for-spokes.sh` probes `LLM_BASE_URL` from inside the Odoo container, where `localhost` resolves to the container itself, not the vLLM instance. With `localhost`, the probe fails, no `dynamo_worker` is registered, `dynamo_vram_mb` stays 0, and Tier 2 never fires. For the current demo, `<V100-LAN-IP>` is `192.168.1.212`.

Verify the dynamo_worker is registered before testing Tier 2:

```bash

docker compose -f deploy/docker/docker-compose.yaml exec -T postgres \
    psql -U odoo -d odoo -tAc \
    "SELECT name FROM gpu_node WHERE inference_capability = 'dynamo_worker';"
# Expected: one row, Remote-vLLM-Hub
```

```bash

# Setup: allow_dynamo_fallback=True on the cluster, V100 vLLM reachable on :8001
# Kill all RPC spokes (or stop nettrades-spoke on the AMD rig)
# Send a request pinned to rpc
# Expect: log shows "Failover: routing to Dynamo cluster"
# Expect: request served from the V100 vLLM endpoint on :8001
```

#### Tier 3 — partial RPC

```bash

# Setup: allow_rpc_partial_fallback=True
# Kill some (but not all) spokes
# Send a request pinned to rpc
# Expect: log shows "Failover: using partial RPC cluster"
# Expect: cluster rebuilds with surviving workers
```

#### Tier 6 — fail loud

```bash

# Setup: all allow_*_fallback=False
# Kill all RPC spokes
# Send a request pinned to rpc
# Expect: HTTP 503 with Retry-After: 30
# Expect: circuit breaker NOT open (subsequent dynamo/local requests succeed)

```    

---

## Graceful shutdown — the precondition for safe failover

Tier 6 is only safe if the spoke stops advertising itself **before** it
stops serving. A spoke that disappears mid-generation loses the tokens
it has emitted since the last checkpoint, and the client has to re-ask.
The checkpoint preserves the conversation transcript, not the partial
output of the turn that was in flight.

The graceful drain closes that window for planned stops (systemctl
stop, reboot, Windows shutdown). It does not close it for power cuts
or forced resets — for those, the only defence is more frequent
checkpointing, and llama.cpp does not currently provide disk-backed
mid-generation checkpoints (issue #20697, open, no maintainer reply).

### Design

Three pieces:

1. **A `draining` field on the heartbeat protocol.** Before the spoke
   stops its RPC workers, it sends one heartbeat with
   `{"is_available": false, "draining": true}`. The hub marks the node
   unhealthy and stops routing new requests to it.
   - Odoo: `gpu.node.state` stays `'active'`, but `status` is set to
     `'draining'` by the heartbeat handler (migration in phase 2 of
     the roadmap; today the status field is not consumed by routing).
   - LangGraph: `NodeHealth.is_healthy` flips to `false` on receipt.
     `_get_available_hardware()` filters on `is_healthy=true`, so the
     node drops out of `rpc_nodes` within one heartbeat (10 s).

2. **A grace window between the drain heartbeat and the RPC worker
   stop.** The spoke agent waits `shutdown_grace_seconds` (default 30)
   before calling `MultiGpuRpcSupervisor.stop_all()`. This is the
   window in which the RPC master can finish the current generation
   on this node. The master does not interrupt in-flight requests when
   it sees a draining node; only the node's own `rpc-server`
   termination does. So the grace window is what actually saves the
   in-flight turn.

3. **OS-level time for the drain to complete.** systemd sends SIGTERM
   on stop/shutdown. The spoke agent's SIGTERM handler starts the
   drain. The unit must allow at least the grace window plus a margin
   before SIGKILL. `install-spoke.sh` writes `TimeoutStopSec=90` on
   the `nettrades-spoke.service` unit; the agent's grace window is 30 s,
   leaving 60 s of margin.

### Triggers

Three triggers, all funnelled through `SpokeAgent._trigger_drain()`:

| Trigger | Source | Platform |
|---|---|---|
| `SIGTERM` | `systemctl stop nettrades-spoke` or system shutdown | Linux (systemd) |
| `SIGINT` | Ctrl+C in an interactive session | Any |
| `drain_requested_file` appears | `nettrades-netsvc.exe` writes it on `SERVICE_CONTROL_PRESHUTDOWN` | Windows |

On Linux, SIGTERM is the primary path. The file trigger is present
but normally unused — `systemctl stop` and shutdown both send
SIGTERM.

On Windows, the file trigger is the only path. The Windows service
(`nettrades-netsvc`) does not run the Python agent as a child process,
so it cannot send a signal directly. Instead, on `PRESHUTDOWN` it
writes `drain.requested`, then polls for `drain.complete` for up to
60 seconds. The Python agent, running as a separate process (started
by the Launcher), polls `drain.requested` from `_watch_drain_file` and
starts the drain. When the drain completes, the agent writes
`drain.complete`, which the service sees and returns from its
PRESHUTDOWN handler.

For the file trigger to work on Windows, two things must be true:
- The Windows service must have its preshutdown timeout configured.
  `installService()` runs `sc.exe config NETTRADESNetSvc preshutdown= 60000`
  during installation; without that call, Windows never sends
  PRESHUTDOWN to the service.
- The Python spoke agent must actually be running. If it is not, the
  service writes `drain.requested` and times out waiting for
  `drain.complete`. Nothing is drained, but nothing is broken either
  — the OS proceeds with the shutdown.

### What it does not protect against

- **Power cut, kernel panic, forced reset.** No user-space process
  gets a chance to run. The in-flight tokens are lost.
- **`kill -9` on the spoke agent.** Same: no SIGTERM, no drain.
- **The AMD rig being unplugged mid-generation.** No drain can run.

For those, the answer is the same as before: the client sees the
`/nodes` entry go unhealthy within 30 s (three failed probes), the
next request fails over per the Tier 2 / Tier 6 rules, and the user
retries. The conversation transcript survives via the checkpointer.

### What it does protect against

- `systemctl stop nettrades-spoke` — the drain fires, the hub stops
  routing to the node, the in-flight turn finishes on the node before
  the RPC workers die.
- `systemctl restart nettrades-spoke` — same.
- Reboot of the AMD rig (or V100 if it's running a spoke) — same,
  because reboot sends SIGTERM.
- Windows shutdown of the spoke machine — the Windows service writes
  the trigger, the agent drains, the service returns from PRESHUTDOWN
  when the drain completes.

### Verification

**Linux (AMD rig or V100):**

```bash
# 1. Start a long-running generation on the spoke via /invoke
curl -s -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $LANGGRAPH_API_KEY" \
  -d '{"input":{"messages":[{"role":"user","content":"Write a 2000-word essay."}]},"config":{"configurable":{"thread_id":"drain-test"}}}' &

# 2. While it runs, stop the spoke
sudo systemctl stop nettrades-spoke

# 3. Observe the hub side
watch -n1 'curl -s http://localhost:8000/nodes -H "X-API-Key: $LANGGRAPH_API_KEY" | jq ".nodes[] | select(.hostname==\"amd-mining-rig\") | {is_healthy, last_heartbeat}"'

# Expected: is_healthy flips to false within 10 s. The generation
# continues on the spoke for up to 30 s, then completes or fails.
# The client sees a complete answer, not a partial one.

# 4. Restart the spoke and verify it comes back
sudo systemctl start nettrades-spoke
# is_healthy flips back to true within 20 s.

Windows:

This is a follow-up item (the Launcher and installer changes are
not on the demo path). The mechanism is in place: the service writes
the trigger, the agent drains. Verification requires a Windows spoke
with the agent installed as a service, which is deferred to Phase 3.

Where the code is

| Component | File | What it does |
|---|---|---|
| `Agent drain | `scripts/spoke-agent.py` | `_trigger_drain`, `_drain_and_exit`, `_on_shutdown_signal`, `_watch_drain_file`, `heartbeat(draining=...)` |
| Linux unit | `scripts/install-spoke.sh` | writes `TimeoutStopSec=90` on `nettrades-spoke.service` |
| Windows service | `nettrades-netsvc/main.go` | `handlePreshutdown`, `sc.exe config ... preshutdown= 60000` in `installService` |
| Hub-side state | `src/core/node_health.py` | `NodeHealth.is_healthy` set to false by the heartbeat with `draining=true` |
| Supervisor | `src/core/supervisor.py` | `_get_available_hardware` filters on `is_healthy=true`, so a draining node drops out of `rpc_nodes` |



### Wording for the demo

Say it exactly this way:

    "When a spoke fails, the scheduler first tries to promote a warm spare — a machine with the same model already cached and with at least as much VRAM as the failed node. If a spare with sufficient VRAM is available, the cluster rebuilds and inference continues. If not, the platform evaluates the failover policy. The last resort is failing loudly with HTTP 503 and a Retry-After header, never silently downgrading to a smaller model."

Do not claim the failover hierarchy "works" until every tier has been exercised on real hardware. Say it is "designed and testable". Update this document when the tests pass.