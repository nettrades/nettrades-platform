# =============================================================================
# NETTRADES Universal Enterprise Connector Framework
# =============================================================================
# FILE: src/core/odoo_proxy/connectors/__init__.py
#
# PURPOSE: Exports all connector framework components.
# =============================================================================

from .base import AbstractEnterpriseConnector
from .registry import ConnectorRegistry
from .odoo import OdooConnector
from .salesforce import SalesforceConnector
from .sap import SAPConnector

__all__ = [
    'AbstractEnterpriseConnector',
    'ConnectorRegistry',
    'OdooConnector',
    'SalesforceConnector',
    'SAPConnector',
]