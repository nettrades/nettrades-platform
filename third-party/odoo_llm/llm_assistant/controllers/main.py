from odoo import http
from odoo.http import request


class LLMAssistantController(http.Controller):
    @http.route("/llm/thread/set_assistant", type="json", auth="user")
    def set_thread_assistant(self, thread_id, assistant_id=False):
        """Set the assistant for a thread and return thread-specific evaluated default values

        Args:
            thread_id (int): ID of the thread to update
            assistant_id (int, optional): ID of the assistant to set, or False to clear

        Returns:
            dict: Result of the operation with evaluated default values if successful
        """
        # Get thread and assistant using the model method
        thread, assistant, error = request.env["llm.thread"].get_thread_and_assistant(
            thread_id, assistant_id
        )
        if error:
            return error

        # Set the assistant on the thread
        result = thread.set_assistant(assistant_id if assistant else False)

        # Return basic result if no assistant was set or operation failed
        if not assistant or not result:
            return {
                "success": bool(result),
                "thread_id": thread_id,
                "assistant_id": assistant_id if assistant else False,
            }

        # Get assistant values with the thread context using the model method
        return assistant.get_assistant_values(thread)

    @http.route("/llm/thread/get_assistant_values", type="json", auth="user")
    def get_thread_assistant_values(self, thread_id, assistant_id):
        """Get thread-specific evaluated default values for an assistant

        Args:
            thread_id (int): ID of the thread
            assistant_id (int): ID of the assistant

        Returns:
            dict: Result with evaluated default values
        """
        # Get thread and assistant using the model method
        thread, assistant, error = request.env["llm.thread"].get_thread_and_assistant(
            thread_id, assistant_id
        )
        if error:
            return error

        # Get assistant values with the thread context using the model method
        return assistant.get_assistant_values(thread)
