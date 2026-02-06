"""
Loki Log Tools
MCP tools for querying syslog data from Loki.
"""

import logging
import re
from typing import Literal
from clients.loki import LokiClient, format_log_entries, build_logql_query

logger = logging.getLogger(__name__)


def register_log_tools(mcp):
    """Register all Loki log query tools with the MCP server."""

    @mcp.tool()
    async def query_store_logs(
        store: str,
        timerange: str = "1h",
        filter_text: str = None,
        limit: int = 100
    ) -> str:
        """
        Query syslog entries for a specific store.

        Args:
            store: Store name to query (e.g., "Store 503", "Main Street 1")
            timerange: How far back to search (e.g., "1h", "24h", "7d")
            filter_text: Optional text to filter log lines (case insensitive)
            limit: Maximum number of log entries to return (default 100)

        Returns:
            Log entries with timestamps matching the criteria
        """
        client = LokiClient()

        # Build LogQL query
        # The pos_name label contains the store name from Vector enrichment
        query = build_logql_query(
            stream_selector={'pos_name': store},
            filter_text=filter_text
        )

        # If no results with pos_name, try with store pattern in the line
        results = await client.query_range(query, timerange=timerange, limit=limit)

        if not results:
            # Try a broader search
            query = f'{{source="syslog"}} |~ "(?i){re.escape(store)}"'
            if filter_text:
                query += f' |~ "(?i){re.escape(filter_text)}"'
            results = await client.query_range(query, timerange=timerange, limit=limit)

        if not results:
            return f"No logs found for {store} in the last {timerange}"

        entries = format_log_entries(results)

        if not entries:
            return f"No logs found for {store} in the last {timerange}"

        lines = [f"Log entries for {store} (last {timerange})", "=" * 60, ""]

        for entry in entries[:limit]:
            ts = entry['timestamp']
            line = entry['line']
            # Truncate very long lines
            if len(line) > 200:
                line = line[:200] + "..."
            lines.append(f"[{ts}] {line}")

        if len(entries) >= limit:
            lines.append(f"\n... (limited to {limit} entries)")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Found {len(entries)} log entries")

        return "\n".join(lines)

    @mcp.tool()
    async def search_security_events(
        timerange: str = "24h",
        event_type: Literal['login', 'logout', 'failed_auth', 'config_change', 'all'] = 'all',
        store: str = None
    ) -> str:
        """
        Search for security-related events across all stores.

        Args:
            timerange: How far back to search (e.g., "1h", "24h", "7d")
            event_type: Type of security event to search for
            store: Optional store name to filter results

        Returns:
            Security events with store, timestamp, and event details
        """
        client = LokiClient()

        # Define regex patterns for each event type
        event_patterns = {
            'login': r'(?i)(logged\s*in|login\s*success|authentication\s*success|user.*connected)',
            'logout': r'(?i)(logged\s*out|logout|session\s*end|disconnected)',
            'failed_auth': r'(?i)(login\s*fail|authentication\s*fail|invalid\s*(password|credential)|access\s*denied)',
            'config_change': r'(?i)(config.*change|setting.*update|parameter.*modif)',
        }

        # Build query
        if event_type == 'all':
            pattern = '|'.join(event_patterns.values())
        else:
            pattern = event_patterns.get(event_type, event_patterns['login'])

        if store:
            query = f'{{pos_name="{store}"}} |~ "{pattern}"'
        else:
            query = f'{{source="syslog"}} |~ "{pattern}"'

        results = await client.query_range(query, timerange=timerange, limit=200)

        if not results:
            return f"No security events found in the last {timerange}"

        entries = format_log_entries(results)

        if not entries:
            return f"No security events found in the last {timerange}"

        lines = [f"Security Events (last {timerange})", "=" * 60, ""]

        # Group by store
        by_store = {}
        for entry in entries:
            store_name = entry['labels'].get('pos_name', 'Unknown')
            if store_name not in by_store:
                by_store[store_name] = []
            by_store[store_name].append(entry)

        for store_name in sorted(by_store.keys()):
            store_entries = by_store[store_name]
            lines.append(f"\n{store_name}:")
            for entry in store_entries[:20]:  # Limit per store
                ts = entry['timestamp']
                line = entry['line']
                # Extract key info from line
                if len(line) > 150:
                    line = line[:150] + "..."
                lines.append(f"  [{ts}] {line}")
            if len(store_entries) > 20:
                lines.append(f"  ... and {len(store_entries) - 20} more")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Found {len(entries)} security events across {len(by_store)} stores")

        return "\n".join(lines)

    @mcp.tool()
    async def search_logs(
        search_text: str,
        timerange: str = "1h",
        store: str = None,
        limit: int = 100
    ) -> str:
        """
        Search all logs for specific text across the fleet.

        Args:
            search_text: Text to search for in log lines (case insensitive)
            timerange: How far back to search (e.g., "1h", "24h", "7d")
            store: Optional store name to filter results
            limit: Maximum number of results to return

        Returns:
            Matching log entries with store and timestamp
        """
        client = LokiClient()

        # Build query
        if store:
            query = f'{{pos_name="{store}"}} |~ "(?i){re.escape(search_text)}"'
        else:
            query = f'{{source="syslog"}} |~ "(?i){re.escape(search_text)}"'

        results = await client.query_range(query, timerange=timerange, limit=limit)

        if not results:
            return f"No logs matching '{search_text}' found in the last {timerange}"

        entries = format_log_entries(results)

        if not entries:
            return f"No logs matching '{search_text}' found in the last {timerange}"

        lines = [f"Search results for '{search_text}' (last {timerange})", "=" * 60, ""]

        for entry in entries[:limit]:
            ts = entry['timestamp']
            store_name = entry['labels'].get('pos_name', 'Unknown')
            line = entry['line']
            if len(line) > 150:
                line = line[:150] + "..."
            lines.append(f"[{ts}] {store_name}: {line}")

        if len(entries) >= limit:
            lines.append(f"\n... (limited to {limit} entries)")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Found {len(entries)} matching entries")

        return "\n".join(lines)

    @mcp.tool()
    async def get_log_summary(
        store: str = None,
        timerange: str = "1h"
    ) -> str:
        """
        Get a summary of log activity for a store or the entire fleet.

        Args:
            store: Optional store name (if not provided, shows fleet summary)
            timerange: Time period to summarize (e.g., "1h", "24h")

        Returns:
            Summary of log volume and top event types
        """
        client = LokiClient()

        # Get log count by store
        if store:
            query = f'count_over_time({{pos_name="{store}"}}[{timerange}])'
        else:
            query = f'sum by (pos_name) (count_over_time({{source="syslog"}}[{timerange}]))'

        results = await client.instant_query(query)

        if not results:
            return f"No log data available for the last {timerange}"

        lines = [f"Log Activity Summary (last {timerange})", "=" * 60, ""]

        # Sort by log count
        store_counts = []
        for r in results:
            labels = r.get('metric', {})
            store_name = labels.get('pos_name', 'Unknown')
            count = int(float(r.get('value', [0, 0])[1]))
            store_counts.append((store_name, count))

        store_counts.sort(key=lambda x: x[1], reverse=True)

        total_logs = sum(c for _, c in store_counts)

        if store:
            lines.append(f"Store: {store}")
            lines.append(f"Total log entries: {total_logs}")
        else:
            lines.append("Top stores by log volume:")
            for store_name, count in store_counts[:15]:
                pct = (count / total_logs * 100) if total_logs > 0 else 0
                bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                lines.append(f"  {store_name}: {count:,} ({pct:.1f}%) {bar}")

            if len(store_counts) > 15:
                lines.append(f"  ... and {len(store_counts) - 15} more stores")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Total: {total_logs:,} log entries from {len(store_counts)} stores")

        return "\n".join(lines)

    logger.info("Registered log tools")
