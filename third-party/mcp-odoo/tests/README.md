# Tests

This directory contains unit tests for the Odoo MCP Server.

## Test Structure

- `test_odoo_mcp_server.py` - Main test file containing:
  - `TestOdooClient` - Tests for OdooClient class methods
  - `TestConfigurationLoading` - Tests for multi-company configuration loading
  - `TestMCPToolIntegration` - Integration tests for MCP tools

## Running Tests

### Run all tests
```bash
pytest tests/ -v
```

### Run specific test class
```bash
pytest tests/test_odoo_mcp_server.py::TestOdooClient -v
```

### Run specific test
```bash
pytest tests/test_odoo_mcp_server.py::TestOdooClient::test_client_initialization -v
```

### Run with coverage
```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

### Generate HTML coverage report
```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

## Test Configuration

Test configuration is defined in `pytest.ini` at the project root.

## Writing New Tests

When adding new features, please include corresponding tests:

1. Add test methods to appropriate test class
2. Use descriptive test names starting with `test_`
3. Use `@pytest.mark.asyncio` for async tests
4. Mock external dependencies (HTTP calls, file I/O)
5. Use fixtures for common test setup

Example:
```python
def test_new_feature(self):
    """Test description"""
    # Arrange
    client = OdooClient(url="...", database="...", api_key="...")

    # Act
    result = client.new_method()

    # Assert
    assert result == expected_value
```
