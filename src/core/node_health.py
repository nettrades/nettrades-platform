#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI — Node Health Monitoring
# =============================================================================
# FILE: src/core/node_health.py
#
# PURPOSE:
#   Continuous health monitoring for distributed inference nodes. This is
#   the src/core/ replacement for the Odoo cron job `_cron_health_watchdog`.
#   It runs as a background task in the LangGraph service (or as a standalone
#   sidecar) and emits Prometheus metrics for alerting.
#
# WHY THIS IS NOT IN ODOO:
#   Health monitoring is a real-time operational concern. Odoo cron jobs
#   run every few minutes at best, which is too slow for detecting a
#   spoke that has been switched off mid-inference. By moving it to
#   src/core/, we can:
#     1. Poll every 5-10 seconds (configurable)
#     2. Push metrics to Prometheus via the pushgateway
#     3. Trigger the supervisor's drain-and-restart logic immediately
#     4. Decouple from Odoo entirely (works even if Odoo is down)
#
# TWO HEALTH SIGNALS (2026-10):
#   This monitor supports two complementary health signals:
#
#   1. Pull probe (`_probe_node`): the monitor sends a GET to each node's
#      /health endpoint. Used for HTTP services (the same-host
#      llama-cpp container, the V100 vLLM endpoint). Does NOT work for
#      spokes behind NAT. RPC workers use the push heartbeat instead:
#      probing their rpc-server sockets over TCP leaves the server-side
#      accept queue stuck (see _probe_all for details).
#
#   2. Push heartbeat (`record_heartbeat`): the spoke agent POSTs to
#      /nodes/heartbeat on the LangGraph service every 10 seconds. Works
#      behind NAT because the spoke dials out. This is the primary signal
#      for RPC worker spokes and freelancer machines off the network.
#
#   A node is marked healthy when EITHER signal confirms liveness. The
#   consecutive_failures counter applies to the pull probe only; the push
#   heartbeat is itself the confirmation.
#
# METRICS EMITTED (Prometheus):
#   nettrades_node_up{node_id, hostname, role}
#   nettrades_node_gpu_utilization{node_id, gpu_index}
#   nettrades_node_gpu_memory_used_mb{node_id, gpu_index}
#   nettrades_node_cpu_utilization{node_id}
#   nettrades_node_heartbeat_age_seconds{node_id}
#   nettrades_node_inference_requests_total{node_id, status}
#   nettrades_node_inference_latency_ms{node_id, quantile}
#
# INTEGRATION:
#   The supervisor's `bridge_route` node calls `is_node_healthy()` before
#   routing a request to the RPC cluster. If a node is unhealthy, the
#   request is either retried on a different node or the conversation is
#   failed with a clear error (see the drain-and-restart pattern).
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Awaitable

try:
    from prometheus_client import Gauge, Counter, Histogram, REGISTRY
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. Prometheus metrics (only registered once)
# =============================================================================

if HAS_PROMETHEUS:
    try:
        NODE_UP = Gauge(
            'nettrades_node_up',
            'Whether a NETTRADES node is healthy (1) or not (0)',
            ['node_id', 'hostname', 'role'],
        )
        NODE_GPU_UTIL = Gauge(
            'nettrades_node_gpu_utilization',
            'GPU utilization percentage on a NETTRADES node',
            ['node_id', 'gpu_index'],
        )
        NODE_GPU_MEM_USED = Gauge(
            'nettrades_node_gpu_memory_used_mb',
            'GPU memory used in MB on a NETTRADES node',
            ['node_id', 'gpu_index'],
        )
        NODE_GPU_MEM_TOTAL = Gauge(
            'nettrades_node_gpu_memory_total_mb',
            'GPU memory total in MB on a NETTRADES node',
            ['node_id'],
        )
        NODE_CPU_UTIL = Gauge(
            'nettrades_node_cpu_utilization',
            'CPU utilization percentage on a NETTRADES node',
            ['node_id'],
        )
        NODE_HEARTBEAT_AGE = Gauge(
            'nettrades_node_heartbeat_age_seconds',
            'Seconds since the last heartbeat from a NETTRADES node',
            ['node_id'],
        )
        NODE_INFERENCE_TOTAL = Counter(
            'nettrades_node_inference_requests_total',
            'Total inference requests served by a NETTRADES node',
            ['node_id', 'status'],
        )
        NODE_INFERENCE_LATENCY = Histogram(
            'nettrades_node_inference_latency_ms',
            'Inference latency in milliseconds on a NETTRADES node',
            ['node_id'],
            buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000),
        )
    except ValueError:
        # Metrics already registered (e.g. module re-imported in tests)
        pass
