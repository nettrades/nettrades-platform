import contextlib
import json
import logging

import emoji
import markdown2
from psycopg2 import OperationalError

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RelatedRecordProxy:
    """
    A proxy object that provides clean access to related record fields in Jinja templates.
    Usage in templates: {{ related_record.get_field('field_name', 'default_value') }}
    When called directly, returns JSON with model name, id, and display name.
    """

    def __init__(self, record):
        self._record = record

    def get_field(self, field_name, default=""):
        """
        Get a field value from the related record.

        Args:
            field_name (str): The field name to access
            default: Default value if field doesn't exist or is empty

        Returns:
            The field value, or default if not available
        """
        if not self._record:
            return default

        try:
            if hasattr(self._record, field_name):
                value = getattr(self._record, field_name)

                # Handle different field types
                if value is None:
                    return default
                elif isinstance(value, bool):
                    return value  # Keep as boolean for Jinja
                elif hasattr(value, "name"):  # Many2one field
                    return value.name
                elif hasattr(value, "mapped"):  # Many2many/One2many field
                    return value.mapped("name")
                else:
                    return value
            else:
                _logger.debug(
                    "Field '%s' not found on record %s", field_name, self._record
                )
                return default

        except Exception as e:
            _logger.error(
                "Error getting field '%s' from record: %s", field_name, str(e)
            )
            return default

    def __getattr__(self, name):
        """Allow direct attribute access as fallback"""
        return self.get_field(name)

    def __bool__(self):
        """Return True if we have a record"""
        return bool(self._record)

    def __str__(self):
        """When called by itself, return JSON of model name, id, and display name"""
        if not self._record:
            return json.dumps({"model": None, "id": None, "display_name": None})

        return json.dumps(
            {
                "model": self._record._name,
                "id": self._record.id,
                "display_name": getattr(
                    self._record, "display_name", str(self._record)
                ),
            }
        )

    def __repr__(self):
        """Same as __str__ for consistency"""
        return self.__str__()


