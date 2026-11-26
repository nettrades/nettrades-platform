#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/vendor/nvidia.py
# =============================================================================
# Same interface as amd.py. Reads from /sys/class/drm for Phase 1,
# nvidia-smi for Phase 2, installs the pinned driver branch, and detects
# NVLink for tensor-parallel support.
# =============================================================================

import glob
import os
import re
import subprocess
from .base import VendorHandler, RawPCIDevice, InstallResult, VerificationResult


class NvidiaHandler(VendorHandler):
    vendor_id = "nvidia"
    pci_vendor_ids = ["0x10de"]

    def detect_from_pci(self):
        devices, seen = [], set()
        for vendor_path in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
            card_dir = os.path.dirname(vendor_path)
            try:
                with open(vendor_path) as f:
                    if f.read().strip().lower() != "0x10de":
                        continue
            except OSError:
                continue
            device_dir = os.path.realpath(card_dir)
            if device_dir in seen:
                continue
            seen.add(device_dir)
            slot = self._read_slot(card_dir) or "unknown"
            pci_id = self._read_pci_id(card_dir) or "10de:unknown"
            _, device_id = pci_id.split(":", 1)
            devices.append(RawPCIDevice(
                pci_vendor="0x10de", pci_device=f"0x{device_id}",
                pci_bus_id=slot, sysfs_card=os.path.basename(card_dir),
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

    def probe_software(self, devices):
        try:
            out = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=index,name,memory.total,compute_cap,driver_version",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        nvlink = self._has_nvlink()
        cuda = self._cuda_version()
        caps = []
        for i, line in enumerate(out.strip().split("\n")):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            try:
                # Match Phase 1 device by index — nvidia-smi's index is
                # stable and corresponds to CUDA_VISIBLE_DEVICES.
                dev = devices[i] if i < len(devices) else None
                caps.append({
                    "index": i,
                    "vendor": "nvidia",
                    "pci_id": f"0x10de:0x{dev.pci_device[2:]}" if dev else "0x10de:0x0",
                    "pci_bus_id": dev.pci_bus_id if dev else "unknown",
                    "model": parts[1],
                    "memory_mb": int(float(parts[2])),
                    "compute_capability": parts[3],
                    "driver_version": parts[4],
                    "toolkit_version": cuda,
                    "pin_env_name": "CUDA_VISIBLE_DEVICES",
                    "pin_env_value": str(i),
                    "rpc_port": 50052 + i,
                    "supports_tensor_parallel": nvlink,
                    "power_state": "D0",   # nvidia-smi only reports active cards
                })
            except (ValueError, IndexError):
                continue
        return caps

    def _has_nvlink(self):
        try:
            out = subprocess.run(
                ["nvidia-smi", "nvlink", "--status"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            return "Active" in out
        except Exception:
            return False

    def _cuda_version(self):
        try:
            out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"CUDA Version:\s*([0-9.]+)", out)
            return m.group(1) if m else None
        except Exception:
            return None

    def install_driver(self, profile):
        branch = profile.get("driver_branch", "550")
        try:
            r = subprocess.run(
                ["sudo", "apt-get", "install", "-y", f"nvidia-driver-{branch}-server"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return InstallResult(success=False, error="apt", log=r.stderr)
            # Configure the container toolkit runtime.
            subprocess.run(
                ["sudo", "nvidia-ctk", "runtime", "configure", "--runtime=docker"],
                check=False,
            )
            return InstallResult(success=True)
        except Exception as e:
            return InstallResult(success=False, error=str(e))

    def build_flags(self):
        return {"GGML_CUDA": "ON"}

    def runtime_env(self, gpu):
        return {"CUDA_VISIBLE_DEVICES": str(gpu.get("index", 0))}

    def verify(self):
        try:
            r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
            return VerificationResult(
                success=r.returncode == 0,
                checks=[("nvidia-smi runs", r.returncode == 0, "")],
            )
        except Exception as e:
            return VerificationResult(success=False, checks=[("nvidia-smi runs", False, str(e))])