else:
    _logger.warning("prometheus_client not installed — metrics will be no-ops")


# =============================================================================
# 2. Node health record
# =============================================================================

@dataclass
class NodeHealth:
    """
    Tracks the health state of a single node.

    The `consecutive_failures` counter is used to implement hysteresis:
    a node is only marked unhealthy after N consecutive failed probes.
    This prevents flapping when a node has a transient network hiccup.

    vram_total_mb and gpu_count (NEW 2026-10):
        These are populated by the inbound heartbeat from the spoke agent.
        They are the authoritative source for the supervisor's
        _get_available_hardware() to decide whether a model fits on the
        RPC cluster. Before this addition, the supervisor fell back to
        gpu_memory_used_mb (consumption, not capacity) and always computed
        a zero VRAM budget for the RPC track, so no request was ever
        routed to it.
    """
    node_id: str
    hostname: str
    role: str                          # 'dynamo_worker', 'rpc_worker', etc.
    endpoint: str                      # e.g. 'http://10.100.0.5:50052'
    last_heartbeat: Optional[datetime] = None
    last_probe_ok: bool = False
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    is_healthy: bool = False
    gpu_utilization: Dict[int, float] = field(default_factory=dict)
    gpu_memory_used_mb: Dict[int, int] = field(default_factory=dict)
    cpu_utilization: float = 0.0
    # Multi-GPU additions:
    vram_total_mb: int = 0
    gpu_count: int = 0
    # NEW (2026-10): the spoke reports whether it has the current model
    # file cached locally. Warm spares have model_cached=True and can be
    # promoted instantly if a worker fails.
    model_cached: bool = False
    rpc_backends: List[str] = field(default_factory=list)
    per_gpu_vram_mb: List[int] = field(default_factory=list)
    draining: bool = False        # field for drain

# =============================================================================
# 3. Health monitor
# =============================================================================

