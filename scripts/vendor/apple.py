#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/vendor/apple.py
# =============================================================================
# Same interface as amd.py and nvidia.py. Apple Silicon GPUs are not PCI
# devices, so Phase 1 returns a synthetic single "device" when running on
# arm64 Darwin. Phase 2 reads unified memory via sysctl.
#
# Returns RawPCIDevice from detect_from_pci() and GPUCapability dicts
# from probe_software(), matching the convention established by
# amd.py and nvidia.py. The previous version returned raw dicts from
# detect_from_pci(), which was inconsistent with the other handlers
# and relied on detect.py's hasattr/dict fallback logic.
# =============================================================================

import platform
import subprocess
from .base import VendorHandler, RawPCIDevice, InstallResult, VerificationResult


class AppleHandler(VendorHandler):
    vendor_id = "apple"
    # Apple Silicon does not have a PCI vendor ID. Empty list means
    # handler_for_pci_id() will never match on a real PCI ID; the
    # handler is dispatched by platform check inside detect_from_pci().
    pci_vendor_ids = []

    # ─── Phase 1: synthetic device (Apple Silicon is not PCI) ───────────────

    def detect_from_pci(self):
        """
        Apple Silicon has no PCI bus. When running on arm64 Darwin, we
        synthesise a single RawPCIDevice with a fixed pci_bus_id ("soc0")
        so the rest of the pipeline treats it uniformly. On every other
        platform this returns [] and the handler is a no-op.
        """
        if platform.machine().lower() not in ("arm64", "aarch64"):
            return []
        if platform.system() != "Darwin":
            return []

        return [RawPCIDevice(
            pci_vendor="apple",
            pci_device="0x0",
            pci_bus_id="soc0",
            sysfs_card="",
        )]

    # ─── Phase 2: software probe ────────────────────────────────────────────

    def probe_software(self, devices):
        """
        Apple Silicon shares system RAM between CPU and GPU. Report total
        system memory as the GPU budget (this is what the Metal backend
        in llama.cpp exposes).
        """
        if not devices:
            return []

        memory_mb = 0
        try:
            mem_out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if mem_out:
                memory_mb = int(mem_out) // (1024 * 1024)
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass

        model = "Apple Silicon"
        try:
            chip_out = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if chip_out:
                model = chip_out
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return [{
            "index": 0,
            "vendor": "apple",
            "pci_id": "apple:0x0",
            "pci_bus_id": "soc0",
            "model": model,
            "memory_mb": memory_mb,
            "memory_kind": "shared",
            "pin_env_name": None,
            "pin_env_value": None,
            "rpc_port": 50052,
            "power_state": "D0",
        }]

    # ─── Installation ───────────────────────────────────────────────────────

    def install_driver(self, profile):
        """Metal is built into macOS; nothing to install."""
        return InstallResult(success=True, already_installed=True)

    def build_flags(self):
        return {"GGML_METAL": "ON"}

    def runtime_env(self, gpu):
        return {}

    def verify(self):
        return VerificationResult(
            success=True,
            checks=[("Metal built into macOS", True, "")],
        )