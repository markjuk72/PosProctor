"""
Loki HTTP API Client
Executes LogQL queries against Loki.
"""

import httpx
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from config import LOKI_URL

logger = logging.getLogger(__name__)


class LokiClient:
    """Client for Loki HTTP API."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or LOKI_URL
        self.timeout = 30.0

    def _parse_timerange(self, timerange: str) -> tuple[datetime, datetime]:
        """Parse human-readable timerange like '1h', '24h', '7d' into start/end datetimes."""
        now = datetime.utcnow()
        unit = timerange[-1].lower()
        try:
            value = int(timerange[:-1])
        except ValueError:
            value = 1

        if unit == 'h':
            delta = timedelta(hours=value)
        elif unit == 'd':
            delta = timedelta(days=value)
        elif unit == 'm':
            delta = timedelta(minutes=value)
        else:
            delta = timedelta(hours=1)

        return now - delta, now

    def _datetime_to_nanoseconds(self, dt: datetime) -> str:
        """Convert datetime to nanoseconds since epoch (Loki format)."""
        return str(int(dt.timestamp() * 1e9))

    async def query_range(
        self,
        query: str,
        timerange: str = "1h",
        limit: int = 100,
        direction: str = "backward"
    ) -> list[dict]:
        """
        Execute a LogQL query over a time range.
        Returns list of log streams with entries.

        Args:
            query: LogQL query string (e.g., '{pos_name="Store 503"}')
            timerange: Time range like "1h", "24h", "7d"
            limit: Maximum number of entries to return
            direction: "forward" (oldest first) or "backward" (newest first)
        """
        start, end = self._parse_timerange(timerange)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/query_range",
                    params={
                        "query": query,
                        "start": self._datetime_to_nanoseconds(start),
                        "end": self._datetime_to_nanoseconds(end),
                        "limit": limit,
                        "direction": direction
                    }
                )
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'success':
                    logger.error(f"Loki query failed: {data.get('error', 'Unknown error')}")
                    return []

                return data.get('data', {}).get('result', [])

            except httpx.HTTPError as e:
                logger.error(f"Loki HTTP error: {e}")
                return []
            except Exception as e:
                logger.error(f"Loki query error: {e}")
                return []

    async def instant_query(self, query: str, limit: int = 100) -> list[dict]:
        """
        Execute an instant LogQL query (at current time).
        Returns list of log streams with entries.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/query",
                    params={
                        "query": query,
                        "limit": limit
                    }
                )
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'success':
                    logger.error(f"Loki instant query failed: {data.get('error', 'Unknown error')}")
                    return []

                return data.get('data', {}).get('result', [])

            except httpx.HTTPError as e:
                logger.error(f"Loki HTTP error: {e}")
                return []
            except Exception as e:
                logger.error(f"Loki instant query error: {e}")
                return []

    async def get_labels(self) -> list[str]:
        """Get all available label names."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/loki/api/v1/labels")
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
            except Exception as e:
                logger.error(f"Failed to get Loki labels: {e}")
                return []

    async def get_label_values(self, label_name: str) -> list[str]:
        """Get all values for a specific label."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/loki/api/v1/label/{label_name}/values"
                )
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
            except Exception as e:
                logger.error(f"Failed to get Loki label values: {e}")
                return []


# Utility functions for working with Loki results

def format_log_entries(streams: list[dict]) -> list[dict]:
    """
    Format Loki stream results into a flat list of log entries.
    Each entry has timestamp, labels, and line.
    """
    entries = []
    for stream in streams:
        labels = stream.get('stream', {})
        for value in stream.get('values', []):
            ts_ns, line = value[0], value[1]
            # Convert nanoseconds to datetime
            ts = datetime.fromtimestamp(int(ts_ns) / 1e9)
            entries.append({
                'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
                'labels': labels,
                'line': line
            })
    return entries


def build_logql_query(
    stream_selector: dict,
    filter_text: str = None,
    regex_filter: str = None
) -> str:
    """
    Build a LogQL query from components.

    Args:
        stream_selector: Dict of label=value pairs (e.g., {'pos_name': 'Store 503'})
        filter_text: Simple text filter (case insensitive)
        regex_filter: Regex pattern filter
    """
    # Build stream selector
    selector_parts = []
    for key, value in stream_selector.items():
        if value is not None:
            escaped_value = str(value).replace('"', '\\"')
            selector_parts.append(f'{key}="{escaped_value}"')

    query = '{' + ','.join(selector_parts) + '}'

    # Add filters
    if filter_text:
        # Case insensitive contains
        escaped_text = filter_text.replace('`', '\\`')
        query += f' |~ "(?i){re.escape(escaped_text)}"'
    elif regex_filter:
        query += f' |~ "{regex_filter}"'

    return query


def extract_store_from_labels(labels: dict) -> str | None:
    """Extract store name from Loki labels."""
    return labels.get('pos_name') or labels.get('store')


def extract_ip_from_labels(labels: dict) -> str | None:
    """Extract IP address from Loki labels."""
    return labels.get('nat_ip') or labels.get('ip')
