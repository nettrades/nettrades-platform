# =============================================================================
# NETTRADES Universal Enterprise Connector Framework
# =============================================================================
# FILE: src/connectors/__init__.py
# PURPOSE: Exports all connector framework components.
# =============================================================================

from .base import AbstractConnector
from .registry import ConnectorRegistry
from .odoo import OdooConnector
from .salesforce import SalesforceConnector
from .sap import SAPConnector

__all__ = [
    'AbstractConnector',
    'ConnectorRegistry',
    'OdooConnector',
    'SalesforceConnector',
    'SAPConnector',
]