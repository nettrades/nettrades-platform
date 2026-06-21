# Odoo 19 MCP Server

A Model Context Protocol (MCP) server that provides tools to interact with Odoo 19's External JSON-2 API. This server enables Claude and other MCP clients to perform CRUD operations and queries on Odoo databases.

## Features

- **Multi-Company Support**: Manage multiple Odoo instances/companies from a single MCP server
- **Full CRUD Operations**: Create, read, update, and delete records
- **Advanced Search**: Search with complex domain filters
- **Batch Operations**: Perform operations on multiple records
- **Image Processing**: Built-in support for processing images with Pillow (resize, format conversion)
- **Robust Error Handling**: Automatic retry with exponential backoff for transient failures
- **Connection Pooling**: Efficient HTTP connection reuse for better performance
- **Configurable Timeouts**: Prevent hanging on slow/unresponsive servers
- **Type-Safe**: Proper input validation and error handling
- **Docker Support**: Multi-stage builds with optimized image size and security
- **Production Ready**: Non-root user, health checks, and comprehensive logging

## Available Tools

### 1. `odoo_list_companies`
List all available company configurations.

**Parameters:** None

**Returns:** List of configured company names

### 2. `odoo_search_read`
Search and read records from an Odoo model.

**Parameters:**
- `company` (required): The company configuration name (from .env sections)
- `model` (required): The Odoo model name (e.g., `res.partner`, `account.move`)
- `domain` (optional): Search criteria as a list (e.g., `[["name", "=", "John"]]`)
- `fields` (optional): List of field names to retrieve
- `limit` (optional): Maximum number of records
- `offset` (optional): Number of records to skip
- `order` (optional): Sorting order (e.g., `"name asc"`)

### 3. `odoo_create`
Create a new record in an Odoo model.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `values` (required): Dictionary of field values

### 4. `odoo_write`
Update existing records.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `ids` (required): List of record IDs to update
- `values` (required): Dictionary of field values to update

### 5. `odoo_unlink`
Delete records from an Odoo model.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `ids` (required): List of record IDs to delete

### 6. `odoo_search`
Search for record IDs without reading full records.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `domain` (optional): Search criteria
- `limit`, `offset`, `order` (optional): Same as search_read

### 7. `odoo_read`
Read specific records by their IDs.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `ids` (required): List of record IDs
- `fields` (optional): List of field names to retrieve

### 8. `odoo_search_count`
Count records matching search criteria.

**Parameters:**
- `company` (required): The company configuration name
- `model` (required): The Odoo model name
- `domain` (optional): Search criteria

## Prerequisites

- Python 3.10 or higher (for local development)
- Docker and Docker Compose (for containerized deployment)
- Odoo 19 instance with External API enabled
- Odoo API key (see Configuration section)

## Configuration

### Getting an Odoo API Key

1. Log in to your Odoo instance
2. Go to **Settings** → **Users & Companies** → **Users**
3. Select your user
4. Go to the **Preferences** tab
5. In the **API Keys** section, click **New API Key**
6. Give it a description and click **Generate**
7. Copy the generated API key (it will only be shown once)

### Multi-Company Configuration

The server supports managing multiple Odoo instances/companies through a single MCP server instance. Each company is configured in the `.env` file using INI-style sections.

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your company configurations:

```ini
# Company 1
[company1]
ODOO_URL=http://localhost:8069
ODOO_DATABASE=database_name
ODOO_API_KEY=your_api_key_here
COMPANY_ID=1  # Optional, defaults to 1

# Company 2 - same database, different company
[company2]
ODOO_URL=http://localhost:8069
ODOO_DATABASE=database_name
ODOO_API_KEY=another_api_key
COMPANY_ID=2

# Company 3 - different database
[production]
ODOO_URL=https://instance.odoo.com
ODOO_DATABASE=production_db
ODOO_API_KEY=production_key
COMPANY_ID=1
```

**Key Points:**
- Each `[section_name]` defines a company configuration
- The section name is used as the `company` parameter in tool calls
- Multiple companies can connect to the same Odoo instance/database with different API keys
- `COMPANY_ID` is optional and defaults to 1 if not specified

