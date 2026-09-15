#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# NETTRADES.AI — Cross-Platform Hardware Detection
# =============================================================================
# FILE: src/core/hardware_detection.py
#
# PURPOSE:
#   Detect the hardware capabilities of the machine this process is running
#   on. This is used by:
#     - The Launcher (to show the user what their machine can do)
#     - The Spoke Agent (to report capabilities to the sub-hub)
#     - The RPC Scheduler (to decide which models can run on which nodes)
#
# WHY THIS IS NOT IN ODOO:
#   Hardware detection is a host-level concern, not a business-logic concern.
#   Putting it in Odoo would mean the Odoo container needs privileged access
#   to the host's /proc, /sys, and nvidia-smi. By keeping it in a standalone
#   module in src/core/, we can:
#     1. Run it from the Launcher (Electron/Node) without Odoo
#     2. Run it from the Spoke Agent (Python) without Odoo
#     3. Run it from a Kubernetes DaemonSet without Odoo
#     4. Test it in isolation
#     5. Move to a non-Odoo enterprise backend in the future
#
# SUPPORTED PLATFORMS:
#   - Linux (bare metal, VM, WSL2)
#   - Windows (native, via WMI)
#   - macOS (Intel and Apple Silicon)
#
# SUPPORTED ACCELERATORS:
#   - NVIDIA (CUDA) via nvidia-smi
#   - AMD (ROCm) via rocm-smi
#   - Intel (oneAPI/Level Zero) via xpu-smi
#   - Apple Silicon (Metal) via system_profiler
#   - CPU (always available as fallback)
# =============================================================================

import os
import sys
import json
import platform
import subprocess
import logging
import shutil
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

_logger = logging.getLogger(__name__)


# =============================================================================
# 1. Data classes
# =============================================================================

@dataclass
class GPUInfo:
    """Information about a single GPU."""
    index: int
    vendor: str                    # 'nvidia', 'amd', 'intel', 'apple'
    model: str                     # e.g. 'NVIDIA GeForce RTX 4090'
    memory_mb: int                 # VRAM in megabytes
    compute_capability: Optional[str] = None   # e.g. '8.9' for CUDA
    driver_version: Optional[str] = None
    cuda_version: Optional[str] = None
    rocm_version: Optional[str] = None
    is_integrated: bool = False
    supports_tensor_parallel: bool = False  # NVLink / NVSwitch present
    max_power_watts: Optional[float] = None


@dataclass
class CPUInfo:
    """Information about the CPU."""
    model: str
    cores: int
    threads: int
    architecture: str              # 'x86_64', 'arm64'
    has_avx512: bool = False
    has_amx: bool = False          # Intel AMX (matrix extensions)
    has_neon: bool = False         # ARM NEON
    frequency_mhz: Optional[float] = None