class NodeHealthMonitor:
    """
    Monitors the health of all nodes in a NETTRADES fabric.

    This class runs a background asyncio task that:
      1. Polls each registered node's /health endpoint every N seconds
         (pull probe — only works for nodes that expose a server).
      2. Also accepts inbound heartbeats via `record_heartbeat()` (push
         model — works for any node that can dial out, including spokes
         behind NAT and freelancer machines off the network).
      3. Updates the Prometheus metrics.
      4. Calls registered callbacks when a node transitions between
         healthy and unhealthy states.

    The callbacks are how the supervisor's drain-and-restart logic is
    triggered: when a node becomes unhealthy, the callback fires and the
    supervisor drains the affected RPC cluster.
    """

    def __init__(
        self,
        probe_interval_seconds: int = 10,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        request_timeout_seconds: int = 5,
        heartbeat_staleness_seconds: int = 30,
    ):
        self.probe_interval = probe_interval_seconds
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.request_timeout = request_timeout_seconds
        # If a node's last heartbeat is older than this, it is considered
        # stale. 30 seconds means two missed heartbeats at the default
        # 10-second interval, which matches the pull-probe threshold of
        # 3 × 10s = 30s. Both signals therefore agree on the same
        # definition of "unhealthy".
        self.heartbeat_staleness = heartbeat_staleness_seconds

        self._nodes: Dict[str, NodeHealth] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Callbacks
        self._on_node_unhealthy: List[Callable[[NodeHealth], Awaitable[None]]] = []
        self._on_node_healthy: List[Callable[[NodeHealth], Awaitable[None]]] = []

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register_node(
        self,
        node_id: str,
        hostname: str,
        role: str,
        endpoint: str,
        vram_total_mb: int = 0,
        gpu_count: int = 0,
        model_cached: bool = False,
        rpc_backends: Optional[List[str]] = None,
    ) -> None:
        """Add a node to the monitor, or update an existing entry.

        The `rpc_backends` parameter was added in 2026-10-28 so that
        app.py's _load_node_inventory_into_monitor can pass each node's
        per-GPU (host:port) probe targets. It is optional so that older
        callers that do not pass it remain valid.
        """
        existing = self._nodes.get(node_id)
        if existing:
            existing.hostname = hostname or existing.hostname
            existing.role = role or existing.role
            existing.endpoint = endpoint or existing.endpoint
            if vram_total_mb:
                existing.vram_total_mb = vram_total_mb
            if gpu_count:
                existing.gpu_count = gpu_count
            existing.model_cached = model_cached
            if rpc_backends is not None:
                existing.rpc_backends = list(rpc_backends)
            return

        self._nodes[node_id] = NodeHealth(
            node_id=node_id,
            hostname=hostname,
            role=role,
            endpoint=endpoint,
            vram_total_mb=vram_total_mb,
            gpu_count=gpu_count,
            model_cached=model_cached,
            rpc_backends=list(rpc_backends) if rpc_backends else [],
        )
        _logger.info(
            f"Registered node {node_id} ({hostname}) at {endpoint} "
            f"with {vram_total_mb}MB VRAM"
        )

    def unregister_node(self, node_id: str) -> None:
        """Remove a node from the monitor."""
        self._nodes.pop(node_id, None)
        _logger.info(f"Unregistered node {node_id}")

    # -------------------------------------------------------------------------
    # Push heartbeat (NEW 2026-10)
    # -------------------------------------------------------------------------

    def record_heartbeat(
        self,
        node_id: str,
        hostname: str = "",
        vram_total_mb: int = 0,
        gpu_count: int = 0,
        gpu_utilization: float = 0.0,
        memory_utilization: float = 0.0,
        temperature: float = 0.0,
        model_cached: bool = False,
        role: str = "rpc_worker",
        rpc_backends: Optional[List[str]] = None,
        draining: bool = False,
    ) -> NodeHealth:
        """
        Record an inbound heartbeat from a node.

        Called by the POST /nodes/heartbeat endpoint in app.py. If the
        node is not yet registered, it is auto-registered so a spoke can
        come online without a separate registration step against LangGraph.

        This method is synchronous and does not do any I/O. It only
        updates in-memory state. The caller is responsible for committing
        any external state (Odoo, database, etc.) if desired.
        """
        node = self._nodes.get(node_id)
        if node is None:
            node = NodeHealth(
                node_id=node_id,
                hostname=hostname or node_id,
                role=role,
                endpoint="",
            )
            self._nodes[node_id] = node
            _logger.info(
                f"Auto-registered node {node_id} on first heartbeat "
                f"({vram_total_mb}MB VRAM, {gpu_count} GPUs)"
            )

        # Update liveness timestamp. The presence of a heartbeat is
        # unconditional evidence that *something* on the node is alive,
        # but it is not evidence that the rpc-server processes are
        # healthy. We therefore separate the two concerns:
        #
        #   - `last_heartbeat` is updated here. It is the timestamp the
        #     probe loop reads for push-only nodes (no endpoint, no
        #     rpc_backends) to decide staleness.
        #
        #   - `consecutive_failures`, `consecutive_successes`, and
        #     `is_healthy` are the PROBE LOOP's state. The probe loop
        #     owns them. A heartbeat must not clear a failing probe
        #     counter, or the health monitor will report a node as
        #     healthy while `pre_generation_check` keeps failing on the
        #     same node — a contradictory state that is hard to
        #     diagnose in the field.
        #
        # The only field a heartbeat is allowed to write on a probe-
        # capable node is `draining`. Drain is an operator-triggered,
        # spoke-reported state that supersedes probe results: a node
        # that is gracefully shutting down must be marked unavailable
        # immediately, without waiting for the probe loop to notice.
        node.last_heartbeat = datetime.utcnow()

        node.draining = draining
        if draining:
            node.is_healthy = False
            _logger.info(
                "Node %s (%s) draining — marked unhealthy; probe loop "
                "will not resurrect it until draining is cleared",
                node.node_id, node.hostname,
            )
        # else: leave is_healthy, consecutive_failures, and
        # consecutive_successes untouched. The probe loop decides.
        # For push-only nodes (no probe target), the probe loop's
        # staleness check will now use the timestamp we just wrote.

        # Update the descriptive fields. These are pure metadata; writing
        # them from a heartbeat is correct and cheap.
        if vram_total_mb:
            node.vram_total_mb = vram_total_mb
        if gpu_count:
            node.gpu_count = gpu_count
        if hostname:
            node.hostname = hostname
        node.model_cached = model_cached
        if rpc_backends is not None:
            node.rpc_backends = list(rpc_backends)
        if gpu_count:
            node.gpu_utilization[0] = gpu_utilization
            if vram_total_mb:
                node.gpu_memory_used_mb[0] = int(
                    vram_total_mb * memory_utilization / 100
                )

        # Prometheus
        if HAS_PROMETHEUS:
            NODE_UP.labels(node.node_id, node.hostname, node.role).set(1)
            NODE_GPU_MEM_TOTAL.labels(node.node_id).set(node.vram_total_mb)
            for gpu_idx, util in node.gpu_utilization.items():
                NODE_GPU_UTIL.labels(node.node_id, str(gpu_idx)).set(util)
            for gpu_idx, mem in node.gpu_memory_used_mb.items():
                NODE_GPU_MEM_USED.labels(node.node_id, str(gpu_idx)).set(mem)
            pass

        return node

    # -------------------------------------------------------------------------
    # Callbacks
    # -------------------------------------------------------------------------

    def on_node_unhealthy(self, callback: Callable[[NodeHealth], Awaitable[None]]) -> None:
        """
        Register a callback that fires when a node transitions to unhealthy.

        The supervisor uses this to trigger drain-and-restart for RPC clusters.
        """
        self._on_node_unhealthy.append(callback)

    def on_node_healthy(self, callback: Callable[[NodeHealth], Awaitable[None]]) -> None:
        """Register a callback that fires when a node recovers."""
        self._on_node_healthy.append(callback)

    # -------------------------------------------------------------------------
    # Health query (used by the supervisor before routing)
    # -------------------------------------------------------------------------

    def is_node_healthy(self, node_id: str) -> bool:
        """Synchronous check used by the supervisor's routing logic."""
        node = self._nodes.get(node_id)
        return node is not None and node.is_healthy

    def get_healthy_nodes_by_role(self, role: str) -> List[NodeHealth]:
        """Return all healthy nodes with the given role."""
        return [n for n in self._nodes.values() if n.is_healthy and n.role == role]

    def get_warm_spares(self) -> List[NodeHealth]:
        """
        Return all healthy nodes that have the current model cached
        locally. These are the candidates for immediate promotion when a
        running worker fails.
        """
        return [
            n for n in self._nodes.values()
            if n.is_healthy and n.model_cached
        ]

    # -------------------------------------------------------------------------
    # Probe loop (pull model — still used for nodes that expose /health)
    # -------------------------------------------------------------------------
    async def _probe_node(self, node: NodeHealth) -> bool:
        """
        Probe a single node.

        Two signals are used:

          1. HTTP GET to `node.endpoint` + "/health". This is the right
             probe for containerised services that expose a health
             endpoint (e.g. the same-host llama-cpp container, or the
             vLLM endpoint on the V100).

        The RPC-backend TCP probe path has been removed. The ggml
        rpc-server does not accept bare TCP connections cleanly; every
        probe left a stuck connection in the 1-deep accept queue and
        made the server unreachable within 20 seconds. See the comment
        in _probe_all for the full diagnosis.
        """
        any_ok = False

        # --- Signal 1: TCP probe of every RPC backend ---
        # DELETED (2026-10-28). A bare TCP connect against the ggml
        # rpc-server completes the kernel handshake, then never sends the
        # ggml binary handshake bytes the server expects. The server's
        # handle_connection() blocks on recv(), the 1-deep accept queue
        # fills with phantom entries, and the worker becomes unreachable
        # until the process is killed. Worker liveness for RPC workers is
        # determined by the push heartbeat in the _probe_all push-only
        # branch, not by opening sockets. Do NOT reintroduce.
        pass

        # --- Signal 2: HTTP probe of the single endpoint ---
        if node.endpoint:
            try:
                import aiohttp
                url = f"{node.endpoint.rstrip('/')}/health"
                timeout = aiohttp.ClientTimeout(total=self.request_timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            any_ok = True
                            try:
                                data = await resp.json()
                                gpu_utils = data.get('gpus', [])
                                for i, gpu in enumerate(gpu_utils):
                                    node.gpu_utilization[i] = float(gpu.get('utilization', 0))
                                    node.gpu_memory_used_mb[i] = int(gpu.get('memory_used_mb', 0))
                                node.cpu_utilization = float(data.get('cpu_utilization', 0))
                                if data.get('vram_total_mb'):
                                    node.vram_total_mb = int(data['vram_total_mb'])
                                if data.get('gpu_count'):
                                    node.gpu_count = int(data['gpu_count'])
                            except Exception:
                                pass
            except Exception as e:
                _logger.debug("HTTP probe of %s failed: %s", node.node_id, e)

        return any_ok

    async def _probe_all(self) -> None:
        """Probe all registered nodes concurrently."""
        if not self._nodes:
            return

        now = datetime.utcnow()
        # Snapshot which nodes have an HTTP endpoint. Only those are pull-
        # probed. RPC workers rely on heartbeat staleness; see the push-only
        # branch below. Do NOT add `or n.rpc_backends` back — that dispatches
        # bare TCP connects to the ggml rpc-server, which fills the 1-deep
        # accept queue with phantoms. 2026-10-28 regression.
        probe_targets = [
            n for n in self._nodes.values()
            if n.endpoint
        ]
        tasks = [self._probe_node(n) for n in probe_targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        probe_results = dict(zip((n.node_id for n in probe_targets), results))

        for node in list(self._nodes.values()):
            was_healthy = node.is_healthy

            if node.draining:
                # A draining node is intentionally shutting down. Its
                # workers are still alive during the grace window, so
                # probing them would incorrectly report it as healthy.
                # We therefore force is_healthy=False, but we MUST NOT
                # skip the rest of the loop body: the transition
                # callback (`_on_node_unhealthy` → the supervisor's
                # `_on_rpc_node_failure` → `restart_without_node`) is
                # what rebuilds the cluster on the reduced topology.
                # Without firing it, the cluster is stale until the
                # next pre_generation_check fails.
                node.is_healthy = False
            else:
                # Only HTTP endpoints count as pull targets. The ggml
                # rpc-server expects a specific binary handshake on every
                # new connection; a bare TCP connect-and-close leaves the
                # server-side connection stuck reading handshake bytes
                # that never arrive. Two probe cycles fill the 1-deep
                # accept queue and every subsequent connection times out
                # at the socket layer. This was observed on the AMD rig
                # on 2026-10-28 (Recv-Q=2, Send-Q=1 on all six sockets,
                # nc to 127.0.0.1:50052 timing out).
                #
                # For RPC workers, we therefore use heartbeat freshness:
                # the spoke agent POSTs /nodes/heartbeat every 10s, and
                # the heartbeat payload carries per-worker status in
                # rpc_workers. The staleness branch below handles the
                # liveness check; worker-level health is out of scope
                # for this fix.
                has_pull_target = bool(node.endpoint)

                if has_pull_target:
                    ok = probe_results.get(node.node_id) is True
                    if ok:
                        node.consecutive_failures = 0
                        node.consecutive_successes += 1
                        node.last_probe_ok = True
                        node.last_heartbeat = now
                        if node.consecutive_successes >= self.success_threshold:
                            node.is_healthy = True
                    else:
                        node.consecutive_successes = 0
                        node.consecutive_failures += 1
                        node.last_probe_ok = False
                        if node.consecutive_failures >= self.failure_threshold:
                            node.is_healthy = False
                else:
                    # Push-only node. Use heartbeat staleness.
                    if node.last_heartbeat:
                        age = (now - node.last_heartbeat).total_seconds()
                        node.is_healthy = age <= self.heartbeat_staleness
                    else:
                        node.is_healthy = False

            # Update Prometheus metrics
            if HAS_PROMETHEUS:
                NODE_UP.labels(node.node_id, node.hostname, node.role).set(
                    1 if node.is_healthy else 0
                )
                NODE_GPU_MEM_TOTAL.labels(node.node_id).set(node.vram_total_mb)
                for gpu_idx, util in node.gpu_utilization.items():
                    NODE_GPU_UTIL.labels(node.node_id, str(gpu_idx)).set(util)
                for gpu_idx, mem in node.gpu_memory_used_mb.items():
                    NODE_GPU_MEM_USED.labels(node.node_id, str(gpu_idx)).set(mem)
                NODE_CPU_UTIL.labels(node.node_id).set(node.cpu_utilization)
                if node.last_heartbeat:
                    age = (now - node.last_heartbeat).total_seconds()
                    NODE_HEARTBEAT_AGE.labels(node.node_id).set(age)

            # Fire transition callbacks
            if was_healthy and not node.is_healthy:
                _logger.warning(
                    f"Node {node.node_id} ({node.hostname}) became UNHEALTHY "
                    f"after {node.consecutive_failures} consecutive failures "
                    f"(endpoint={node.endpoint or 'push-only'})"
                )
                for cb in self._on_node_unhealthy:
                    try:
                        await cb(node)
                    except Exception as e:
                        _logger.error(f"on_node_unhealthy callback failed: {e}")

            elif not was_healthy and node.is_healthy:
                _logger.info(f"Node {node.node_id} ({node.hostname}) recovered")
                for cb in self._on_node_healthy:
                    try:
                        await cb(node)
                    except Exception as e:
                        _logger.error(f"on_node_healthy callback failed: {e}")

    async def _run_loop(self) -> None:
        """The main probe loop."""
        _logger.info(
            f"NodeHealthMonitor starting "
            f"(interval={self.probe_interval}s, "
            f"failure_threshold={self.failure_threshold}, "
            f"heartbeat_staleness={self.heartbeat_staleness}s)"
        )
        while self._running:
            try:
                await self._probe_all()
            except Exception as e:
                _logger.error(f"Health probe loop error: {e}")
            await asyncio.sleep(self.probe_interval)
        _logger.info("NodeHealthMonitor stopped")

    def start(self) -> None:
        """Start the background health monitoring task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the background health monitoring task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


# =============================================================================
# 4. Singleton instance
# =============================================================================
# The supervisor imports this instance and uses it to check node health
# before routing. The LangGraph app.py starts and stops it in its lifespan.
# =============================================================================

_health_monitor: Optional[NodeHealthMonitor] = None


def get_health_monitor() -> NodeHealthMonitor:
    """Get or create the global health monitor singleton."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = NodeHealthMonitor()
    return _health_monitor
