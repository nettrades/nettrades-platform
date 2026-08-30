# =============================================================================
# NETTRADES Universal Enterprise Proxy Framework - Registry
# =============================================================================
# FILE: src/core/proxy_framework/registry.py
# PURPOSE: Provides a registry for all available enterprise connectors.
#          Connectors are registered by name and can be retrieved dynamically.
#
# USAGE:
#   from proxy_framework.registry import ProxyRegistry
#   from proxy_framework.connectors.odoo import OdooConnector
#
#   # Register a connector
#   ProxyRegistry.register('odoo', OdooConnector)
#
#   # Get a connector instance
#   connector = ProxyRegistry.get_connector('odoo', config)
# =============================================================================

from typing import Dict, Type, Optional, List, Any
import logging
from .base import AbstractEnterpriseConnector

logger = logging.getLogger(__name__)


class ProxyRegistry:
    """
    Registry for enterprise connectors.
    
    Connectors are registered by name and can be retrieved by name.
    This enables dynamic switching between backends without changing
    the core engine or UI.
    """
    
    _connectors: Dict[str, Type[AbstractEnterpriseConnector]] = {}
    _instances: Dict[str, AbstractEnterpriseConnector] = {}
    
    @classmethod
    def register(cls, name: str, connector_class: Type[AbstractEnterpriseConnector]) -> None:
        """
        Register a connector class.
        
        Args:
            name: The unique name for this connector (e.g., 'odoo', 'salesforce')
            connector_class: The connector class (must inherit from AbstractEnterpriseConnector)
        
        Raises:
            ValueError: If a connector with the same name is already registered
        """
        if name in cls._connectors:
            logger.warning(f"Connector '{name}' is already registered. Overwriting.")
        cls._connectors[name] = connector_class
        logger.info(f"Registered connector: {name}")
    
    @classmethod
    def get_connector(cls, name: str, 
                      config: Optional[Dict[str, Any]] = None,
                      force_new: bool = False) -> AbstractEnterpriseConnector:
        """
        Get or create a connector instance.
        
        Args:
            name: The name of the connector to retrieve
            config: Configuration for the connector (required for new instances)
            force_new: If True, creates a new instance even if one exists
            
        Returns:
            An instance of the requested connector
            
        Raises:
            ValueError: If the connector is not registered
        """
        if name not in cls._connectors:
            raise ValueError(f"Connector '{name}' not registered. Available: {cls.list_connectors()}")
        
        if not force_new and name in cls._instances:
            return cls._instances[name]
        
        connector_class = cls._connectors[name]
        instance = connector_class(config or {})
        cls._instances[name] = instance
        logger.info(f"Created connector instance: {name}")
        return instance
    
    @classmethod
    def list_connectors(cls) -> List[str]:
        """List all registered connector names."""
        return list(cls._connectors.keys())
    
    @classmethod
    def clear_instances(cls) -> None:
        """Clear all cached connector instances."""
        cls._instances.clear()
        logger.info("Cleared all connector instances")
    
    @classmethod
    def get_connector_info(cls, name: str) -> Dict[str, Any]:
        """
        Get information about a registered connector.
        
        Args:
            name: The name of the connector
            
        Returns:
            Dict containing connector information
        """
        if name not in cls._connectors:
            return {'registered': False}
        
        connector_class = cls._connectors[name]
        return {
            'registered': True,
            'class_name': connector_class.__name__,
            'module': connector_class.__module__,
            'has_instance': name in cls._instances,
        }