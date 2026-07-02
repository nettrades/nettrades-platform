# -*- coding: utf-8 -*-
# =============================================================================
# Section H – Container runtime isolation for GPU nodes.
# =============================================================================
# gVisor is the preferred runtime for ALL GPU pools (Trusted & Untrusted).
# It uses a userspace kernel (Sentry) that intercepts syscalls, providing
# strong isolation WITHOUT the memory-hoarding problem of VM-based solutions.
#
# gVisor avoids memory hoarding because freed memory returns to the host
# immediately — there is no guest VM retaining physical pages.
#
# GPU support is provided by nvproxy, which "proxies the application's
# interactions with NVIDIA's driver on the host" and "supports a wide range
# of CUDA workloads, including PyTorch and various generative models like LLMs."
#
# Installation: curl -fsSL https://gvisor.dev/archive/runsc > /usr/local/bin/runsc
#                chmod +x /usr/local/bin/runsc
#                runsc install
#                systemctl restart docker
#
# To enable GPU: add --nvproxy flag when running containers.
# Supported drivers: 570.124.06 through 580.105.08 (verified Feb 2026).
# =============================================================================
import subprocess, os, shutil, sys, logging

_logger = logging.getLogger(__name__)


def detect_best_runtime():
    """
    Return the strongest available container runtime.
    Preference: gVisor > Docker.
    gVisor provides syscall-level isolation without memory hoarding.
    Docker is used as a fallback only for trusted internal pools.
    """
    if shutil.which('runsc'):
        return 'gvisor'
    if shutil.which('docker'):
        return 'docker'
    raise RuntimeError(
        "No supported container runtime found. "
        "Please install gVisor: "
        "https://gvisor.dev/docs/user_guide/install/"
    )


def start_isolated(server_url, token):
    """
    Start the GPUStack worker inside the appropriate isolation container.
    
    gVisor mode (preferred):
        Uses runsc with --nvproxy flag for GPU passthrough.
        Memory is managed by the host kernel — no hoarding, no balloon drivers.
    
    Docker mode (fallback, trusted internal pools only):
        Standard Docker with --gpus all.
    """
    runtime = detect_best_runtime()
    
    if runtime == 'gvisor':
        _logger.info("Starting GPUStack worker with gVisor isolation (nvproxy GPU support).")
        # Transparent Huge Pages (THP) is recommended for production:
        # "page fault for every page of application memory, and THP reduces the
        # fault count by 512x (2MB / 4KB). This is the recommended configuration
        # for production gVisor deployments with GPU workloads."
        # Use Popen (non-blocking) so agent main loop can continue
        subprocess.Popen([
            "runsc", "--nvproxy", "run",
            "worker-container",
            "gpustack-worker", "--server-url", server_url, "--token", token
        ], check=True)
    elif runtime == 'docker':
        _logger.warning(
            "gVisor not found — falling back to Docker (trusted internal pool only)."
        )
        # Use Popen (non-blocking) so agent main loop can continue
        subprocess.Popen(["gpustack", "start", "--server-url", server_url, "--token", token])
    else:
        raise RuntimeError("No suitable runtime available for GPU isolation.")


# For informational purposes only — no Kata-specific code remains.
# gVisor avoids the following Kata limitations:
#   - Memory hoarding (guest VM retains physical pages)
#   - virtio-mem configuration complexity
#   - KVM requirement (not available in WSL2, cloud VMs, etc.)
#   - All-GPUs-per-VM restriction
# FUTURE: Consider adding Firecracker as an alternative microVM option if
# stronger hardware-level isolation is ever needed.