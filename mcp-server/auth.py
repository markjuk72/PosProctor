"""
MCP Server Authentication
Simple Bearer token validation against database-stored API key.
"""

import logging
from starlette.requests import Request
from starlette.responses import JSONResponse
from config import get_mcp_api_key, is_mcp_enabled

logger = logging.getLogger(__name__)


def validate_auth(request: Request) -> tuple[bool, str | None]:
    """
    Validate the Authorization header.
    Returns (is_valid, error_message).
    """
    # Check if MCP is enabled
    if not is_mcp_enabled():
        return False, "MCP server is disabled"

    # Get the expected API key
    expected_key = get_mcp_api_key()
    if not expected_key:
        logger.warning("MCP API key not configured - rejecting request")
        return False, "MCP API key not configured"

    # Get Authorization header
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return False, "Missing Authorization header"

    # Parse Bearer token
    if not auth_header.startswith('Bearer '):
        return False, "Invalid Authorization header format (expected: Bearer <token>)"

    token = auth_header[7:]  # Remove 'Bearer ' prefix

    # Validate token
    if token != expected_key:
        logger.warning(f"Invalid API key attempt from {request.client.host}")
        return False, "Invalid API key"

    return True, None


async def auth_middleware(request: Request, call_next):
    """
    Starlette middleware for authentication.
    Allows /health endpoint without auth.
    """
    # Allow health check without auth
    if request.url.path in ('/health', '/health/'):
        return await call_next(request)

    # Validate auth for all other endpoints
    is_valid, error = validate_auth(request)
    if not is_valid:
        return JSONResponse(
            status_code=401,
            content={"error": error},
            headers={"WWW-Authenticate": "Bearer"}
        )

    return await call_next(request)