class LLMThread(models.Model):
    _name = "llm.thread"
    _description = "LLM Chat Thread"
    _inherit = ["mail.thread"]
    _order = "write_date DESC"

    name = fields.Char(
        string="Title",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
    )
    provider_id = fields.Many2one(
        "llm.provider",
        string="Provider",
        required=True,
        ondelete="restrict",
    )
    model_id = fields.Many2one(
        "llm.model",
        string="Model",
        required=True,
        domain="[('provider_id', '=', provider_id), ('model_use', 'in', ['chat', 'multimodal'])]",
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)

    # Updated fields for related record reference
    model = fields.Char(
        string="Related Document Model", help="Technical name of the related model"
    )
    res_id = fields.Many2oneReference(
        string="Related Document ID",
        model_field="model",
        help="ID of the related record",
    )

    tool_ids = fields.Many2many(
        "llm.tool",
        string="Available Tools",
        help="Tools that can be used by the LLM in this thread",
    )

    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="All Thread Attachments",
        compute="_compute_attachment_ids",
        store=True,
        help="All attachments from all messages in this thread",
    )

    attachment_count = fields.Integer(
        string="Thread Attachments",
        compute="_compute_attachment_count",
        store=True,
        help="Total number of attachments in this thread",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Set default title if not provided"""
        needs_unique_name = []

        for vals in vals_list:
            if not vals.get("name"):
                # If linked to a record, use its display name
                if vals.get("model") and vals.get("res_id"):
                    try:
                        record = self.env[vals["model"]].browse(vals["res_id"])
                        if record.exists():
                            vals["name"] = f"AI Chat - {record.display_name}"
                        else:
                            # Record doesn't exist, use technical format
                            vals["name"] = f"AI Chat - {vals['model']}#{vals['res_id']}"
                    except Exception:
                        # Model doesn't exist or access error, use technical format
                        vals["name"] = f"AI Chat - {vals['model']}#{vals['res_id']}"
                else:
                    # Generic name - will add unique ID after creation
                    vals["name"] = "New Chat"
                    needs_unique_name.append(True)
            else:
                needs_unique_name.append(False)

        records = super().create(vals_list)

        # Update generic thread names to include unique ID
        for record, needs_update in zip(records, needs_unique_name):
            if needs_update:
                record.name = f"New Chat #{record.id}"

        return records

    @api.depends("message_ids.attachment_ids")
    def _compute_attachment_ids(self):
        """Compute all attachments from all messages in this thread."""
        for thread in self:
            # Get all attachments from all messages in this thread
            all_attachments = thread.message_ids.mapped("attachment_ids")
            thread.attachment_ids = [(6, 0, all_attachments.ids)]

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        """Compute the total number of attachments in this thread."""
        for thread in self:
            thread.attachment_count = len(thread.attachment_ids)

    # ============================================================================
    # MESSAGE POST OVERRIDES - Clean integration with mail.thread
    # ============================================================================

    def message_post(
        self, *, llm_role=None, message_type="comment", body_json=None, **kwargs
    ):
        """Override to handle LLM-specific message types and metadata.

        Args:
            llm_role (str): The LLM role ('user', 'assistant', 'tool', 'system')
                           If provided, will automatically set the appropriate subtype
            body_json (dict): JSON body for tool calls - will be set after message creation
        """

        # Convert LLM role to subtype_xmlid if provided
        if llm_role:
            _, role_to_id = self.env["mail.message"].get_llm_roles()
            if llm_role in role_to_id:
                # Get the xmlid from the role
                subtype_xmlid = f"llm.mt_{llm_role}"
                kwargs["subtype_xmlid"] = subtype_xmlid

        # Handle LLM-specific subtypes and email_from generation
        if not kwargs.get("author_id") and not kwargs.get("email_from"):
            kwargs["email_from"] = self._get_llm_email_from(
                kwargs.get("subtype_xmlid"), kwargs.get("author_id"), llm_role
            )

        # Convert markdown to HTML if needed (only for assistant messages)
        # User messages should be plain text, tool messages use body_json
        if kwargs.get("body") and llm_role == "assistant":
            kwargs["body"] = self._process_llm_body(kwargs["body"])

        # Create the message using standard mail.thread flow (without body_json)
        message = super().message_post(message_type=message_type, **kwargs)

        # Set body_json after message creation if provided
        if body_json:
            message.write({"body_json": body_json})

        return message

    def _get_llm_email_from(self, subtype_xmlid, author_id, llm_role=None):
        """Generate appropriate email_from for LLM messages."""
        if author_id:
            return None  # Let standard flow handle it

        provider_name = self.provider_id.name
        model_name = self.model_id.name

        if subtype_xmlid == "llm.mt_tool" or llm_role == "tool":
            return f"Tool <tool@{provider_name.lower().replace(' ', '')}.ai>"
        elif subtype_xmlid == "llm.mt_assistant" or llm_role == "assistant":
            return f"{model_name} <ai@{provider_name.lower().replace(' ', '')}.ai>"

        return None

    def _process_llm_body(self, body):
        """Process body content for LLM messages (markdown to HTML conversion)."""
        if not body:
            return body
        return markdown2.markdown(emoji.demojize(body))

    # ============================================================================
    # STREAMING MESSAGE CREATION
    # ============================================================================

    def message_post_from_stream(
        self, stream, llm_role, placeholder_text="…", **kwargs
    ):
        """Create and update a message from a streaming response.

        Args:
            stream: Generator yielding chunks of response data
            llm_role (str): The LLM role ('user', 'assistant', 'tool', 'system')
            placeholder_text (str): Text to show while streaming

        Returns:
            message: The created/updated message record
        """
        message = None
        accumulated_content = ""

        for chunk in stream:
            # Initialize message on first content
            if message is None and chunk.get("content"):
                message = self.message_post(
                    body=placeholder_text, llm_role=llm_role, author_id=False, **kwargs
                )
                yield {"type": "message_create", "message": message.to_store_format()}

            # Handle content streaming
            if chunk.get("content"):
                accumulated_content += chunk["content"]
                message.write({"body": self._process_llm_body(accumulated_content)})
                yield {"type": "message_chunk", "message": message.to_store_format()}

            # Handle errors
            if chunk.get("error"):
                yield {"type": "error", "error": chunk["error"]}
                return message

        # Final update for assistant message
        if message and accumulated_content:
            message.write({"body": self._process_llm_body(accumulated_content)})
            yield {"type": "message_update", "message": message.to_store_format()}

        return message

    # ============================================================================
    # GENERATION FLOW - Refactored to use message_post with roles
    # ============================================================================

    def generate(self, user_message_body=None, **kwargs):
        """Main generation method with PostgreSQL advisory locking.

        Args:
            user_message_body: Optional message body. If not provided, will use
                              the latest message in the thread to start generation.
        """
        self.ensure_one()

        with self._generation_lock():
            last_message = False
            # Post user message if provided
            if user_message_body:
                last_message = self.message_post(
                    body=user_message_body,
                    llm_role="user",
                    author_id=self.env.user.partner_id.id,
                    **kwargs,
                )
                yield {
                    "type": "message_create",
                    "message": last_message.to_store_format(),
                }

            # Call the actual generation implementation
            last_message = yield from self.generate_messages(last_message)
            return last_message

    def generate_messages(self, last_message=None):
        """Generate messages - to be overridden by llm_assistant module."""
        raise UserError(
            _("Please install the llm_assistant module for actual AI generation.")
        )

    def get_context(self, base_context=None):
        context = {
            **(base_context or {}),
            "thread_id": self.id,
        }
        # Guard clause: skip if model or res_id not set
        if not self.model or not self.res_id:
            return context

        try:
            related_record = self.env[self.model].browse(self.res_id)
            if related_record:
                context["related_record"] = RelatedRecordProxy(related_record)
                context["related_model"] = self.model
                context["related_res_id"] = self.res_id
            else:
                context["related_record"] = None
                context["related_model"] = None
                context["related_res_id"] = None
        except Exception as e:
            _logger.warning(
                "Error accessing related record %s,%s: %s", self.model, self.res_id, e
            )

        return context

    # ============================================================================
    # POSTGRESQL ADVISORY LOCK IMPLEMENTATION
    # ============================================================================

    def _acquire_thread_lock(self):
        """Acquire PostgreSQL advisory lock for this thread."""
        self.ensure_one()

        try:
            query = "SELECT pg_try_advisory_lock(%s)"
            self.env.cr.execute(query, (self.id,))
            result = self.env.cr.fetchone()

            if not result or not result[0]:
                raise UserError(
                    _(
                        "This conversation is currently generating a response. "
                        "Please wait for it to complete before sending another message."
                    )
                )

            _logger.info(f"Acquired advisory lock for thread {self.id}")

        except UserError:
            raise
        except OperationalError as e:
            _logger.error("Database error acquiring lock for thread %s: %s", self.id, e)
            raise UserError(
                _(
                    "Unable to process your request due to a system conflict. "
                    "Please wait a moment and try again."
                )
            ) from e
        except Exception as e:
            _logger.error(
                "Unexpected error acquiring lock for thread %s: %s", self.id, e
            )
            raise UserError(
                _(
                    "Your request could not be processed. Please refresh the page and try again."
                )
            ) from e

    def _release_thread_lock(self):
        """Release PostgreSQL advisory lock for this thread."""
        self.ensure_one()

        try:
            query = "SELECT pg_advisory_unlock(%s)"
            self.env.cr.execute(query, (self.id,))
            result = self.env.cr.fetchone()

            success = result and result[0]
            if success:
                _logger.info(f"Released advisory lock for thread {self.id}")
            else:
                _logger.warning(f"Advisory lock for thread {self.id} was not held")

            return success

        except Exception as e:
            _logger.error(f"Error releasing lock for thread {self.id}: {e}")
            return False

    @contextlib.contextmanager
    def _generation_lock(self):
        """Context manager for thread generation with automatic lock cleanup."""
        self.ensure_one()

        self._acquire_thread_lock()

        try:
            _logger.info(f"Starting locked generation for thread {self.id}")
            yield self

        finally:
            released = self._release_thread_lock()
            if released:
                _logger.info(f"Finished locked generation for thread {self.id}")
            else:
                _logger.warning(f"Lock release failed for thread {self.id}")

    # ============================================================================
    # ODOO HOOKS AND CLEANUP
    # ============================================================================

    # ============================================================================
    # STORE INTEGRATION - For mail.store compatibility
    # ============================================================================

    def _thread_to_store(self, store, **kwargs):
        """Extend base _thread_to_store to include LLM-specific fields."""
        super()._thread_to_store(store, **kwargs)

        # Add LLM-specific thread data
        for thread in self:
            # Build the data dict with only the fields we need
            thread_data = {
                "id": thread.id,
                "model": "llm.thread",
                "name": thread.name,  # Essential for UI display
                "write_date": thread.write_date,  # For sorting in thread list
                "channel_type": "llm_chat",  # Custom type for LLM threads
            }

            # Related record fields (for linking threads to Odoo records)
            # Use res_model to avoid conflict with "model": "llm.thread"
            if thread.model:
                thread_data["res_model"] = thread.model
            if thread.res_id:
                thread_data["res_id"] = thread.res_id

            # Add LLM-specific fields using proper Store.one/Store.many format
            if thread.provider_id:
                thread_data["provider_id"] = {
                    "id": thread.provider_id.id,
                    "name": thread.provider_id.name,
                    "model": "llm.provider",
                }

            if thread.model_id:
                thread_data["model_id"] = {
                    "id": thread.model_id.id,
                    "name": thread.model_id.name,
                    "model": "llm.model",
                }

            if thread.tool_ids:
                thread_data["tool_ids"] = [
                    {"id": tool.id, "name": tool.name, "model": "llm.tool"}
                    for tool in thread.tool_ids
                ]

            store.add("mail.thread", thread_data)

    @api.ondelete(at_uninstall=False)
    def _unlink_llm_thread(self):
        unlink_ids = [record.id for record in self]
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id, "llm.thread/delete", {"ids": unlink_ids}
        )
