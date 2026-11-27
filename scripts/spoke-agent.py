#!/usr/bin/env python3
# =============================================================================
# NETTRADES Spoke Agent
# =============================================================================
# FILE: scripts/spoke-agent.py
#
# PURPOSE:
#   Lightweight agent that runs on spoke nodes. It:
#     1. Detects every GPU on the host (NVIDIA, AMD, Intel, Apple, CPU).
#     2. Registers with the hub (Odoo) using a one-time token.
#     3. Starts and supervises one rpc-server instance per GPU.
#     4. Sends heartbeats to the hub (Odoo) AND to the LangGraph supervisor.
#     5. Optionally writes a WireGuard client config and starts the tunnel.
#
#   NO Odoo, NO PostgreSQL, NO LangGraph on the spoke. Compute node only.
#
# MULTI-GPU DESIGN (2026-10):
#   llama.cpp's ggml-rpc-server exposes all accelerator devices by default.
#   To use more than one GPU in a pipeline, the standard pattern is to run
#   one rpc-server per GPU, pinned with CUDA_VISIBLE_DEVICES / HIP_VISIBLE_DEVICES
#   and listening on a distinct port:
#
#       CUDA_VISIBLE_DEVICES=0 rpc-server -H 0.0.0.0 -p 50052
#       CUDA_VISIBLE_DEVICES=1 rpc-server -H 0.0.0.0 -p 50053
#       ...
#
#   The hub's RPC master then connects with:
#       --rpc <host>:50052,<host>:50053,...
#
#   We generate exactly this layout. Each RPC worker is its own process with
#   its own systemd transient unit (or Windows scheduled task / process group),
#   and each is restarted independently if it exits.
#
# CROSS-VENDOR RPC:
#   A CUDA master can dispatch to ROCm workers and vice versa. The RPC wire
#   protocol is backend-agnostic; only the tensor data crosses the network.
#   This is why the whole demo works even though the AMD rig, the NVIDIA
#   laptop and the Windows GeForce PC all run different backends.
#
# WIREGUARD MODES:
#   - use_wireguard: false (default) — LAN mode. The spoke registers with its
#     LAN IP; the RPC master connects over plain TCP.
#   - use_wireguard: true — production mode for untrusted networks. The spoke
#     generates a keypair, the hub returns a peer config, the tunnel comes up.
#
# PORTABILITY:
#   The agent runs on Linux, WSL2, Windows and macOS. It degrades gracefully
#   when a vendor's tooling is absent: it probes several fallbacks per vendor
#   (nvidia-smi → /sys → lspci → WMI) and never raises on detection failure.
#
# GRACEFUL DRAIN (2026-10-20):
#   If a spoke is switched off mid-generation, the tokens generated since
#   the last checkpoint are lost and the user has to re-ask the question.
#   The agent now supports a "drain" sequence that gives the hub time to
#   re-route before this node's workers are stopped.
#
#   Three drain triggers, all funnelled through `_trigger_drain()`:
#     1. SIGTERM (from `systemctl stop nettrades-spoke` or system shutdown)
#     2. SIGINT  (Ctrl+C in an interactive session)
#     3. Appearance of the file named in `drain_requested_file` in config
#        (the Windows service writes this file on SERVICE_CONTROL_PRESHUTDOWN)
#
#   Drain sequence in `_drain_and_exit()`:
#     1. Send one heartbeat with `draining=true` so the hub marks the node
#        unavailable and stops routing new requests to it.
#     2. Wait `shutdown_grace_seconds` (default 30) for any in-flight
#        generation on this node to complete.
#     3. Stop the RPC workers. Any tokens still in flight are lost —
#        this is unavoidable without disk-backed llama.cpp checkpoints
#        (llama.cpp issue #20697, unimplemented).
#     4. Write `drain_complete_file` so the Windows service knows we are
#        done, then delete `drain_requested_file`.
#     5. Set `self.running = False` so the main loop exits.
#
#   The systemd unit must set `TimeoutStopSec=90` (>= grace + margin) for
#   the drain to complete before systemd sends SIGKILL. See FAILOVER-HIERARCHY.md
#   § Graceful shutdown for the design rationale.
#
# DESIGN TARGET: < 200 MB RAM, no Odoo/PG/LangGraph dependencies.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.


import argparse
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

# =============================================================================
# Configuration & constants
# =============================================================================

CONFIG_FILE = os.environ.get("SPOKE_CONFIG", "/etc/nettrades/spoke/config.yaml")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("spoke-agent")

WG_INTERFACE = "nettrades"
WG_CONFIG_PATH = os.environ.get("WG_CONFIG_PATH", "/etc/wireguard/nettrades.conf")

# RPC server binary. The installer places it on PATH; the env var lets
# operators point at a custom build (e.g. a Vulkan build on Windows).
RPC_SERVER_BIN = os.environ.get("RPC_SERVER_BIN", "rpc-server")
# Base port for the first GPU. Individual GPUs get base + index.
# The config file's `rpc_port` takes precedence; this is the fallback.
RPC_SERVER_PORT_BASE = int(os.environ.get("RPC_PORT", "50052"))
RPC_HOST = os.environ.get("RPC_HOST", "0.0.0.0")

# If the rpc-server supports the local tensor cache, this flag enables it.
# The cache dramatically reduces re-transfer time across reconnects.
RPC_CACHE_DIR = os.environ.get("RPC_CACHE_DIR", "/var/lib/nettrades/rpc-cache")

DEFAULT_MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    "/var/lib/nettrades/models/model.gguf",
)

# Drain signal file paths (see GRACEFUL DRAIN above). The defaults are
# platform-aware: the Windows path is where the NETTRADES Networking
# Service (nettrades-netsvc) writes its PRESHUTDOWN trigger. The Linux
# path is used only if an external process wants to trigger a drain
# without sending a signal (e.g. a graceful-drain.sh helper).
def _default_drain_paths() -> Tuple[str, str]:
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "NETTRADES")
        return (
            os.path.join(base, "drain.requested"),
            os.path.join(base, "drain.complete"),
        )
    return (
        "/var/lib/nettrades/spoke/drain.requested",
        "/var/lib/nettrades/spoke/drain.complete",
    )


_DEFAULT_DRAIN_REQUESTED, _DEFAULT_DRAIN_COMPLETE = _default_drain_paths()

# Windows: the WMI AdapterRAM field is a 32-bit integer and saturates at
# ~4 GB for any card of 4 GB or larger. The registry value below is the
# only reliable source for VRAM on Windows.
WIN_GPU_REG_PATH = (
    r"HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
)

# PCI vendor IDs used by the sysfs fallback on Linux.
PCI_VENDOR_NVIDIA = "0x10de"
PCI_VENDOR_AMD = "0x1002"
PCI_VENDOR_INTEL = "0x8086"

# ROCm gfx targets that need HSA_OVERRIDE_GFX_VERSION to work under a
# consumer GPU that ROCm does not officially list.
#   RDNA1  (gfx1010/1011/1012)      -> 10.3.0 (looks like RDNA2)
#   RDNA2  (gfx1030/1031/1032/1034) -> 10.3.0
#   RDNA3  (gfx1102/1103)           -> 11.0.0
#   RDNA3+ (gfx1100/1101)           -> 11.0.0 (usually native)
HSA_OVERRIDE_MAP = {
    "gfx1010": "10.3.0",
    "gfx1011": "10.3.0",
    "gfx1012": "10.3.0",
    "gfx1030": "10.3.0",
    "gfx1031": "10.3.0",
    "gfx1032": "10.3.0",
    "gfx1034": "10.3.0",
    "gfx1100": "11.0.0",
    "gfx1101": "11.0.0",
    "gfx1102": "11.0.0",
    "gfx1103": "11.0.0",
}


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class CPUInfo:
    model: str = "unknown"
    physical_cores: int = 0
    logical_cores: int = 0
    architecture: str = "unknown"
    has_avx: bool = False
    has_avx2: bool = False
    has_avx512: bool = False
    has_amx: bool = False
    has_neon: bool = False
    frequency_mhz: float = 0.0
    system_memory_gb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GPUInfo:
    """One physical GPU on this host."""
    index: int                                  # 0-based, order of discovery
    vendor: str                                 # nvidia | amd | intel | apple | unknown
    model: str = "unknown"
    memory_mb: int = 0                          # total VRAM in MB (0 = unknown)
    compute_capability: Optional[str] = None    # CUDA compute cap, e.g. "8.9"
    driver_version: Optional[str] = None
    pci_id: Optional[str] = None
    is_integrated: bool = False
    is_wsl: bool = False

    # Per-vendor device index used for pinning an rpc-server to this GPU.
    # For NVIDIA this is the CUDA_VISIBLE_DEVICES index.
    # For AMD this is the HIP_VISIBLE_DEVICES index.
    # For Intel this is the SYCL / ONEAPI device index.
    vendor_device_index: int = 0

    # Environment variable name and value that pin the rpc-server to this
    # exact device. This is the mechanism that makes multi-GPU pipelines
    # work — one process, one device.
    pin_env_name: Optional[str] = None
    pin_env_value: Optional[str] = None

    # The port this GPU's rpc-server will listen on. Assigned by the
    # agent, starting at RPC_SERVER_PORT_BASE and incrementing.
    rpc_port: int = 0

    # ROCm gfx target and the matching HSA_OVERRIDE_GFX_VERSION value, if
    # this GPU requires one. Empty when the GPU is natively supported.
    gfx_target: Optional[str] = None
    hsa_override_gfx_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SystemProfile:
    """Full hardware profile sent to the hub at registration."""
    hostname: str
    platform: str                               # linux | win32 | darwin
    is_wsl: bool
    cpu: CPUInfo
    gpus: List[GPUInfo]
    rpc_backends: List[str]                     # ["host:50052", "host:50053"]
    has_nvidia_smi: bool = False
    has_rocm: bool = False
    has_vulkan: bool = False
    has_rpc_server: bool = False
    rpc_server_version: Optional[str] = None
    model_cached: bool = False

    @property
    def total_vram_mb(self) -> int:
        return sum(g.memory_mb for g in self.gpus)

    @property
    def gpu_count(self) -> int:
        return len(self.gpus)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hostname": self.hostname,
            "platform": self.platform,
            "is_wsl": self.is_wsl,
            "cpu": self.cpu.to_dict(),
            "gpus": [g.to_dict() for g in self.gpus],
            "rpc_backends": self.rpc_backends,
            "has_nvidia_smi": self.has_nvidia_smi,
            "has_rocm": self.has_rocm,
            "has_vulkan": self.has_vulkan,
            "has_rpc_server": self.has_rpc_server,
            "rpc_server_version": self.rpc_server_version,
            "model_cached": self.model_cached,
            "total_vram_mb": self.total_vram_mb,
            "gpu_count": self.gpu_count,
        }


