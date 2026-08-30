# =============================================================================
# NETTRADES Universal Enterprise Connector Framework - Exceptions
# =============================================================================
# FILE: src/connectors/exceptions.py
# =============================================================================

class ConnectorError(Exception):
    """Base exception for all connector errors."""
    pass

class ConnectorNotFoundError(ConnectorError):
    """Raised when a connector is not found in the registry."""
    pass

class ConnectorAuthenticationError(ConnectorError):
    """Raised when authentication fails."""
    pass

class ConnectorConnectionError(ConnectorError):
    """Raised when a connection to the backend fails."""
    pass