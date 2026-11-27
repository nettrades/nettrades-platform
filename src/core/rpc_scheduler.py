#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI — RPC Cluster Scheduler
# =============================================================================
# FILE: src/core/rpc_scheduler.py
#
# PURPOSE:
#   Orchestrate the llama.cpp RPC cluster from src/core/, not from Odoo.
#
#   This is the missing piece that makes the office RPC track start,
#   health-check, drain, and restart on its own — independent of Odoo.
#
#   DESIGN LESSONS (from Ghostlink PR #352 and llama.cpp PR #18933):
#     1. Pre-generation health check: before any request, verify every
#        RPC peer is reachable. If not, do not route.
#     2. Drain-and-restart on failure: llama.cpp RPC has no graceful
#        error recovery. A single failed worker hard-aborts the master.
#        We must therefore drain (fail in-flight requests) and restart
#        the master with a reduced topology before the next request.
#     3. Proportional split: weight by VRAM. If VRAM is zero, fall back
#        to RAM x 0.5 (Ghostlink's CPU_RAM_HAIRCUT heuristic).
#     4. Reject no-op distributed offload: if -ngl is 0 or the remote
#        share is < 1%, omit the --rpc flags entirely.
#
# WHY NOT IN ODOO:
#   - Survives Odoo upgrades.
#   - Can be triggered from the Launcher without going through the
#     Odoo UI.
#   - When the backend is swapped to Salesforce/SAP, only the read and
#     persist calls change. The layer-assignment algorithm is unchanged.
#
# INTEGRATION POINTS:
#   - Odoo: reads gpu.cluster and gpu.node via the odoo-proxy.
#   - Docker: recreates llama-rpc-master via the docker socket.
#   - Supervisor: called from _on_rpc_node_failure and /rpc/relaunch.
#
# PIPELINE PARALLELISM SEMANTICS (2026-10 — re-emphasised):
#   llama.cpp RPC uses PIPELINE PARALLELISM. The model's transformer
#   layers are split into contiguous chunks and each chunk lives in the
#   VRAM of exactly one worker. If a worker fails, only its chunk is
#   lost — not the whole model. A replacement worker therefore has to
#   be able to hold the lost chunk, which is proportional to the failed
#   worker's VRAM share. This is why _find_warm_spare compares the
#   spare against `failed_vram_mb` and NOT against the full model size.
#
#   After any failure the reconstituted cluster must still fit the whole
#   model with headroom. That second check is a safety net against a
#   cluster that was already undersized at launch.
#
# MULTI-GPU (2026-10):
#   A single machine can host more than one GPU. The spoke agent starts
#   one rpc-server process per GPU, each on a distinct port. A failure
#   therefore has two forms:
#     (a) Whole-node failure — the machine is powered off, the network
#         is down, or the OS crashed. Every GPU on the machine is gone.
#     (b) Per-GPU failure — one rpc-server process or one GPU failed,
#         but the machine is up and its other GPUs are healthy.
#   restart_without_node() accepts an optional `failed_port` argument
#   so the caller can express both cases. When failed_port is None, the
#   whole node is dropped. When set, only the failed GPU is dropped.
#
# UPDATES (2026-10-12):
#   - Added `import json` (was missing, causing NameError on AMD nodes
#     whose `gpus` field is a JSON list).
#   - Added `_remove_failed_node()` and `_remove_failed_gpu()` helpers.
#   - `_find_warm_spare()` now takes `surviving_nodes` and
#     `failed_vram_mb` as arguments instead of computing them from a
#     mismatched list. The previous version always saw
#     `failed_vram_mb == 0` because the failed node had already been
#     filtered out of the list that was passed in, so Condition 1 of
#     the warm-spare check never fired.
#   - `restart_without_node()` accepts `failed_port` for per-GPU
#     failures and returns `vram_lost_mb` in the response.
#
# UPDATES (2026-10-19):
#   - `_find_warm_spare()` is now async. It awaits `asyncio.to_thread`
#     around `_odoo_rpc_sync_search` so the Odoo query does not block
#     the asyncio event loop. A 15-second synchronous Odoo call inside
#     an async function freezes every other request served by the
#     LangGraph container for the duration of the call, which is
#     especially damaging during a demo failover because the Launcher
#     health probe and any in-flight chat request are stalled by it.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

import asyncio
import json
import logging
import os
import re
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import httpx

_logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PROXY_URL = os.getenv("ODOO_PROXY_URL", "http://odoo-proxy:8080")
PROXY_API_KEY = os.getenv("ODOO_API_KEY", "")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_UID = int(os.getenv("ODOO_USER", "1"))
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")

# Paths inside the langgraph-server container.
COMPOSE_FILE = os.getenv(
    "RPC_COMPOSE_FILE",
    "/app/deploy/docker/docker-compose.yaml",
)
RPC_ENV_FILE = os.getenv("RPC_ENV_FILE", "/app/deploy/docker/rpc.env")

# Distributed offload rejection threshold.
MIN_REMOTE_SHARE = 0.01

# CPU RAM haircut factor.
CPU_RAM_HAIRCUT = 0.5

# Default model layer count. Overridable by MODEL_LAYERS env var.
DEFAULT_MODEL_LAYERS = int(os.getenv("MODEL_LAYERS", "28"))

# RPC worker port. Individual GPUs get their own ports; the spoke agent
# assigns port = base + gpu_index. This constant is the starting point.
RPC_WORKER_PORT = int(os.getenv("RPC_WORKER_PORT", "50052"))

# TCP probe timeout for pre-generation checks.
RPC_PROBE_TIMEOUT = 2.0