# =============================================================================
# Platform helpers
# =============================================================================

def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_darwin() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _is_wsl() -> bool:
    """
    Detect WSL2. On WSL2 the kernel string contains "microsoft" and the
    binfmt misc file exists. NVIDIA GPUs are visible via passthrough;
    AMD GPUs are generally NOT usable through ROCm inside WSL2.
    """
    if not _is_linux():
        return False
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                return True
    except (IOError, OSError):
        pass
    return os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")


def _run(cmd: List[str], timeout: int = 5, **kwargs) -> Optional[str]:
    """
    Run a command and return stdout, or None on any failure.

    Defensive wrapper: never raises. Timeouts prevent a hung subprocess
    from blocking the entire detection pass. `shell=False` is the default
    so we are not exposed to shell injection from a corrupted PATH.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            **kwargs,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.debug("command %s returned rc=%s: %s",
                     " ".join(cmd), result.returncode, result.stderr.strip()[:200])
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug("command %s failed: %s", " ".join(cmd), e)
        return None


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


# =============================================================================
# CPU detection
# =============================================================================

def detect_cpu() -> CPUInfo:
    """
    Detect CPU model, core counts, instruction-set features and system RAM.

    On Linux we read /proc/cpuinfo for the feature flags. On macOS we use
    sysctl. On Windows we use platform.processor() and ctypes for RAM.
    """
    info = CPUInfo()

    # ---- model name ----
    if _is_linux():
        try:
            with open("/proc/cpuinfo", "r") as f:
                content = f.read()
            for line in content.split("\n"):
                if line.lower().startswith("model name"):
                    info.model = line.split(":", 1)[1].strip()
                    break
            lower = content.lower()
            info.has_avx = " avx " in lower or " avx\n" in lower
            info.has_avx2 = "avx2" in lower
            info.has_avx512 = "avx512" in lower
            info.has_amx = "amx_" in lower or " amx " in lower
            info.has_neon = "neon" in lower or "asimd" in lower
        except (IOError, OSError):
            pass
    elif _is_darwin():
        info.model = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()
        if platform.machine().lower() in ("arm64", "aarch64"):
            info.has_neon = True
    elif _is_windows():
        info.model = os.environ.get("PROCESSOR_IDENTIFIER", platform.processor())

    # ---- core counts ----
    info.logical_cores = os.cpu_count() or 1
    try:
        info.physical_cores = len(os.sched_getaffinity(0))  # Linux only
    except (AttributeError, OSError):
        info.physical_cores = info.logical_cores

    # ---- architecture ----
    arch = platform.machine().lower()
    info.architecture = (
        "x86_64" if arch in ("x86_64", "amd64")
        else "arm64" if arch in ("aarch64", "arm64")
        else arch
    )

    # ---- RAM ----
    try:
        if _is_linux():
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        info.system_memory_gb = int(line.split()[1]) / (1024 * 1024)
                        break
        elif _is_darwin():
            out = _run(["sysctl", "-n", "hw.memsize"])
            if out:
                info.system_memory_gb = int(out) / (1024 ** 3)
        elif _is_windows():
            import ctypes
            class _MS(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            st = _MS()
            st.dwLength = ctypes.sizeof(st)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            info.system_memory_gb = st.ullTotalPhys / (1024 ** 3)
    except Exception as e:
        logger.debug("RAM detection failed: %s", e)

    return info


# =============================================================================
# GPU detection — per vendor
# =============================================================================

def _detect_nvidia_gpus() -> List[GPUInfo]:
    """
    Detect NVIDIA GPUs via nvidia-smi, which is available on Linux, WSL2
    and Windows (as nvidia-smi.exe). We query one row per GPU and parse
    the CSV output.

    The per-GPU index returned by nvidia-smi is the CUDA_VISIBLE_DEVICES
    index, so we record it as vendor_device_index and build the
    CUDA_VISIBLE_DEVICES pin for each GPU.
    """
    if not _have("nvidia-smi"):
        return []

    out = _run([
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,compute_cap,driver_version",
        "--format=csv,noheader,nounits",
    ], timeout=10)
    if not out:
        return []

    gpus: List[GPUInfo] = []
    for line in out.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            idx = int(parts[0])
            gpu = GPUInfo(
                index=0,  # assigned later
                vendor="nvidia",
                model=parts[1],
                memory_mb=int(float(parts[2])),
                compute_capability=parts[3],
                driver_version=parts[4],
                vendor_device_index=idx,
                pin_env_name="CUDA_VISIBLE_DEVICES",
                pin_env_value=str(idx),
                is_wsl=_is_wsl(),
            )
            gpus.append(gpu)
        except (ValueError, IndexError) as e:
            logger.debug("failed to parse nvidia-smi line %r: %s", line, e)
    return gpus


# =============================================================================
# AMD GPU detection (2026-10-12)
# =============================================================================
# Layered, sysfs-first detection. The sysfs interface exposed by the
# amdgpu kernel driver is the authoritative source for VRAM and GPU
# enumeration. It requires no user-space tooling, runs in microseconds
# per GPU, and does not depend on which ROCm version is installed.
#
# rocm-smi remains a fallback because its output format varies across
# ROCm releases and because we have observed in the field that a
# blank-line-based parser silently merges every GPU into one record
# (rocm-smi does not emit blank lines between GPUs).
#
# rocminfo is still required for one thing only: the per-GPU gfx target,
# which determines whether an HSA_OVERRIDE_GFX_VERSION is needed for a
# consumer card that ROCm does not officially support. It is called ONCE
# per detection pass, not once per GPU.
#
# lspci is used once to translate PCI device IDs into human-readable
# model names. It is optional; if absent, the model name falls back to
# the PCI device ID.
# =============================================================================

# amdgpu sysfs file paths (relative to /sys/class/drm/cardN/device/)
_SYSFS_VRAM_TOTAL = "mem_info_vram_total"
_SYSFS_PCI_DEVICE = "device"
_SYSFS_PCI_VENDOR = "vendor"

# (The dedupe set is per-call, not module-level. See the `seen` local
# inside _detect_amd_gpus_from_sysfs. A module-level set makes the
# function return [] on the second call in the same process, which
# silently breaks any re-detection path. This is fixed 2026-11-16.)


def _detect_amd_gpus() -> List[GPUInfo]:
    """
    Detect every AMD GPU on the host with its VRAM, model name, gfx
    target, and HSA override (if required).

    Order of preference:

      1. Linux sysfs (fast, authoritative, no tools required).
      2. rocm-smi text parse (fallback for non-standard kernels).

    Returns a list of GPUInfo, one per physical AMD GPU, in the same
    order the kernel enumerates them. The order matters because the
    spoke agent pins one rpc-server per GPU by HIP_VISIBLE_DEVICES
    index and the kernel's enumeration order is what HIP uses.

    If no AMD GPU is detected, returns an empty list. The caller then
    tries the next vendor.
    """
    if _is_linux():
        gpus = _detect_amd_gpus_from_sysfs()
        if gpus:
            return gpus

    return _detect_amd_gpus_via_rocm_smi()


def _detect_amd_gpus_from_sysfs() -> List[GPUInfo]:
    """
    Enumerate AMD GPUs from /sys/class/drm and read VRAM, PCI IDs, and
    gfx targets.

    This function is the primary AMD detection path on Linux. It does
    not require ROCm to be installed. It does not require rocm-smi. It
    reads the kernel's view of the hardware directly.

    Fast path cost: ~500 microseconds for a 6-GPU rig (sysfs reads).
    Slow path cost: ~1.5 seconds for the single rocminfo call (gfx
    targets) plus ~10 ms for the single lspci call (model names). The
    slow-path cost is only paid once per detection pass.
    """
    if not _is_linux():
        return []

    import glob as _glob

    # -------------------------------------------------------------------------
    # Step 1: enumerate AMD cards by scanning the DRM vendor files.
    # -------------------------------------------------------------------------
    # /sys/class/drm/cardN/device/vendor is a plain text file containing
    # the PCI vendor ID as a hex string (e.g. "0x1002\n"). It is world
    # readable. Every amdgpu-managed card has one.
    #
    # We dedupe on the realpath of the parent device directory because
    # some kernel configurations expose the same physical GPU under
    # multiple DRM card entries (connector symlinks).
    # -------------------------------------------------------------------------
    raw_cards: List[Tuple[str, Optional[str], int]] = []
    # Per-call dedupe set. Do NOT move this to module level — that makes
    # the function return [] on the second call in the same process, which
    # would silently return no AMD GPUs from any re-detection path
    # (SIGHUP refresh, tests, future endpoints). Diagnosed 2026-11-16.
    seen: set = set()
    for vendor_path in sorted(_glob.glob("/sys/class/drm/card*/device/vendor")):
        card_dir = os.path.dirname(vendor_path)

        # Dedupe by resolved device directory.
        try:
            device_dir = os.path.realpath(card_dir)
        except OSError:
            device_dir = card_dir
        if device_dir in seen:
            continue

        # Read vendor ID.
        try:
            with open(vendor_path, "r") as f:
                vendor_id = f.read().strip().lower()
        except (IOError, OSError):
            continue
        if vendor_id != PCI_VENDOR_AMD:
            continue

        seen.add(device_dir)

        # PCI device ID, used for model-name lookup via lspci.
        device_id: Optional[str] = None
        try:
            with open(os.path.join(card_dir, _SYSFS_PCI_DEVICE), "r") as f:
                device_id = f.read().strip().lower()
        except (IOError, OSError):
            pass

        # VRAM total in bytes. This is the authoritative source.
        vram_bytes = 0
        try:
            with open(os.path.join(card_dir, _SYSFS_VRAM_TOTAL), "r") as f:
                vram_bytes = int(f.read().strip())
        except (IOError, OSError, ValueError):
            vram_bytes = 0

        raw_cards.append((card_dir, device_id, vram_bytes))

    if not raw_cards:
        return []

    # -------------------------------------------------------------------------
    # Step 2: one rocminfo call for all gfx targets.
    # -------------------------------------------------------------------------
    # rocminfo is the only tool that reliably reports the gfx string.
    # Without it, we cannot decide whether an HSA override is needed.
    # It is called once, not once per GPU.
    # -------------------------------------------------------------------------
    gfx_targets = _query_all_amd_gfx_targets()

    # Replicate single-gfx target across all GPUs for homogeneous rigs.
    #
    # _query_all_amd_gfx_targets() deduplicates, so a six-card RX 6700 XT
    # rig (all gfx1031) returns ['gfx1031']. Indexing that list then leaves
    # GPUs 1..5 with gfx_target=None, hence hsa_override_gfx_version=None,
    # hence ROCm refuses the card and rpc-server blocks in GPU init before
    # reaching accept(). The 1-deep accept queue then fills with phantom
    # connections that never reach ESTABLISHED. Confirmed on the demo rig
    # on 2026-10-28: only port 50052 logged (HSA=10.3.0).
    if raw_cards and 0 < len(gfx_targets) < len(raw_cards):
        if len(set(gfx_targets)) == 1:
            gfx_targets = gfx_targets * len(raw_cards)

    # -------------------------------------------------------------------------
    # Step 3: one lspci call for human-readable model names.
    # -------------------------------------------------------------------------
    model_names = _query_amd_model_names_from_lspci()

    # -------------------------------------------------------------------------
    # Step 4: assemble the GPUInfo records.
    # -------------------------------------------------------------------------
    gpus: List[GPUInfo] = []
    for idx, (card_dir, device_id, vram_bytes) in enumerate(raw_cards):
        memory_mb = vram_bytes // (1024 * 1024) if vram_bytes > 0 else 0

        # Model name: lspci lookup first, then PCI device ID, then generic.
        if device_id and device_id in model_names:
            model = model_names[device_id]
        elif device_id:
            model = f"AMD GPU (PCI {device_id})"
        else:
            model = "AMD GPU"

        gfx = gfx_targets[idx] if idx < len(gfx_targets) else None

        gpu = GPUInfo(
            index=0,  # reassigned by detect_gpus
            vendor="amd",
            model=model,
            memory_mb=memory_mb,
            vendor_device_index=idx,
            pin_env_name="HIP_VISIBLE_DEVICES",
            pin_env_value=str(idx),
            pci_id=device_id,
            gfx_target=gfx,
            hsa_override_gfx_version=(
                HSA_OVERRIDE_MAP.get(gfx) if gfx else None
            ),
        )
        gpus.append(gpu)

    # Log a warning if rocminfo is missing but we found AMD GPUs. This
    # is a real diagnostic value: without rocminfo, HSA overrides are
    # not applied and the RX 6700 XT class of card will not work.
    if gpus and not gfx_targets and _have("rocm-smi"):
        logger.warning(
            "AMD GPUs detected via sysfs but rocminfo is unavailable. "
            "HSA overrides cannot be applied, so consumer cards that "
            "require them (e.g. RX 6700 XT / gfx1031) will not run. "
            "Install rocm-hip-libraries to enable rocminfo."
        )

    return gpus


def _query_all_amd_gfx_targets() -> List[str]:
    """
    Return the ROCm gfx target for every AMD GPU on the host, in the
    order the kernel enumerates them.

    A single rocminfo call. rocminfo groups physical agents into
    "Agent" blocks, and each GPU agent carries a line of the form
    "Name: gfxNNNN". We collect every distinct gfx target in order of
    first appearance.

    Returns an empty list if rocminfo is unavailable. In that case the
    caller does not apply HSA overrides — safe, because without ROCm
    the override is not needed.
    """
    if not _have("rocminfo"):
        return []

    out = _run(["rocminfo"], timeout=15)
    if not out:
        return []

    targets: List[str] = []
    for line in out.split("\n"):
        m = re.search(r"\bgfx(\d+[a-z0-9]*)", line, re.IGNORECASE)
        if m:
            target = "gfx" + m.group(1)
            if target not in targets:
                targets.append(target)
    return targets


def _query_amd_model_names_from_lspci() -> Dict[str, str]:
    """
    Return a mapping of PCI device ID -> human-readable GPU model name.

    Source: a single `lspci -nn` invocation (~10 ms).

    lspci lines look like:
        03:00.0 VGA compatible controller [0300]: Advanced Micro Devices,
        Inc. [AMD/ATI] Navi 22 [Radeon RX 6700/6700 XT/6750 XT / 6800M]
        [1002:73df] (rev c1)

    We extract:
      - The PCI device ID from the final [1002:73df] bracket.
      - The model name from the last human-readable bracket.

    Returns an empty dict if lspci is unavailable, in which case the
    caller uses the PCI device ID as the model name.
    """
    if not _have("lspci"):
        return {}

    out = _run(["lspci", "-nn"], timeout=5)
    if not out:
        return {}

    names: Dict[str, str] = {}
    for line in out.split("\n"):
        # Only interested in display-class devices.
        if not any(tag in line for tag in ("VGA", "Display", "3D")):
            continue
        # Only interested in AMD.
        if not any(
            tag in line
            for tag in ("AMD", "Radeon", "Advanced Micro", "ATI")
        ):
            continue

        # The PCI device ID is inside the last [xxxx:xxxx] bracket.
        pci_match = re.search(
            r"\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]", line
        )
        if not pci_match:
            continue
        device_id = "0x" + pci_match.group(2).lower()

        # The model name is the last bracket that contains letters and
        # does not look like a PCI ID.
        brackets = re.findall(r"\[([^\]]+)\]", line)
        model_name = None
        for candidate in reversed(brackets):
            # Skip the PCI ID bracket itself and the class-code bracket.
            if re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", candidate):
                continue
            if re.fullmatch(r"[0-9a-fA-F]{4}", candidate):
                continue
            model_name = candidate.strip()
            break

        if model_name:
            names[device_id] = model_name

    return names


def _detect_amd_gpus_via_rocm_smi() -> List[GPUInfo]:
    """
    Fallback AMD detection that parses rocm-smi's text output.

    Only used when sysfs enumeration fails (non-standard kernel, or a
    userspace-only ROCm backend without an amdgpu kernel driver). The
    parser keys on the GPU[N] prefix that rocm-smi prints on every
    line. Do NOT split on blank lines: rocm-smi does not emit blank
    lines between GPUs, so a blank-line split merges every GPU into one
    record. That was the root cause of the "six GPUs collapse into one"
    bug in earlier versions of this file.
    """
    binary = shutil.which("rocm-smi") or shutil.which("amd-smi")
    if not binary:
        return []

    out = _run(
        [binary, "--showproductname", "--showmeminfo", "vram"],
        timeout=10,
    )
    if not out:
        return []

    # card_index -> {model, vram_mb}
    cards: Dict[int, Dict[str, Any]] = {}
    for line in out.split("\n"):
        m = re.match(r"\s*GPU\[(\d+)\]\s*[:\-]?\s*(.+)$", line)
        if not m:
            continue
        idx = int(m.group(1))
        rest = m.group(2).strip()
        card = cards.setdefault(idx, {})

        if (
            "Card series" in rest
            or "Card model" in rest
            or "Card SKU" in rest
        ):
            if "model" not in card:
                value = rest.split(":", 1)[-1].strip()
                card["model"] = value or "AMD GPU"

        if "VRAM Total Memory" in rest or "VRAM Total" in rest:
            num = re.search(r"([\d.]+)", rest.split(":", 1)[-1])
            if num:
                raw = float(num.group(1))
                # Heuristic: values > 100_000 are bytes, smaller are MB.
                card["vram_mb"] = (
                    int(raw / (1024 * 1024)) if raw > 100_000 else int(raw)
                )

    if not cards:
        return []

    # One rocminfo call for all gfx targets.
    gfx_targets = _query_all_amd_gfx_targets()

    gpus: List[GPUInfo] = []
    for idx in sorted(cards.keys()):
        c = cards[idx]
        gfx = gfx_targets[idx] if idx < len(gfx_targets) else None
        gpu = GPUInfo(
            index=0,
            vendor="amd",
            model=c.get("model", "AMD GPU"),
            memory_mb=c.get("vram_mb", 0),
            vendor_device_index=idx,
            pin_env_name="HIP_VISIBLE_DEVICES",
            pin_env_value=str(idx),
            gfx_target=gfx,
            hsa_override_gfx_version=(
                HSA_OVERRIDE_MAP.get(gfx) if gfx else None
            ),
        )
        gpus.append(gpu)
    return gpus


def _detect_intel_gpus() -> List[GPUInfo]:
    """
    Detect Intel GPUs via xpu-smi (Arc / Data Center) or clinfo.

    Intel GPUs are supported in llama.cpp through the SYCL backend, which
    is built with -DGGML_SYCL=ON.
    """
    gpus: List[GPUInfo] = []

    if _have("xpu-smi"):
        out = _run(["xpu-smi", "discovery"], timeout=10)
        if out:
            device_idx = 0
            for line in out.split("\n"):
                if "device name" in line.lower() or "Device Name" in line:
                    name = line.split(":", 1)[-1].strip().strip('"')
                    gpus.append(GPUInfo(
                        index=0,
                        vendor="intel",
                        model=name,
                        vendor_device_index=device_idx,
                        pin_env_name="ONEAPI_DEVICE_SELECTOR",
                        pin_env_value=f"level_zero:{device_idx}",
                    ))
                    device_idx += 1
            if gpus:
                return gpus

    if _have("clinfo"):
        out = _run(["clinfo"], timeout=10)
        if out and "intel" in out.lower():
            # clinfo lists every OpenCL device. Take the Intel ones.
            idx = 0
            for block in out.split("Platform Name"):
                if "intel" in block.lower():
                    m = re.search(r"Device Name\s+(.+)", block)
                    name = m.group(1).strip() if m else "Intel GPU"
                    gpus.append(GPUInfo(
                        index=0,
                        vendor="intel",
                        model=name,
                        vendor_device_index=idx,
                        pin_env_name="ONEAPI_DEVICE_SELECTOR",
                        pin_env_value=f"level_zero:{idx}",
                    ))
                    idx += 1
    return gpus


def _detect_apple_gpus() -> List[GPUInfo]:
    """
    Detect Apple Silicon GPU. There is no separate VRAM on Apple Silicon;
    the GPU shares the unified memory pool. We report total system RAM as
    the GPU's budget, which is what llama.cpp's Metal backend uses.
    """
    if not (_is_darwin() and platform.machine().lower() in ("arm64", "aarch64")):
        return []
    chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon"
    mem_bytes = _run(["sysctl", "-n", "hw.memsize"])
    total_mb = int(int(mem_bytes) / (1024 * 1024)) if mem_bytes else 0
    return [GPUInfo(
        index=0,
        vendor="apple",
        model=chip,
        memory_mb=total_mb,
        is_integrated=True,
        pin_env_name=None,
        pin_env_value=None,
    )]


def _detect_gpus_from_sysfs(vendor_filter: Optional[str] = None) -> List[GPUInfo]:
    """
    Fallback GPU detection that reads PCI vendor IDs from sysfs.

    /sys/class/drm/card*/device/vendor exposes the PCI vendor as a hex
    string. This works on any Linux system regardless of which userspace
    tools are installed — it is the ultimate fallback.

    Vendor IDs:
       0x10de = NVIDIA
       0x1002 = AMD
       0x8086 = Intel
       0x1a03 = ASPEED (BMC)
    """
    if not _is_linux():
        return []
    gpus: List[GPUInfo] = []
    try:
        import glob
        cards = sorted(glob.glob("/sys/class/drm/card[0-9]*/device/vendor"))
        seen: set = set()
        for vendor_path in cards:
            card_dir = os.path.dirname(vendor_path)
            try:
                with open(vendor_path) as f:
                    vendor_id = f.read().strip().lower()
            except (IOError, OSError):
                continue
            if vendor_id == PCI_VENDOR_NVIDIA:
                vendor = "nvidia"
            elif vendor_id == PCI_VENDOR_AMD:
                vendor = "amd"
            elif vendor_id == PCI_VENDOR_INTEL:
                vendor = "intel"
            else:
                continue
            if vendor_filter and vendor != vendor_filter:
                continue

            # Read the device ID for diagnostics.
            device_id = None
            try:
                with open(os.path.join(card_dir, "device")) as f:
                    device_id = f.read().strip().lower()
            except (IOError, OSError):
                pass

            # Build a stable key so we don't double-count.
            key = (vendor, device_id, card_dir)
            if key in seen:
                continue
            seen.add(key)

            idx = sum(1 for g in gpus if g.vendor == vendor)
            if vendor == "nvidia":
                pin_name, pin_value = "CUDA_VISIBLE_DEVICES", str(idx)
            elif vendor == "amd":
                pin_name, pin_value = "HIP_VISIBLE_DEVICES", str(idx)
            else:
                pin_name, pin_value = "ONEAPI_DEVICE_SELECTOR", f"level_zero:{idx}"

            gpu = GPUInfo(
                index=0,
                vendor=vendor,
                model=f"{vendor.upper()} GPU (PCI {device_id or '?'})",
                vendor_device_index=idx,
                pin_env_name=pin_name,
                pin_env_value=pin_value,
                pci_id=device_id,
            )
            if vendor == "amd":
                gfx_list = _query_all_amd_gfx_targets()
                if idx < len(gfx_list):
                    gpu.gfx_target = gfx_list[idx]
                    gpu.hsa_override_gfx_version = HSA_OVERRIDE_MAP.get(gpu.gfx_target)
            gpus.append(gpu)
    except Exception as e:
        logger.debug("sysfs GPU scan failed: %s", e)
    return gpus


def _detect_windows_gpus() -> List[GPUInfo]:
    """
    Windows GPU detection via WMI.

    nvidia-smi is used first for NVIDIA cards (it reports accurate VRAM).
    For AMD and Intel on Windows we query Win32_VideoController. The WMI
    AdapterRAM field is a uint32 that saturates at ~4 GB, so we cross-check
    the display driver registry for the true VRAM value.
    """
    if not _is_windows():
        return []
    gpus: List[GPUInfo] = []

    # NVIDIA path
    gpus.extend(_detect_nvidia_gpus())
    # nvidia_count = len(gpus)

    # WMI path for everything else
    ps = (
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion,PNPDeviceID | "
        "ConvertTo-Json -Compress"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=15)
    if not out:
        return gpus

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return gpus
    if isinstance(data, dict):
        data = [data]

    for entry in data:
        name = (entry.get("Name") or "").strip()
        if not name:
            continue
        lower = name.lower()
        if "nvidia" in lower:
            continue  # already handled by nvidia-smi
        if "amd" in lower or "radeon" in lower:
            vendor = "amd"
        elif "intel" in lower:
            vendor = "intel"
        else:
            vendor = "unknown"

        # WMI AdapterRAM is unreliable; try the registry instead.
        memory_mb = 0
        vram = _read_windows_vram_from_registry()
        if vram:
            memory_mb = vram
        else:
            try:
                memory_mb = int(int(entry.get("AdapterRAM") or 0) / (1024 * 1024))
            except (TypeError, ValueError):
                memory_mb = 0

        idx = sum(1 for g in gpus if g.vendor == vendor)
        gpu = GPUInfo(
            index=0,
            vendor=vendor,
            model=name,
            memory_mb=memory_mb,
            driver_version=entry.get("DriverVersion"),
            vendor_device_index=idx,
            pin_env_name=("HIP_VISIBLE_DEVICES" if vendor == "amd"
                          else "ONEAPI_DEVICE_SELECTOR" if vendor == "intel"
                          else None),
            pin_env_value=(str(idx) if vendor == "amd"
                           else f"level_zero:{idx}" if vendor == "intel"
                           else None),
        )
        gpus.append(gpu)

    return gpus


def _read_windows_vram_from_registry() -> int:
    """
    Read the true VRAM size from the display driver registry on Windows.

    The value we want is `HardwareInformation.qwMemorySize` (QWORD) under
    each subkey of the display class key. If it is missing, we fall back
    to `HardwareInformation.MemorySize` (DWORD, capped at 4 GB).
    Returns the value in MB, or 0 on failure.
    """
    if not _is_windows():
        return 0
    ps = (
        f"Get-ChildItem -Path 'Registry::HKEY_LOCAL_MACHINE\\"
        f"{WIN_GPU_REG_PATH}' | "
        "ForEach-Object { "
        "  $p = $_.PSPath; "
        "  try { "
        "    $v = (Get-ItemProperty -Path $p -Name 'HardwareInformation.qwMemorySize' -EA Stop)."
        "'HardwareInformation.qwMemorySize'; "
        "    if ($v) { Write-Output $v } "
        "  } catch {} "
        "} | Select-Object -First 1"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=10)
    if not out:
        return 0
    try:
        return int(int(out.strip()) / (1024 * 1024))
    except ValueError:
        return 0


# =============================================================================
# Combined GPU detection
# =============================================================================

def detect_gpus() -> List[GPUInfo]:
    """
    Detect every GPU on this host, from every vendor, in a deterministic
    order: NVIDIA, AMD, Intel, Apple.

    Each GPU receives a per-vendor device index and a pin_env_name/value
    pair that lets a child rpc-server process target that exact device.
    This is the foundation of the multi-GPU RPC layout.
    """
    gpus: List[GPUInfo] = []

    if _is_windows():
        gpus = _detect_windows_gpus()
    else:
        gpus.extend(_detect_nvidia_gpus())
        gpus.extend(_detect_amd_gpus())
        gpus.extend(_detect_intel_gpus())
        gpus.extend(_detect_apple_gpus())

    # If nothing was found through vendor tooling, fall back to sysfs
    # (Linux only). This catches GPUs the vendor tools are missing.
    if not gpus and _is_linux():
        gpus = _detect_gpus_from_sysfs()

    # Assign the final 0-based indices and the RPC port for each GPU.
    for i, gpu in enumerate(gpus):
        gpu.index = i
        gpu.rpc_port = RPC_SERVER_PORT_BASE + i

    if not gpus:
        logger.warning("no GPUs detected; the spoke will register as a CPU-only node")

    return gpus


def _build_rpc_backends(gpus: List[GPUInfo], lan_ip: str) -> List[str]:
    """Build the host:port list that the hub's RPC master will connect to."""
    return [f"{lan_ip}:{g.rpc_port}" for g in gpus]


