#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# FILE: scripts/vendor/amd.py
# =============================================================================
# PURPOSE:
#   AMD ROCm vendor handler.
#
#   FIXES vs the previous version:
#     1. pci_bus_id is now the real PCI slot name ("0000:0b:00.0"),
#        read from /sys/class/drm/cardN/device/uevent (PCI_SLOT_NAME=).
#        The previous version used basename(dirname(card_dir)), which is
#        "card0", not a PCI bus ID. That worked by accident for VRAM
#        reads but broke deterministic ordering.
#     2. _query_gfx_targets NO LONGER DEDUPLICATES. The previous version
#        collapsed six identical gfx1031 lines to one, so gfx_list[idx]
#        returned None for idx>0, and only GPU 0 got the HSA override.
#        That is the exact root cause of the AMD rig "only one GPU
#        works" bug. The new version returns one entry per rocminfo
#        agent in the order rocminfo emits them, which matches kernel
#        enumeration order.
#     3. HSA_OVERRIDE_MAP is now the full table, not just gfx1031.
# =============================================================================

import glob
import os
import re
import subprocess
from .base import VendorHandler, RawPCIDevice, InstallResult, VerificationResult


HSA_OVERRIDE_MAP = {
    "gfx1010": "10.3.0", "gfx1011": "10.3.0", "gfx1012": "10.3.0",
    "gfx1030": "10.3.0", "gfx1031": "10.3.0", "gfx1032": "10.3.0", "gfx1034": "10.3.0",
    "gfx1100": "11.0.0", "gfx1101": "11.0.0", "gfx1102": "11.0.0", "gfx1103": "11.0.0",
}


