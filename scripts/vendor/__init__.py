# File: scripts/vendor/__init__.py
from .base import VendorHandler, RawPCIDevice, InstallResult, VerificationResult
from .nvidia import NvidiaHandler
from .amd import AmdHandler
from .intel import IntelHandler
from .apple import AppleHandler

VENDOR_HANDLERS = [NvidiaHandler(), AmdHandler(), IntelHandler(), AppleHandler()]

def handler_for_pci_id(pci_vendor):
    for h in VENDOR_HANDLERS:
        if pci_vendor in h.pci_vendor_ids:
            return h
    return None

__all__ = [
    'VendorHandler', 'RawPCIDevice', 'InstallResult', 'VerificationResult',
    'NvidiaHandler', 'AmdHandler', 'IntelHandler', 'AppleHandler',
    'VENDOR_HANDLERS', 'handler_for_pci_id',
]