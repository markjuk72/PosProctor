"""
MCP Server Configuration
Loads settings from environment variables and SQLite database.
"""

import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

# Environment configuration
DB_PATH = os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')
PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
LOKI_URL = os.getenv('LOKI_URL', 'http://loki:3100')
MCP_PORT = int(os.getenv('MCP_PORT', '8002'))


def get_db_connection():
    """Get read-only database connection."""
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key: str, default: str = None) -> str | None:
    """Get a setting value from the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row['value'] if row else default
    except Exception as e:
        logger.warning(f"Could not read setting {key}: {e}")
        return default


def get_mcp_api_key() -> str | None:
    """Get the MCP API key from database settings."""
    return get_setting('mcp_api_key')


def is_mcp_enabled() -> bool:
    """Check if MCP server is enabled in settings."""
    value = get_setting('mcp_enabled', 'true')
    return value.lower() in ('true', '1', 'yes')


def get_commanders(group: str = None, brand: str = None, enabled_only: bool = True) -> list[dict]:
    """Get commanders from database with optional filtering."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT id, ip, store_name, group_name, brand, enabled FROM commanders WHERE 1=1"
        params = []

        if enabled_only:
            query += " AND enabled = 1"
        if group:
            query += " AND group_name = ?"
            params.append(group)
        if brand:
            query += " AND brand = ?"
            params.append(brand)

        query += " ORDER BY store_name"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Could not read commanders: {e}")
        return []


def find_commander(store_query: str) -> dict | None:
    """Find a commander by store name or IP address."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Try exact IP match first
        cursor.execute(
            "SELECT id, ip, store_name, group_name, brand, enabled FROM commanders WHERE ip = ?",
            (store_query,)
        )
        row = cursor.fetchone()

        if not row:
            # Try store name contains (case insensitive)
            cursor.execute(
                "SELECT id, ip, store_name, group_name, brand, enabled FROM commanders WHERE store_name LIKE ?",
                (f'%{store_query}%',)
            )
            row = cursor.fetchone()

        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Could not find commander: {e}")
        return None