class AmdHandler(VendorHandler):
    vendor_id = "amd"
    pci_vendor_ids = ["0x1002"]

    # ─── Phase 1: PCI enumeration ───────────────────────────────────────────

    def detect_from_pci(self):
        """
        Read /sys/class/drm/*/device/uevent. Each amdgpu-managed card
        has a uevent file with:
            DRIVER=amdgpu
            PCI_CLASS=30000
            PCI_ID=1002:73DF
            PCI_SLOT_NAME=0000:0b:00.0
            ...
        Deduplicate on the realpath of the device directory (connector
        symlinks like card0-DP-1 resolve to the same device).
        """
        devices = []
        seen = set()
        for vendor_path in sorted(glob.glob("/sys/class/drm/card*/device/vendor")):
            card_dir = os.path.dirname(vendor_path)
            try:
                with open(vendor_path) as f:
                    if f.read().strip().lower() != "0x1002":
                        continue
            except OSError:
                continue

            device_dir = os.path.realpath(card_dir)
            if device_dir in seen:
                continue
            seen.add(device_dir)

            pci_slot = self._read_pci_slot_name(card_dir) or "unknown"
            pci_id = self._read_pci_id(card_dir) or "1002:unknown"
            _, device_id = pci_id.split(":", 1)

            devices.append(RawPCIDevice(
                pci_vendor="0x1002",
                pci_device=f"0x{device_id}",
                pci_bus_id=pci_slot,
                sysfs_card=os.path.basename(card_dir),
            ))

        # Deterministic order — required for HSA override correctness.
        devices.sort(key=lambda d: d.pci_bus_id)
        return devices

    def _read_pci_slot_name(self, card_dir):
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

    # ─── Phase 2: software probe ────────────────────────────────────────────

    def probe_software(self, devices):
        """
        Read VRAM from sysfs (authoritative), model from lspci, gfx from
        rocminfo. Return one GPUCapability per device.

        Do NOT deduplicate gfx targets. rocminfo emits one gfx line per
        HIP agent, and there are typically 2 agents per GPU (one compute,
        one HSA). Filter to compute agents by checking "Name: gfx" (the
        HSA agent uses "Name: AMD Radeon..." instead).
        """
        gfx_list = self._query_gfx_targets_per_gpu(len(devices))
        model_names = self._query_model_names_from_lspci()
        caps = []

        for i, dev in enumerate(devices):
            vram_bytes = self._read_vram_bytes(dev.sysfs_card)
            memory_mb = vram_bytes // (1024 * 1024) if vram_bytes else 0

            device_key = dev.pci_device.replace("0x", "").lower()
            model = model_names.get(device_key, f"AMD GPU ({dev.pci_device})")

            gfx = gfx_list[i] if i < len(gfx_list) else None
            hsa = HSA_OVERRIDE_MAP.get(gfx) if gfx else None

            caps.append({
                "index": i,
                "vendor": "amd",
                "pci_id": f"{dev.pci_vendor}:{dev.pci_device}",
                "pci_bus_id": dev.pci_bus_id,
                "model": model,
                "memory_mb": memory_mb,
                "gfx_target": gfx,
                "hsa_override": hsa,
                "pin_env_name": "HIP_VISIBLE_DEVICES",
                "pin_env_value": str(i),
                "rpc_port": 50052 + i,
                "power_state": self._read_power_state(dev.sysfs_card),
            })

        return caps

    def _read_vram_bytes(self, card_name):
        try:
            with open(f"/sys/class/drm/{card_name}/device/mem_info_vram_total") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return 0

    def _read_power_state(self, card_name):
        try:
            with open(f"/sys/class/drm/{card_name}/device/power_state") as f:
                return f.read().strip()
        except OSError:
            return "unknown"

    def _query_gfx_targets_per_gpu(self, expected_count):
        """
        Return a list of gfx targets, one per compute agent, in
        kernel order. Length should equal expected_count on a healthy
        system. If rocminfo is missing or fails, return [] and the
        caller will install with hsa_override=None (safe on officially
        supported cards; the installer will warn on consumer cards).
        """
        try:
            out = subprocess.run(
                ["rocminfo"], capture_output=True, text=True, timeout=15,
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []

        # Filter to CPU-independent GPU agents only. rocminfo emits
        # two "Name:" lines per GPU: one gfx target (compute agent)
        # and one marketing name (HSA agent). We want only the gfx
        # ones, in the order they appear.
        targets = []
        for line in out.split("\n"):
            m = re.search(r"\bgfx(\d+[a-z0-9]*)", line, re.IGNORECASE)
            if m:
                targets.append("gfx" + m.group(1))

        # If rocminfo emitted more targets than devices (2 per GPU on
        # a rig with HSA agents), take every other one starting at 0.
        # This is the empirical pattern on ROCm 6.3 for RDNA2.
        if len(targets) == expected_count * 2:
            targets = targets[0::2]
        return targets

    def _query_model_names_from_lspci(self):
        """Map PCI device ID (without 0x) to model name."""
        try:
            out = subprocess.run(
                ["lspci", "-nn"], capture_output=True, text=True, timeout=5,
            ).stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {}

        names = {}
        for line in out.split("\n"):
            if not any(t in line for t in ("VGA", "Display", "3D")):
                continue
            if not any(t in line for t in ("AMD", "Radeon", "Advanced Micro", "ATI")):
                continue
            m = re.search(r"\[([0-9a-f]{4}):([0-9a-f]{4})\]", line)
            if not m:
                continue
            device_id = m.group(2).lower()
            brackets = re.findall(r"\[([^\]]+)\]", line)
            for cand in reversed(brackets):
                if re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{4}", cand):
                    continue
                if re.fullmatch(r"[0-9a-f]{4}", cand):
                    continue
                names[device_id] = cand.strip()
                break
        return names

    # ─── Installation (moved from install-spoke.sh) ─────────────────────────

    def install_driver(self, profile):
        """
        Install ROCm at the pinned version. This subsumes the
        for ROCM_VER in latest 6.3 6.2 loop, the apt purge rocminfo
        step, the hipcc symlink step, and the HIP_DEVICE_LIB_PATH
        export from install-spoke.sh Step 3.
        """
        rocm_version = profile.get("rocm_version", "6.3.0")
        # Ubuntu's rocminfo conflicts with ROCm's own package.
        # Purge first, always.
        subprocess.run(["sudo", "apt-get", "remove", "-y", "rocminfo"], check=False)
        # Install the pinned ROCm stack.
        cmds = [
            ["sudo", "mkdir", "-p", "/etc/apt/keyrings"],
            ["bash", "-c",
             "wget -qO- https://repo.radeon.com/rocm/rocm.gpg.key | "
             "gpg --dearmor -o /etc/apt/keyrings/rocm.gpg"],
            ["bash", "-c",
             f"echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/rocm.gpg] "
             f"https://repo.radeon.com/rocm/apt/{rocm_version} noble main' "
             f"| sudo tee /etc/apt/sources.list.d/rocm.list"],
            ["sudo", "apt-get", "update", "-qq"],
            ["sudo", "apt-get", "install", "-y",
             "rocm-hip-libraries", "rocm-device-libs", "rocm-libs",
             "hipcc", "hipblas-dev", "libnuma-dev"],
        ]
        log = ""
        for cmd in cmds:
            r = subprocess.run(cmd, capture_output=True, text=True)
            log += r.stdout + r.stderr
            if r.returncode != 0:
                return InstallResult(success=False, error=cmd[0], log=log)

        # Symlinks — required because some build scripts invoke hipcc
        # without /opt/rocm/bin on PATH.
        for binary in ("hipcc", "hipconfig", "rocminfo"):
            subprocess.run(["sudo", "ln", "-sf",
                            f"/opt/rocm/bin/{binary}", f"/usr/local/bin/{binary}"],
                           check=False)
        return InstallResult(success=True, log=log)

    def build_flags(self):
        return {"GGML_HIP": "ON", "GPU_TARGETS": "gfx1030,gfx1031,gfx1032"}

    def runtime_env(self, gpu):
        env = {}
        if gpu.get("hsa_override"):
            env["HSA_OVERRIDE_GFX_VERSION"] = gpu["hsa_override"]
        env["HIP_VISIBLE_DEVICES"] = str(gpu.get("index", 0))
        return env

    def systemd_environment(self, manifest):
        """
        Return the LD_LIBRARY_PATH and (if uniform) HSA_OVERRIDE for the
        systemd unit drop-in. This replaces the hand-written
        /etc/systemd/system/nettrades-spoke.service.d/ld-path.conf.
        """
        env = {"LD_LIBRARY_PATH": "/opt/rocm/lib:/opt/rocm/lib64"}
        overrides = {g.get("hsa_override") for g in manifest.gpus if g.get("hsa_override")}
        if len(overrides) == 1:
            env["HSA_OVERRIDE_GFX_VERSION"] = overrides.pop()
        return env

    def verify(self):
        """Run rocminfo and confirm at least one GPU agent is visible."""
        checks = []
        try:
            r = subprocess.run(["rocminfo"], capture_output=True, text=True, timeout=10)
            gfx_count = len(re.findall(r"\bgfx\d+", r.stdout))
            checks.append(("rocminfo reports gfx targets", gfx_count > 0,
                           f"{gfx_count} agents"))
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            checks.append(("rocminfo runs", False, str(e)))

        try:
            r = subprocess.run(["hipcc", "--version"], capture_output=True, text=True, timeout=10)
            checks.append(("hipcc runs", r.returncode == 0, ""))
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            checks.append(("hipcc runs", False, str(e)))

        return VerificationResult(
            success=all(ok for _, ok, _ in checks),
            checks=checks,
        )