"""
Unit tests for Odoo MCP Server
"""

import os
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from configparser import ConfigParser
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from odoo_mcp_server import (
    OdooClient,
    load_company_configs,
    get_odoo_client,
    list_available_companies
)


class TestOdooClient:
    """Tests for OdooClient class"""

    def test_client_initialization(self):
        """Test OdooClient initialization"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        assert client.url == "http://localhost:8069"
        assert client.database == "test_db"
        assert client.api_key == "test_key"
        assert "Bearer test_key" in client.session.headers["Authorization"]
        assert client.session.headers["X-Odoo-Database"] == "test_db"

    def test_url_strip_trailing_slash(self):
        """Test that trailing slash is removed from URL"""
        client = OdooClient(
            url="http://localhost:8069/",
            database="test_db",
            api_key="test_key"
        )
        assert client.url == "http://localhost:8069"

    @patch('odoo_mcp_server.requests.Session')
    def test_make_request_success(self, mock_session):
        """Test successful API request"""
        mock_response = Mock()
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()

        mock_session_instance = Mock()
        mock_session_instance.post.return_value = mock_response
        mock_session_instance.headers = {}
        mock_session.return_value = mock_session_instance

        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )
        client.session = mock_session_instance

        result = client._make_request("res.partner", "search_read", {"domain": []})

        assert result == {"result": "success"}
        mock_session_instance.post.assert_called_once()

    def test_search_read_basic(self):
        """Test search_read method"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = [{"id": 1, "name": "Test"}]

            result = client.search_read(
                model="res.partner",
                domain=[["name", "=", "Test"]],
                fields=["id", "name"],
                limit=10
            )

            assert result == [{"id": 1, "name": "Test"}]
            mock_request.assert_called_once_with(
                "res.partner",
                "search_read",
                {
                    "domain": [["name", "=", "Test"]],
                    "fields": ["id", "name"],
                    "limit": 10
                }
            )

    def test_create_record(self):
        """Test create method"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = 42

            result = client.create(
                model="res.partner",
                values={"name": "Test Partner", "email": "test@example.com"}
            )

            assert result == 42
            mock_request.assert_called_once()

    def test_write_record(self):
        """Test write method"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = True

            result = client.write(
                model="res.partner",
                ids=[1, 2],
                values={"phone": "555-1234"}
            )

            assert result is True

    def test_unlink_record(self):
        """Test unlink method"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = True

            result = client.unlink(model="res.partner", ids=[1, 2])

            assert result is True

    def test_search_count(self):
        """Test search_count method"""
        client = OdooClient(
            url="http://localhost:8069",
            database="test_db",
            api_key="test_key"
        )

        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = 42

            result = client.search_count(
                model="res.partner",
                domain=[["active", "=", True]]
            )

            assert result == 42


class TestConfigurationLoading:
    """Tests for configuration loading"""

    @pytest.fixture
    def temp_env_file(self, tmp_path):
        """Create a temporary .env file"""
        env_file = tmp_path / ".env"
        config = ConfigParser()

        config.add_section("company1")
        config.set("company1", "ODOO_URL", "http://localhost:8069")
        config.set("company1", "ODOO_DATABASE", "db1")
        config.set("company1", "ODOO_API_KEY", "key1")
        config.set("company1", "COMPANY_ID", "1")

        config.add_section("company2")
        config.set("company2", "ODOO_URL", "http://localhost:8069")
        config.set("company2", "ODOO_DATABASE", "db2")
        config.set("company2", "ODOO_API_KEY", "key2")
        config.set("company2", "COMPANY_ID", "2")

        with open(env_file, 'w') as f:
            config.write(f)

        return str(env_file)

    def test_load_company_configs(self, temp_env_file):
        """Test loading company configurations"""
        import odoo_mcp_server

        # Reset global configs
        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.CONFIG_FILE = temp_env_file

        configs = load_company_configs()

        assert len(configs) == 2
        assert "company1" in configs
        assert "company2" in configs
        assert configs["company1"]["database"] == "db1"
        assert configs["company2"]["database"] == "db2"

    def test_list_available_companies(self, temp_env_file):
        """Test listing available companies"""
        import odoo_mcp_server

        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.CONFIG_FILE = temp_env_file

        companies = list_available_companies()

        assert len(companies) == 2
        assert "company1" in companies
        assert "company2" in companies

    def test_get_odoo_client(self, temp_env_file):
        """Test getting Odoo client for specific company"""
        import odoo_mcp_server

        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.odoo_clients = {}
        odoo_mcp_server.CONFIG_FILE = temp_env_file

        client = get_odoo_client("company1")

        assert client is not None
        assert client.database == "db1"
        assert client.api_key == "key1"

        # Test caching - should return same instance
        client2 = get_odoo_client("company1")
        assert client is client2

    def test_get_odoo_client_invalid_company(self, temp_env_file):
        """Test error handling for invalid company"""
        import odoo_mcp_server

        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.odoo_clients = {}
        odoo_mcp_server.CONFIG_FILE = temp_env_file

        with pytest.raises(ValueError, match="Company 'invalid' not found"):
            get_odoo_client("invalid")

    def test_missing_config_file(self):
        """Test error when config file doesn't exist"""
        import odoo_mcp_server

        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.CONFIG_FILE = "/nonexistent/file.env"

        with pytest.raises(ValueError, match="Configuration file not found"):
            load_company_configs()


class TestMCPToolIntegration:
    """Integration tests for MCP tools"""

    @pytest.fixture
    def temp_env_file(self, tmp_path):
        """Create a temporary .env file"""
        env_file = tmp_path / ".env"
        config = ConfigParser()

        config.add_section("testcompany")
        config.set("testcompany", "ODOO_URL", "http://localhost:8069")
        config.set("testcompany", "ODOO_DATABASE", "test_db")
        config.set("testcompany", "ODOO_API_KEY", "test_key")
        config.set("testcompany", "COMPANY_ID", "1")

        with open(env_file, 'w') as f:
            config.write(f)

        return str(env_file)

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test that list_tools returns all tools"""
        from odoo_mcp_server import list_tools

        tools = await list_tools()

        assert len(tools) == 8
        tool_names = [tool.name for tool in tools]

        assert "odoo_list_companies" in tool_names
        assert "odoo_search_read" in tool_names
        assert "odoo_create" in tool_names
        assert "odoo_write" in tool_names
        assert "odoo_unlink" in tool_names
        assert "odoo_search" in tool_names
        assert "odoo_read" in tool_names
        assert "odoo_search_count" in tool_names

    @pytest.mark.asyncio
    async def test_call_list_companies(self, temp_env_file):
        """Test odoo_list_companies tool"""
        import odoo_mcp_server
        from odoo_mcp_server import call_tool

        odoo_mcp_server.company_configs = {}
        odoo_mcp_server.CONFIG_FILE = temp_env_file

        result = await call_tool("odoo_list_companies", {})

        assert len(result) == 1
        assert "testcompany" in result[0].text
        assert "Total: 1" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_without_company(self):
        """Test that tools require company parameter"""
        from odoo_mcp_server import call_tool

        result = await call_tool("odoo_search_read", {"model": "res.partner"})

        assert len(result) == 1
        assert "Error" in result[0].text
        assert "Company parameter is required" in result[0].text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
