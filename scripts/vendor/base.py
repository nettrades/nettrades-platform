#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/vendor/base.py
# =============================================================================
# PURPOSE:
#   Abstract base class for vendor-specific GPU handlers.
#
#   The interface is modelled on TensorFusion's vendorSpecificHandler and
#   the NCSA ansible-role-gpu design. Adding a new vendor means writing
#   one file that subclasses this, and registering it in __init__.py.
#   Nothing else in the codebase changes.
#
#   Do NOT put vendor-specific assumptions anywhere outside a vendor
#   handler. No `if vendor == 'amd'` in install-spoke.sh. No
#   `if gfx in ('gfx1031',)` in spoke-agent.py. The handler owns all
#   vendor knowledge; the rest of the system only knows about the
#   CapabilityManifest contract.
# =============================================================================

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RawPCIDevice:
    """A single PCI device. Populated by Phase 1 detection only."""
    pci_vendor: str            # "0x1002"
    pci_device: str            # "0x73df"
    pci_bus_id: str            # "0000:0b:00.0" (stable, from /sys/.../uevent)
    sysfs_card: str            # "/sys/class/drm/card0" (for probe phase)


@dataclass
class InstallResult:
    success: bool
    already_installed: bool = False
    error: str = ""
    log: str = ""


@dataclass
class VerificationResult:
    success: bool
    checks: list = None          # [(name, ok, detail), ...]


class VendorHandler(ABC):
    """
    Vendor-specific GPU handler.

    Lifecycle:
      1. detect_from_pci()   — Phase 1, no drivers required.
      2. probe_software()    — Phase 2, drivers must be present.
      3. install_driver()    — Idempotent. Called by install-spoke.sh.
      4. build_flags()       — CMake flags for llama.cpp.
      5. runtime_env()       — Per-process pinning for one rpc-server.
      6. systemd_environment — Values for the systemd unit drop-in.
      7. verify()            — Post-install gate.

    All methods are safe to call in any order, but the installer calls
    them in the order listed above.
    """

    vendor_id: str
    pci_vendor_ids: list

    @abstractmethod
    def detect_from_pci(self) -> list:
        """
        Enumerate every device this vendor owns, using /sys/class/drm
        (Linux) or WMI (Windows) or system_profiler (macOS).

        MUST succeed on a bare OS with no drivers installed. Do NOT
        call nvidia-smi / rocminfo / xpu-smi here — those tools may
        not exist yet.
        """

    @abstractmethod
    def probe_software(self, devices: list) -> list:
        """
        Return a GPUCapability for each device, with accurate VRAM,
        compute capability, gfx target, driver version.

        Returns a SUBSET of `devices` if some are not driver-visible.
        The caller compares lengths and reports the difference as a
        diagnostic.
        """

    @abstractmethod
    def install_driver(self, profile: dict) -> InstallResult:
        """Install the pinned driver/toolkit. Idempotent."""

    @abstractmethod
    def build_flags(self) -> dict:
        """CMake flags for llama.cpp, e.g. {'GGML_HIP': 'ON', ...}."""

    @abstractmethod
    def runtime_env(self, gpu) -> dict:
        """Per-process env for one rpc-server, e.g. {'HIP_VISIBLE_DEVICES': '3'}."""

    def systemd_environment(self, manifest) -> dict:
        """
        Values for the systemd unit drop-in. Default: empty. Override
        in a vendor handler if the vendor needs LD_LIBRARY_PATH or a
        unit-level HSA override.
        """
        return {}

    def verify(self) -> VerificationResult:
        """Post-install gate. Default: pass."""
        return VerificationResult(success=True, checks=[])