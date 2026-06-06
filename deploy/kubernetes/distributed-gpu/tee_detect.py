# -*- coding: utf-8 -*-
# =============================================================================
# Section H – TEE / Confidential Computing Auto-Detection
# =============================================================================
# Detects whether the GPU node supports hardware-backed Trusted Execution
# Environments.  The detection runs once during agent startup and the
# results are reported to Odoo, enabling the platform to prefer TEE-capable
# nodes for high-sensitivity workloads.
#
# Detection methods (all non-privileged for querying):
#   - NVIDIA CC:  nvidia-smi conf-compute -f  →  "CC status: ON"
#   - Intel SGX:  cpuid -l 0x12 | grep SGX    →  flag present
#   - AMD SEV-SNP: CPUID 0x8000001f bit 1     →  SEV supported
#   - Intel TDX:  /sys/devices/system/cpu/microcode/tdx exists
#   - Generic TEE: /dev/tee[0-9]* exists       →  kernel TEE framework active
#
# IMPORTANT: Consumer GPUs (RTX 4090, RTX 3090, Apple Silicon) do NOT
# support any TEE technology.  Detection will return False for all checks
# on these platforms, which is the expected and correct behaviour.
# =============================================================================
import subprocess, os, logging, platform
from pathlib import Path

_logger = logging.getLogger(__name__)


def detect_nvidia_cc() -> bool:
    """
    Check whether any NVIDIA GPU on this machine supports Confidential Computing.
    Uses nvidia-smi conf-compute -f, which works on Hopper (H100/H200) and
    Blackwell (B100/B200) GPUs.
    Returns True if CC mode is active on at least one GPU.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "conf-compute", "-f"],
            capture_output=True, text=True, timeout=10
        )
        # Output contains "CC status: ON" when active
        return "CC status: ON" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        # nvidia-smi not installed or no NVIDIA GPU present
        return False


def detect_intel_sgx() -> bool:
    """
    Detect Intel SGX support via CPUID leaf 12h.
    Requires the 'cpuid' tool (apt-get install cpuid).
    Falls back to /sys/devices/system/cpu/sgx/status on kernel >=5.11.
    """
    # Method 1: CPUID tool
    try:
        result = subprocess.run(
            ["cpuid", "-l", "0x12"],
            capture_output=True, text=True, timeout=10
        )
        if "SGX" in result.stdout:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Method 2: Kernel sysfs interface (kernel >=5.11)
    sgx_status = Path("/sys/devices/system/cpu/sgx/status")
    if sgx_status.exists():
        try:
            return "enabled" in sgx_status.read_text().strip().lower()
        except (OSError, PermissionError):
            pass
    return False


def detect_amd_sev() -> bool:
    """
    Detect AMD SEV / SEV-ES / SEV-SNP support via CPUID.
    Checks CPUID function 0x8000001f bit 1 (SEV).
    on bare-metal hosts the microcode path is checked.
    """
    # Check for TDX microcode directory (bare-metal)
    try:
        result = subprocess.run(
            ["cpuid", "-l", "0x8000001f"],
            capture_output=True, text=True, timeout=10
        )
        # SEV is indicated by EAX bit 1 being True
        if "EAX bit 1 is True" in result.stdout or "SEV" in result.stdout:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if Path("/dev/sev").exists():
        return True
    return False


def detect_intel_tdx() -> bool:
    """
    Detect Intel TDX (Trust Domain Extensions) support.
    Checks bare-metal microcode directory and guest attestation device.
    """
    # Check for TDX microcode directory (bare-metal)
    if Path("/sys/devices/system/cpu/microcode/tdx").exists():
        return True
    # Check for TDX guest attestation device (inside a TD)
    if Path("/dev/tdx-guest").exists():
        return True
    # Check via virt-what-cvm (detects TDX guest)        
    try:
        result = subprocess.run(
            ["virt-what-cvm"],
            capture_output=True, text=True, timeout=10
        )
        if "intel-tdx" in result.stdout:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def detect_generic_tee() -> bool:
    """
    Detect any generic TEE framework active on the system
    (ARM TrustZone, OP-TEE, etc.) via /dev/tee* device nodes.
    Checks for /dev/tee[0-9]* or /dev/teepriv[0-9]* device nodes.
    """
    return bool(list(Path("/dev").glob("tee[0-9]*"))) or \
           bool(list(Path("/dev").glob("teepriv[0-9]*")))


def get_tee_capabilities() -> dict:
    """
    Return a dictionary summarising all TEE/Confidential Computing
    capabilities detected on this machine.  Called once at agent startup
    and included in the Odoo registration payload.
    """
    return {
        "nvidia_cc": detect_nvidia_cc(),
        "intel_sgx": detect_intel_sgx(),
        "amd_sev": detect_amd_sev(),
        "intel_tdx": detect_intel_tdx(),
        "generic_tee": detect_generic_tee(),  
#       "has_any_tee": False,   
    }


def get_tee_summary() -> dict:
    """Return the capabilities dict with has_any_tee computed."""
    caps = get_tee_capabilities()
    caps["has_any_tee"] = any(caps.values())
    return caps