@dataclass
class SystemProfile:
    """
    The complete hardware profile of a machine.

    This is the canonical data structure that is sent from a spoke to the
    hub when the spoke registers. It is also used by the RPC scheduler to
    decide which model layers can be assigned to which node.
    """
    hostname: str
    platform: str                  # 'linux', 'win32', 'darwin'
    is_wsl: bool
    cpu: CPUInfo
    gpus: List[GPUInfo]
    total_ram_mb: int
    available_ram_mb: int
    disk_free_gb: float
    has_nvidia_container_toolkit: bool = False
    has_docker: bool = False
    has_wireguard: bool = False
    has_rpc_server: bool = False
    rpc_server_version: Optional[str] = None
    llama_cpp_version: Optional[str] = None
    vllm_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serialisable dictionary."""
        return {
            'hostname': self.hostname,
            'platform': self.platform,
            'is_wsl': self.is_wsl,
            'cpu': asdict(self.cpu),
            'gpus': [asdict(g) for g in self.gpus],
            'total_ram_mb': self.total_ram_mb,
            'available_ram_mb': self.available_ram_mb,
            'disk_free_gb': self.disk_free_gb,
            'has_nvidia_container_toolkit': self.has_nvidia_container_toolkit,
            'has_docker': self.has_docker,
            'has_wireguard': self.has_wireguard,
            'has_rpc_server': self.has_rpc_server,
            'rpc_server_version': self.rpc_server_version,
            'llama_cpp_version': self.llama_cpp_version,
            'vllm_version': self.vllm_version,
        }

    @property
    def total_vram_mb(self) -> int:
        """Total VRAM across all GPUs (MB)."""
        return sum(g.memory_mb for g in self.gpus)

    @property
    def is_apple_silicon(self) -> bool:
        return self.platform == 'darwin' and self.cpu.architecture == 'arm64'

    @property
    def recommended_role(self) -> str:
        """
        Recommend a role for this node in the NETTRADES fabric.

        Returns one of:
          - 'dynamo_worker'  : NVIDIA GPU with NVLink, suitable for tensor parallelism
          - 'rpc_worker'     : any GPU or CPU, suitable for pipeline parallelism
          - 'rpc_master'     : coordinator role for a pipeline-parallel cluster
          - 'local_only'     : no distributed capability, local inference only
        """
        nvidia_gpus = [g for g in self.gpus if g.vendor == 'nvidia']
        if nvidia_gpus and any(g.supports_tensor_parallel for g in nvidia_gpus):
            return 'dynamo_worker'
        if self.gpus:
            return 'rpc_worker'
        if self.cpu.cores >= 8:
            return 'rpc_worker'  # CPU-only nodes can still contribute
        return 'local_only'


# =============================================================================
# 2. Platform detection
# =============================================================================

def _detect_os() -> str:
    """Return 'linux', 'win32', or 'darwin'."""
    if sys.platform.startswith('linux'):
        return 'linux'
    if sys.platform == 'win32':
        return 'win32'
    if sys.platform == 'darwin':
        return 'darwin'
    return sys.platform


def _detect_wsl() -> bool:
    """
    Detect whether we are running inside WSL2.

    We check three signals in order of reliability:
      1. The kernel version string (contains 'microsoft')
      2. The presence of /proc/sys/fs/binfmt_misc/WSLInterop
      3. The WSL_DISTRO_NAME environment variable (less reliable, may be unset)
    """
    if not sys.platform.startswith('linux'):
        return False
    try:
        with open('/proc/version', 'r') as f:
            if 'microsoft' in f.read().lower():
                return True
    except (IOError, OSError):
        pass
    if os.path.exists('/proc/sys/fs/binfmt_misc/WSLInterop'):
        return True
    if os.environ.get('WSL_DISTRO_NAME'):
        return True
    return False


def _run(cmd: List[str], timeout: int = 5) -> Optional[str]:
    """
    Run a command and return its stdout, or None if it fails.

    This is a defensive wrapper: it never raises, always returns None on
    failure, and enforces a timeout so a hung subprocess can't block the
    whole detection routine.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        _logger.debug(f"Command {' '.join(cmd)} returned {result.returncode}")
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        _logger.debug(f"Command {' '.join(cmd)} failed: {e}")
        return None


# =============================================================================
# 3. CPU detection
# =============================================================================

def detect_cpu() -> CPUInfo:
    """Detect CPU model, cores, threads, and instruction-set features."""
    os_name = _detect_os()
    arch = platform.machine().lower()
    # Normalise architecture names
    if arch in ('x86_64', 'amd64'):
        arch = 'x86_64'
    elif arch in ('aarch64', 'arm64'):
        arch = 'arm64'

    model = platform.processor() or 'unknown'
    cores = os.cpu_count() or 1
    threads = cores

    has_avx512 = False
    has_amx = False
    has_neon = False

    if os_name == 'linux':
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read().lower()
                if 'avx512' in content:
                    has_avx512 = True
                if 'amx' in content:
                    has_amx = True
                if 'neon' in content or 'asimd' in content:
                    has_neon = True
                # Try to get a nicer model name from the first processor block
                for line in content.split('\n'):
                    if 'model name' in line:
                        model = line.split(':', 1)[1].strip()
                        break
        except (IOError, OSError):
            pass
    elif os_name == 'darwin':
        # macOS: use sysctl
        brand = _run(['sysctl', '-n', 'machdep.cpu.brand_string'])
        if brand:
            model = brand
        # Apple Silicon always has NEON
        if arch == 'arm64':
            has_neon = True
    elif os_name == 'win32':
        # Windows: use the PROCESSOR_IDENTIFIER env var as a fallback
        model = os.environ.get('PROCESSOR_IDENTIFIER', model)

    return CPUInfo(
        model=model,
        cores=cores,
        threads=threads,
        architecture=arch,
        has_avx512=has_avx512,
        has_amx=has_amx,
        has_neon=has_neon,
    )


# =============================================================================
# 4. GPU detection — one function per vendor
# =============================================================================