# =============================================================================
# mDNS hub discovery
# =============================================================================

def discover_hub_via_mdns(timeout: int = 5) -> Optional[str]:
    """
    Discover a NETTRADES hub on the local network via mDNS / DNS-SD.

    Preferred strategy is `avahi-browse` (present on Ubuntu/Debian). A
    Python `zeroconf` fallback is used if avahi is absent. Returns the
    hub's base URL as "http://<ip>" or None.
    """
    # ---- Strategy 1: avahi-browse ----
    if _have("avahi-browse"):
        try:
            result = subprocess.run(
                ["avahi-browse", "-t", "-r", "-p", "_nettrades._tcp"],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.split("\n"):
                    if not line.startswith("="):
                        continue
                    parts = line.split(";")
                    if len(parts) < 8 or parts[2] != "IPv4":
                        continue
                    address = parts[7].strip()
                    if address and not address.startswith("127."):
                        logger.info("discovered hub via avahi-browse: %s", address)
                        return f"http://{address}"
        except Exception as e:
            logger.debug("avahi-browse failed: %s", e)

    # ---- Strategy 2: zeroconf ----
    try:
        import socket as _socket
        from zeroconf import Zeroconf, ServiceBrowser

        discovered: List[str] = []

        class _Listener:
            def add_service(self, zc, type_, name):
                info = zc.get_service_info(type_, name)
                if info and info.addresses:
                    try:
                        addr = _socket.inet_ntoa(info.addresses[0])
                        if not addr.startswith("127."):
                            discovered.append(addr)
                    except Exception:
                        pass

            def remove_service(self, *a): pass
            def update_service(self, *a): pass

        zc = Zeroconf()
        try:
            ServiceBrowser(zc, "_nettrades._tcp.local.", _Listener())
            end = time.time() + timeout
            while time.time() < end and not discovered:
                time.sleep(0.2)
        finally:
            zc.close()
        if discovered:
            logger.info("discovered hub via zeroconf: %s", discovered[0])
            return f"http://{discovered[0]}"
    except ImportError:
        logger.debug("zeroconf not installed; mDNS via avahi only")
    except Exception as e:
        logger.debug("zeroconf failed: %s", e)

    return None


# =============================================================================
# WireGuard (unchanged from prior version; used only when use_wireguard=true)
# =============================================================================

def write_wg_config(config: Dict[str, Any], private_key: str) -> None:
    os.makedirs(os.path.dirname(WG_CONFIG_PATH), exist_ok=True)
    text = (
        f"[Interface]\n"
        f"PrivateKey = {private_key}\n"
        f"Address = {config['address']}\n"
        f"DNS = {config.get('dns_servers', '8.8.8.8, 1.1.1.1')}\n"
        f"\n"
        f"[Peer]\n"
        f"PublicKey = {config['server_public_key']}\n"
        f"Endpoint = {config['server_endpoint']}:{config['server_port']}\n"
        f"AllowedIPs = {config['allowed_ips']}\n"
        f"PersistentKeepalive = {config.get('persistent_keepalive', 25)}\n"
    )
    with open(WG_CONFIG_PATH, "w") as f:
        f.write(text)
    os.chmod(WG_CONFIG_PATH, 0o600)


def wg_up() -> bool:
    try:
        subprocess.run(["wg-quick", "up", WG_INTERFACE], check=True,
                       capture_output=True, text=True, timeout=30)
        return True
    except subprocess.CalledProcessError as e:
        return "already exists" in (e.stderr or "") or "already up" in (e.stderr or "")
    except FileNotFoundError:
        return False


def wg_down() -> None:
    try:
        subprocess.run(["wg-quick", "down", WG_INTERFACE],
                       capture_output=True, text=True, timeout=30)
    except Exception:
        pass


def wg_is_up() -> bool:
    try:
        r = subprocess.run(["wg", "show", WG_INTERFACE],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


# =============================================================================
# Multi-GPU RPC supervisor
# =============================================================================
# One RPC process per GPU. Each gets its own environment (the pin_env_name
# = pin_env_value pair) so it is bound to one device. Each has its own
# port, its own stdout capture, and its own watchdog thread. If any exits
# it is restarted independently — a failure on one GPU must not take down
# the others, because the hub's RPC master will reduce the topology and
# continue with the survivors.
# =============================================================================

class RpcWorker:
    """One rpc-server process bound to one GPU (or to the CPU)."""

    def __init__(self, gpu: Optional[GPUInfo], port: int, host: str = RPC_HOST):
        self.gpu = gpu
        self.port = port
        self.host = host
        self.proc: Optional[subprocess.Popen] = None
        self._stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None

    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if self.gpu and self.gpu.pin_env_name and self.gpu.pin_env_value:
            env[self.gpu.pin_env_name] = self.gpu.pin_env_value
        # The HSA override must be exported into every rpc-server process
        # that uses an AMD GPU requiring it. Without it, ROCm ignores the
        # card and the server runs on CPU.
        if self.gpu and self.gpu.hsa_override_gfx_version:
            env["HSA_OVERRIDE_GFX_VERSION"] = self.gpu.hsa_override_gfx_version
        # Enable the local tensor cache for faster reconnects.
        env.setdefault("LLAMA_CACHE", RPC_CACHE_DIR)
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

    def _build_args(self) -> List[str]:
        # rpc-server accepts -H (host), -p (port), and optionally -c <cache-dir>.
        # Do NOT pass --mem: it takes a proportion (0.0-1.0) in some llama.cpp
        # builds and is absent in others. Passing megabytes causes rpc-server
        # to exit with "unknown option" and the watchdog to restart-loop it.
        # The master determines layer split from the VRAM reported in the
        # heartbeat, not from a per-worker flag.
        return [RPC_SERVER_BIN, "-H", self.host, "-p", str(self.port)]

    def start(self) -> bool:
        if not _have(RPC_SERVER_BIN):
            logger.error("rpc-server binary '%s' not on PATH", RPC_SERVER_BIN)
            return False

        # Ensure cache dir exists.
        try:
            os.makedirs(RPC_CACHE_DIR, exist_ok=True)
        except OSError:
            pass

        try:
            self.proc = subprocess.Popen(
                self._build_args(),
                env=self._build_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            logger.error("failed to exec %s", RPC_SERVER_BIN)
            return False

        gpu_label = (self.gpu.model if self.gpu else "CPU")
        logger.info("rpc-server up: pid=%d port=%d device=%s%s",
                    self.proc.pid, self.port, gpu_label,
                    f" (HSA={self.gpu.hsa_override_gfx_version})"
                    if self.gpu and self.gpu.hsa_override_gfx_version else "")

        self._watchdog = threading.Thread(target=self._watch, daemon=True)
        self._watchdog.start()
        return True

    def _watch(self) -> None:
        # Drain the child's stdout in a separate thread.
        #
        # llama.cpp's rpc-server emits enough startup output (GPU
        # enumeration, ROCm init, backend selection) to fill the 64KB
        # pipe buffer. The previous version of this method never read
        # from proc.stdout, so once the pipe filled, the rpc-server
        # blocked on the first write inside the accept loop and never
        # returned to accept(). Connections piled up in the 1-deep
        # accept queue and timed out at the client.
        #
        # Diagnosed 2026-10-28 on the AMD rig: ss -ltnp showed
        # Recv-Q=2 Send-Q=1 on all six ports while
        # ss -tn | grep ESTABLISHED returned nothing, and
        # /proc/<pid>/wchan showed the rpc-server in pipe_write.
        def _drain():
            try:
                for line in self.proc.stdout:
                    logger.debug("rpc-server[%d] %s", self.port, line.rstrip())
            except Exception:
                pass

        threading.Thread(target=_drain, daemon=True).start()

        while not self._stop.is_set():
            if self.proc is None:
                return
            rc = self.proc.poll()
            if rc is not None:
                logger.warning("rpc-server on port %d exited rc=%s — restarting", self.port, rc)
                time.sleep(3)
                self.start()
                return
            time.sleep(2)

    def stop(self) -> None:
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class MultiGpuRpcSupervisor:
    """
    Manages the full set of per-GPU rpc-server instances.

    The list of (gpu, port) pairs comes from the detect_gpus() output. If
    no GPUs are found, the supervisor starts exactly one CPU-only
    rpc-server on the base port so the hub can still route to this spoke.
    """

    def __init__(self, gpus: List[GPUInfo], base_port: int = RPC_SERVER_PORT_BASE):
        self.workers: List[RpcWorker] = []
        if gpus:
            for gpu in gpus:
                self.workers.append(RpcWorker(gpu, base_port + gpu.index))
        else:
            self.workers.append(RpcWorker(None, base_port))

    def start_all(self) -> bool:
        any_started = False
        for w in self.workers:
            if w.start():
                any_started = True
        return any_started

    def stop_all(self) -> None:
        """
        Stop all rpc-server processes concurrently.

        Concurrent stop matters for the graceful drain (2026-10-22):
        each RpcWorker.stop() does terminate() + wait(timeout=10). If a
        worker hangs and we stop them serially, six hung workers take
        60 seconds, eating the entire TimeoutStopSec budget and
        preventing the drain from completing before systemd SIGKILLs.

        By running them in parallel, the worst-case drain-to-stopped
        time is bounded by a single worker's timeout (10s), not
        6 × 10s, regardless of GPU count. This makes the drain time
        predictable at every fleet size.
        """
        import threading
        threads: List[threading.Thread] = []
        for w in self.workers:
            t = threading.Thread(
                target=w.stop,
                name=f"rpc-stop-{w.port}",
                daemon=True,
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)  # join is sequential; worker execution is parallel

    def endpoints(self, lan_ip: str) -> List[str]:
        return [f"{lan_ip}:{w.port}" for w in self.workers]

    def status(self) -> Dict[str, Any]:
        return {
            "workers": [
                {
                    "port": w.port,
                    "device": w.gpu.model if w.gpu else "CPU",
                    "vendor": w.gpu.vendor if w.gpu else "cpu",
                    "hsa_override": w.gpu.hsa_override_gfx_version if w.gpu else None,
                    "alive": w.is_alive(),
                }
                for w in self.workers
            ]
        }


# =============================================================================
# Utility
# =============================================================================

def model_is_cached() -> bool:
    """Return True if the model file exists locally (this makes us a warm spare)."""
    try:
        return bool(DEFAULT_MODEL_PATH) and os.path.isfile(DEFAULT_MODEL_PATH) \
               and os.path.getsize(DEFAULT_MODEL_PATH) > 0
    except OSError:
        return False


def get_lan_ip() -> str:
    """Return the machine's primary LAN IP (does not send packets)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"

def _manifest_gpus_to_gpuinfo(manifest_gpus):
    """Convert manifest JSON gpus list to GPUInfo dataclasses.

    Manifest format is defined by scripts/lib/capability.py::GPUCapability.
    This preserves the existing self.gpus type so downstream code
    (RpcWorker, heartbeat, etc.) needs no changes.

    Field mapping:
      - hsa_override (capability)  -> hsa_override_gfx_version (GPUInfo)
      - pin_env_value (str of int) -> vendor_device_index, when the
        latter is absent from the manifest. This is how the per-GPU
        pin survives the manifest round-trip.

    Index handling:
      - We re-stamp index to enumerate order so rpc_port assignment
        (base + index) is deterministic regardless of the manifest's
        own ordering. vendor_device_index is preserved from the
        manifest so each worker still pins to the physical GPU the
        vendor tool reported.
    """
    from dataclasses import fields as _fields
    known = {f.name for f in _fields(GPUInfo)}
    field_map = {"hsa_override": "hsa_override_gfx_version"}

    out = []
    for i, g in enumerate(manifest_gpus):
        kwargs = {"index": i}
        for k, v in g.items():
            if k == "index":
                continue  # re-stamped above
            if k in field_map:
                kwargs[field_map[k]] = v
            elif k in known:
                kwargs[k] = v

        # Derive vendor_device_index from pin_env_value when the manifest
        # does not carry it directly.
        if "vendor_device_index" not in kwargs and "pin_env_value" in kwargs:
            try:
                kwargs["vendor_device_index"] = int(kwargs["pin_env_value"])
            except (TypeError, ValueError):
                kwargs["vendor_device_index"] = i

        out.append(GPUInfo(**kwargs))
    return out


# =============================================================================
# Spoke agent
# =============================================================================

class SpokeAgent:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sub_hub_url = config["sub_hub_url"].rstrip("/")
        self.langgraph_url = (config.get("langgraph_url") or
                              os.environ.get("LANGGRAPH_URL", "")).rstrip("/")
        self.node_name = config.get("node_name") or platform.node()
        self.registration_token = (config.get("registration_token")
                                   or os.environ.get("NETTRADES_REGISTRATION_TOKEN", ""))
        self.heartbeat_interval = int(config.get("heartbeat_interval", 10))
        self.inference_capability = config.get("inference_capability", "rpc_worker")
        self.use_wireguard = bool(config.get("use_wireguard", False))

        # --- graceful drain configuration (2026-10-20) ---
        # shutdown_grace_seconds is how long the agent waits, after sending
        # the drain heartbeat, before stopping its RPC workers. It must be
        # strictly less than the systemd unit's TimeoutStopSec (or the
        # Windows preshutdown timeout) so the drain completes before the OS
        # kills the process.
        self.shutdown_grace_seconds = int(
            config.get("shutdown_grace_seconds", 30)
        )
        self.drain_requested_file = (
            config.get("drain_requested_file") or _DEFAULT_DRAIN_REQUESTED
        )
        self.drain_complete_file = (
            config.get("drain_complete_file") or _DEFAULT_DRAIN_COMPLETE
        )

        # Drain state. `_draining` is checked by `heartbeat()` so that every
        # heartbeat sent after a drain trigger carries `draining=true`.
        # `_drain_thread` is the worker that performs the drain; the main
        # loop awaits it in `run()`'s finally block.
        self._draining = False
        self._exit_event = threading.Event()
        self._drain_thread: Optional[threading.Thread] = None

        # --- hardware: read manifest if present, else detect at runtime ---
        # Fallback: runtime detection for scenarios where the manifest is
        # missing (dev machines, re-runs, etc.).
        manifest_path = "/etc/nettrades/spoke/manifest.json"
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                self.cpu = detect_cpu()  # CPU info is cheap, always fresh
                self.gpus = _manifest_gpus_to_gpuinfo(manifest["gpus"])
                logger.info("Loaded %d GPU(s) from manifest", len(self.gpus))
            except Exception as e:
                logger.warning("Manifest read failed (%s); falling back to runtime detection", e)
                self.cpu = detect_cpu()
                self.gpus = detect_gpus()
        else:
            self.cpu = detect_cpu()
            self.gpus = detect_gpus()

        self.lan_ip = get_lan_ip()

        # Cap RPC workers to avoid OOM-kill on memory-constrained hosts.
        # Each rpc-server needs ~1 GB system RAM for HIP/CUDA init plus
        # shared libraries. On a 6-GPU box with <8 GB free, starting all
        # six triggers the kernel OOM killer (rc=-9 in the crash loop).
        # Default 0 = no cap. Set RPC_MAX_WORKERS=N in the systemd unit
        # (install-spoke.sh writes Environment=RPC_MAX_WORKERS=N).
        _max_workers = int(os.environ.get("RPC_MAX_WORKERS", "0"))
        if _max_workers > 0 and len(self.gpus) > _max_workers:
            logger.warning(
                "Capping RPC workers: %d of %d GPUs (RPC_MAX_WORKERS=%d)",
                _max_workers, len(self.gpus), _max_workers,
            )
            self.gpus = self.gpus[:_max_workers]

        # The config file's `rpc_port` is the base port for the first
        # GPU. GPUs get base + index. This makes the port layout
        # configurable from install-spoke.sh without needing an
        # environment variable in the systemd unit.
        self.rpc_port_base = int(
            config.get("rpc_port", RPC_SERVER_PORT_BASE)
        )

        # Re-stamp each GPU's rpc_port from the configured base.
        #
        # detect_gpus() assigns ports from the module-level
        # RPC_SERVER_PORT_BASE constant (an env var defaulting to
        # 50052). If the operator overrides `rpc_port` in the config
        # file, the RpcWorker constructor uses `self.rpc_port_base +
        # gpu.index`, but `_build_rpc_backends` still advertises the
        # constant-derived ports. That mismatch makes the hub probe
        # ports nobody is listening on, and the cluster permanently
        # looks unreachable at every pre_generation_check.
        #
        # Re-stamping the ports here ensures that the worker start
        # ports, the heartbeat payload, and the registered backends
        # all agree.
        for _idx, _gpu in enumerate(self.gpus):
            _gpu.rpc_port = self.rpc_port_base + _idx
        self.rpc_backends = _build_rpc_backends(self.gpus, self.lan_ip)

        # --- RPC supervisor ---
        self.rpc = MultiGpuRpcSupervisor(self.gpus, base_port=self.rpc_port_base)

        # --- state ---
        self.node_id: Optional[int] = None
        self.wg_public_key: Optional[str] = None
        self.wg_private_key: Optional[str] = None
        self.registered = False
        self.running = True

        # --- logging ---
        logger.info("Spoke agent initialised")
        logger.info("  node:            %s", self.node_name)
        logger.info("  platform:        %s%s", sys.platform, " (WSL2)" if _is_wsl() else "")
        logger.info("  cpu:             %s (%d cores)", self.cpu.model, self.cpu.logical_cores)
        logger.info("  gpus:            %d", len(self.gpus))
        for g in self.gpus:
            logger.info("    [%d] %s %s (%d MB)%s", g.index, g.vendor, g.model,
                        g.memory_mb,
                        f"  HSA_OVERRIDE={g.hsa_override_gfx_version}"
                        if g.hsa_override_gfx_version else "")
        logger.info("  rpc_backends:    %s", ",".join(self.rpc_backends) or "(none)")
        logger.info("  rpc_port_base:   %d", self.rpc_port_base)
        logger.info("  sub_hub:         %s", self.sub_hub_url)
        logger.info("  langgraph:       %s", self.langgraph_url or "(not configured)")
        logger.info("  drain grace:     %ds", self.shutdown_grace_seconds)
        logger.info("  drain signal:    %s", self.drain_requested_file)

    # -------------------------------------------------------------------------
    # Config persistence (survives hub IP change)
    # -------------------------------------------------------------------------

    def _save_config(self) -> None:
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
        except Exception as e:
            logger.warning("could not persist config to %s: %s", CONFIG_FILE, e)

    def _rediscover_hub(self) -> bool:
        new_base = discover_hub_via_mdns(timeout=5)
        if not new_base or new_base == self.sub_hub_url:
            return False
        logger.warning("hub URL changed: %s -> %s", self.sub_hub_url, new_base)
        self.sub_hub_url = new_base
        self.config["sub_hub_url"] = new_base
        old_lg = self.config.get("langgraph_url", "")
        if old_lg:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(old_lg)
                if parsed.hostname and parsed.hostname in old_lg:
                    new_lg = old_lg.replace(parsed.hostname, new_base.split("//", 1)[1])
                    self.config["langgraph_url"] = new_lg
                    self.langgraph_url = new_lg
            except Exception:
                pass
        self._save_config()
        return True

    # -------------------------------------------------------------------------
    # WireGuard keygen
    # -------------------------------------------------------------------------

    def _gen_wg_keypair(self) -> Optional[str]:
        try:
            priv = subprocess.run(["wg", "genkey"], capture_output=True, text=True,
                                  check=True, timeout=5).stdout.strip()
            pub = subprocess.run(["wg", "pubkey"], input=priv, capture_output=True,
                                 text=True, check=True, timeout=5).stdout.strip()
            self.wg_public_key = pub
            return priv
        except Exception as e:
            logger.error("WireGuard keygen failed: %s", e)
            return None

    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------

    def register(self) -> bool:
        if not self.registration_token:
            logger.error("no registration token configured")
            return False

        # Build the GPU inventory in the format the hub expects. The hub
        # uses this to compute the layer assignment — each entry must
        # carry the port the corresponding rpc-server will listen on.
        gpus_payload = []
        for g in self.gpus:
            gpus_payload.append({
                "index": g.index,
                "vendor": g.vendor,
                "model": g.model,
                "memory_mb": g.memory_mb,
                "compute_capability": g.compute_capability,
                "device_index": g.vendor_device_index,
                "rpc_port": g.rpc_port,
                "gfx_target": g.gfx_target,
                "hsa_override_gfx_version": g.hsa_override_gfx_version,
            })

        compute_profile = {
            "ram_gb": self.cpu.system_memory_gb,
            "cpu_model": self.cpu.model,
            "cpu_cores": self.cpu.logical_cores,
            "cpu_architecture": self.cpu.architecture,
            "has_avx512": self.cpu.has_avx512,
            "has_amx": self.cpu.has_amx,
            "has_neon": self.cpu.has_neon,
            "vendor": self.gpus[0].vendor if self.gpus else "cpu",
            "model": self.gpus[0].model if self.gpus else self.cpu.model,
            "model_cached": model_is_cached(),
            "lan_ip": self.lan_ip,
            "rpc_backends": self.rpc_backends,
        }

        payload: Dict[str, Any] = {
            "name": self.node_name,
            "inference_capability": self.inference_capability,
            "gpus": gpus_payload,
            "compute_profile": compute_profile,
            "use_wireguard": self.use_wireguard,
        }
        if self.use_wireguard:
            priv = self._gen_wg_keypair()
            if not priv:
                return False
            self.wg_private_key = priv
            payload["public_key"] = self.wg_public_key
        else:
            payload["subnet_ip"] = self.lan_ip

        # - /api/v1/gpu/heartbeat (Odoo) → registration token
        # - /nodes/heartbeat (LangGraph) → heartbeat secret, falls back to
        #   LANGGRAPH_API_KEY if not configured (matches app.py's fallback)
        # Registration only talks to Odoo — use the registration token.
        # The LangGraph heartbeat secret is only needed for /nodes/heartbeat
        # (see heartbeat() below). Building it here as _headers_lg was
        # leftover from the incomplete P1 fix and caused a NameError on
        # `headers` (undefined).
        _headers_odoo = {"Authorization": f"Bearer {self.registration_token}"}

        try:
            r = requests.post(
                f"{self.sub_hub_url}/api/v1/gpu/register",
                json=payload, headers=_headers_odoo, timeout=15,
            )
        except Exception as e:
            logger.error("registration HTTP error: %s", e)
            return False
        if r.status_code != 200:
            logger.error("registration failed: HTTP %s — %s", r.status_code, r.text[:200])
            return False
        try:
            body = r.json()
        except Exception:
            logger.error("registration returned non-JSON: %s", r.text[:200])
            return False

        # Odoo's type='jsonrpc' routes wrap the controller's return value
        # in a {"jsonrpc": ..., "result": {...}} envelope. Unwrap it.
        result = body.get("result", body) if isinstance(body, dict) else body

        if not isinstance(result, dict) or result.get("status") != "success":
            logger.error(
                "registration rejected: %s (full response: %s)",
                result.get("error") if isinstance(result, dict) else None,
                body,
            )
            return False

        self.node_id = result["node"]["id"]

        # NEW: Write the node_id to disk so `--drain-only` can find it
        try:
            node_id_file = os.path.join(os.path.dirname(self.drain_requested_file), "node-id")
            dir_name = os.path.dirname(node_id_file)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(node_id_file, "w") as f:
                f.write(str(self.node_id))
        except Exception as e:
            logger.warning("could not write node-id file: %s", e)
        
        logger.info("registered with hub: node_id=%s ip=%s backends=%s",
                    self.node_id, result["node"].get("ip"),
                    len(self.rpc_backends))

        # Option B (2026-11-16): persist the heartbeat secret that the
        # hub included in the registration response. The spoke uses this
        # only for /nodes/heartbeat on langgraph-server (see heartbeat()).
        #
        # Why persist to config.yaml rather than hold in memory only:
        #   - The heartbeat loop sends every 10 s. If the process restarts
        #     (systemctl restart, crash, OOM), the next start would need
        #     re-registration before the first heartbeat. Persisting means
        #     heartbeats resume immediately on restart, even before
        #     re-registration finishes.
        #   - The config file is the same file install-spoke.sh wrote, so
        #     the operator already knows where to inspect it.
        #
        # Never log the value. The log line below records only that it
        # was received and where it was written.
        _hb_secret = result["node"].get("heartbeat_secret")
        if _hb_secret:
            already_have = self.config.get("heartbeat_secret") == _hb_secret
            self.config["heartbeat_secret"] = _hb_secret
            if not already_have:
                self._save_config()
                logger.info(
                    "heartbeat_secret received from hub and persisted to %s",
                    CONFIG_FILE,
                )
            else:
                logger.debug("heartbeat_secret unchanged from hub")
        else:
            # Hub did not include a secret. Two possible causes:
            #   1. Hub's LANGGRAPH_HEARTBEAT_SECRET is not set (warning
            #      logged on the hub side).
            #   2. Spoke is talking to an older hub that predates this fix.
            # Either way the spoke falls back to its own env var (if set)
            # or to sending an empty token. Both produce a visible 401 on
            # /nodes/heartbeat; nothing silently pretends to work.
            logger.warning(
                "hub did not return a heartbeat_secret — /nodes/heartbeat "
                "may fail with 401. Check LANGGRAPH_HEARTBEAT_SECRET on the "
                "hub, or set it locally on this spoke."
            )

        if self.use_wireguard:
            wg = result["node"].get("wireguard")
            if not wg:
                logger.error("hub did not return a WireGuard config")
                return False
            write_wg_config(wg, self.wg_private_key)
            if not wg_up():
                return False

        self.registered = True
        return True

    # -------------------------------------------------------------------------
    # Heartbeat
    # -------------------------------------------------------------------------

    def _gpu_utilisation_for(self, gpu: GPUInfo) -> Dict[str, float]:
        """
        Read per-GPU utilisation via nvidia-smi or rocm-smi. Used for
        metrics; if the vendor tool is absent we return zeros.
        """
        stats = {"util": 0.0, "mem_util": 0.0, "temp": 0.0}
        if gpu.vendor == "nvidia" and _have("nvidia-smi"):
            out = _run([
                "nvidia-smi", "-i", str(gpu.vendor_device_index),
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ], timeout=5)
            if out:
                p = [x.strip() for x in out.split(",")]
                try:
                    stats["util"] = float(p[0])
                    used, total = float(p[1]), float(p[2])
                    stats["mem_util"] = (used / total * 100) if total else 0.0
                    stats["temp"] = float(p[3])
                except (ValueError, IndexError):
                    pass
        elif gpu.vendor == "amd" and _have("rocm-smi"):
            out = _run(["rocm-smi", "-d", str(gpu.vendor_device_index),
                        "--showuse", "--showtemp"], timeout=5)
            if out:
                m = re.search(r"GPU use \(%\): (\d+)", out)
                if m:
                    stats["util"] = float(m.group(1))
                m = re.search(r"Temperature \(Sensor edge\) \(C\): ([\d.]+)", out)
                if m:
                    stats["temp"] = float(m.group(1))
        return stats

    def heartbeat(self, draining: bool = False) -> bool:
        """
        Send a heartbeat to both Odoo and LangGraph.

        `draining` (2026-10-20):
            When True, the heartbeat marks the node as unavailable. The
            supervisor's _get_available_hardware() filters on
            is_healthy=true for rpc_workers, and the health monitor sets
            is_healthy=false when it receives draining=true. So a draining
            node stops receiving new requests within one heartbeat interval.

            The `_draining` instance flag is OR'd in here, so once a drain
            has been triggered every subsequent heartbeat (including the
            ones sent by the background heartbeat loop) carries
            draining=true. Without this, the heartbeat loop would keep
            advertising the node as available during the drain window.
        """
        if not self.registered or self.node_id is None:
            return False

        effective_draining = draining or self._draining

        # Per-GPU stats
        gpu_stats = [self._gpu_utilisation_for(g) for g in self.gpus]
        # Average across GPUs (or zero if no GPUs).
        avg_util = (sum(s["util"] for s in gpu_stats) / len(gpu_stats)
                    if gpu_stats else 0.0)
        avg_mem = (sum(s["mem_util"] for s in gpu_stats) / len(gpu_stats)
                   if gpu_stats else 0.0)

        payload = {
            "node_id": self.node_id,
            "timestamp": datetime.utcnow().isoformat(),
            "vram_total_mb": sum(g.memory_mb for g in self.gpus),
            "gpu_count": len(self.gpus),
            "model_cached": model_is_cached(),
            "gpu_utilization": avg_util,
            "memory_utilization": avg_mem,
            # NEW (2026-10-20): draining flips is_available to False so the
            # hub stops routing new requests to this node. The supervisor
            # already filters on is_healthy; draining flips that to False.
            "is_available": not effective_draining,
            "draining": effective_draining,
            # The health monitor's TCP probe needs a flat list of
            # host:port strings, one per rpc-server. This is the same list
            # the spoke registers with.
            "rpc_backends": self.rpc_backends,
            # Keep the structured per-worker status for diagnostics.
            "rpc_workers": self.rpc.status(),
        }
        # Two endpoints, two different secrets (P1 fix, 2026-11-16):
        #   - /api/v1/gpu/heartbeat (Odoo)        → registration token
        #   - /nodes/heartbeat      (LangGraph)   → heartbeat secret
        #
        # The heartbeat secret comes from (in order):
        #   1. config.yaml `heartbeat_secret:` — written by install-spoke.sh
        #      when the installer was invoked with --heartbeat-secret
        #   2. LANGGRAPH_HEARTBEAT_SECRET env var on the spoke (if set)
        #   3. Empty string — this falls back to the old "any bearer"
        #      behaviour ONLY if the hub's app.py still accepts it, which
        #      it does not (app.py fails closed with 503 if the secret is
        #      not configured, 401 if the token is wrong). So an empty
        #      secret here means the LangGraph heartbeat will 401 and the
        #      node will not become healthy. That is the desired behaviour
        #      — better to fail visibly than to silently appear healthy.
        _heartbeat_secret = (
            self.config.get("heartbeat_secret")
            or os.getenv("LANGGRAPH_HEARTBEAT_SECRET", "")
        )
        _headers_odoo = {"Authorization": f"Bearer {self.registration_token}"}
        _headers_lg   = {"Authorization": f"Bearer {_heartbeat_secret}"}

        if not _heartbeat_secret:
            logger.warning(
                "heartbeat_secret not configured — LangGraph heartbeats "
                "will be rejected by /nodes/heartbeat. Set heartbeat_secret "
                "in /etc/nettrades/spoke/config.yaml (re-run install-spoke.sh "
                "with --heartbeat-secret=<value>) or export "
                "LANGGRAPH_HEARTBEAT_SECRET on the spoke."
            )

        ok = False

        # Odoo (durable record) — registration token
        try:
            r = requests.post(f"{self.sub_hub_url}/api/v1/gpu/heartbeat",
                              json=payload, headers=_headers_odoo, timeout=10)
            ok = ok or (r.status_code == 200)
        except Exception as e:
            logger.debug("Odoo heartbeat failed: %s", e)

        # LangGraph (real-time signal) — heartbeat secret
        if self.langgraph_url:
            try:
                r = requests.post(f"{self.langgraph_url}/nodes/heartbeat",
                                  json=payload, headers=_headers_lg, timeout=10)
                if r.status_code not in (200,):
                    logger.warning(
                        "LangGraph heartbeat rejected: HTTP %s — %s",
                        r.status_code, r.text[:120],
                    )
                ok = ok or (r.status_code == 200)
            except Exception as e:
                logger.debug("LangGraph heartbeat failed: %s", e)
        return ok

    # -------------------------------------------------------------------------
    # Graceful drain (2026-10-20)
    # -------------------------------------------------------------------------

    def _notify_drain(self) -> bool:
        """
        Send one drain heartbeat to the hub. Returns True if at least one
        endpoint (Odoo or LangGraph) accepted it.

        This is called at the start of the drain sequence, before we stop
        the RPC workers. It gives the hub a head start on re-routing.
        """
        return self.heartbeat(draining=True)

    def _trigger_drain(self, reason: str) -> None:
        """
        Kick off the drain sequence. Idempotent: a second call while a
        drain is in progress is a no-op. The drain itself runs on a
        dedicated thread so the caller (a signal handler or the file
        watcher) returns immediately.

        Called by:
          - `_on_shutdown_signal` on SIGTERM / SIGINT
          - `_watch_drain_file` when the drain trigger file appears
        """
        if self._draining:
            logger.info("drain already in progress, ignoring trigger (%s)", reason)
            return
        logger.info("drain triggered: %s", reason)
        self._draining = True
        self._drain_thread = threading.Thread(
            target=self._drain_and_exit,
            name="drain",
            daemon=False,
        )
        self._drain_thread.start()

    def _drain_and_exit(self) -> None:
        """
        Graceful drain sequence. Runs on `self._drain_thread`.

        See the GRACEFUL DRAIN block in the file header for the design.
        """
        grace = self.shutdown_grace_seconds

        # --- 1. Tell the hub we are going away. -----------------------------
        # One heartbeat with draining=true. The supervisor's
        # _get_available_hardware() will no longer return this node once
        # the health monitor processes the heartbeat. New requests will
        # be routed to another track.
        try:
            if self._notify_drain():
                logger.info("drain heartbeat sent to hub")
            else:
                logger.warning(
                    "drain heartbeat was not accepted by any endpoint "
                    "(hub unreachable?); proceeding with drain anyway"
                )
        except Exception as e:
            logger.warning("drain heartbeat failed: %s", e)

        # --- 2. Wait for in-flight generation to complete. -----------------
        # This is the whole point of the drain: give the RPC master time
        # to finish the current token generation before we kill the
        # workers. The RPC master does not interrupt in-flight requests
        # when it sees a node draining; only our own rpc-server termination
        # does. So the grace window is the window in which the model can
        # finish its current generation.
        #
        # We use the exit event so that a future forced-drain path could
        # short-circuit this wait. Today there is no such path.
        logger.info(
            "waiting %ds for in-flight generation to complete "
            "(shutdown_grace_seconds)", grace
        )
        self._exit_event.wait(timeout=grace)

        # --- 3. Stop the RPC workers. -------------------------------------
        # Any tokens still in flight after the grace window are lost.
        # Disk-backed llama.cpp checkpoints would fix this; they do not
        # exist yet (llama.cpp issue #20697).
        logger.info("stopping rpc workers")
        try:
            self.rpc.stop_all()
        except Exception as e:
            logger.error("error stopping rpc workers: %s", e)

        if self.use_wireguard:
            try:
                wg_down()
            except Exception as e:
                logger.warning("error stopping wireguard: %s", e)

        # --- 4. Signal completion. ----------------------------------------
        # On Windows, the NETTRADES Networking Service polls for
        # `drain_complete_file` after sending its PRESHUTDOWN trigger.
        # Writing it lets the service return promptly from PRESHUTDOWN.
        # On Linux, this file is informational.
        try:
            os.makedirs(os.path.dirname(self.drain_complete_file), exist_ok=True)
            with open(self.drain_complete_file, "w") as f:
                f.write(datetime.utcnow().isoformat())
            logger.info("wrote drain completion marker: %s", self.drain_complete_file)
        except Exception as e:
            logger.warning("could not write drain completion marker: %s", e)

        # Delete the trigger file so a future stop is not pre-empted.
        try:
            if os.path.isfile(self.drain_requested_file):
                os.remove(self.drain_requested_file)
                logger.info("removed drain trigger file: %s", self.drain_requested_file)
        except Exception as e:
            logger.warning("could not remove drain trigger file: %s", e)

        # --- 5. Signal the main loop to exit. -----------------------------
        logger.info("drain complete; exiting")
        self.running = False

    def _on_shutdown_signal(self, signum, frame) -> None:
        """Signal handler for SIGTERM / SIGINT. Delegates to `_trigger_drain`."""
        logger.info("shutdown signal %d received", signum)
        self._trigger_drain(f"signal {signum}")

    def _watch_drain_file(self) -> None:
        """
        Poll for the drain trigger file. If it appears, trigger drain.
    
        This is the Windows path: the NETTRADES Networking Service writes
        the trigger file on SERVICE_CONTROL_PRESHUTDOWN (see
        nettrades-netsvc/main.go), and this thread turns that into the
        same drain sequence that SIGTERM triggers on Linux.
    
        On Linux, the file is optional. If no external process writes it,
        this thread simply sleeps. The primary Linux path is SIGTERM.
    
        STALE-FILE HANDLING (2026-10-22):
        If the machine lost power during a previous shutdown, the trigger
        file may survive the reboot. We must NOT interpret that as a live
        drain request, or the spoke will immediately disconnect itself on
        every boot until the file is manually removed. We therefore only
        honour the trigger if it was written AFTER this process started.
        """
        path = self.drain_requested_file
        if not path:
            return
    
        # Record the process start time. A trigger file older than this was
        # left behind by a previous run and must be ignored.
        process_start_ts = time.time()
    
        # If a stale trigger exists from before we started, delete it. It is
        # not a live signal.
        try:
            if os.path.isfile(path):
                mtime = os.path.getmtime(path)
                if mtime < process_start_ts - 2:  # 2s slack for startup
                    logger.warning(
                        "Ignoring stale drain trigger file %s "
                        "(written %.1fs before startup)",
                        path, process_start_ts - mtime,
                    )
                    os.remove(path)
        except OSError:
            pass
    
        while self.running and not self._draining:
            try:
                if os.path.isfile(path):
                    logger.info("drain trigger file found: %s", path)
                    self._trigger_drain(f"file {path}")
                    return
            except OSError:
                pass
            time.sleep(1)

    # -------------------------------------------------------------------------
    # Loops
    # -------------------------------------------------------------------------

    def run_heartbeat_loop(self) -> None:
        consecutive = 0
        while self.running:
            if self.heartbeat():
                if consecutive:
                    logger.info("heartbeat recovered after %d failures", consecutive)
                consecutive = 0
            else:
                consecutive += 1
                logger.warning("heartbeat failed (%d consecutive)", consecutive)
                self.registered = False
                if consecutive >= 3 and self._rediscover_hub():
                    consecutive = 0
                    if self.register():
                        continue
                if not self.register():
                    time.sleep(15)
            time.sleep(self.heartbeat_interval)

    def run_wg_loop(self) -> None:
        while self.running:
            if self.registered and self.use_wireguard and not wg_is_up():
                logger.warning("WireGuard tunnel down — bringing up")
                wg_up()
            time.sleep(30)

    def run(self) -> None:
        if not self.register():
            logger.error("initial registration failed; exiting")
            return

        if not self.rpc.start_all():
            logger.error("no rpc-server could be started; exiting")
            if self.use_wireguard:
                wg_down()
            return

        threading.Thread(target=self.run_heartbeat_loop, daemon=True).start()
        if self.use_wireguard:
            threading.Thread(target=self.run_wg_loop, daemon=True).start()
        # NEW (2026-10-20): file-based drain watcher. See _watch_drain_file.
        threading.Thread(
            target=self._watch_drain_file,
            name="drain-watcher",
            daemon=True,
        ).start()

        # NEW (2026-10-20): SIGTERM / SIGINT both trigger a graceful drain
        # rather than an immediate stop. The drain sequence is the same on
        # every platform; only the trigger differs.
        signal.signal(signal.SIGTERM, self._on_shutdown_signal)
        signal.signal(signal.SIGINT, self._on_shutdown_signal)

        try:
            while self.running:
                time.sleep(0.5)
        finally:
            # Wait for the drain thread to finish if it is running. The
            # systemd unit's TimeoutStopSec (>= 60s, recommend 90s) gives
            # this plenty of headroom. If we exit before the drain
            # completes, the RPC workers are killed by the OS and the
            # grace window is wasted.
            if self._drain_thread is not None:
                self._drain_thread.join(timeout=120)


# =============================================================================
# CLI
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="NETTRADES Spoke Agent")
    parser.add_argument("--config", default=CONFIG_FILE)
    parser.add_argument("--sub-hub")
    parser.add_argument("--langgraph")
    parser.add_argument("--node-name")
    parser.add_argument("--token")
    parser.add_argument("--use-wireguard", action="store_true", default=None)
    parser.add_argument("--detect-only", action="store_true",
                        help="Print detected hardware profile and exit")
    parser.add_argument("--drain-only", action="store_true",
                        help="Send one drain heartbeat to the hub and exit "
                             "without starting RPC workers. Useful for "
                             "external shutdown hooks.")
    args = parser.parse_args()

    config: Dict[str, Any] = {}
    if os.path.exists(args.config):
        with open(args.config) as f:
            config = yaml.safe_load(f) or {}

    if args.sub_hub:
        config["sub_hub_url"] = args.sub_hub
    if args.langgraph:
        config["langgraph_url"] = args.langgraph
    if args.node_name:
        config["node_name"] = args.node_name
    if args.token:
        config["registration_token"] = args.token
    if args.use_wireguard is not None:
        config["use_wireguard"] = args.use_wireguard

    # --detect-only: print hardware and exit. Useful for debugging on a
    # new machine before you commit to installing.
    if args.detect_only:
        cpu = detect_cpu()
        gpus = detect_gpus()
        profile = {
            "hostname": platform.node(),
            "platform": sys.platform,
            "is_wsl": _is_wsl(),
            "cpu": cpu.to_dict(),
            "gpus": [g.to_dict() for g in gpus],
            "rpc_backends": _build_rpc_backends(gpus, get_lan_ip()),
        }
        print(json.dumps(profile, indent=2))
        return

    if not config.get("sub_hub_url"):
        logger.error("sub_hub_url is required (use --sub-hub or edit %s)", CONFIG_FILE)
        sys.exit(1)

    agent = SpokeAgent(config)

    # --drain-only: send one drain heartbeat and exit. This is what a
    # graceful-drain.sh ExecStop calls when the agent itself is not the
    # one receiving the signal (e.g. when the agent runs under a
    # different service manager). It requires the node to already be
    # registered, so it reads node_id from a state file written by the
    # running agent. If no state file exists, it fails quietly.
    if args.drain_only:
        node_id_file = os.path.join(
            os.path.dirname(agent.drain_requested_file), "node-id"
        )
        try:
            with open(node_id_file) as f:
                agent.node_id = int(f.read().strip())
            agent.registered = True
        except (IOError, OSError, ValueError):
            logger.error(
                "--drain-only requires a running agent (state file %s not found)",
                node_id_file,
            )
            sys.exit(2)
        ok = agent._notify_drain()
        sys.exit(0 if ok else 1)

    agent.run()


if __name__ == "__main__":
    main()
