#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/lib/capability.py
# =============================================================================
# PURPOSE:
#   Canonical data model for hardware capabilities. This is the contract
#   between detection (vendor handlers), installation (install-spoke.sh),
#   and runtime (spoke-agent.py, rpc_scheduler.py).
#
# WHY A SCHEMA VERSION:
#   Once a spoke has registered, the hub stores its manifest. A future
#   spoke-agent might add fields; the hub must be able to tell old
#   manifests from new ones. schema_version is the discriminator.
#
# DETERMINISM:
#   GPUs are ordered by PCI bus ID, not by enumeration order. Enumeration
#   order changes across reboots when cards are added or a driver
#   reloads. The AMD rig's "only GPU 0 gets the HSA override" bug was a
#   direct consequence of non-deterministic ordering — rocminfo emitted
#   six identical gfx1031 lines, the dedup collapsed them to one, and
#   gfx_list[idx] returned None for idx > 0. Sorting by PCI bus ID and
#   never deduplicating fixes it structurally.
# =============================================================================
#
# SPDX-License-Identifier: BUSL-1.1 OR LicenseRef-NETTRADES-Commercial
# Copyright (c) 2026 NETTRADES LIMITED (UK Company No. 08160657). Patent Pending. All rights reserved.
# Licensed under LICENSE.txt (BUSL-1.1 -> Open RAIL-S) and strictly conditioned
# upon compliance with ETHICAL-STATEMENT.md. See also LEGAL/IP-AND-PATENTS.md.
# THE FUTURE OF WORK is a registered trade mark in the United Kingdom (No. UK00004257743) of NETTRADES LIMITED.
# Distributed WITHOUT ANY WARRANTY.

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class CPUInfo:
    model: str
    cores: int
    threads: int
    architecture: str              # x86_64 | arm64
    has_avx512: bool = False
    has_amx: bool = False
    has_neon: bool = False


@dataclass
class GPUCapability:
    index: int                     # 0-based, ordered by pci_bus_id ascending
    vendor: str                    # nvidia | amd | intel | apple | unknown
    pci_id: str                    # "0x1002:0x73df"
    pci_bus_id: str                # "0000:0b:00.0" — stable ordering key
    model: str
    memory_mb: int
    compute_capability: Optional[str] = None   # "7.0" for CUDA
    gfx_target: Optional[str] = None           # "gfx1031" for ROCm
    driver_version: Optional[str] = None
    toolkit_version: Optional[str] = None      # CUDA / ROCm / oneAPI
    hsa_override: Optional[str] = None
    pin_env_name: Optional[str] = None
    pin_env_value: Optional[str] = None
    rpc_port: Optional[int] = None
    supports_tensor_parallel: bool = False
    memory_kind: str = "dedicated"             # dedicated | shared | unknown
    power_state: str = "unknown"               # D0 | D3hot | unknown


@dataclass
class CapabilityManifest:
    schema_version: str = "1.0"
    hostname: str = ""
    platform: str = ""             # linux | win32 | darwin
    is_wsl: bool = False
    cpu: CPUInfo = None
    gpus: list = field(default_factory=list)
    total_ram_mb: int = 0
    available_ram_mb: int = 0
    disk_free_gb: float = 0.0
    detected_profile: str = ""     # key into hardware-matrix.yaml
    recommended_role: str = "local_only"
    tooling: dict = field(default_factory=dict)   # {"nvidia-smi": "550.54"}
    rpc_backends: list = field(default_factory=list)

    def to_dict(self):
        d = asdict(self)
        if self.cpu:
            d["cpu"] = asdict(self.cpu)
        d["gpus"] = [asdict(g) if hasattr(g, "__dataclass_fields__") else g for g in self.gpus]
        return d

    @property
    def total_vram_mb(self):
        return sum(g.memory_mb for g in self.gpus if hasattr(g, "memory_mb"))