def _detect_nvidia() -> List[GPUInfo]:
    """
    Detect NVIDIA GPUs via nvidia-smi.

    The query we use:
      --query-gpu=index,name,memory.total,compute_cap,driver_version
      --format=csv,noheader,nounits

    We also try to detect NVLink presence (needed for tensor parallelism).
    """
    if not shutil.which('nvidia-smi'):
        return []

    out = _run([
        'nvidia-smi',
        '--query-gpu=index,name,memory.total,compute_cap,driver_version',
        '--format=csv,noheader,nounits',
    ])
    if not out:
        return []

    gpus: List[GPUInfo] = []
    for line in out.split('\n'):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 5:
            continue
        try:
            gpus.append(GPUInfo(
                index=int(parts[0]),
                vendor='nvidia',
                model=parts[1],
                memory_mb=int(float(parts[2])),
                compute_capability=parts[3],
                driver_version=parts[4],
                cuda_version=None,  # filled below
            ))
        except (ValueError, IndexError) as e:
            _logger.debug(f"Failed to parse nvidia-smi line: {line} ({e})")

    # Try to detect NVLink (needed for tensor parallelism in vLLM/Dynamo)
    nvlink_out = _run(['nvidia-smi', 'nvlink', '--status'])
    if nvlink_out and 'Link' in nvlink_out and 'Active' in nvlink_out:
        for g in gpus:
            g.supports_tensor_parallel = True
        _logger.info("NVLink detected — tensor parallelism is supported")

    # Try to detect CUDA version from nvidia-smi header
    full = _run(['nvidia-smi'])
    if full:
        for line in full.split('\n'):
            if 'CUDA Version' in line:
                try:
                    cuda_ver = line.split('CUDA Version:')[1].split()[0]
                    for g in gpus:
                        g.cuda_version = cuda_ver
                except IndexError:
                    pass
                break

    return gpus


def _detect_amd() -> List[GPUInfo]:
    """
    Detect AMD GPUs via rocm-smi or amd-smi.

    ROCm is the AMD equivalent of CUDA. We try rocm-smi first, then fall
    back to amd-smi (newer name).
    """
    binary = shutil.which('rocm-smi') or shutil.which('amd-smi')
    if not binary:
        return []

    out = _run([binary, '--showproductname', '--showmeminfo', 'vram'])
    if not out:
        return []

    gpus: List[GPUInfo] = []
    # rocm-smi output is not CSV; parse heuristically
    current: Dict[str, Any] = {}
    for line in out.split('\n'):
        line = line.strip()
        if not line:
            if current:
                gpus.append(GPUInfo(
                    index=len(gpus),
                    vendor='amd',
                    model=current.get('model', 'AMD GPU'),
                    memory_mb=current.get('vram_mb', 0),
                ))
                current = {}
            continue
        if 'Card series' in line or 'Card model' in line:
            current['model'] = line.split(':', 1)[-1].strip()
        if 'VRAM Total Memory' in line:
            try:
                # Usually in MB or bytes depending on version
                val = line.split(':', 1)[-1].strip().split()[0]
                current['vram_mb'] = int(float(val))
            except (ValueError, IndexError):
                pass
    if current:
        gpus.append(GPUInfo(
            index=len(gpus),
            vendor='amd',
            model=current.get('model', 'AMD GPU'),
            memory_mb=current.get('vram_mb', 0),
        ))
    return gpus


def _detect_apple_silicon() -> List[GPUInfo]:
    """
    Detect Apple Silicon GPU (M1/M2/M3/M4).

    Apple Silicon has a unified memory architecture: the GPU shares RAM
    with the CPU. There is no separate "VRAM". We report the total system
    memory as the GPU's usable memory.
    """
    if platform.machine().lower() not in ('arm64', 'aarch64'):
        return []
    if sys.platform != 'darwin':
        return []

    # Get total system memory as a proxy for GPU memory
    mem_bytes = _run(['sysctl', '-n', 'hw.memsize'])
    total_mb = 0
    if mem_bytes:
        try:
            total_mb = int(mem_bytes) // (1024 * 1024)
        except ValueError:
            pass

    # Get the chip name (e.g. "Apple M3 Max")
    chip = _run(['sysctl', '-n', 'machdep.cpu.brand_string']) or 'Apple Silicon'

    return [GPUInfo(
        index=0,
        vendor='apple',
        model=chip,
        memory_mb=total_mb,
        is_integrated=True,
        supports_tensor_parallel=False,  # No NVLink equivalent
    )]


def _detect_intel() -> List[GPUInfo]:
    """
    Detect Intel GPUs (Arc, Data Center GPU Max).

    We try xpu-smi first (for discrete GPUs), then fall back to
    checking /sys/class/drm for integrated graphics.
    """
    binary = shutil.which('xpu-smi')
    if binary:
        out = _run([binary, 'discovery'])
        if out:
            gpus: List[GPUInfo] = []
            for line in out.split('\n'):
                if 'Device Name' in line or 'device_name' in line:
                    name = line.split(':', 1)[-1].strip().strip('"')
                    gpus.append(GPUInfo(
                        index=len(gpus),
                        vendor='intel',
                        model=name,
                        memory_mb=0,  # xpu-smi memory query varies by version
                    ))
            return gpus
    return []


