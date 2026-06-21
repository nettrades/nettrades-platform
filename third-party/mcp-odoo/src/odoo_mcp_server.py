#!/usr/bin/env python3
"""
Odoo 19 MCP Server

This MCP server provides tools to interact with Odoo 19's External JSON-2 API.
Supports multiple company configurations with enhanced error handling, retry logic,
and image processing capabilities.
"""

import os
import json
import logging
import time
from typing import Any, Optional, Dict
from configparser import ConfigParser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("odoo-mcp-server")

# Configuration file path
CONFIG_FILE = os.getenv("ODOO_CONFIG_FILE", ".env")

# Request configuration from environment
REQUEST_TIMEOUT = int(os.getenv("ODOO_REQUEST_TIMEOUT", "30"))
MAX_RETRIES = int(os.getenv("ODOO_MAX_RETRIES", "3"))


class OdooClient:
    """Client for interacting with Odoo JSON-2 API with retry logic and connection pooling"""

    def __init__(self, url: str, database: str, api_key: str):
        self.url = url.rstrip("/")
        self.database = database
        self.api_key = api_key

        # Create session with retry logic
        self.session = self._create_session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "X-Odoo-Database": database,
            "Content-Type": "application/json"
        })

        logger.info(f"Initialized OdooClient for {database} at {url}")

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic and connection pooling"""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=MAX_RETRIES,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"],
            backoff_factor=1  # Will retry after 1, 2, 4 seconds
        )

        # Mount adapter with retry strategy
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _make_request(self, model: str, method: str, payload: dict) -> Any:
        """Make a request to the Odoo API with timeout and error handling"""
        endpoint = f"{self.url}/json/2/{model}/{method}"

        start_time = time.time()
        logger.debug(f"Making request to {endpoint} with payload: {json.dumps(payload, default=str)[:200]}...")

        try:
            response = self.session.post(
                endpoint,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            elapsed = time.time() - start_time
            logger.debug(f"Request completed in {elapsed:.2f}s with status {response.status_code}")

            response.raise_for_status()
            result = response.json()

            # Validate response structure
            if isinstance(result, dict) and 'error' in result:
                error_msg = result.get('error', {}).get('message', 'Unknown error')
                logger.error(f"Odoo API returned error: {error_msg}")
                raise ValueError(f"Odoo API error: {error_msg}")

            return result

        except requests.exceptions.Timeout:
            logger.error(f"Request timeout after {REQUEST_TIMEOUT}s for {endpoint}")
            raise TimeoutError(f"Request to Odoo API timed out after {REQUEST_TIMEOUT}s")

        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error to {endpoint}: {e}")
            raise ConnectionError(f"Failed to connect to Odoo API: {e}")

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for {endpoint}: {e}")
            try:
                error_detail = e.response.json()
                raise ValueError(f"Odoo API HTTP {e.response.status_code}: {error_detail}")
            except json.JSONDecodeError:
                raise ValueError(f"Odoo API HTTP {e.response.status_code}: {e.response.text}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            raise

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {endpoint}: {e}")
            raise ValueError(f"Invalid JSON response from Odoo API: {e}")

        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            raise

    def search_read(
        self,
        model: str,
        domain: list,
        fields: Optional[list] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None
    ) -> list:
        """Search and read records"""
        payload = {"domain": domain}
        if fields:
            payload["fields"] = fields
        if limit:
            payload["limit"] = limit
        if offset:
            payload["offset"] = offset
        if order:
            payload["order"] = order

        return self._make_request(model, "search_read", payload)

    def create(self, model: str, values: dict) -> int:
        """Create a new record"""
        payload = {"values": values}
        return self._make_request(model, "create", payload)

    def write(self, model: str, ids: list, values: dict) -> bool:
        """Update existing records"""
        payload = {"ids": ids, "values": values}
        return self._make_request(model, "write", payload)

    def unlink(self, model: str, ids: list) -> bool:
        """Delete records"""
        payload = {"ids": ids}
        return self._make_request(model, "unlink", payload)

    def search(
        self,
        model: str,
        domain: list,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None
    ) -> list:
        """Search for record IDs"""
        payload = {"domain": domain}
        if limit:
            payload["limit"] = limit
        if offset:
            payload["offset"] = offset
        if order:
            payload["order"] = order

        return self._make_request(model, "search", payload)

    def read(self, model: str, ids: list, fields: Optional[list] = None) -> list:
        """Read specific records by ID"""
        payload = {"ids": ids}
        if fields:
            payload["fields"] = fields

        return self._make_request(model, "read", payload)

    def search_count(self, model: str, domain: list) -> int:
        """Count records matching domain"""
        payload = {"domain": domain}
        return self._make_request(model, "search_count", payload)


# Initialize the MCP server
app = Server("odoo-mcp-server")

# Store multiple company configurations
company_configs: Dict[str, Dict[str, str]] = {}
odoo_clients: Dict[str, OdooClient] = {}


def load_company_configs() -> Dict[str, Dict[str, str]]:
    """Load company configurations from .env file"""
    global company_configs

    if company_configs:
        return company_configs

    if not os.path.exists(CONFIG_FILE):
        raise ValueError(f"Configuration file not found: {CONFIG_FILE}")

    config = ConfigParser()
    config.read(CONFIG_FILE)

    for section in config.sections():
        company_configs[section] = {
            'url': config.get(section, 'ODOO_URL'),
            'database': config.get(section, 'ODOO_DATABASE'),
            'api_key': config.get(section, 'ODOO_API_KEY'),
            'company_id': config.get(section, 'COMPANY_ID', fallback='1')
        }

    if not company_configs:
        raise ValueError("No company configurations found in .env file")

    logger.info(f"Loaded {len(company_configs)} company configurations: {list(company_configs.keys())}")
    return company_configs


def get_odoo_client(company: str) -> OdooClient:
    """Get or create Odoo client instance for specific company"""
    global odoo_clients

    if company not in odoo_clients:
        configs = load_company_configs()

        if company not in configs:
            available = ", ".join(configs.keys())
            raise ValueError(f"Company '{company}' not found. Available companies: {available}")

        config = configs[company]
        odoo_clients[company] = OdooClient(
            config['url'],
            config['database'],
            config['api_key']
        )
        logger.info(f"Created Odoo client for company: {company}")

    return odoo_clients[company]


def list_available_companies() -> list[str]:
    """Get list of available company names"""
    configs = load_company_configs()
    return list(configs.keys())


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available Odoo tools"""
    return [
        Tool(
            name="odoo_list_companies",
            description="List all available company configurations",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="odoo_search_read",
            description="Search and read records from an Odoo model. Combines search and read operations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use (as defined in .env file sections)"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name (e.g., 'res.partner', 'account.move', 'product.product')"
                    },
                    "domain": {
                        "type": "array",
                        "description": "Search domain as a list of criteria (e.g., [['name', '=', 'John']]). Use [] for all records.",
                        "default": []
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of field names to retrieve. If not specified, returns all fields."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of records to return"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of records to skip"
                    },
                    "order": {
                        "type": "string",
                        "description": "Sorting order (e.g., 'name asc', 'create_date desc')"
                    }
                },
                "required": ["company", "model"]
            }
        ),
        Tool(
            name="odoo_create",
            description="Create a new record in an Odoo model",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name (e.g., 'res.partner', 'account.move')"
                    },
                    "values": {
                        "type": "object",
                        "description": "Dictionary of field values for the new record"
                    }
                },
                "required": ["company", "model", "values"]
            }
        ),
        Tool(
            name="odoo_write",
            description="Update existing records in an Odoo model",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of record IDs to update"
                    },
                    "values": {
                        "type": "object",
                        "description": "Dictionary of field values to update"
                    }
                },
                "required": ["company", "model", "ids", "values"]
            }
        ),
        Tool(
            name="odoo_unlink",
            description="Delete records from an Odoo model",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of record IDs to delete"
                    }
                },
                "required": ["company", "model", "ids"]
            }
        ),
        Tool(
            name="odoo_search",
            description="Search for record IDs matching criteria (without reading full records)",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name"
                    },
                    "domain": {
                        "type": "array",
                        "description": "Search domain as a list of criteria",
                        "default": []
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of IDs to return"
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of records to skip"
                    },
                    "order": {
                        "type": "string",
                        "description": "Sorting order"
                    }
                },
                "required": ["company", "model"]
            }
        ),
        Tool(
            name="odoo_read",
            description="Read specific records by their IDs",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of record IDs to read"
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of field names to retrieve"
                    }
                },
                "required": ["company", "model", "ids"]
            }
        ),
        Tool(
            name="odoo_search_count",
            description="Count the number of records matching search criteria",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "The company configuration name to use"
                    },
                    "model": {
                        "type": "string",
                        "description": "The Odoo model name"
                    },
                    "domain": {
                        "type": "array",
                        "description": "Search domain as a list of criteria",
                        "default": []
                    }
                },
                "required": ["company", "model"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "odoo_list_companies":
            companies = list_available_companies()
            return [TextContent(
                type="text",
                text=f"Available companies: {', '.join(companies)}\n\nTotal: {len(companies)}"
            )]

        # All other tools require a company parameter
        company = arguments.get("company")
        if not company:
            raise ValueError("Company parameter is required")

        client = get_odoo_client(company)

        if name == "odoo_search_read":
            result = client.search_read(
                model=arguments["model"],
                domain=arguments.get("domain", []),
                fields=arguments.get("fields"),
                limit=arguments.get("limit"),
                offset=arguments.get("offset"),
                order=arguments.get("order")
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "odoo_create":
            result = client.create(
                model=arguments["model"],
                values=arguments["values"]
            )
            return [TextContent(type="text", text=f"Created record with ID: {result}")]

        elif name == "odoo_write":
            result = client.write(
                model=arguments["model"],
                ids=arguments["ids"],
                values=arguments["values"]
            )
            return [TextContent(type="text", text=f"Updated successfully: {result}")]

        elif name == "odoo_unlink":
            result = client.unlink(
                model=arguments["model"],
                ids=arguments["ids"]
            )
            return [TextContent(type="text", text=f"Deleted successfully: {result}")]

        elif name == "odoo_search":
            result = client.search(
                model=arguments["model"],
                domain=arguments.get("domain", []),
                limit=arguments.get("limit"),
                offset=arguments.get("offset"),
                order=arguments.get("order")
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "odoo_read":
            result = client.read(
                model=arguments["model"],
                ids=arguments["ids"],
                fields=arguments.get("fields")
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "odoo_search_count":
            result = client.search_count(
                model=arguments["model"],
                domain=arguments.get("domain", [])
            )
            return [TextContent(type="text", text=f"Count: {result}")]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server"""
    logger.info("Starting Odoo MCP Server (Multi-Company Support)")
    logger.info(f"Configuration file: {CONFIG_FILE}")

    try:
        companies = list_available_companies()
        logger.info(f"Loaded {len(companies)} companies: {', '.join(companies)}")
    except Exception as e:
        logger.warning(f"Could not load company configurations on startup: {e}")
        logger.warning("Configurations will be loaded on first tool call")

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