### Advanced Configuration

You can configure request behavior using environment variables:

```ini
[company1]
ODOO_URL=http://localhost:8069
ODOO_DATABASE=database_name
ODOO_API_KEY=your_api_key_here
COMPANY_ID=1

# Optional: Override global settings per company
ODOO_REQUEST_TIMEOUT=30  # Request timeout in seconds (default: 30)
ODOO_MAX_RETRIES=3       # Maximum retry attempts (default: 3)
```

Or set global defaults in your environment/docker-compose:

```yaml
# docker-compose.yml
environment:
  - ODOO_REQUEST_TIMEOUT=60    # Longer timeout for slow networks
  - ODOO_MAX_RETRIES=5         # More retries for unreliable connections
```

**Performance Tuning:**
- Lower `ODOO_REQUEST_TIMEOUT` for faster failure detection on bad connections
- Increase `ODOO_MAX_RETRIES` for unreliable networks (max recommended: 5)
- Retry uses exponential backoff: waits 1s, 2s, 4s between attempts

## Installation & Usage

### Option 1: Docker (Recommended)

1. Build and run with Docker Compose:

```bash
docker-compose up -d
```

2. View logs:

```bash
docker-compose logs -f
```

3. Stop the server:

```bash
docker-compose down
```

### Option 2: Local Development

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the server:

```bash
python src/odoo_mcp_server.py
```

## Using with Claude Desktop

### Quick Setup (Recommended)

Run the automated setup script:

```bash
./setup-claude-desktop.sh
```

This script will:
1. Build the Docker image
2. Verify Docker is running
3. Show you the exact configuration to add to Claude Desktop

### Manual Setup

For detailed instructions, including troubleshooting and advanced configurations, see **[CLAUDE_DESKTOP_SETUP.md](CLAUDE_DESKTOP_SETUP.md)**.

**Configuration file location:**
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

**Docker Setup (Recommended):**

```json
{
  "mcpServers": {
    "odoo": {
      "command": "docker",
      "args": [
        "run",
        "--rm",
        "-i",
        "--env-file",
        "/absolute/path/to/claude-odoo-api/.env",
        "odoo-mcp-server"
      ]
    }
  }
}
```

**Local Python Setup:**

```json
{
  "mcpServers": {
    "odoo": {
      "command": "python",
      "args": [
        "/absolute/path/to/claude-odoo-api/src/odoo_mcp_server.py"
      ],
      "env": {
        "ODOO_CONFIG_FILE": "/absolute/path/to/claude-odoo-api/.env"
      }
    }
  }
}
```

**Important Notes:**
- Replace paths with your actual absolute paths
- If your Odoo is on localhost, use `host.docker.internal` in `.env` or add `"--network", "host"` to Docker args
- After updating the configuration, restart Claude Desktop completely

See [CLAUDE_DESKTOP_SETUP.md](CLAUDE_DESKTOP_SETUP.md) for complete setup instructions and troubleshooting.

## Examples & Scripts

Check out the `examples/` directory for ready-to-use scripts:

- **`process_contact_images.py`**: Export and process contact images with automatic resizing and HTML gallery generation
  ```bash
  python examples/process_contact_images.py
  ```

See [examples/README.md](examples/README.md) for detailed documentation and more examples.

## Example Usage

Once connected, you can ask Claude to interact with your Odoo instances:

**List available companies:**
```
List all available Odoo companies
```

**Search for partners:**
```
Find all partners with 'John' in their name in company1
```

**Create a new partner:**
```
Create a new partner in company2 with name "Acme Corp" and email "contact@acme.com"
```

**Update records:**
```
Update partner ID 42 in production to set their phone to "555-1234"
```

**Count records:**
```
How many invoices do we have in draft status in company1?
```

**Complex queries:**
```
Find all sales orders in company2 created in the last 30 days with a total amount greater than $1000
```

**Multi-company operations:**
```
Compare the number of active customers between company1 and company2
```