def detect_gpus() -> List[GPUInfo]:
    """
    Detect all GPUs on this machine, regardless of vendor.

    Order of detection:
      1. NVIDIA (most common for AI workloads)
      2. AMD (ROCm)
      3. Apple Silicon (Metal)
      4. Intel (oneAPI)
    """
    gpus: List[GPUInfo] = []
    gpus.extend(_detect_nvidia())
    gpus.extend(_detect_amd())
    gpus.extend(_detect_apple_silicon())
    gpus.extend(_detect_intel())

    # Re-index to ensure indices are contiguous
    for i, gpu in enumerate(gpus):
        gpu.index = i

    return gpus


# =============================================================================
# 5. Software detection
# =============================================================================

def _detect_software() -> Dict[str, Any]:
    """Detect installed software relevant to NETTRADES."""
    info: Dict[str, Any] = {
        'has_docker': shutil.which('docker') is not None,
        'has_wireguard': shutil.which('wg') is not None,
        'has_nvidia_container_toolkit': os.path.exists('/usr/bin/nvidia-container-toolkit')
            or os.path.exists('/usr/bin/nvidia-container-runtime'),
        'has_rpc_server': shutil.which('rpc-server') is not None
            or shutil.which('ggml-rpc-server') is not None
            or shutil.which('ggml-rpc-server.exe') is not None,
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


def _detect_memory() -> Dict[str, int]:
    """Detect total and available RAM in MB."""
    total_mb = 0
    available_mb = 0

    if sys.platform.startswith('linux'):
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        total_mb = int(line.split()[1]) // 1024
                    elif line.startswith('MemAvailable:'):
                        available_mb = int(line.split()[1]) // 1024
        except (IOError, OSError):
            pass
    elif sys.platform == 'darwin':
        out = _run(['sysctl', '-n', 'hw.memsize'])
        if out:
            try:
                total_mb = int(out) // (1024 * 1024)
                available_mb = total_mb  # macOS doesn't expose "available" easily
            except ValueError:
                pass
    elif sys.platform == 'win32':
        # Windows: use ctypes GlobalMemoryStatusEx
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_mb = stat.ullTotalPhys // (1024 * 1024)
            available_mb = stat.ullAvailPhys // (1024 * 1024)
        except Exception:
            pass

    return {'total_mb': total_mb, 'available_mb': available_mb}


def _detect_disk_free() -> float:
    """Detect free disk space in GB on the filesystem containing the CWD."""
    try:
        st = os.statvfs(os.getcwd())
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except (AttributeError, OSError):
        # Windows fallback
        try:
            import shutil
            return shutil.disk_usage(os.getcwd()).free / (1024 ** 3)
        except Exception:
            return 0.0


# =============================================================================
# 6. Main entry point
# =============================================================================

def detect_system_profile() -> SystemProfile:
    """
    Detect the full system profile of the current machine.

    This is the main entry point. It runs all sub-detectors and assembles
    a single SystemProfile object that can be serialised to JSON and sent
    over the network to the hub.

    Returns:
        SystemProfile: The complete hardware profile.
    """
    import socket

    os_name = _detect_os()
    is_wsl = _detect_wsl()
    cpu = detect_cpu()
    gpus = detect_gpus()
    mem = _detect_memory()
    software = _detect_software()

    profile = SystemProfile(
        hostname=socket.gethostname(),
        platform=os_name,
        is_wsl=is_wsl,
        cpu=cpu,
        gpus=gpus,
        total_ram_mb=mem['total_mb'],
        available_ram_mb=mem['available_mb'],
        disk_free_gb=_detect_disk_free(),
        has_nvidia_container_toolkit=software['has_nvidia_container_toolkit'],
        has_docker=software['has_docker'],
        has_wireguard=software['has_wireguard'],
        has_rpc_server=software['has_rpc_server'],
        rpc_server_version=software['rpc_server_version'],
        llama_cpp_version=software['llama_cpp_version'],
        vllm_version=software['vllm_version'],
    )

    _logger.info(
        f"Detected system: {profile.hostname} ({profile.platform}"
        f"{', WSL2' if is_wsl else ''}), "
        f"{len(gpus)} GPU(s), {cpu.cores} CPU cores, "
        f"{mem['total_mb'] // 1024} GB RAM, "
        f"recommended role: {profile.recommended_role}"
    )

    return profile


# =============================================================================
# 7. CLI entry point
# =============================================================================

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    profile = detect_system_profile()
    print(json.dumps(profile.to_dict(), indent=2))