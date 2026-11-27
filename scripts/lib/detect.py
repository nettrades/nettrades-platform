#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/lib/detect.py
# =============================================================================
# PURPOSE:
#   Two-phase hardware detection. Emits CapabilityManifest as JSON.
#
#   Phase 1 (PCI enumeration) always succeeds on a bare OS.
#   Phase 2 (software probe) returns a SUBSET if drivers are missing.
#   The difference between the two is the diagnostic signal:
#     - 6 in Phase 1, 6 in Phase 2  → healthy
#     - 6 in Phase 1, 1 in Phase 2  → driver/ROCm installation problem
#     - 6 in Phase 1, 0 in Phase 2  → driver not installed
#
#   The AMD rig failed with 6 in Phase 1, 6 in Phase 2, but only 1 with
#   gfx_target set. That's a third kind of failure — hardware present,
#   driver visible, gfx mapping wrong. The two-phase detector does not
#   catch it directly, but the *_query_gfx_targets_per_gpu fix in
#   amd.py does.
#
# USAGE:
#   python3 scripts/lib/detect.py --json           # full manifest
#   python3 scripts/lib/detect.py --phase 1        # Phase 1 only
#   python3 scripts/lib/detect.py --phase 2        # Phase 2 only
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
import os
import platform
import shutil
import socket
import subprocess
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from vendor import VENDOR_HANDLERS
from capability import CapabilityManifest, CPUInfo, GPUCapability

def _cpu():
    model = platform.processor() or "unknown"
    cores = os.cpu_count() or 1
    arch = platform.machine().lower()
    has_avx512 = has_amx = has_neon = False
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo") as f:
                content = f.read().lower()
            has_avx512 = "avx512" in content
            has_amx = "amx_" in content
            has_neon = "neon" in content or "asimd" in content
            for line in content.split("\n"):
                if "model name" in line:
                    model = line.split(":", 1)[1].strip(); break
        except OSError:
            pass
    return CPUInfo(model=model, cores=cores, threads=cores, architecture=arch,
                   has_avx512=has_avx512, has_amx=has_amx, has_neon=has_neon)


def _mem():
    total = avail = 0
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):     total = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"): avail = int(line.split()[1]) // 1024
        except OSError:
            pass
    return total, avail


def _disk_free_gb():
    try:
        st = os.statvfs(os.getcwd())
        return (st.f_bavail * st.f_frsize) / (1024**3)
    except (AttributeError, OSError):
        return 0.0

# =============================================================================
# Software detection
# =============================================================================

def _detect_software() -> Dict[str, Any]:
    """Detect installed software relevant to NETTRADES."""
    info: Dict[str, Any] = {
        'has_docker': shutil.which('docker') is not None,
        'has_wireguard': shutil.which('wg') is not None,
        'has_nvidia_container_toolkit': (
            os.path.exists('/usr/bin/nvidia-container-toolkit')
            or os.path.exists('/usr/bin/nvidia-container-runtime')
        ),
        'has_rpc_server': (
            shutil.which('rpc-server') is not None
            or shutil.which('ggml-rpc-server') is not None
            or shutil.which('ggml-rpc-server.exe') is not None
        ),
        'rpc_server_version': None,
        'llama_cpp_version': None,
        'vllm_version': None,
    }

    # Try to get rpc-server version
    for binary in ('ggml-rpc-server', 'rpc-server', 'ggml-rpc-server.exe'):
        if shutil.which(binary):
            out = _run([binary, '--version'])
            if out:
                info['rpc_server_version'] = out.split('\n')[0]
            break

    # Try to get llama.cpp version
    for binary in ('llama-server', 'llama-server.exe', 'llama-cli'):
        if shutil.which(binary):
            out = _run([binary, '--version'])
            if out:
                info['llama_cpp_version'] = out.split('\n')[0]
            break

    # Try to get vLLM version (Python package)
    try:
        import importlib.metadata
        info['vllm_version'] = importlib.metadata.version('vllm')
    except Exception:
        pass

    return info

def detect(phase=None):
    # Phase 1
    raw = []
    for h in VENDOR_HANDLERS:
        raw.extend(h.detect_from_pci())
    raw.sort(key=lambda d: d.pci_bus_id if hasattr(d, "pci_bus_id") else d.get("pci_bus_id", ""))

    if phase == 1:
        return [d.__dict__ if hasattr(d, "__dict__") else d for d in raw]

    # Phase 2
    caps_by_vendor = {}
    for h in VENDOR_HANDLERS:
        vendor_devices = [d for d in raw if (d.pci_vendor if hasattr(d, "pci_vendor") else d.get("pci_vendor")) in h.pci_vendor_ids]
        caps_by_vendor[h.vendor_id] = h.probe_software(vendor_devices)

    all_caps = []
    for h in VENDOR_HANDLERS:
        all_caps.extend(caps_by_vendor[h.vendor_id])

    all_caps.sort(key=lambda c: c["pci_bus_id"])

    if phase == 2:
        return all_caps

    # Build full manifest.
    mem_total, mem_avail = _mem()
    software = _detect_software()
    manifest = CapabilityManifest(
        hostname=socket.gethostname(),
        platform=sys.platform,
        is_wsl=("microsoft" in open("/proc/version").read().lower()
                if os.path.exists("/proc/version") else False),
        cpu=_cpu(),
        gpus=[GPUCapability(**{k: v for k, v in c.items()
                               if k in GPUCapability.__dataclass_fields__})
              for c in all_caps],
        total_ram_mb=mem_total,
        available_ram_mb=mem_avail,
        disk_free_gb=_disk_free_gb(),
        tooling=software,
    )

    # Diagnose. Three cases:
    #   len(raw) == len(all_caps)  → healthy
    #   len(raw) > len(all_caps)   → hardware present, drivers missing (real problem)
    #   len(raw) < len(all_caps)   → drivers found GPUs PCI didn't see (WSL2 pattern; benign)
    if len(raw) > len(all_caps):
        missing = [d.pci_bus_id for d in raw
                   if (d.pci_bus_id if hasattr(d, "pci_bus_id") else d.get("pci_bus_id"))
                   not in {c["pci_bus_id"] for c in all_caps}]
        print(f"[detect] WARNING: PCI enumerates {len(raw)} GPUs but "
              f"only {len(all_caps)} are driver-visible. Missing: {missing}",
              file=sys.stderr)
    elif len(raw) < len(all_caps):
        # WSL2: no /sys/class/drm entries, but nvidia-smi works.
        # Not a problem — the driver is forwarding from the Windows host.
        print(f"[detect] NOTE: PCI enumeration found {len(raw)} GPUs; "
              f"software probe found {len(all_caps)}. This is normal on WSL2.",
              file=sys.stderr)

    # Recommend a role.
    nvlink_caps = [g for g in manifest.gpus if g.supports_tensor_parallel]
    if nvlink_caps:
        manifest.recommended_role = "dynamo_worker"
    elif manifest.gpus:
        manifest.recommended_role = "rpc_worker"
    elif manifest.cpu and manifest.cpu.cores >= 8:
        manifest.recommended_role = "rpc_worker"
    else:
        manifest.recommended_role = "local_only"

    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--phase", type=int, choices=[1, 2])
    args = ap.parse_args()

    result = detect(args.phase)
    if args.json or not args.phase:
        if hasattr(result, "to_dict"):
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(json.dumps(result, indent=2, default=str))