## Odoo Domain Syntax

Odoo uses a domain filter syntax for searching. Here are common examples:

```python
# Equals
[["name", "=", "John"]]

# Not equals
[["state", "!=", "draft"]]

# Greater than / Less than
[["amount_total", ">", 1000]]

# In list
[["state", "in", ["sale", "done"]]]

# Like (contains)
[["name", "ilike", "john"]]  # case-insensitive

# AND conditions (default)
[["name", "=", "John"], ["city", "=", "New York"]]

# OR conditions
["|", ["name", "=", "John"], ["name", "=", "Jane"]]

# Complex nested conditions
["|", ["state", "=", "draft"], "&", ["amount_total", ">", 1000], ["partner_id", "!=", False]]
```

## Common Odoo Models

- `res.partner` - Customers, vendors, contacts
- `product.product` - Products
- `product.template` - Product templates
- `sale.order` - Sales orders
- `sale.order.line` - Sales order lines
- `account.move` - Invoices, bills, journal entries
- `account.move.line` - Invoice/bill lines
- `stock.picking` - Warehouse transfers
- `purchase.order` - Purchase orders
- `project.project` - Projects
- `project.task` - Tasks
- `hr.employee` - Employees
- `crm.lead` - CRM leads/opportunities

## Troubleshooting

### Connection Issues

1. Verify Odoo is accessible:
```bash
curl http://your-odoo-url:8069/web/database/selector
```

2. Test API key authentication:
```bash
curl -X POST http://your-odoo-url:8069/json/2/res.partner/search_count \
  -H "Authorization: Bearer your_api_key" \
  -H "X-Odoo-Database: your_database" \
  -H "Content-Type: application/json" \
  -d '{"domain": []}'
```

### Docker Network Issues

If running Odoo locally and the container can't reach it, use `host.docker.internal` instead of `localhost`:

```env
ODOO_URL=http://host.docker.internal:8069
```

Or use host networking:
```bash
docker run --network host ...
```

### API Access Denied

Ensure your Odoo plan supports the External API. According to Odoo documentation:
- External API access requires Custom Odoo pricing plans
- Not available on One App Free or Standard plans

## Testing

The project includes comprehensive unit tests.

### Running Tests Locally

1. Install test dependencies:
```bash
pip install -r requirements.txt
```

2. Run all tests:
```bash
pytest tests/ -v
```

3. Run with coverage report:
```bash
pytest tests/ -v --cov=src --cov-report=html
```

4. View coverage report:
```bash
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
```

### Continuous Integration

The project uses GitHub Actions for CI/CD:
- **Tests**: Run on Python 3.10, 3.11, and 3.12
- **Linting**: Code style checks with flake8, black, and isort
- **Docker**: Automated Docker image builds

See `.github/workflows/ci.yml` for workflow details.

## Development

### Project Structure

```
claude-odoo-api/
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI/CD workflow
├── src/
│   └── odoo_mcp_server.py     # Main MCP server implementation
├── tests/
│   ├── __init__.py
│   ├── test_odoo_mcp_server.py # Unit tests
│   └── README.md              # Test documentation
├── Dockerfile                 # Docker image definition
├── docker-compose.yml         # Docker Compose configuration
├── requirements.txt           # Python dependencies (includes test deps)
├── pytest.ini                 # Pytest configuration
├── pyproject.toml            # Python project metadata
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules
├── CLAUDE.md                 # Developer documentation
├── README.md                 # This file
└── create_odoo_invoices.py   # Example usage script
```

### Adding New Tools

To add new Odoo API operations:

1. Add a method to the `OdooClient` class (if needed)
2. Add the tool definition in `list_tools()`
   - Include `company` as a required parameter for Odoo operations
3. Add the tool handler in `call_tool()`
   - Extract company parameter and get client instance
4. Add corresponding unit tests in `tests/`

See `CLAUDE.md` for detailed implementation guide.

## Resources

- [Odoo 19 External API Documentation](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Odoo Development Documentation](https://www.odoo.com/documentation/19.0/developer.html)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
