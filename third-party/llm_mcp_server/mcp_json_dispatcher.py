"""
Custom MCP Dispatcher for handling MCP-specific JSON-RPC requirements
"""

import logging
from typing import Optional

import werkzeug.exceptions
from mcp.types import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)

from odoo.http import JsonRPCDispatcher, request

_logger = logging.getLogger(__name__)

# MCP Constants
MCP_SESSION_ID_HEADER = "Mcp-Session-Id"
MCP_PROTOCOL_VERSION_HEADER = "Mcp-Protocol-Version"


class MCPError(Exception):
    """Enhanced MCP exception with both JSON-RPC and HTTP status codes"""

    def __init__(
        self, message: str, code: int = INTERNAL_ERROR, http_status: int = 200
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class MCPSessionError(MCPError):
    """Session-related errors (typically HTTP 404/400)"""

    def __init__(self, message: str = "Session error", http_status: int = 404):
        super().__init__(message, INVALID_REQUEST, http_status)


class MCPProtocolError(MCPError):
    """Protocol validation errors (typically HTTP 400)"""

    def __init__(self, message: str = "Protocol error", http_status: int = 400):
        super().__init__(message, INVALID_REQUEST, http_status)


class MCPParseError(MCPError):
    """JSON parsing errors"""

    def __init__(self, message: str = "Parse error"):
        super().__init__(message, PARSE_ERROR, 400)


class MCPMethodNotFoundError(MCPError):
    """Method not found errors"""

    def __init__(self, method: str):
        message = f"Method not found: {method}"
        super().__init__(message, METHOD_NOT_FOUND)


class MCPInvalidParamsError(MCPError):
    """Invalid parameters errors"""

    def __init__(self, message: str = "Invalid parameters"):
        super().__init__(message, INVALID_PARAMS)


class MCPJsonRPCDispatcher(JsonRPCDispatcher):
    """
    Custom dispatcher for MCP (Model Context Protocol) that extends JSON-RPC
    with MCP-specific error handling, custom HTTP status codes, and protocol headers.
    """

    routing_type = "mcp_json"

    def dispatch(self, endpoint, args):
        """
        Hybrid approach: peek at JSON for MCP validation, then let parent handle dispatch.
        """
        # 1. Peek at JSON to get method for PRE-validation (don't handle errors here)
        try:
            jsonrequest = self.request.get_json_data()
            method = jsonrequest.get("method")
            session_id = request.httprequest.headers.get(MCP_SESSION_ID_HEADER.lower())

            # 2. MCP validations BEFORE endpoint execution
            if method:
                self._validate_session_requirements(method, session_id)
            self._validate_protocol_version()

        except (ValueError, AttributeError):
            # Let parent handle JSON parsing errors properly
            pass

        # 3. Let parent handle ALL JSON-RPC work (parsing, validation, dispatch)
        return super().dispatch(endpoint, args)

    def handle_error(self, exc: Exception):
        """
        Custom error handler that preserves MCP error codes and HTTP status codes
        """
        # Log all errors for debugging
        _logger.error(
            f"MCP Dispatcher handling error: {exc.__class__.__name__}: {exc}",
            exc_info=True,
        )

        # Handle MCP errors with custom HTTP status codes
        if isinstance(exc, MCPError) and exc.http_status != 200:
            # Build JSON-RPC error response with custom HTTP status
            response_data = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                },
            }
            return request.make_json_response(
                response_data,
                status=exc.http_status,
                headers={"Content-Type": "application/json"},
            )

        # Handle Werkzeug HTTP exceptions (401, 404, etc.)
        if isinstance(exc, werkzeug.exceptions.HTTPException):
            # Return proper HTTP status for Werkzeug exceptions
            response_data = {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "error": {
                    "code": exc.code,
                    "message": exc.description or str(exc),
                },
            }
            return request.make_json_response(
                response_data,
                status=exc.code,  # Use the actual HTTP status
            )

        # For everything else, let parent handle it
        return super().handle_error(exc)

    def pre_dispatch(self, rule, args):
        """
        Add custom MCP headers to CORS responses
        """
        # Let parent handle standard pre-dispatch (CORS, etc.)
        super().pre_dispatch(rule, args)

        # Add custom MCP headers to CORS responses
        routing = rule.endpoint.routing
        cors = routing.get("cors")
        if cors and self.request.httprequest.method == "OPTIONS":
            allowed_headers = (
                "Origin, X-Requested-With, Content-Type, Accept, Authorization, "
                "Mcp-Session-Id, Mcp-Protocol-Version"
            )
            self.request.future_response.headers.set(
                "Access-Control-Allow-Headers", allowed_headers
            )

    def _response(self, result=None, error=None):
        """
        Override to add MCP-specific headers to responses.

        Note: Streaming/keep-alive is handled by the production HTTP server
        (nginx/Gunicorn). The Werkzeug development server does not support
        HTTP keep-alive, so MCP clients may not work in local development.
        """
        # Use parent's _response for JSON-RPC structure
        response = super()._response(result, error)

        # Add MCP session header if present
        if hasattr(request, "mcp_session_id"):
            response.headers[MCP_SESSION_ID_HEADER] = request.mcp_session_id

        return response

    def _validate_session_requirements(
        self, method_name: str, session_id: Optional[str]
    ):
        """
        Validate session requirements based on server mode and method
        Raises MCPError with appropriate HTTP status codes
        Following MCP SDK pattern (lines 677-704)
        """
        # Skip validation for test methods
        if method_name and method_name.startswith("test"):
            return

        config = request.env["llm.mcp.server.config"].get_active_config()

        # For stateless mode, no session validation needed
        if config.mode == "stateless":
            return

        # For stateful mode, check session requirements
        if method_name not in ["initialize", "ping", "notifications/initialized"]:
            if not session_id:
                raise MCPSessionError("Missing mcp-session-id header", http_status=400)

            session = request.env["llm.mcp.session"].get_session(session_id)
            if not session:
                raise MCPSessionError("Session not found", http_status=404)

            # Check if method is allowed in current session state
            if not session.is_method_allowed(method_name):
                raise MCPSessionError(
                    f"Method '{method_name}' not allowed in state '{session.state}'",
                    http_status=400,
                )

    def _validate_protocol_version(self):
        """
        Validate protocol version header in the request
        Following MCP SDK pattern (lines 706-726)
        """
        # Get protocol version from headers
        protocol_version = request.httprequest.headers.get(
            MCP_PROTOCOL_VERSION_HEADER.lower()
        )

        # If no version provided, that's OK (we'll use default)
        if not protocol_version:
            return

        # Get supported versions from config
        config = request.env["llm.mcp.server.config"].get_active_config()

        if not config.is_protocol_version_supported(protocol_version):
            supported_versions = config.get_supported_versions_string()
            raise MCPProtocolError(
                f"Unsupported protocol version: {protocol_version}. "
                f"Supported versions: {supported_versions}",
                http_status=400,
            )
