"""
PosProctor MCP Server
Exposes PosProctor data (logs, metrics, stores) via Model Context Protocol.
"""

import logging
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from config import MCP_PORT, is_mcp_enabled

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Transport security settings - disable DNS rebinding protection since we're behind nginx
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=False
)

# Create FastMCP server
mcp = FastMCP(
    "posproctor-mcp",
    transport_security=transport_security
)

# Import and register tools after mcp is created
from tools.metrics import register_metrics_tools
from tools.logs import register_log_tools
from tools.stores import register_store_tools

register_metrics_tools(mcp)
register_log_tools(mcp)
register_store_tools(mcp)

# Add a health check tool
@mcp.tool()
def health_check() -> str:
    """Check the health status of the PosProctor MCP server."""
    enabled = is_mcp_enabled()
    return f"Status: {'healthy' if enabled else 'disabled'}\nMCP Enabled: {enabled}"


@mcp.tool()
def list_available_tools() -> str:
    """
    List all available tools in the PosProctor MCP server.
    Use this to discover what capabilities are available.

    Returns:
        List of all tools with descriptions
    """
    tools_info = """
PosProctor MCP Server - Available Tools
========================================

STORE MANAGEMENT:
  - list_stores(group, brand, enabled_only)
      List all configured stores, optionally filtered by group or brand

  - get_store_details(store)
      Get detailed info about a specific store including equipment status

  - search_stores(query)
      Search for stores by name, IP, group, or brand

  - get_groups()
      List all geographic groups with store counts

  - get_brands()
      List all brands with store counts

EQUIPMENT METRICS:
  - get_pump_status(store, group)
      Get current pump status across fleet or for a specific store

  - get_equipment_uptime(equipment_type, group, timerange)
      Calculate uptime % for equipment types: pump, dcr, price_display, pinpad, fep, pos

  - get_offline_equipment(equipment_type, group)
      List all currently offline equipment

  - get_scrape_failures()
      Get stores with failed monitoring (unreachable commanders)

  - get_fleet_tank_status()
      Get tank level sensor (TLS) status across all stores

LOG QUERIES:
  - query_store_logs(store, timerange, filter_text, limit)
      Query syslog entries for a specific store

  - search_logs(search_text, timerange, store, limit)
      Search all logs for specific text across the fleet

  - search_security_events(timerange, event_type, store)
      Search for security events: login, logout, failed_auth, config_change

  - get_log_summary(store, timerange)
      Get summary of log activity for a store or fleet

SYSTEM:
  - health_check()
      Check health status of the MCP server

  - list_available_tools()
      This tool - lists all available tools
"""
    return tools_info


# Health check HTTP endpoint (separate from MCP tools)
async def health_endpoint(request):
    """HTTP health check endpoint."""
    enabled = is_mcp_enabled()

    return JSONResponse({
        "status": "healthy" if enabled else "disabled",
        "service": "posproctor-mcp",
        "mcp_enabled": enabled
    })


class MCPEnabledMiddleware:
    """ASGI middleware to check if MCP is enabled."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Get path
        path = scope.get("path", "")

        # Allow health checks always
        if path.rstrip("/") in ["/health", ""]:
            await self.app(scope, receive, send)
            return

        # Check if MCP is enabled
        if not is_mcp_enabled():
            response = Response("MCP server is disabled", status_code=503)
            await response(scope, receive, send)
            return

        # MCP enabled - proceed without auth
        await self.app(scope, receive, send)


def create_app():
    """Create the combined Starlette app with health endpoint and MCP SSE."""
    # Get the SSE app from FastMCP
    sse_app = mcp.sse_app()

    # Wrap SSE app with enabled-check middleware (no auth)
    wrapped_sse_app = MCPEnabledMiddleware(sse_app)

    # Create the main app with health route
    main_app = Starlette(
        routes=[
            Route("/health", health_endpoint, methods=["GET"]),
            Route("/health/", health_endpoint, methods=["GET"]),
        ]
    )

    # Mount the wrapped SSE app
    main_app.mount("/", wrapped_sse_app)

    return main_app


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Starting PosProctor MCP Server (No Auth)")
    logger.info(f"Port: {MCP_PORT}")
    logger.info(f"MCP Enabled: {is_mcp_enabled()}")
    logger.info("=" * 60)

    app = create_app()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=MCP_PORT,
        log_level="info"
    )


if __name__ == "__main__":
    main()
