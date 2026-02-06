"""
Store Data Tools
MCP tools for querying store/commander information from the database.
"""

import logging
from typing import Literal
from config import get_commanders, find_commander
from clients.prometheus import PrometheusClient

logger = logging.getLogger(__name__)


def register_store_tools(mcp):
    """Register all store data tools with the MCP server."""

    @mcp.tool()
    async def list_stores(
        group: str = None,
        brand: str = None,
        enabled_only: bool = True
    ) -> str:
        """
        List all configured stores in the PosProctor system.

        Args:
            group: Filter by geographic group (e.g., "Region A", "Region B", "Region C")
            brand: Filter by brand (e.g., "BrandA", "BrandB")
            enabled_only: Only show enabled stores (default True)

        Returns:
            Table of stores with IP, group, brand, and enabled status
        """
        commanders = get_commanders(group=group, brand=brand, enabled_only=enabled_only)

        if not commanders:
            filters = []
            if group:
                filters.append(f"group={group}")
            if brand:
                filters.append(f"brand={brand}")
            filter_str = f" ({', '.join(filters)})" if filters else ""
            return f"No stores found{filter_str}"

        lines = ["Store List", "=" * 70, ""]
        lines.append(f"{'Store Name':<25} {'IP Address':<16} {'Group':<12} {'Brand':<15}")
        lines.append("-" * 70)

        # Group by geographic group
        by_group = {}
        for cmd in commanders:
            g = cmd.get('group_name', 'Unknown')
            if g not in by_group:
                by_group[g] = []
            by_group[g].append(cmd)

        for group_name in sorted(by_group.keys()):
            group_stores = by_group[group_name]
            for cmd in sorted(group_stores, key=lambda x: x.get('store_name', '')):
                store_name = cmd.get('store_name', 'Unknown')[:24]
                ip = cmd.get('ip', 'Unknown')
                grp = cmd.get('group_name', 'Unknown')[:11]
                brand_name = cmd.get('brand', 'Unknown')[:14]
                lines.append(f"{store_name:<25} {ip:<16} {grp:<12} {brand_name:<15}")

        lines.append("")
        lines.append("=" * 70)
        lines.append(f"Total: {len(commanders)} stores")

        # Show group breakdown
        if len(by_group) > 1:
            lines.append("\nBy Group:")
            for g in sorted(by_group.keys()):
                lines.append(f"  {g}: {len(by_group[g])} stores")

        return "\n".join(lines)

    @mcp.tool()
    async def get_store_details(
        store: str
    ) -> str:
        """
        Get detailed information about a specific store including current equipment status.

        Args:
            store: Store name or IP address to look up

        Returns:
            Store details including configuration and current equipment status
        """
        commander = find_commander(store)

        if not commander:
            return f"Store not found: {store}"

        store_name = commander.get('store_name', 'Unknown')
        ip = commander.get('ip', 'Unknown')
        group = commander.get('group_name', 'Unknown')
        brand = commander.get('brand', 'Unknown')
        enabled = commander.get('enabled', 0)

        lines = [
            f"Store Details: {store_name}",
            "=" * 60,
            "",
            f"IP Address: {ip}",
            f"Group: {group}",
            f"Brand: {brand}",
            f"Enabled: {'Yes' if enabled else 'No'}",
            "",
        ]

        # Get current equipment status from Prometheus
        client = PrometheusClient()

        # Scrape status
        scrape_results = await client.instant_query(f'posproctor_scrape_success{{store="{store_name}"}}')
        if scrape_results:
            scrape_ok = float(scrape_results[0].get('value', [0, 0])[1]) == 1
            lines.append(f"Monitoring Status: {'✓ Online' if scrape_ok else '✗ Offline'}")
        else:
            lines.append("Monitoring Status: Unknown")

        # Pump status
        pump_results = await client.instant_query(f'posproctor_pump_status{{store="{store_name}"}}')
        if pump_results:
            total_pumps = len(pump_results)
            online_pumps = sum(1 for r in pump_results if float(r.get('value', [0, 0])[1]) == 1)
            lines.append(f"Pumps: {online_pumps}/{total_pumps} online")
        else:
            lines.append("Pumps: No data")

        # DCR status
        dcr_results = await client.instant_query(f'posproctor_dcr_status{{store="{store_name}"}}')
        if dcr_results:
            total_dcrs = len(dcr_results)
            online_dcrs = sum(1 for r in dcr_results if float(r.get('value', [0, 0])[1]) == 1)
            lines.append(f"DCRs: {online_dcrs}/{total_dcrs} online")

        # Price displays
        display_results = await client.instant_query(f'posproctor_price_display_status{{store="{store_name}"}}')
        if display_results:
            total_displays = len(display_results)
            online_displays = sum(1 for r in display_results if float(r.get('value', [0, 0])[1]) == 1)
            lines.append(f"Price Displays: {online_displays}/{total_displays} online")

        # Pinpads
        pinpad_results = await client.instant_query(f'posproctor_pinpad_status{{store="{store_name}"}}')
        if pinpad_results:
            total_pinpads = len(pinpad_results)
            online_pinpads = sum(1 for r in pinpad_results if float(r.get('value', [0, 0])[1]) == 1)
            lines.append(f"Pinpads: {online_pinpads}/{total_pinpads} online")

        # TLS status
        tls_results = await client.instant_query(f'posproctor_tank_monitor_status{{store="{store_name}"}}')
        if tls_results:
            tls_status = float(tls_results[0].get('value', [0, 0])[1])
            if tls_status == 1:
                lines.append("Tank Level Sensor: ✓ Online")
            elif tls_status == 0:
                lines.append("Tank Level Sensor: ✗ Offline")
            else:
                lines.append("Tank Level Sensor: No TLS")

        lines.append("")
        lines.append("=" * 60)
        lines.append(f"Commander UI: https://{ip}/ConfigClient.html")

        return "\n".join(lines)

    @mcp.tool()
    async def get_groups() -> str:
        """
        List all geographic groups and their store counts.

        Returns:
            List of groups with store counts
        """
        commanders = get_commanders(enabled_only=True)

        if not commanders:
            return "No stores configured"

        # Count by group
        by_group = {}
        for cmd in commanders:
            group = cmd.get('group_name', 'Unknown')
            if group not in by_group:
                by_group[group] = 0
            by_group[group] += 1

        lines = ["Geographic Groups", "=" * 40, ""]

        for group in sorted(by_group.keys()):
            count = by_group[group]
            bar = "█" * min(count, 20)
            lines.append(f"{group:<15} {count:>3} stores {bar}")

        lines.append("")
        lines.append("=" * 40)
        lines.append(f"Total: {len(commanders)} stores in {len(by_group)} groups")

        return "\n".join(lines)

    @mcp.tool()
    async def get_brands() -> str:
        """
        List all brands and their store counts.

        Returns:
            List of brands with store counts
        """
        commanders = get_commanders(enabled_only=True)

        if not commanders:
            return "No stores configured"

        # Count by brand
        by_brand = {}
        for cmd in commanders:
            brand = cmd.get('brand', 'Unknown')
            if brand not in by_brand:
                by_brand[brand] = 0
            by_brand[brand] += 1

        lines = ["Store Brands", "=" * 40, ""]

        for brand in sorted(by_brand.keys(), key=lambda x: by_brand[x], reverse=True):
            count = by_brand[brand]
            bar = "█" * min(count, 20)
            lines.append(f"{brand:<20} {count:>3} stores {bar}")

        lines.append("")
        lines.append("=" * 40)
        lines.append(f"Total: {len(commanders)} stores across {len(by_brand)} brands")

        return "\n".join(lines)

    @mcp.tool()
    async def search_stores(
        query: str
    ) -> str:
        """
        Search for stores by name, IP, group, or brand.

        Args:
            query: Search term to match against store attributes

        Returns:
            Matching stores with their details
        """
        commanders = get_commanders(enabled_only=False)

        if not commanders:
            return "No stores configured"

        query_lower = query.lower()
        matches = []

        for cmd in commanders:
            store_name = cmd.get('store_name', '').lower()
            ip = cmd.get('ip', '').lower()
            group = cmd.get('group_name', '').lower()
            brand = cmd.get('brand', '').lower()

            if (query_lower in store_name or
                query_lower in ip or
                query_lower in group or
                query_lower in brand):
                matches.append(cmd)

        if not matches:
            return f"No stores matching '{query}'"

        lines = [f"Search Results for '{query}'", "=" * 60, ""]

        for cmd in matches:
            store_name = cmd.get('store_name', 'Unknown')
            ip = cmd.get('ip', 'Unknown')
            group = cmd.get('group_name', 'Unknown')
            brand = cmd.get('brand', 'Unknown')
            enabled = cmd.get('enabled', 0)
            status = "✓" if enabled else "✗"

            lines.append(f"{status} {store_name}")
            lines.append(f"    IP: {ip} | Group: {group} | Brand: {brand}")
            lines.append("")

        lines.append("=" * 60)
        lines.append(f"Found {len(matches)} matching stores")

        return "\n".join(lines)

    logger.info("Registered store tools")
