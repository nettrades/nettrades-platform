#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/vendor/intel.py
# =============================================================================
# Same interface as amd.py and nvidia.py. Reads from /sys/class/drm for
# Phase 1 (matches AMD/NVIDIA pattern), xpu-smi/clinfo for Phase 2.
#
# Returns RawPCIDevice from detect_from_pci() and GPUCapability dicts
# from probe_software(), matching the convention established by
# amd.py and nvidia.py. The previous version returned raw dicts from
# detect_from_pci(), which was inconsistent with the other handlers
# and relied on detect.py's hasattr/dict fallback logic.
# =============================================================================

import glob
import os
import subprocess
from .base import VendorHandler, RawPCIDevice, InstallResult, VerificationResult


class IntelHandler(VendorHandler):
    vendor_id = "intel"
    pci_vendor_ids = ["0x8086"]

    # ─── Phase 1: PCI enumeration ───────────────────────────────────────────

    def detect_from_pci(self):
        """
        Read /sys/class/drm/*/device/uevent for PCI vendor 0x8086.
        Same pattern as amd.py and nvidia.py, so ordering is deterministic
        (sorted by PCI slot name).
        """
        devices, seen = [], set()
        for vendor_path in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
            card_dir = os.path.dirname(vendor_path)
            try:
                with open(vendor_path) as f:
                    if f.read().strip().lower() != "0x8086":
                        continue
            except OSError:
                continue

            device_dir = os.path.realpath(card_dir)
            if device_dir in seen:
                continue
            seen.add(device_dir)

            slot = self._read_slot(card_dir) or "unknown"
            pci_id = self._read_pci_id(card_dir) or "8086:unknown"
            _, device_id = pci_id.split(":", 1)

            devices.append(RawPCIDevice(
                pci_vendor="0x8086",
                pci_device=f"0x{device_id}",
                pci_bus_id=slot,
                sysfs_card=os.path.basename(card_dir),
            ))

        devices.sort(key=lambda d: d.pci_bus_id)
        return devices

    def _read_slot(self, card_dir):
        try:
            with open(os.path.join(card_dir, "uevent")) as f:
                for line in f:
                    if line.startswith("PCI_SLOT_NAME="):
                        return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    def _read_pci_id(self, card_dir):
        try:
            with open(os.path.join(card_dir, "uevent")) as f:
                for line in f:
                    if line.startswith("PCI_ID="):
                        return line.split("=", 1)[1].strip().lower()
        except OSError:
            pass
        return None

    def _read_power_state(self, card_name):
        try:
            with open(f"/sys/class/drm/{card_name}/device/power_state") as f:
                return f.read().strip()
        except OSError:
            return "unknown"

    # ─── Phase 2: software probe ────────────────────────────────────────────

    def probe_software(self, devices):
        """
        Parse xpu-smi discovery output (preferred, modern Arc / Data Center
        GPU Max) or clinfo (fallback, older Intel integrated GPUs).

        Matches Phase 1 devices by index. If a driver tool reports more
        devices than Phase 1 found, the extras are ignored. If it reports
        fewer, the caller (detect.py) reports the count mismatch as a
        diagnostic.
        """
        if not devices:
            return []

        # xpu-smi is the modern Intel tool (Arc, Data Center GPU Max).
        try:
            out = subprocess.run(
                ["xpu-smi", "discovery"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            names = self._parse_xpu_smi_names(out)
            if names:
                return [
                    self._make_cap(dev, i,
                                   model=names[i] if i < len(names) else "Intel GPU")
                    for i, dev in enumerate(devices)
                ]
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass

        # clinfo fallback (older Intel iGPU with OpenCL-only driver).
        try:
            out = subprocess.run(
                ["clinfo"], capture_output=True, text=True, timeout=10,
            ).stdout
            if out and "intel" in out.lower():
                names = self._parse_clinfo_intel_names(out)
                return [
                    self._make_cap(dev, i,
                                   model=names[i] if i < len(names) else "Intel GPU")
                    for i, dev in enumerate(devices)
                ]
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass

        return []

    def _parse_xpu_smi_names(self, output):
        """
        xpu-smi discovery output contains blocks per device with a line
        like `Device Name : Intel(R) Arc(TM) A770 Graphics` (whitespace
        and separators vary by version). Return the names in order.
        """
        names = []
        for line in output.split("\n"):
            lower = line.lower()
            if "device name" in lower or "device_name" in lower:
                name = line.split(":", 1)[-1].strip().strip('"')
                if name:
                    names.append(name)
        return names

    def _parse_clinfo_intel_names(self, output):
        """clinfo output: one block per platform, `Device Name` per device."""
        names = []
        for line in output.split("\n"):
            if "Device Name" in line:
                name = line.split(":", 1)[-1].strip()
                if "intel" in name.lower():
                    names.append(name)
        return names

    def _make_cap(self, dev, index, model):
        """Build a GPUCapability-shaped dict for one Intel GPU."""
        return {
            "index": index,
            "vendor": "intel",
            "pci_id": f"{dev.pci_vendor}:{dev.pci_device}",
            "pci_bus_id": dev.pci_bus_id,
            "model": model,
            "memory_mb": 0,  # xpu-smi/clinfo don't uniformly report VRAM
            "pin_env_name": "ONEAPI_DEVICE_SELECTOR",
            "pin_env_value": f"level_zero:{index}",
            "rpc_port": 50052 + index,
            "power_state": self._read_power_state(dev.sysfs_card),
        }

    # ─── Installation ───────────────────────────────────────────────────────

    def install_driver(self, profile):
        """
        Install Intel oneAPI DPC++ compiler and OpenCL / Level Zero
        runtime. The profile's oneapi_version is informational; Intel's
        repo serves the current release, so exact pinning would require
        the .deb-by-version path. Not critical for the demo.
        """
        try:
            cmds = [
                ["sudo", "apt-get", "update", "-qq"],
                ["sudo", "apt-get", "install", "-y",
                 "intel-opencl-icd", "intel-level-zero-gpu", "level-zero",
                 "intel-oneapi-compiler-dpcpp-cpp"],
            ]
            log = ""
            for cmd in cmds:
                r = subprocess.run(cmd, capture_output=True, text=True)
                log += r.stdout + r.stderr
                if r.returncode != 0:
                    return InstallResult(success=False, error=cmd[0], log=log)
            return InstallResult(success=True, log=log)
        except Exception as e:
            return InstallResult(success=False, error=str(e))

    def build_flags(self):
        return {"GGML_SYCL": "ON"}

    def runtime_env(self, gpu):
        return {"ONEAPI_DEVICE_SELECTOR": f"level_zero:{gpu.get('index', 0)}"}

    def verify(self):
        checks = []
        try:
            r = subprocess.run(
                ["xpu-smi", "discovery"],
                capture_output=True, text=True, timeout=10,
            )
            checks.append(("xpu-smi runs", r.returncode == 0, ""))
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            checks.append(("xpu-smi runs", False, str(e)))

        return VerificationResult(
            success=all(ok for _, ok, _ in checks),
            checks=checks,
        )