"""
Prometheus Metrics Tools
MCP tools for querying equipment status and uptime from Prometheus.
"""

import logging
from typing import Literal
from clients.prometheus import PrometheusClient, build_label_selector

logger = logging.getLogger(__name__)

# Equipment type to metric name mapping
EQUIPMENT_METRICS = {
    'pump': 'posproctor_pump_status',
    'dcr': 'posproctor_dcr_status',
    'price_display': 'posproctor_price_display_status',
    'pinpad': 'posproctor_pinpad_status',
    'fep': 'posproctor_primary_fep_status',
    'pos': 'posproctor_pos_terminal_status',
}


def register_metrics_tools(mcp):
    """Register all Prometheus metrics tools with the MCP server."""

    @mcp.tool()
    async def get_pump_status(
        store: str = None,
        group: str = None
    ) -> str:
        """
        Get current pump status across the fleet or for a specific store.

        Args:
            store: Optional store name filter (e.g., "Store 503", "Main Street")
            group: Optional geographic group filter (e.g., "Region A", "Region B", "Region C")

        Returns:
            Table of pumps with their current status (online/offline)
        """
        client = PrometheusClient()

        # Build query
        labels = {}
        if store:
            labels['store'] = f'.*{store}.*'
            query = f'posproctor_pump_status{{store=~".*{store}.*"}}'
        elif group:
            query = f'posproctor_pump_status{{group="{group}"}}'
        else:
            query = 'posproctor_pump_status'

        results = await client.instant_query(query)

        if not results:
            return "No pump data found for the specified criteria."

        # Format results
        lines = ["Pump Status Report", "=" * 60]

        # Group by store
        stores = {}
        for r in results:
            metric = r.get('metric', {})
            store_name = metric.get('store', 'Unknown')
            pump_id = metric.get('fueling_point_id', '?')
            value = float(r.get('value', [0, 0])[1])
            status = 'Online' if value == 1 else 'Offline'

            if store_name not in stores:
                stores[store_name] = []
            stores[store_name].append((pump_id, status))

        # Output
        total_online = 0
        total_offline = 0
        for store_name in sorted(stores.keys()):
            pumps = stores[store_name]
            online = sum(1 for _, s in pumps if s == 'Online')
            offline = len(pumps) - online
            total_online += online
            total_offline += offline

            lines.append(f"\n{store_name}:")
            for pump_id, status in sorted(pumps, key=lambda x: int(x[0]) if x[0].isdigit() else 999):
                marker = "✓" if status == "Online" else "✗"
                lines.append(f"  Pump {pump_id}: {marker} {status}")

        total = total_online + total_offline
        uptime_pct = (total_online / total * 100) if total > 0 else 0
        lines.append(f"\n{'=' * 60}")
        lines.append(f"Summary: {total_online} online, {total_offline} offline ({uptime_pct:.1f}% uptime)")

        return "\n".join(lines)

    @mcp.tool()
    async def get_equipment_uptime(
        equipment_type: Literal['pump', 'dcr', 'price_display', 'pinpad', 'fep', 'pos'],
        group: str = None,
        timerange: str = "24h"
    ) -> str:
        """
        Calculate equipment uptime percentage over a time period.

        Args:
            equipment_type: Type of equipment (pump, dcr, price_display, pinpad, fep, pos)
            group: Optional geographic group filter (e.g., "Region A", "Region B")
            timerange: Time range for uptime calculation (e.g., "1h", "24h", "7d")

        Returns:
            Uptime percentages by store and overall fleet average
        """
        client = PrometheusClient()

        metric_name = EQUIPMENT_METRICS.get(equipment_type)
        if not metric_name:
            return f"Unknown equipment type: {equipment_type}"

        # Build query for average over time
        if group:
            query = f'avg_over_time({metric_name}{{group="{group}"}}[{timerange}]) * 100'
        else:
            query = f'avg_over_time({metric_name}[{timerange}]) * 100'

        results = await client.instant_query(query)

        if not results:
            return f"No {equipment_type} uptime data found."

        lines = [f"{equipment_type.title()} Uptime Report (last {timerange})", "=" * 60]

        # Group by store
        stores = {}
        for r in results:
            metric = r.get('metric', {})
            store_name = metric.get('store', 'Unknown')
            uptime = float(r.get('value', [0, 0])[1])

            if store_name not in stores:
                stores[store_name] = []
            stores[store_name].append(uptime)

        # Calculate store averages
        store_averages = []
        for store_name in sorted(stores.keys()):
            uptimes = stores[store_name]
            avg_uptime = sum(uptimes) / len(uptimes)
            store_averages.append((store_name, avg_uptime))
            status = "✓" if avg_uptime >= 99 else "⚠" if avg_uptime >= 90 else "✗"
            lines.append(f"{status} {store_name}: {avg_uptime:.1f}%")

        # Fleet average
        if store_averages:
            fleet_avg = sum(u for _, u in store_averages) / len(store_averages)
            lines.append(f"\n{'=' * 60}")
            lines.append(f"Fleet Average: {fleet_avg:.1f}%")

        return "\n".join(lines)

    @mcp.tool()
    async def get_offline_equipment(
        equipment_type: Literal['pump', 'dcr', 'price_display', 'pinpad', 'fep', 'pos', 'all'] = 'all',
        group: str = None
    ) -> str:
        """
        List all currently offline equipment across the fleet.

        Args:
            equipment_type: Type of equipment to check, or 'all' for everything
            group: Optional geographic group filter

        Returns:
            List of offline equipment with store and device details
        """
        client = PrometheusClient()

        types_to_check = list(EQUIPMENT_METRICS.keys()) if equipment_type == 'all' else [equipment_type]

        all_offline = []
        for eq_type in types_to_check:
            metric_name = EQUIPMENT_METRICS.get(eq_type)
            if not metric_name:
                continue

            if group:
                query = f'{metric_name}{{group="{group}"}} == 0'
            else:
                query = f'{metric_name} == 0'

            results = await client.instant_query(query)

            for r in results:
                metric = r.get('metric', {})
                store_name = metric.get('store', 'Unknown')
                device_id = metric.get('fueling_point_id') or metric.get('pinpad_id') or metric.get('display_id') or metric.get('terminal_id') or 'N/A'

                all_offline.append({
                    'type': eq_type,
                    'store': store_name,
                    'id': device_id
                })

        if not all_offline:
            return "✓ No offline equipment found - all systems operational!"

        lines = ["Offline Equipment Report", "=" * 60]

        # Group by store
        by_store = {}
        for item in all_offline:
            store = item['store']
            if store not in by_store:
                by_store[store] = []
            by_store[store].append(item)

        for store_name in sorted(by_store.keys()):
            items = by_store[store_name]
            lines.append(f"\n{store_name}:")
            for item in items:
                lines.append(f"  ✗ {item['type'].title()} {item['id']} - OFFLINE")

        lines.append(f"\n{'=' * 60}")
        lines.append(f"Total offline: {len(all_offline)} devices")

        return "\n".join(lines)

    @mcp.tool()
    async def get_scrape_failures() -> str:
        """
        Get stores with failed monitoring scrapes (unreachable commanders).

        Returns:
            List of stores that failed recent monitoring scrapes
        """
        client = PrometheusClient()

        # Query for failed scrapes
        results = await client.instant_query('posproctor_scrape_success == 0')

        if not results:
            return "✓ All stores are responding to monitoring - no scrape failures!"

        lines = ["Scrape Failure Report", "=" * 60, ""]

        for r in results:
            metric = r.get('metric', {})
            store_name = metric.get('store', 'Unknown')
            ip = metric.get('ip', 'Unknown')
            group = metric.get('group', 'Unknown')

            lines.append(f"✗ {store_name}")
            lines.append(f"  IP: {ip}")
            lines.append(f"  Group: {group}")
            lines.append("")

        lines.append("=" * 60)
        lines.append(f"Total unreachable: {len(results)} stores")

        return "\n".join(lines)

    @mcp.tool()
    async def get_fleet_tank_status() -> str:
        """
        Get tank level sensor (TLS) status across all stores.

        Returns:
            Table of stores with their TLS connection status
        """
        client = PrometheusClient()

        results = await client.instant_query('posproctor_tank_monitor_status')

        if not results:
            return "No tank monitoring data available."

        lines = ["Tank Level Sensor (TLS) Status", "=" * 60, ""]

        online = []
        offline = []
        no_tls = []

        for r in results:
            metric = r.get('metric', {})
            store_name = metric.get('store', 'Unknown')
            value = float(r.get('value', [0, 0])[1])

            if value == 1:
                online.append(store_name)
            elif value == 0:
                offline.append(store_name)
            else:
                no_tls.append(store_name)

        if online:
            lines.append(f"✓ Online ({len(online)}):")
            for store in sorted(online):
                lines.append(f"  {store}")
            lines.append("")

        if offline:
            lines.append(f"✗ Offline ({len(offline)}):")
            for store in sorted(offline):
                lines.append(f"  {store}")
            lines.append("")

        if no_tls:
            lines.append(f"- No TLS ({len(no_tls)}):")
            for store in sorted(no_tls):
                lines.append(f"  {store}")
            lines.append("")

        lines.append("=" * 60)
        total = len(online) + len(offline) + len(no_tls)
        lines.append(f"Summary: {len(online)}/{total} TLS online")

        return "\n".join(lines)

    logger.info("Registered metrics tools")