class RPCSchedulerError(Exception):
    """Raised when the scheduler cannot complete an operation."""


class RPCScheduler:
    """
    Orchestrates the llama.cpp RPC cluster.

    Public entry points:
      - launch_cluster(cluster_id): start the master with all healthy workers
      - restart_without_node(cluster_id, failed_node_id, failed_port=None):
        drain-and-restart after a worker failure
      - pre_generation_check(cluster_id): verify all workers are reachable
    """

    def __init__(self, connector=None):
        """
        connector is an optional override for future use with the connector
        framework. When None, uses the odoo-proxy directly over httpx.
        """
        self.connector = connector

    # -------------------------------------------------------------------------
    # Odoo RPC helpers
    # -------------------------------------------------------------------------

    async def _odoo_rpc(
        self,
        model: str,
        method: str,
        args: List[Any],
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Call an Odoo model method via the odoo-proxy's JSON-RPC endpoint.

        All reads and writes go through this helper. Using the proxy
        instead of the direct Odoo endpoint means the scheduler works
        inside the langgraph-server container without needing the Odoo
        URL, and the proxy handles authentication with the service user.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [ODOO_DB, ODOO_UID, ODOO_PASSWORD, model, method, args, kwargs or {}],
            },
            "id": 1,
        }
        headers = {"X-API-Key": PROXY_API_KEY, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{PROXY_URL}/jsonrpc", json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise RPCSchedulerError(f"Odoo error: {body['error']}")
            return body.get("result")

    # -------------------------------------------------------------------------
    # Read cluster state
    # -------------------------------------------------------------------------

    async def read_cluster_and_nodes(
        self, cluster_id: int
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Read the cluster record and its RPC worker nodes from Odoo.

        Field names — important:
          The gpu.node model uses `wireguard_ip` (set at registration
          time to either the WireGuard address or the spoke's LAN IP)
          and `state` (active / inactive). Reading any other field name
          causes search_read to silently drop the field, and the
          scheduler then fails to find any usable workers.

        The `gpus` field is a JSON list. Each entry describes one GPU:
            {
              "index": 0,
              "vendor": "amd",
              "model": "AMD Radeon RX 6700 XT",
              "memory_mb": 16384,
              "rpc_port": 50052,
              ...
            }
        Reading it lets effective_capacity compute real VRAM even when
        the (non-stored) total_vram_gb compute field is unavailable.
        """
        clusters = await self._odoo_rpc(
            "gpu.cluster",
            "read",
            [[cluster_id]],
            {
                "fields": [
                    "id",
                    "name",
                    "layer_assignment",
                    "wireguard_mesh_subnet",
                    "allow_dynamo_fallback",
                    "allow_rpc_partial_fallback",
                    "allow_marketplace_fallback",
                    "allow_external_api_fallback",
                    "external_api_provider",
                    "external_api_model",
                ]
            },
        )
        if not clusters:
            raise RPCSchedulerError(f"Cluster {cluster_id} not found")

        nodes = await self._odoo_rpc(
            "gpu.node",
            "search_read",
            [
                [
                    ("cluster_id", "=", cluster_id),
                    ("inference_capability", "=", "rpc_worker"),
                    ("state", "=", "active"),
                ]
            ],
            {
                "fields": [
                    "id",
                    "name",
                    "hostname",
                    "wireguard_ip",
                    "gpus",
                    "compute_profile",
                    "state",
                    "last_seen",
                ]
            },
        )
        return clusters[0], nodes

    # -------------------------------------------------------------------------
    # Pre-generation health check
    # -------------------------------------------------------------------------

    async def pre_generation_check(self, cluster_id: int) -> bool:
        """
        Verify that every RPC worker in the cluster is reachable AND the
        cluster has enough total VRAM to hold the model.

        Called by the supervisor before routing a pinned RPC request.

        Two checks:

          (a) TCP connect to every worker port. We iterate over each
              GPU in each node's `gpus` JSON list, because a multi-GPU
              node exposes one port per GPU.

          (b) Sum VRAM across every GPU and compare against
              `MODEL_SIZE_BYTES × 1.15`. The 15% headroom accounts for
              fragmentation and runtime scratch buffers.

        Returns False on any failure. The supervisor uses that to enter
        the failover hierarchy (Dynamo, partial RPC, marketplace,
        external API, or fail-loud with HTTP 503).
        """
        try:
            cluster, nodes = await self.read_cluster_and_nodes(cluster_id)
        except RPCSchedulerError:
            _logger.warning("pre_generation_check: cluster %s not found", cluster_id)
            return False
        except httpx.HTTPError as e:
            # Odoo or the proxy is unreachable or returned an error.
            # Treat this as "cannot verify the cluster", which is what
            # we want: the caller then evaluates the failover policy.
            # If the policy permits Dynamo, the request routes there.
            # If not, it fails loudly. It never silently downgrades to
            # local CPU.
            _logger.warning(
                "pre_generation_check: Odoo unreachable (%s) — "
                "cluster cannot be verified; treating as unreachable",
                e,
            )
            return False
        if not nodes:
            _logger.warning("pre_generation_check: no workers in cluster %s", cluster_id)
            return False

        # Build the list of (label, ip, port) probe targets. One per GPU.
        probes: List[Tuple[str, str, int]] = []
        total_vram_mb = 0
        for n in nodes:
            ip = n.get("wireguard_ip")
            if not ip:
                _logger.debug(
                    "pre_generation_check: node %s has no wireguard_ip; skipping",
                    n.get("name"),
                )
                continue
            gpus = n.get("gpus") or []
            if isinstance(gpus, str):
                try:
                    gpus = json.loads(gpus)
                except Exception:
                    gpus = []
            if gpus:
                for i, g in enumerate(gpus):
                    port = int(g.get("rpc_port") or (RPC_WORKER_PORT + i))
                    probes.append((f"{n.get('name')}#{i}", ip, port))
                    total_vram_mb += int(g.get("memory_mb") or 0)
            else:
                # Node with no GPU list (CPU-only or missing data).
                probes.append((n.get("name", "?"), ip, RPC_WORKER_PORT))
                total_vram_mb += self._node_vram_mb(n)

        if not probes:
            _logger.warning(
                "pre_generation_check: no probe targets in cluster %s", cluster_id,
            )
            return False

        # ---- Check (a): heartbeat freshness ------------------------------
        # Do NOT TCP-probe the rpc-server ports. A bare TCP connect
        # (asyncio.open_connection) against the ggml rpc-server completes
        # the kernel handshake, then never sends the ggml binary handshake
        # bytes. The server's handle_connection() blocks on recv(), the
        # 1-deep accept queue fills with phantom connections, and the
        # worker becomes unreachable until the process is killed.
        #
        # Instead use the spoke's 10-second heartbeat. Odoo's
        # gpu.node.last_seen is updated on every /api/v1/gpu/heartbeat POST.
        # A node whose last_seen is older than 30 seconds is offline.
        # Same threshold as the health monitor's heartbeat_staleness.
        from datetime import datetime as _dt
        _now = _dt.utcnow()
        for n in nodes:
            _ls = n.get("last_seen")
            if not _ls:
                _logger.warning(
                    "pre_generation_check: node %s has no last_seen",
                    n.get("name"),
                )
                return False
            try:
                _ts = _dt.strptime(_ls, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                _logger.warning(
                    "pre_generation_check: node %s malformed last_seen=%r",
                    n.get("name"), _ls,
                )
                return False
            _age = (_now - _ts).total_seconds()
            if _age > 30:
                _logger.warning(
                    "pre_generation_check: node %s last_seen is %.0fs old",
                    n.get("name"), _age,
                )
                return False

        # ---- Check (b): VRAM sufficiency ----------------------------------
        # Even if every worker is reachable, the cluster must have enough
        # total VRAM to hold the model. This catches the case where a
        # worker was removed from gpu.node in Odoo, or where the cluster
        # was undersized at launch and never had enough capacity.
        #
        # Without this check, an undersized cluster would pass the TCP
        # probe, the supervisor would route the request to RPC, and the
        # master would either silently offload layers to CPU (producing
        # worse answers) or abort mid-request (producing a debug-hostile
        # 500). Neither is acceptable.
        model_size_bytes = int(os.getenv("MODEL_SIZE_BYTES", "4683073248"))
        required_vram_mb = int((model_size_bytes / (1024 * 1024)) * 1.15)
        if total_vram_mb < required_vram_mb:
            _logger.warning(
                "pre_generation_check: cluster %s has %dMB VRAM across "
                "%d workers, below the %dMB needed for the model. "
                "Failing the check so the supervisor applies the "
                "failover policy.",
                cluster_id, total_vram_mb, len(probes), required_vram_mb,
            )
            return False
        # Verify the master is actually running and healthy
        try:
            async with httpx.AsyncClient(timeout=2.0) as _client:
                resp = await _client.get("http://llama-rpc-master:8082/health")
            if resp.status_code != 200:
                _logger.warning("pre_generation_check: master is up but unhealthy")
                return False
        except Exception as e:
            _logger.warning("pre_generation_check: master unreachable: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Capacity model
    # -------------------------------------------------------------------------

    def effective_capacity(self, node: Dict[str, Any]) -> float:
        """
        Compute a node's effective capacity for the tensor-split weighting.

        Rules:
          - Sum VRAM from the `gpus` JSON field. This is the authoritative
            value written by the spoke at registration and refreshed on
            each heartbeat.
          - If the sum is zero, fall back to system RAM * 0.5.
          - If both are zero, return a small positive value so the node
            still receives one layer (llama.cpp requires at least one).
        """
        gpus = node.get("gpus") or []
        if isinstance(gpus, str):
            try:
                gpus = json.loads(gpus)
            except Exception:
                gpus = []
        total_vram_mb = 0
        for g in gpus:
            try:
                total_vram_mb += int(g.get("memory_mb") or 0)
            except (TypeError, ValueError):
                pass
        if total_vram_mb > 0:
            return total_vram_mb / 1024.0  # GB

        profile = node.get("compute_profile") or {}
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except Exception:
                profile = {}
        ram_gb = float(profile.get("ram_gb") or 0.0)
        if ram_gb > 0:
            return ram_gb * CPU_RAM_HAIRCUT
        return 0.5

    # -------------------------------------------------------------------------
    # VRAM extraction helper (used by _find_warm_spare and elsewhere)
    # -------------------------------------------------------------------------

    def _node_vram_mb(self, node: Dict[str, Any]) -> int:
        """
        Sum the VRAM of a node from its `gpus` JSON field.

        Falls back to `compute_profile.vram_gb`, then to zero. Returns
        an int count of megabytes. Never raises.

        Used by:
          - _find_warm_spare to check the spare against the lost capacity
          - restart_without_node to check the reconstituted cluster
          - pre_generation_check as a fallback when no GPU list is present
        """
        gpus = node.get("gpus") or []
        if isinstance(gpus, str):
            try:
                gpus = json.loads(gpus)
            except Exception:
                gpus = []
        total = 0
        for g in gpus:
            try:
                total += int(g.get("memory_mb") or 0)
            except (TypeError, ValueError):
                pass
        if total > 0:
            return total

        profile = node.get("compute_profile") or {}
        if isinstance(profile, str):
            try:
                profile = json.loads(profile)
            except Exception:
                profile = {}
        vram_gb = float(profile.get("vram_gb") or 0.0)
        return int(vram_gb * 1024)

    # -------------------------------------------------------------------------
    # Layer assignment
    # -------------------------------------------------------------------------

    def compute_layer_assignment(
        self, nodes, total_layers=None,
    ):
        """
        Compute a proportional layer assignment across every GPU of every
        node.

        A node with N GPUs contributes N backends, not one. The port of
        each backend comes from the GPU record's `rpc_port` field, or
        falls back to `RPC_WORKER_PORT + i`.

        Returns a 3-tuple:
            assignment    : {f"{node_id}:{port}": {hostname, wg_ip,
                             rpc_port, start_layer, end_layer, share}}
            rpc_backends  : ["10.100.0.5:50052", "10.100.0.6:50052", ...]
            rpc_split     : ["0.727", "0.182", "0.091"]

        Raises RPCSchedulerError if no node has a usable IP, or if the
        resulting remote share is below MIN_REMOTE_SHARE.
        """
        total_layers = total_layers or DEFAULT_MODEL_LAYERS
        if not nodes:
            raise RPCSchedulerError("No healthy RPC workers available")

        # Expand nodes → (node, ip, port, capacity) tuples.
        expanded: List[Tuple[Dict[str, Any], str, int, float]] = []
        for n in nodes:
            wg_ip = n.get("wireguard_ip")
            if not wg_ip:
                continue
            gpus = n.get("gpus") or []
            if isinstance(gpus, str):
                try:
                    gpus = json.loads(gpus)
                except Exception:
                    gpus = []
            if not gpus:
                # CPU-only node: one backend per node, port = base.
                expanded.append(
                    (n, wg_ip, RPC_WORKER_PORT, self.effective_capacity(n))
                )
                continue
            for i, g in enumerate(gpus):
                port = int(g.get("rpc_port") or (RPC_WORKER_PORT + i))
                # Per-GPU capacity, not per-node.
                cap = max(1.0, int(g.get("memory_mb") or 0) / 1024.0)
                expanded.append((n, wg_ip, port, cap))

        if not expanded:
            raise RPCSchedulerError("No RPC worker has a usable device")

        total_cap = sum(c for _, _, _, c in expanded)
        if total_cap <= 0:
            raise RPCSchedulerError("Total capacity is zero")

        # Reject no-op distributed offload.
        shares = [c / total_cap for _, _, _, c in expanded]
        remote_share = sum(shares)
        if remote_share < MIN_REMOTE_SHARE:
            raise RPCSchedulerError(
                f"Remote share {remote_share:.4f} below threshold "
                f"{MIN_REMOTE_SHARE} — refusing to enable RPC"
            )

        # Assign layers proportionally, ensuring every worker gets ≥1 layer.
        rpc_backends: List[str] = []
        rpc_split: List[str] = []
        assignment: Dict[str, Any] = {}
        cursor = 0
        for (node, ip, port, cap), share in zip(expanded, shares):
            layers = max(1, round(total_layers * share))
            end = min(cursor + layers - 1, total_layers - 1)
            rpc_backends.append(f"{ip}:{port}")
            rpc_split.append(f"{share:.6f}")
            key = f"{node['id']}:{port}"
            assignment[key] = {
                "hostname": node.get("hostname"),
                "wg_ip": ip,
                "rpc_port": port,
                "start_layer": cursor,
                "end_layer": end,
                "share": round(share, 6),
            }
            cursor = end + 1
            if cursor >= total_layers:
                break

        # Re-normalise rpc_split so the sum is exactly 1.0 (llama.cpp is
        # strict about this).
        s = sum(float(x) for x in rpc_split)
        if s > 0:
            rpc_split = [f"{float(x) / s:.6f}" for x in rpc_split]

        return assignment, rpc_backends, rpc_split

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    async def persist_assignment(
        self, cluster_id: int, assignment: Dict[str, Any]
    ) -> None:
        """
        Write the layer assignment back to gpu.cluster.layer_assignment.

        Preserved even when the cluster is stopped, so the operator can
        inspect the topology that was last running.
        """
        await self._odoo_rpc(
            "gpu.cluster",
            "write",
            [[cluster_id], {"layer_assignment": assignment}],
        )

    def write_rpc_env(self, rpc_backends: List[str], rpc_split: List[str]) -> None:
        """
        Write RPC_BACKENDS and RPC_SPLIT to the rpc.env file.

        The master container reads these at startup. When both are empty,
        the master runs single-node (no distributed offload).

        The write is done through a small helper that does an in-place
        replace of the key if present, or appends it at the end with a
        proper leading newline if absent. This avoids the class of bug
        where two keys get concatenated onto one line.
        """
        backends_str = ",".join(rpc_backends)
        split_str = ",".join(rpc_split)

        try:
            with open(RPC_ENV_FILE, "r") as f:
                content = f.read()
        except FileNotFoundError:
            content = ""

        def _set(content: str, key: str, value: str) -> str:
            pattern = rf"^{re.escape(key)}=.*$"
            if re.search(pattern, content, flags=re.MULTILINE):
                return re.sub(pattern, f"{key}={value}", content, flags=re.MULTILINE)
            if content and not content.endswith("\n"):
                content += "\n"
            return content + f"{key}={value}\n"

        content = _set(content, "RPC_BACKENDS", backends_str)
        content = _set(content, "RPC_SPLIT", split_str)
        # NEW: ensure all layers are offloaded to the RPC fabric.
        # MODEL_LAYERS is the model's layer count; using it (or 99) ensures
        # the master does not silently keep layers on CPU.
        model_layers = os.getenv("MODEL_LAYERS", "28")
        content = _set(content, "RPC_N_GPU_LAYERS", model_layers)

        with open(RPC_ENV_FILE, "w") as f:
            f.write(content)

        _logger.info(
            "rpc.env updated: RPC_BACKENDS=%s RPC_SPLIT=%s",
            backends_str,
            split_str,
        )

    # -------------------------------------------------------------------------
    # Docker control
    # -------------------------------------------------------------------------

    def _recreate_master_sync(self) -> bool:
        """
        Synchronous master recreation. Called via run_in_executor from
        the async wrapper. Do not call directly from async code — a
        120-second docker compose run would freeze the event loop.

        Uses docker compose with --force-recreate so the master picks up
        the new RPC_BACKENDS and RPC_SPLIT from rpc.env.
        """
        cmd = [
            "docker", "compose", "-f", COMPOSE_FILE,
            "--profile", "rpc", "up", "-d", "--force-recreate",
            "llama-rpc-master",
        ]
        _logger.info("Recreating llama-rpc-master: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, 
                cwd=os.path.dirname(COMPOSE_FILE)  # <-- Add this line
            )
        except subprocess.TimeoutExpired:
            _logger.error("docker compose timed out")
            return False
        if result.returncode != 0:
            _logger.error(
                "docker compose failed (rc=%s): %s",
                result.returncode, result.stderr,
            )
            return False
        _logger.info("llama-rpc-master recreated")
        return True

    async def recreate_master(self) -> bool:
        """
        Async wrapper. Runs the synchronous docker compose call in the
        default thread pool so the asyncio event loop stays responsive.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._recreate_master_sync)

    def stop_master(self) -> bool:
        """Stop the master cleanly (used before recreate)."""
        cmd = [
            "docker", "compose", "-f", COMPOSE_FILE,
            "--profile", "rpc", "stop", "llama-rpc-master",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except Exception as e:
            _logger.warning("stop_master failed: %s", e)
            return False

    # -------------------------------------------------------------------------
    # Failure filtering helpers (2026-10-12)
    # -------------------------------------------------------------------------

    def _remove_failed_node(
        self,
        nodes: List[Dict[str, Any]],
        failed_node_id: Any,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove an entire node from the cluster (whole-machine failure).

        Use this when the machine is powered off, the network is down,
        or the OS has crashed — in other words, every GPU on the node is
        gone. The lost capacity is the node's total VRAM.

        Returns:
            (surviving_nodes, failed_vram_mb)
            - surviving_nodes: the list without the failed node
            - failed_vram_mb: total VRAM of the failed node, i.e. the
              capacity that must be replaced to rebuild the pipeline.
        """
        failed_vram_mb = 0
        surviving: List[Dict[str, Any]] = []
        for n in nodes:
            if str(n.get("id")) == str(failed_node_id):
                failed_vram_mb = self._node_vram_mb(n)
                _logger.info(
                    "Whole-node failure: removing node %s (id=%s, %dMB VRAM)",
                    n.get("name"), n.get("id"), failed_vram_mb,
                )
            else:
                surviving.append(n)
        return surviving, failed_vram_mb

    def _remove_failed_gpu(
        self,
        nodes: List[Dict[str, Any]],
        failed_node_id: Any,
        failed_port: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove a single GPU from a node (per-GPU / per-rpc-server failure).

        Use this when one rpc-server process on one GPU has crashed or
        one GPU has failed, but the machine and its other GPUs are still
        healthy. The node stays in the cluster with its remaining GPUs.
        The lost capacity is that one GPU's VRAM.

        If the failed port is the last port on the node, the whole node
        is dropped — there is nothing left to contribute.

        Returns:
            (surviving_nodes, failed_vram_mb)
            - surviving_nodes: the list, with the failed GPU filtered out
              of the failed node's `gpus` array. A shallow copy of the
              node dict is used so the caller's data is not mutated.
            - failed_vram_mb: VRAM of the failed GPU.
        """
        failed_vram_mb = 0
        surviving: List[Dict[str, Any]] = []
        for n in nodes:
            if str(n.get("id")) != str(failed_node_id):
                surviving.append(n)
                continue

            # This is the failed node. Parse its GPUs and remove the
            # failed port's GPU.
            gpus = n.get("gpus") or []
            if isinstance(gpus, str):
                try:
                    gpus = json.loads(gpus)
                except Exception:
                    gpus = []

            surviving_gpus: List[Dict[str, Any]] = []
            for i, g in enumerate(gpus):
                port = int(g.get("rpc_port") or (RPC_WORKER_PORT + i))
                if port == int(failed_port):
                    failed_vram_mb = int(g.get("memory_mb") or 0)
                    _logger.info(
                        "Per-GPU failure: dropping GPU %d from node %s "
                        "(port=%d, vram=%dMB)",
                        i, n.get("name"), port, failed_vram_mb,
                    )
                else:
                    surviving_gpus.append(g)

            if not surviving_gpus:
                _logger.info(
                    "Node %s has no surviving GPUs after removing port "
                    "%s — dropping whole node",
                    n.get("name"), failed_port,
                )
                continue

            # Shallow copy so we do not mutate the caller's node dict.
            # The `gpus` key gets a fresh list; everything else is shared.
            n_copy = dict(n)
            n_copy["gpus"] = surviving_gpus
            surviving.append(n_copy)

        return surviving, failed_vram_mb

    # -------------------------------------------------------------------------
    # Warm spare promotion
    # -------------------------------------------------------------------------

    async def _find_warm_spare(
        self,
        cluster: Dict[str, Any],
        surviving_nodes: List[Dict[str, Any]],
        failed_vram_mb: int,
        exclude_node_ids: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Find a node that can replace the capacity lost in an RPC pipeline.

        ## Pipeline-parallelism reminder

        llama.cpp RPC uses pipeline parallelism: the model's layers are
        split into contiguous chunks and each chunk lives in the VRAM of
        exactly one worker. Losing a worker means losing that worker's
        layer chunk AND its VRAM. A replacement worker must therefore be
        able to hold roughly the same chunk — NOT the whole model. That
        is why condition 1 below compares the spare against
        `failed_vram_mb` (the capacity that was lost) rather than against
        the model size.

        ## Conditions

        A spare is viable if BOTH hold:

          1. `spare_vram_mb >= failed_vram_mb`
             The spare can absorb the failed chunk without compressing
             or offloading it. This is the pipeline-parallelism
             requirement and it is the primary test.

          2. `surviving_vram_mb + spare_vram_mb >= required_vram_mb`
             The reconstituted cluster can still hold the whole model.
             `required_vram_mb = model_size_bytes × 1.15 / 1MB`. The
             15% headroom accounts for fragmentation and runtime scratch
             buffers. This is a defensive check against a cluster that
             was undersized at launch time.

        ## What happens if no spare qualifies

        Returns None. The caller (`restart_without_node`) then checks
        whether the surviving nodes alone can hold the model. If not, it
        stops the master and lets the supervisor apply the failover
        policy (Dynamo, partial RPC, marketplace, external API, or
        fail-loud). The scheduler never silently degrades to a smaller
        model.

        ## Async note (2026-10-19)

        This method is `async` even though its body is mostly pure
        Python. The one I/O call — the Odoo query for candidate spares —
        is dispatched to a worker thread via `asyncio.to_thread` so the
        synchronous `httpx.Client` inside `_odoo_rpc_sync_search` does
        not block the LangGraph event loop. A 15-second Odoo call
        inside an async function freezes every other request served by
        the container for the duration of the call.
        """
        # ---- 1. Compute surviving cluster VRAM ---------------------------
        surviving_vram_mb = sum(
            self._node_vram_mb(n) for n in surviving_nodes
        )

        # ---- 2. Model-size threshold -------------------------------------
        # MODEL_SIZE_BYTES defaults to the DeepSeek-R1-7B-Q4_K_M size.
        # 15% headroom is applied so we do not promote a spare that
        # exactly matches the model size (fragmentation eats ~10-15%).
        model_size_bytes = int(os.getenv("MODEL_SIZE_BYTES", "4683073248"))
        required_vram_mb = int((model_size_bytes / (1024 * 1024)) * 1.15)

        # ---- 3. Query candidate spares -----------------------------------
        # A candidate is any gpu.node in the same cluster that:
        #   - is an rpc_worker
        #   - is active
        #   - is not already contributing to the surviving cluster
        #   - is not the failed node itself
        #
        # We include nodes that were never part of the cluster — a cold
        # spare that has been warming up will appear here the moment its
        # `model_cached` flag flips true.
        #
        # CRITICAL: do not pass an empty `not in []` list. Odoo's domain
        # evaluator matches every row when the list is empty, which would
        # cause the failed node to be returned as a viable spare for
        # itself, followed by restart_without_node adding it back to the
        # surviving set. That produces a "cluster" that contains only the
        # node that just died, and the next request then has to fail
        # over anyway — but the assignment is now corrupt.
        #
        # We also cast ids to int because Odoo's `not in` on an Integer
        # field silently matches everything when the list contains
        # strings instead of ints. That mistake is easy to make because
        # the health monitor keys nodes by string (str(n.id)).
        excluded_ids: List[int] = []
        for n in surviving_nodes:
            try:
                excluded_ids.append(int(n["id"]))
            except (KeyError, TypeError, ValueError):
                pass
        for eid in (exclude_node_ids or []):
            try:
                excluded_ids.append(int(eid))
            except (TypeError, ValueError):
                pass

        if excluded_ids:
            domain = [
                ("cluster_id", "=", cluster["id"]),
                ("inference_capability", "=", "rpc_worker"),
                ("state", "=", "active"),
                ("id", "not in", excluded_ids),
            ]
        else:
            # No surviving nodes and no explicit exclusion. This should not
            # happen in practice because the caller always passes the
            # failed node id, but we fail safe: return None rather than
            # promote anything. The caller will then follow the failover
            # policy (Tier 2 / Tier 6) instead of silently rebuilding an
            # empty cluster.
            _logger.warning(
                "_find_warm_spare called with no surviving nodes and no "
                "exclusion — refusing to promote any candidate. The "
                "caller should pass exclude_node_ids=[failed_node_id]."
            )
            return None

        try:
            spares = await asyncio.to_thread(
                self._odoo_rpc_sync_search,
                "gpu.node",
                domain,
                [
                    "id", "name", "hostname", "wireguard_ip",
                    "gpus", "compute_profile", "state",
                ],
            )
        except Exception as e:
            _logger.warning("Warm-spare lookup failed: %s", e)
            return None

        # ---- 4. Filter candidates ----------------------------------------
        for spare in spares:
            profile = spare.get("compute_profile") or {}
            if isinstance(profile, str):
                try:
                    profile = json.loads(profile)
                except Exception:
                    profile = {}
            if not profile.get("model_cached"):
                # A spare that does not have the model cached cannot be
                # promoted instantly. It would need to download the GGUF
                # first, which defeats the purpose of a "warm" spare.
                continue

            spare_vram_mb = self._node_vram_mb(spare)

            # Condition 1: the spare must be at least as big as the lost
            # capacity. This is the pipeline-parallelism requirement.
            if failed_vram_mb > 0 and spare_vram_mb < failed_vram_mb:
                _logger.warning(
                    "Warm spare %s (id=%s) has %dMB VRAM, less than the "
                    "lost capacity %dMB. Not promoting — the rebuilt "
                    "pipeline would be under capacity.",
                    spare.get("name"), spare.get("id"),
                    spare_vram_mb, failed_vram_mb,
                )
                continue

            # Condition 2: the reconstituted cluster must still hold the
            # whole model with headroom.
            total_vram_mb = surviving_vram_mb + spare_vram_mb
            if total_vram_mb < required_vram_mb:
                _logger.warning(
                    "Warm spare %s (id=%s) would bring the cluster to "
                    "%dMB, below the %dMB needed to fit the model. Not "
                    "promoting.",
                    spare.get("name"), spare.get("id"),
                    total_vram_mb, required_vram_mb,
                )
                continue

            _logger.info(
                "Found viable warm spare: %s (id=%s, %dMB VRAM, "
                "matches lost capacity's %dMB; cluster total %dMB >= "
                "required %dMB)",
                spare.get("name"), spare.get("id"),
                spare_vram_mb, failed_vram_mb,
                total_vram_mb, required_vram_mb,
            )
            return spare

        _logger.warning(
            "No viable warm spare found in cluster %s. "
            "Falling through to failover policy tiers.",
            cluster.get("name"),
        )
        return None

    # -------------------------------------------------------------------------
    # Public entry points
    # -------------------------------------------------------------------------

    async def launch_cluster(self, cluster_id: int) -> Dict[str, Any]:
        """
        Read cluster state, compute the assignment, write rpc.env, and
        recreate the master container.

        Called on first launch, and any time the operator wants to force
        a topology refresh.
        """
        cluster, nodes = await self.read_cluster_and_nodes(cluster_id)
        _logger.info(
            "launch_cluster: cluster=%s workers=%d",
            cluster["name"], len(nodes),
        )

        try:
            assignment, backends, splits = self.compute_layer_assignment(nodes)
        except RPCSchedulerError as e:
            _logger.warning("launch_cluster aborted: %s", e)
            return {"success": False, "error": str(e)}

        await self.persist_assignment(cluster_id, assignment)
        self.write_rpc_env(backends, splits)
        ok = await self.recreate_master()

        return {
            "success": ok,
            "cluster_id": cluster_id,
            "workers": len(backends),
            "assignment": assignment,
        }

    async def restart_without_node(
        self,
        cluster_id: int,
        failed_node_id: Any,
        failed_port: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Drain-and-restart after a worker (or whole node) fails.

        Two failure modes:

          * Whole-node failure (failed_port is None):
              The entire node is removed from the cluster. All its GPUs
              and their RPC workers go with it. `failed_vram_mb` is the
              whole node's VRAM. Use this when the machine is powered
              off, the network is down, or the OS has crashed.

          * Per-GPU failure (failed_port set):
              Only the specific rpc-server instance on the failed port
              is removed. The node stays in the cluster with its
              remaining GPUs. `failed_vram_mb` is that one GPU's VRAM.
              Use this when a single GPU has failed or a single
              rpc-server process has crashed but the machine is up.

        Priority order:
          1. If a warm spare exists (model cached, enough VRAM to hold
             the lost chunk, cluster still fits the model), promote it
             and rebuild at full capacity.
          2. Otherwise, rebuild with whatever workers remain.
          3. If no workers remain, return failure so the supervisor can
             apply the failover policy (Dynamo, marketplace, etc.).
          4. If the survivors are undersized for the model, STOP the
             master and leave RPC_BACKENDS empty. Do NOT rebuild with a
             topology that cannot hold the model — that would either
             silently offload layers to CPU (producing worse answers)
             or abort at load time (producing a debug-hostile 500).
        """
        cluster, nodes = await self.read_cluster_and_nodes(cluster_id)

        # -----------------------------------------------------------------
        # Step 1 — compute the surviving set and the lost VRAM.
        #
        # The two helper methods encapsulate the difference between
        # whole-node failure and per-GPU failure. Both return
        # (surviving_nodes, failed_vram_mb).
        # -----------------------------------------------------------------
        if failed_port is not None:
            surviving_nodes, failed_vram_mb = self._remove_failed_gpu(
                nodes, failed_node_id, failed_port,
            )
        else:
            surviving_nodes, failed_vram_mb = self._remove_failed_node(
                nodes, failed_node_id,
            )

        _logger.warning(
            "restart_without_node: cluster=%s failed_node=%s "
            "failed_port=%s vram_lost=%dMB surviving_nodes=%d",
            cluster["name"], failed_node_id, failed_port,
            failed_vram_mb, len(surviving_nodes),
        )

        # -----------------------------------------------------------------
        # Step 2 — try to promote a warm spare.
        #
        # This is the fast path: a spare with the model cached and
        # enough VRAM to hold the lost chunk rebuilds the cluster at
        # full capacity. Conditions are checked inside _find_warm_spare.
        # -----------------------------------------------------------------
        # Pass the failed node id explicitly so it can never be selected as
        # its own spare. This is the belt-and-braces partner to the domain
        # fix in _find_warm_spare.
        spare = await self._find_warm_spare(
            cluster, surviving_nodes, failed_vram_mb,
            exclude_node_ids=[failed_node_id],
        )
        if spare:
            surviving_nodes.append(spare)
            _logger.info(
                "Promoted warm spare %s (id=%s) to replace the lost capacity",
                spare.get("name"), spare.get("id"),
            )

        # -----------------------------------------------------------------
        # Step 3 — if there are no workers left, signal failover.
        # -----------------------------------------------------------------
        if not surviving_nodes:
            _logger.warning(
                "No workers left in cluster %s — signalling failover policy",
                cluster_id,
            )
            self.stop_master()
            self.write_rpc_env([], [])
            await self.recreate_master()
            return {
                "success": False,
                "cluster_id": cluster_id,
                "no_workers": True,
                "error": "All RPC workers are offline. Failover policy required.",
            }

        # -----------------------------------------------------------------
        # Step 4 — VRAM sufficiency check on the reconstituted cluster.
        #
        # This is the CRITICAL check. The reduced cluster (survivors +
        # any promoted spare) must still be able to hold the WHOLE model.
        # If it cannot, we do NOT rebuild with fewer workers.
        #
        # Instead we stop the master and leave RPC_BACKENDS empty. The
        # next pinned RPC request will fail its pre_generation_check and
        # the supervisor will apply the failover policy (Tier 2 Dynamo,
        # Tier 3 partial, Tier 4 marketplace, Tier 5 external, Tier 6
        # fail-loud).
        #
        # Without this check, the master would either silently offload
        # layers to CPU (producing worse answers) or abort at load time
        # (producing a debug-hostile 500). Neither is acceptable.
        # -----------------------------------------------------------------
        model_size_bytes = int(os.getenv("MODEL_SIZE_BYTES", "4683073248"))
        required_vram_mb = int((model_size_bytes / (1024 * 1024)) * 1.15)
        total_vram_mb = sum(self._node_vram_mb(n) for n in surviving_nodes)

        if total_vram_mb < required_vram_mb:
            _logger.error(
                "restart_without_node: remaining cluster %s has only "
                "%dMB VRAM across %d nodes, below the %dMB needed for "
                "the model. Refusing to rebuild with an undersized "
                "topology. Failover policy required.",
                cluster["name"], total_vram_mb, len(surviving_nodes),
                required_vram_mb,
            )
            self.stop_master()
            self.write_rpc_env([], [])
            await self.recreate_master()
            return {
                "success": False,
                "cluster_id": cluster_id,
                "no_workers": False,
                "undersized": True,
                "vram_available_mb": total_vram_mb,
                "vram_required_mb": required_vram_mb,
                "error": (
                    f"Remaining cluster has {total_vram_mb}MB VRAM, "
                    f"below the {required_vram_mb}MB needed to fit the "
                    f"model. Failover policy required."
                ),
            }

        # -----------------------------------------------------------------
        # Step 5 — rebuild with the surviving nodes.
        #
        # compute_layer_assignment redistributes the model's layers
        # across every GPU of every surviving node in proportion to
        # each GPU's VRAM. If the promotion of a warm spare introduced
        # new GPUs, they participate in the redistribution.
        # -----------------------------------------------------------------
        try:
            assignment, backends, splits = self.compute_layer_assignment(
                surviving_nodes,
            )
        except RPCSchedulerError as e:
            _logger.error("Cannot rebuild cluster: %s", e)
            self.stop_master()
            self.write_rpc_env([], [])
            await self.recreate_master()
            return {"success": False, "error": str(e), "no_workers": False}

        await self.persist_assignment(cluster_id, assignment)
        self.write_rpc_env(backends, splits)
        ok = await self.recreate_master()

        return {
            "success": ok,
            "cluster_id": cluster_id,
            "workers": len(backends),
            "assignment": assignment,
            "used_warm_spare": bool(spare),
            "no_workers": False,
            "failed_port": failed_port,
            "vram_lost_mb": failed_vram_mb,
        }

    # -------------------------------------------------------------------------
    # Synchronous Odoo search (used by _find_warm_spare)
    # -------------------------------------------------------------------------

    def _odoo_rpc_sync_search(
        self, model: str, domain: list, fields: list
    ) -> list:
        """
        Synchronous Odoo search_read.

        Used by `_find_warm_spare`. Since the 2026-10-19 fix, the caller
        dispatches this method to a worker thread via
        `asyncio.to_thread`, so the sync `httpx.Client` inside this
        method does not block the asyncio event loop.

        The function is kept synchronous because it is also reachable
        from genuinely synchronous code paths (e.g. a future operator
        CLI). The async/sync boundary lives at the caller, not here.
        """
        import httpx as _httpx
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    ODOO_DB, ODOO_UID, ODOO_PASSWORD,
                    model, "search_read", [domain], {"fields": fields},
                ],
            },
            "id": 1,
        }
        headers = {"X-API-Key": PROXY_API_KEY, "Content-Type": "application/json"}
        with _httpx.Client(timeout=15) as client:
            r = client.post(f"{PROXY_URL}/jsonrpc", json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
            if body.get("error"):
                raise RPCSchedulerError(f"Odoo error: {body['error']}")
            return body.get("result", []) or []
