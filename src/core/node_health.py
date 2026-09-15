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


# =============================================================================
# 3. Health monitor
# =============================================================================

class NodeHealthMonitor:
    """
    Monitors the health of all nodes in a NETTRADES fabric.

    This class runs a background asyncio task that:
      1. Polls each registered node's /health endpoint every N seconds
      2. Updates the Prometheus metrics
      3. Calls registered callbacks when a node transitions
         between healthy and unhealthy states

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
    ):
        self.probe_interval = probe_interval_seconds
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.request_timeout = request_timeout_seconds

        self._nodes: Dict[str, NodeHealth] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Callbacks
        self._on_node_unhealthy: List[Callable[[NodeHealth], Awaitable[None]]] = []
        self._on_node_healthy: List[Callable[[NodeHealth], Awaitable[None]]] = []

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register_node(self, node_id: str, hostname: str, role: str, endpoint: str) -> None:
        """Add a node to the monitor."""
        self._nodes[node_id] = NodeHealth(
            node_id=node_id,
            hostname=hostname,
            role=role,
            endpoint=endpoint,
        )
        _logger.info(f"Registered node {node_id} ({hostname}) at {endpoint}")

    def unregister_node(self, node_id: str) -> None:
        """Remove a node from the monitor."""
        self._nodes.pop(node_id, None)
        _logger.info(f"Unregistered node {node_id}")

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

    # -------------------------------------------------------------------------
    # Probe loop
    # -------------------------------------------------------------------------

    async def _probe_node(self, node: NodeHealth) -> bool:
        """
        Probe a single node's health endpoint.

        Returns True if the probe succeeded, False otherwise.
        """
        try:
            import aiohttp
            url = f"{node.endpoint.rstrip('/')}/health"
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        _logger.debug(f"Node {node.node_id} returned HTTP {resp.status}")
                        return False
                    data = await resp.json()
                    # Extract metrics if the node reports them
                    gpu_utils = data.get('gpus', [])
                    for i, gpu in enumerate(gpu_utils):
                        node.gpu_utilization[i] = float(gpu.get('utilization', 0))
                        node.gpu_memory_used_mb[i] = int(gpu.get('memory_used_mb', 0))
                    node.cpu_utilization = float(data.get('cpu_utilization', 0))
                    return True
        except Exception as e:
            _logger.debug(f"Probe of {node.node_id} failed: {e}")
            return False

    async def _probe_all(self) -> None:
        """Probe all registered nodes concurrently."""
        if not self._nodes:
            return

        tasks = [self._probe_node(n) for n in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for node, ok in zip(self._nodes.values(), results):
            was_healthy = node.is_healthy

            if ok is True:
                node.consecutive_failures = 0
                node.consecutive_successes += 1
                node.last_probe_ok = True
                node.last_heartbeat = datetime.utcnow()

                if node.consecutive_successes >= self.success_threshold:
                    node.is_healthy = True
            else:
                node.consecutive_successes = 0
                node.consecutive_failures += 1
                node.last_probe_ok = False

                if node.consecutive_failures >= self.failure_threshold:
                    node.is_healthy = False

            # Update Prometheus metrics
            if HAS_PROMETHEUS:
                NODE_UP.labels(node.node_id, node.hostname, node.role).set(
                    1 if node.is_healthy else 0
                )
                for gpu_idx, util in node.gpu_utilization.items():
                    NODE_GPU_UTIL.labels(node.node_id, str(gpu_idx)).set(util)
                for gpu_idx, mem in node.gpu_memory_used_mb.items():
                    NODE_GPU_MEM_USED.labels(node.node_id, str(gpu_idx)).set(mem)
                NODE_CPU_UTIL.labels(node.node_id).set(node.cpu_utilization)
                if node.last_heartbeat:
                    age = (datetime.utcnow() - node.last_heartbeat).total_seconds()
                    NODE_HEARTBEAT_AGE.labels(node.node_id).set(age)

            # Fire transition callbacks
            if was_healthy and not node.is_healthy:
                _logger.warning(
                    f"Node {node.node_id} ({node.hostname}) became UNHEALTHY "
                    f"after {node.consecutive_failures} consecutive failures"
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
            f"failure_threshold={self.failure_threshold})"
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