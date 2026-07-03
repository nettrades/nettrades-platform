# -*- coding: utf-8 -*-
# =============================================================================
# Edge-Device Detection - identifies Jetson, Raspberry Pi, and Coral TPU.
# =============================================================================
import subprocess, logging, os

_logger = logging.getLogger(__name__)


def detect_jetson() -> str | None:
    try:
        result = subprocess.run(
            ["jetson_release", "-s"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "MODEL" in line:
                return line.split(":")[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if os.path.exists("/proc/device-tree/compatible"):
        with open("/proc/device-tree/compatible") as f:
            content = f.read()
            if "tegra" in content or "jetson" in content.lower():
                return "Jetson (unknown model)"
    return None


def detect_raspberry_pi() -> str | None:
    if not os.path.exists("/proc/device-tree/model"):
        return None
    with open("/proc/device-tree/model") as f:
        content = f.read().strip()
        if "raspberry pi" in content.lower():
            return content
    return None


def detect_coral_tpu() -> bool:
    try:
        result = subprocess.run(
            ["lsusb"],
            capture_output=True, text=True, timeout=10
        )
        return "Global Unichip" in result.stdout or "Coral" in result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def get_edge_device_info() -> dict:
    info = {
        "jetson": detect_jetson(),
        "raspberry_pi": detect_raspberry_pi(),
        "coral_tpu": detect_coral_tpu(),
        "is_edge_device": False,
    }
    info["is_edge_device"] = bool(info["jetson"] or info["raspberry_pi"] or info["coral_tpu"])
    return info