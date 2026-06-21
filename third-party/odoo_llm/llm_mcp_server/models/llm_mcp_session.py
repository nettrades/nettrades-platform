import logging
import uuid

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class LLMMCPSession(models.Model):
    _name = "llm.mcp.session"
    _description = "MCP Session Management"

    # Odoo 19: Use models.Constraint instead of _sql_constraints
    _session_id_unique = models.Constraint(
        "UNIQUE(session_id)",
        "Session ID must be unique",
    )

    # Required fields
    session_id = fields.Char(required=True, index=True, help="UUID hex format")
    state = fields.Selection(
        [
            ("not_initialized", "Not Initialized"),
            ("initializing", "Initializing"),
            ("initialized", "Initialized"),
        ],
        default="not_initialized",
        required=True,
    )

    user_id = fields.Many2one(
        "res.users",
        index=True,
        help="User associated with session, set when Bearer token is available",
    )

    # Client data
    client_capabilities = fields.Json(
        help="Client capabilities from initialize request"
    )
    client_info = fields.Json(help="Client information (name, version, etc.)")
    protocol_version = fields.Char(help="MCP protocol version requested by client")

    @api.model
    def generate_session_id(self):
        """Generate a new session ID in UUID hex format"""
        return uuid.uuid4().hex

    @api.model
    def validate_session_id(self, session_id):
        """Validate session ID format (ASCII 0x21-0x7E only)"""
        if not session_id:
            return False

        # Check if all characters are in ASCII printable range (0x21-0x7E)
        try:
            return all(0x21 <= ord(char) <= 0x7E for char in session_id)
        except (TypeError, ValueError):
            return False

    @api.model
    def get_session(self, session_id):
        """Get existing session by ID and optional user_id"""
        if not session_id:
            return self.browse()

        # Validate session_id format
        if not self.validate_session_id(session_id):
            raise ValidationError(f"Invalid session ID format: {session_id}")

        # Build search domain
        domain = [("session_id", "=", session_id)]

        return self.search(domain, limit=1)

    @api.model
    def create_new_session(self, user_id=None):
        """Create a new session for initialize method (only for stateful mode)"""
        # Always generate a new session_id
        session_id = self.generate_session_id()

        # Create new session (always starts as not_initialized for stateful mode)
        session_vals = {
            "session_id": session_id,
            "state": "not_initialized",
        }
        if user_id:
            session_vals["user_id"] = user_id

        session = self.create(session_vals)

        return session

    def is_method_allowed(self, method):
        """Check if method is allowed in current session state (stateful mode only)"""
        self.ensure_one()

        # Define allowed methods per state for stateful mode
        allowed_methods = {
            "not_initialized": ["initialize", "ping"],
            "initializing": [
                "*"
            ],  # TODO: temporarily allow, because claude desktop is sending both notifications/initialize and tools/list at the similar time and causing race condition
            "initialized": ["*"],  # Allow any method when initialized
        }

        allowed = allowed_methods.get(self.state, [])
        return "*" in allowed or method in allowed

    def transition_to(self, new_state):
        """Transition session to new state with validation"""
        self.ensure_one()

        # Define valid transitions
        valid_transitions = {
            "not_initialized": ["initializing"],
            "initializing": ["initialized"],
            "initialized": [],  # Terminal state
        }

        if new_state not in valid_transitions.get(self.state, []):
            raise ValidationError(
                f"Invalid state transition from '{self.state}' to '{new_state}'"
            )

        self.state = new_state

    def terminate(self):
        """Terminate the session (delete it)"""
        self.ensure_one()
        session_id = self.session_id
        self.unlink()
        _logger.info(f"Terminated MCP session {session_id}")
