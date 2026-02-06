"""
Prometheus HTTP API Client
Executes PromQL queries against Prometheus.
"""

import httpx
import logging
from datetime import datetime, timedelta
from typing import Any
from config import PROMETHEUS_URL

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for Prometheus HTTP API."""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or PROMETHEUS_URL
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

    async def instant_query(self, query: str) -> list[dict]:
        """
        Execute an instant PromQL query.
        Returns list of results with metric labels and value.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/query",
                    params={"query": query}
                )
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'success':
                    logger.error(f"Prometheus query failed: {data.get('error', 'Unknown error')}")
                    return []

                return data.get('data', {}).get('result', [])

            except httpx.HTTPError as e:
                logger.error(f"Prometheus HTTP error: {e}")
                return []
            except Exception as e:
                logger.error(f"Prometheus query error: {e}")
                return []

    async def range_query(
        self,
        query: str,
        timerange: str = "1h",
        step: str = "1m"
    ) -> list[dict]:
        """
        Execute a range PromQL query.
        Returns list of results with metric labels and time series values.
        """
        start, end = self._parse_timerange(timerange)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start.isoformat() + "Z",
                        "end": end.isoformat() + "Z",
                        "step": step
                    }
                )
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'success':
                    logger.error(f"Prometheus range query failed: {data.get('error', 'Unknown error')}")
                    return []

                return data.get('data', {}).get('result', [])

            except httpx.HTTPError as e:
                logger.error(f"Prometheus HTTP error: {e}")
                return []
            except Exception as e:
                logger.error(f"Prometheus range query error: {e}")
                return []

    async def get_metric_labels(self, metric_name: str) -> list[str]:
        """Get all label names for a metric."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/v1/labels",
                    params={"match[]": metric_name}
                )
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
            except Exception as e:
                logger.error(f"Failed to get metric labels: {e}")
                return []

    async def get_label_values(self, label_name: str, metric_match: str = None) -> list[str]:
        """Get all values for a label, optionally filtered by metric."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                params = {}
                if metric_match:
                    params["match[]"] = metric_match
                response = await client.get(
                    f"{self.base_url}/api/v1/label/{label_name}/values",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                return data.get('data', [])
            except Exception as e:
                logger.error(f"Failed to get label values: {e}")
                return []


# Utility functions for common queries

def build_label_selector(**labels) -> str:
    """Build a Prometheus label selector from keyword arguments."""
    parts = []
    for key, value in labels.items():
        if value is not None:
            # Escape quotes in value
            escaped_value = str(value).replace('"', '\\"')
            parts.append(f'{key}="{escaped_value}"')
    return '{' + ','.join(parts) + '}' if parts else ''


def format_metric_result(result: dict) -> dict:
    """Format a single metric result for display."""
    metric = result.get('metric', {})
    value = result.get('value', [0, 0])

    return {
        'labels': {k: v for k, v in metric.items() if not k.startswith('__')},
        'value': float(value[1]) if len(value) > 1 else 0,
        'timestamp': value[0] if len(value) > 0 else 0
    }


def format_range_result(result: dict) -> dict:
    """Format a range query result for display."""
    metric = result.get('metric', {})
    values = result.get('values', [])

    return {
        'labels': {k: v for k, v in metric.items() if not k.startswith('__')},
        'values': [
            {'timestamp': v[0], 'value': float(v[1])}
            for v in values
        ]
    }
