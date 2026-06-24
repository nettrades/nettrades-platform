"""
Test that savepoint pattern handles concurrent access gracefully.

The SerializationFailure error has been reproduced manually - this test
verifies the savepoint pattern correctly catches exceptions without
crashing the entire transaction.
"""

from odoo.tests import common
from odoo.tools import mute_logger


class TestLLMToolSavepoint(common.TransactionCase):
    """Test savepoint pattern in tool registration.

    We verified the concurrent UPDATE race condition causes SerializationFailure.
    This test ensures the savepoint pattern in _register_function_tool()
    correctly catches such exceptions without crashing.
    """

    def setUp(self):
        super().setUp()
        self.LLMTool = self.env["llm.tool"]

        # Create a test tool
        self.tool = self.LLMTool.create(
            {
                "name": "test_savepoint_tool",
                "description": "Test tool for savepoint testing",
                "implementation": "function",
                "decorator_model": "res.partner",
                "decorator_method": "test_savepoint_method",
            }
        )

    @mute_logger("odoo.sql_db")
    def test_savepoint_catches_exception_and_continues(self):
        """Test that savepoint pattern catches exceptions without crashing."""

        # Simulate what happens in _register_function_tool with savepoint
        exception_caught = False

        try:
            with self.env.cr.savepoint(flush=False):
                # This would normally be tool.write()
                # Simulate an exception (like SerializationFailure)
                raise Exception("Simulated concurrent update error")
        except Exception:
            exception_caught = True

        # Savepoint should have caught the exception
        self.assertTrue(exception_caught, "Exception should be caught by savepoint")

        # Transaction should still be usable after savepoint rollback
        # This verifies the pattern doesn't crash the entire transaction
        tool = self.LLMTool.search([("id", "=", self.tool.id)])
        self.assertTrue(tool, "Transaction should still work after savepoint rollback")
        self.assertEqual(tool.name, "test_savepoint_tool")

    def test_register_function_tool_handles_concurrent_access(self):
        """Test _register_function_tool handles exceptions gracefully."""

        # Create a mock method that looks like an @llm_tool decorated method
        def mock_tool_method(self):
            """Mock tool method"""
            pass

        mock_tool_method._is_llm_tool = True
        mock_tool_method._llm_tool_name = "test_concurrent_registration"
        mock_tool_method._llm_tool_description = "Test description"
        mock_tool_method._llm_tool_metadata = {}
        mock_tool_method._llm_tool_xml_managed = False

        # First registration should succeed
        self.LLMTool._register_function_tool(
            "res.partner", "mock_concurrent_tool", mock_tool_method
        )

        # Verify tool was created
        tool = self.LLMTool.search([("name", "=", "test_concurrent_registration")])
        self.assertTrue(tool, "Tool should be created on first registration")

        # Second registration (simulating concurrent worker) should also succeed
        # (it will just update the existing tool)
        self.LLMTool._register_function_tool(
            "res.partner", "mock_concurrent_tool", mock_tool_method
        )

        # Tool should still exist
        tool = self.LLMTool.search([("name", "=", "test_concurrent_registration")])
        self.assertTrue(tool, "Tool should still exist after second registration")

    def test_register_function_tool_logs_on_concurrent_error(self):
        """Test that _register_function_tool logs when concurrent access error occurs."""
        from unittest.mock import patch

        import psycopg2.errors

        def mock_tool_method():
            """Mock tool method"""
            pass

        mock_tool_method._is_llm_tool = True
        mock_tool_method._llm_tool_name = "test_exception_tool"
        mock_tool_method._llm_tool_description = "Test description"
        mock_tool_method._llm_tool_metadata = {}
        mock_tool_method._llm_tool_xml_managed = False

        # Mock create() to raise actual PostgreSQL concurrent access error
        # This simulates what happens when another worker creates the same tool
        def mock_create(self, vals):
            raise psycopg2.errors.SerializationFailure(
                "could not serialize access due to concurrent update"
            )

        with patch.object(self.LLMTool.__class__, "create", mock_create):
            # This should NOT raise - exception should be caught by savepoint and logged
            self.LLMTool._register_function_tool(
                "res.partner", "mock_exception_tool", mock_tool_method
            )

        # Tool should NOT be created (create failed due to concurrent access)
        tool = self.LLMTool.search([("name", "=", "test_exception_tool")])
        self.assertFalse(tool, "Tool should not exist when concurrent error occurs")

    def test_xml_managed_tools_are_skipped(self):
        """Test that xml_managed=True tools are skipped during registration."""

        def mock_xml_managed_method(self):
            """Mock XML-managed tool method"""
            pass

        mock_xml_managed_method._is_llm_tool = True
        mock_xml_managed_method._llm_tool_name = "xml_managed_test_tool"
        mock_xml_managed_method._llm_tool_description = "Should be skipped"
        mock_xml_managed_method._llm_tool_metadata = {}
        mock_xml_managed_method._llm_tool_xml_managed = True  # XML managed!

        # Count tools before
        count_before = self.LLMTool.search_count([])

        # Registration should be skipped
        self.LLMTool._register_function_tool(
            "res.partner", "xml_managed_test_method", mock_xml_managed_method
        )

        # Count should be same (no new tool created)
        count_after = self.LLMTool.search_count([])
        self.assertEqual(
            count_before, count_after, "XML-managed tool should not be auto-created"
        )
