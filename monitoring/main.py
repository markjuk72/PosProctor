"""
POSProctor 2.0 - Monitoring Service
Polls Verifone Commander APIs and exports Prometheus metrics
"""

import time
import logging
import json
import os
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer
from prometheus_client import Gauge, Counter, Histogram, Info, MetricsHandler
from verifone_api import VerifoneAPIClient
from database import DatabaseManager
from credential_service import get_credential_service, get_commander_credentials

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
DB_PATH = os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '300'))  # seconds
DEV_MODE = os.getenv('DEV_MODE', 'false').lower() == 'true'
DEV_STORE_FILTER = os.getenv('DEV_STORE_FILTER', '')

# Track application state
_app_start_time = time.time()
_last_scrape_success = {'timestamp': None, 'success_count': 0, 'total_count': 0}
_config_reload_count = 0

# Track known pump/DCR/display IDs per store to detect and remove stale metrics
# Structure: { 'store_name': { 'pumps': set(), 'dcrs': set(), 'displays': set() } }
_known_device_ids = {}


class HealthMetricsHandler(MetricsHandler):
    """Custom handler that serves both /health and /metrics endpoints."""

    def do_GET(self):
        if self.path == '/health' or self.path == '/health/':
            self._serve_health()
        else:
            super().do_GET()

    def _serve_health(self):
        """Serve health check endpoint."""
        uptime = time.time() - _app_start_time
        health_data = {
            'status': 'healthy',
            'uptime_seconds': round(uptime, 2),
            'version': '2.0',
            'poll_interval_seconds': POLL_INTERVAL,
            'last_scrape': _last_scrape_success
        }
        self._send_json_response(200, health_data)

    def _send_json_response(self, status_code, data):
        """Send a JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))


class ConfigFileWatcher:
    """
    Watches the SQLite database file for changes and triggers config reload.

    This allows the web UI to modify commander data and have the monitoring service
    pick up the changes automatically without requiring a restart.
    """

    def __init__(self, db_manager: DatabaseManager, check_interval: int = 10):
        self.db_manager = db_manager
        self.db_path = Path(DB_PATH)
        self.check_interval = check_interval
        self._last_mtime = None
        self._running = False
        self._thread = None

    def start(self):
        """Start the file watcher in a background thread."""
        if self._running:
            return

        self._running = True
        self._last_mtime = self._get_mtime()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True, name="ConfigWatcher")
        self._thread.start()
        logger.info(f"Config file watcher started (checking every {self.check_interval}s, initial mtime: {self._last_mtime})")

    def stop(self):
        """Stop the file watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _get_mtime(self) -> float:
        """Get the modification time of the database file."""
        try:
            if self.db_path.exists():
                return self.db_path.stat().st_mtime
        except OSError as e:
            logger.warning(f"Could not stat database file: {e}")
        return 0

    def _watch_loop(self):
        """Background loop that checks for file changes."""
        global _config_reload_count

        logger.info(f"Config watcher thread running, watching {self.db_path}")
        check_count = 0

        try:
            while self._running:
                try:
                    time.sleep(self.check_interval)
                    check_count += 1

                    # Get current modification time
                    current_mtime = self._get_mtime()

                    # Log every 30 checks (5 minutes at 10s interval) to confirm thread is alive
                    if check_count % 30 == 0:
                        logger.debug(f"Config watcher alive (check #{check_count})")

                    if current_mtime > self._last_mtime:
                        logger.info(f"Database file changed (mtime: {self._last_mtime:.2f} -> {current_mtime:.2f}), reloading configuration...")
                        self._last_mtime = current_mtime

                        # Reload commander list from database
                        # The database manager will fetch fresh data on next call
                        _config_reload_count += 1

                        # Get updated commander count
                        commanders = self.db_manager.get_enabled_commanders()
                        commander_count = len(commanders)
                        logger.info(f"Configuration reloaded successfully ({commander_count} commanders, reload #{_config_reload_count})")

                except Exception as e:
                    logger.error(f"Error in config watcher iteration: {e}")

        except Exception as e:
            logger.error(f"Config watcher thread crashed: {e}")

        logger.warning("Config watcher thread exiting")


# Prometheus Metrics
controller_status = Gauge(
    'posproctor_controller_status',
    'Status of the forecourt controller (1=online, 0=offline)',
    ['store', 'ip', 'group', 'brand']
)
pump_status = Gauge(
    'posproctor_pump_status',
    'Status of individual pumps (1=online, 0=offline)',
    ['store', 'ip', 'fueling_point_id', 'group', 'brand']
)
dcr_status = Gauge(
    'posproctor_dcr_status',
    'Status of individual DCRs (1=online, 0=offline)',
    ['store', 'ip', 'fueling_point_id', 'group', 'brand']
)
price_display_status = Gauge(
    'posproctor_price_display_status',
    'Status of fuel price displays (1=online, 0=offline)',
    ['store', 'ip', 'display_id', 'group', 'brand']
)
primary_fep_status = Gauge(
    'posproctor_primary_fep_status',
    'Status of the primary card processor FEP (1=online, 0=offline)',
    ['store', 'ip', 'group', 'brand', 'fep_name']
)
loyalty_fep_status = Gauge(
    'posproctor_loyalty_fep_status',
    'Status of the loyalty FEP (1=online, 0=offline)',
    ['store', 'ip', 'group', 'brand', 'loyalty_name']
)
pos_terminal_status = Gauge(
    'posproctor_pos_terminal_status',
    'Status of POS terminals (1=online, 0=offline)',
    ['store', 'ip', 'group', 'brand', 'terminal_id', 'terminal_type']
)
pinpad_status = Gauge(
    'posproctor_pinpad_status',
    'Status of pinpads (1=online, 0=offline)',
    ['store', 'ip', 'group', 'brand', 'pinpad_id', 'workstation']
)
scrape_success = Gauge(
    'posproctor_scrape_success',
    'Indicates if the scrape for a commander was successful (1=success, 0=failed)',
    ['store', 'ip', 'group', 'brand']
)
query_duration = Histogram(
    'posproctor_query_duration_seconds',
    'Time spent querying commander APIs',
    ['store', 'ip', 'endpoint']
)
scrape_cycle_duration = Histogram(
    'posproctor_scrape_cycle_duration_seconds',
    'Total time to complete a scrape cycle'
)
total_commanders = Gauge(
    'posproctor_total_commanders',
    'Total number of commanders being monitored'
)
consecutive_failures = Gauge(
    'posproctor_consecutive_failures',
    'Number of consecutive failed scrapes for a commander',
    ['store', 'ip', 'group', 'brand']
)
last_successful_connection = Gauge(
    'posproctor_last_successful_connection_timestamp',
    'Unix timestamp of last successful connection to commander',
    ['store', 'ip', 'group', 'brand']
)
commander_error_state = Info(
    'posproctor_commander_error_state',
    'Current error state and details for a commander',
    ['store', 'ip', 'group', 'brand']
)

# Tank Level Metrics
tank_volume = Gauge(
    'posproctor_tank_volume_gallons',
    'Current fuel volume in tank (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_level = Gauge(
    'posproctor_tank_level_inches',
    'Current fuel level in tank (inches)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_temperature = Gauge(
    'posproctor_tank_temperature_fahrenheit',
    'Current fuel temperature in tank (Fahrenheit)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_water_level = Gauge(
    'posproctor_tank_water_inches',
    'Current water level in tank (inches)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_ullage = Gauge(
    'posproctor_tank_ullage_gallons',
    'Available space in tank (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_capacity = Gauge(
    'posproctor_tank_capacity_gallons',
    'Total tank capacity (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_fill_percentage = Gauge(
    'posproctor_tank_fill_percent',
    'Tank fill percentage (0-100)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)

# Tank Alarm Metrics
tank_alarm_leak = Gauge(
    'posproctor_tank_alarm_leak',
    'Tank leak alarm status (1=active, 0=inactive)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_alarm_high_water = Gauge(
    'posproctor_tank_alarm_high_water',
    'Tank high water alarm status (1=active, 0=inactive)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_alarm_overfill = Gauge(
    'posproctor_tank_alarm_overfill',
    'Tank overfill alarm status (1=active, 0=inactive)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_alarm_low_limit = Gauge(
    'posproctor_tank_alarm_low_limit',
    'Tank low limit alarm status (1=active, 0=inactive)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_alarm_theft = Gauge(
    'posproctor_tank_alarm_theft',
    'Tank theft alarm status (1=active, 0=inactive)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_alarm_active = Gauge(
    'posproctor_tank_alarm_active',
    'Any tank alarm currently active (1=yes, 0=no)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_monitor_status = Gauge(
    'posproctor_tank_monitor_status',
    'Tank Level Sensor (TLS) connectivity status (1=online, 0=offline/error)',
    ['store', 'ip', 'group', 'brand']
)

# Tank Reconciliation/Variance Metrics (for inventory discrepancy detection)
tank_begin_inventory = Gauge(
    'posproctor_tank_begin_inventory_gallons',
    'Beginning inventory volume for reconciliation period (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_end_inventory = Gauge(
    'posproctor_tank_end_inventory_gallons',
    'Ending inventory volume for reconciliation period (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_dispensed = Gauge(
    'posproctor_tank_dispensed_gallons',
    'Volume dispensed during reconciliation period (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_variance = Gauge(
    'posproctor_tank_variance_gallons',
    'Inventory variance (end - begin + dispensed, negative = loss)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_variance_percent = Gauge(
    'posproctor_tank_variance_percent',
    'Inventory variance as percentage of beginning inventory',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)

# Tank Delivery Metrics
tank_delivery_volume = Gauge(
    'posproctor_tank_delivery_volume_gallons',
    'Most recent delivery volume (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_total_deliveries = Gauge(
    'posproctor_tank_total_deliveries_gallons',
    'Total delivery volume in current period (gallons)',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)
tank_delivery_count = Gauge(
    'posproctor_tank_delivery_count',
    'Number of deliveries in current period',
    ['store', 'ip', 'group', 'brand', 'tank_id', 'product']
)

# Global tracking dictionary for error states (thread-safe)
from threading import Lock
_error_states = {}
_error_states_lock = Lock()


def _update_error_state(store, ip, group, brand, error_type=None, error_message=None, is_success=False):
    """Update error state tracking for a commander."""
    key = f"{store}_{ip}"

    with _error_states_lock:
        if is_success:
            # Reset error state on success
            if key in _error_states:
                _error_states[key] = {'failures': 0, 'last_success': time.time()}
            else:
                _error_states[key] = {'failures': 0, 'last_success': time.time()}

            # Update metrics
            consecutive_failures.labels(store=store, ip=ip, group=group, brand=brand).set(0)
            last_successful_connection.labels(store=store, ip=ip, group=group, brand=brand).set(time.time())
            commander_error_state.labels(store=store, ip=ip, group=group, brand=brand).info({
                'error_type': 'none',
                'error_message': 'Connection successful',
                'last_success': str(int(time.time()))
            })
        else:
            # Increment failure count
            if key not in _error_states:
                _error_states[key] = {'failures': 1, 'last_success': 0}
            else:
                _error_states[key]['failures'] += 1

            # Update metrics
            consecutive_failures.labels(store=store, ip=ip, group=group, brand=brand).set(
                _error_states[key]['failures']
            )
            if _error_states[key]['last_success'] > 0:
                last_successful_connection.labels(store=store, ip=ip, group=group, brand=brand).set(
                    _error_states[key]['last_success']
                )
            commander_error_state.labels(store=store, ip=ip, group=group, brand=brand).info({
                'error_type': error_type or 'unknown',
                'error_message': error_message or 'Unknown error',
                'consecutive_failures': str(_error_states[key]['failures']),
                'last_success': str(int(_error_states[key].get('last_success', 0)))
            })


def fetch_commander_metrics(commander, username, password, timeout):
    """Fetch metrics for a single commander and update Prometheus gauges."""
    store = commander['store_name']
    ip = commander['ip']
    group = commander.get('group_name', 'Unknown')
    brand = commander.get('brand', 'Unknown')

    logger.info(f"Fetching metrics for commander: {store} ({ip}) - {brand}")

    try:
        client = VerifoneAPIClient(
            ip=ip,
            username=username,
            password=password,
            timeout=timeout,
            store_name=store
        )

        # Fetch forecourt diagnostics
        diagnostics_start = time.time()
        xml_data = client.get_forecourt_diagnostics()
        query_duration.labels(store=store, ip=ip, endpoint='diagnostics').observe(
            time.time() - diagnostics_start
        )

        if xml_data is not None:
            diagnostics = client.parse_diagnostics(xml_data)

            # Update controller status
            controller_status.labels(
                store=store, ip=ip, group=group, brand=brand
            ).set(diagnostics['controller_status'])

            # Track current device IDs for this store
            current_pump_ids = set()
            current_dcr_ids = set()
            current_display_ids = set()

            # Update pump statuses
            for pump in diagnostics['pumps']:
                pump_status.labels(
                    store=store, ip=ip, fueling_point_id=pump['id'],
                    group=group, brand=brand
                ).set(pump['status'])
                current_pump_ids.add(pump['id'])

            # Update DCR statuses
            for dcr in diagnostics['dcrs']:
                dcr_status.labels(
                    store=store, ip=ip, fueling_point_id=dcr['id'],
                    group=group, brand=brand
                ).set(dcr['status'])
                current_dcr_ids.add(dcr['id'])

            # Update price display statuses
            for display in diagnostics['price_displays']:
                price_display_status.labels(
                    store=store, ip=ip, display_id=display['id'],
                    group=group, brand=brand
                ).set(display['status'])
                current_display_ids.add(display['id'])

            # Clean up stale metrics for devices that no longer exist
            if store in _known_device_ids:
                old_state = _known_device_ids[store]

                # Remove stale pump metrics
                stale_pumps = old_state.get('pumps', set()) - current_pump_ids
                for pump_id in stale_pumps:
                    try:
                        pump_status.remove(store, ip, pump_id, group, brand)
                        logger.info(f"Removed stale pump metric: {store} pump {pump_id}")
                    except KeyError:
                        pass  # Already removed or never existed

                # Remove stale DCR metrics
                stale_dcrs = old_state.get('dcrs', set()) - current_dcr_ids
                for dcr_id in stale_dcrs:
                    try:
                        dcr_status.remove(store, ip, dcr_id, group, brand)
                        logger.info(f"Removed stale DCR metric: {store} DCR {dcr_id}")
                    except KeyError:
                        pass

                # Remove stale display metrics
                stale_displays = old_state.get('displays', set()) - current_display_ids
                for display_id in stale_displays:
                    try:
                        price_display_status.remove(store, ip, display_id, group, brand)
                        logger.info(f"Removed stale display metric: {store} display {display_id}")
                    except KeyError:
                        pass

            # Update known device IDs for this store
            _known_device_ids[store] = {
                'pumps': current_pump_ids,
                'dcrs': current_dcr_ids,
                'displays': current_display_ids
            }

        # Fetch payment diagnostics (primary FEP, loyalty FEP, and pinpads - single API call)
        payment_start = time.time()
        payment_xml = client.get_payment_diagnostics()
        query_duration.labels(store=store, ip=ip, endpoint='payment_diagnostics').observe(
            time.time() - payment_start
        )

        if payment_xml is not None:
            # Parse all payment data from single response
            payment_data = client.parse_payment_diagnostics(payment_xml)

            # Update primary FEP status
            if payment_data['primary_fep']:
                primary_fep_status.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    fep_name=payment_data['primary_fep']['fep_name']
                ).set(payment_data['primary_fep']['status'])

            # Update loyalty FEP status
            if payment_data['loyalty_fep']:
                loyalty_fep_status.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    loyalty_name=payment_data['loyalty_fep']['loyalty_name']
                ).set(payment_data['loyalty_fep']['status'])

            # Update pinpad statuses
            for pinpad in payment_data['pinpads']:
                pinpad_status.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    pinpad_id=pinpad['id'], workstation=pinpad['workstation']
                ).set(pinpad['status'])

        # Fetch POS diagnostics (POS terminals)
        pos_start = time.time()
        pos_xml = client.get_pos_diagnostics()
        query_duration.labels(store=store, ip=ip, endpoint='pos_diagnostics').observe(
            time.time() - pos_start
        )

        if pos_xml is not None:
            terminals = client.parse_pos_terminal_status(pos_xml)
            for terminal in terminals:
                pos_terminal_status.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    terminal_id=terminal['id'], terminal_type=terminal['type']
                ).set(terminal['status'])

        # Fetch tank monitor data
        tank_start = time.time()
        tank_xml = client.get_tank_monitor()
        query_duration.labels(store=store, ip=ip, endpoint='tank_monitor').observe(
            time.time() - tank_start
        )

        if tank_xml is not None:
            # Use improved TLS detection (matches webapp logic)
            has_tls, tls_tank_count = client.has_tls_data(tank_xml)

            # Parse tank levels
            tanks = client.parse_tank_monitor(tank_xml)

            if tanks or has_tls:
                # TLS is responding with data
                tank_monitor_status.labels(store=store, ip=ip, group=group, brand=brand).set(1)

                for tank in tanks:
                    tank_id = str(tank['id'])
                    product = tank['name']

                    # Update tank level metrics
                    tank_volume.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['volume'])

                    tank_level.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['level'])

                    tank_temperature.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['temperature'])

                    tank_water_level.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['water'])

                    tank_ullage.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['ullage'])

                    tank_capacity.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(tank['capacity'])

                    # Calculate fill percentage
                    fill_pct = (tank['volume'] / tank['capacity'] * 100) if tank['capacity'] > 0 else 0
                    tank_fill_percentage.labels(
                        store=store, ip=ip, group=group, brand=brand,
                        tank_id=tank_id, product=product
                    ).set(round(fill_pct, 1))

                logger.debug(f"[{ip}] Updated metrics for {len(tanks)} tanks")
            else:
                # TLS returned fault or no data (likely TLS COMMS ERROR)
                tank_monitor_status.labels(store=store, ip=ip, group=group, brand=brand).set(0)
                logger.warning(f"[{ip}] Tank monitor returned no data (TLS offline or error)")

            # Parse tank alarms (from same XML response)
            alarm_status, alarm_history = client.parse_tank_alarms(tank_xml)

            for alarm in alarm_status:
                tank_id = str(alarm['tank_id'])
                product = alarm['tank_name']

                tank_alarm_leak.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if alarm['leak'] else 0)

                tank_alarm_high_water.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if alarm['high_water'] else 0)

                tank_alarm_overfill.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if alarm['overfill'] else 0)

                tank_alarm_low_limit.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if alarm['low_limit'] else 0)

                tank_alarm_theft.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if alarm['theft'] else 0)

                # Any alarm active
                any_active = alarm['leak'] or alarm['high_water'] or alarm['overfill'] or alarm['low_limit'] or alarm['theft']
                tank_alarm_active.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(1 if any_active else 0)

            if alarm_status:
                logger.debug(f"[{ip}] Updated alarm status for {len(alarm_status)} tanks")

            # Parse reconciliation data (variance detection)
            reconciliation = client.parse_tank_reconciliation(tank_xml)
            for rec in reconciliation:
                tank_id = str(rec['tank_id'])
                product = rec['product']

                tank_begin_inventory.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(rec['begin_volume'])

                tank_end_inventory.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(rec['end_volume'])

                tank_dispensed.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(rec['dispensed'])

                tank_variance.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(rec['variance'])

                tank_variance_percent.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=product
                ).set(rec['variance_pct'])

            if reconciliation:
                logger.debug(f"[{ip}] Updated reconciliation for {len(reconciliation)} tanks")

            # Parse delivery data
            deliveries = client.parse_tank_deliveries(tank_xml)

            # Aggregate deliveries by tank
            delivery_by_tank = {}
            for delivery in deliveries:
                tank_id = str(delivery['tank_id'])
                if tank_id not in delivery_by_tank:
                    delivery_by_tank[tank_id] = {
                        'product': delivery['product'],
                        'total_volume': 0,
                        'count': 0,
                        'last_volume': 0
                    }
                delivery_by_tank[tank_id]['total_volume'] += delivery['delivery_volume']
                delivery_by_tank[tank_id]['count'] += 1
                delivery_by_tank[tank_id]['last_volume'] = delivery['delivery_volume']

            for tank_id, del_data in delivery_by_tank.items():
                tank_delivery_volume.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=del_data['product']
                ).set(del_data['last_volume'])

                tank_total_deliveries.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=del_data['product']
                ).set(del_data['total_volume'])

                tank_delivery_count.labels(
                    store=store, ip=ip, group=group, brand=brand,
                    tank_id=tank_id, product=del_data['product']
                ).set(del_data['count'])

            if delivery_by_tank:
                logger.debug(f"[{ip}] Updated delivery metrics for {len(delivery_by_tank)} tanks")

        else:
            # Could not fetch tank monitor at all
            tank_monitor_status.labels(store=store, ip=ip, group=group, brand=brand).set(0)

        # Mark scrape as successful
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(1)
        _update_error_state(store, ip, group, brand, is_success=True)
        logger.info(f"✓ Successfully fetched metrics for {store} ({ip})")
        return True

    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        logger.error(f"✗ Failed to fetch metrics for {store} ({ip}): {e}")
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
        _update_error_state(store, ip, group, brand, error_type=error_type, error_message=error_message, is_success=False)
        return False


def scrape_all_commanders(db: DatabaseManager):
    """Scrape all enabled commanders in parallel."""
    cycle_start = time.time()

    # Reset failed attempts at the start of each cycle
    # This ensures temporarily unreachable commanders aren't permanently blocked
    VerifoneAPIClient.reset_failed_attempts()

    # Get commanders from database
    commanders = db.get_commanders(enabled_only=True)

    # Apply dev mode filter if enabled
    if DEV_MODE and DEV_STORE_FILTER:
        filter_stores = [s.strip() for s in DEV_STORE_FILTER.split(',')]
        commanders = [c for c in commanders if c['store_name'] in filter_stores]
        logger.info(f"DEV MODE ENABLED - Filtering to stores: {filter_stores}")

    total_commanders.set(len(commanders))
    logger.info(f"Loaded {len(commanders)} commander(s) for monitoring")

    if not commanders:
        logger.warning("No commanders found to monitor")
        return

    # Get credentials from unified credential service
    # Priority: Bitwarden -> Database cache -> Environment variables
    creds = get_commander_credentials()
    if not creds:
        logger.error("No credentials found (tried Bitwarden, database, and environment)")
        return

    username = creds['username']
    password = creds['password']
    logger.info(f"Using credentials for {username} (source: {creds.get('source', 'unknown')})")
    timeout = db.get_setting('timeout_seconds', 30)
    max_workers = db.get_setting('max_workers', 10)

    # Fetch metrics in parallel
    logger.info(f"Starting parallel fetch for {len(commanders)} commanders with {max_workers} workers")
    success_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_commander_metrics, cmd, username, password, timeout): cmd
            for cmd in commanders
        }

        for future in as_completed(futures):
            if future.result():
                success_count += 1

    cycle_duration = time.time() - cycle_start
    scrape_cycle_duration.observe(cycle_duration)

    # Update global scrape status
    _last_scrape_success['timestamp'] = time.time()
    _last_scrape_success['success_count'] = success_count
    _last_scrape_success['total_count'] = len(commanders)

    logger.info(
        f"Parallel fetch completed for all {len(commanders)} commanders in {cycle_duration:.2f}s "
        f"({success_count} successful)"
    )


def start_metrics_server(port=8000):
    """Start HTTP server for metrics and health endpoints."""
    server = HTTPServer(('', port), HealthMetricsHandler)
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Prometheus metrics server started on port {port}")
    return server


def main():
    """Main application loop."""
    logger.info("Starting Verifone monitoring")

    # Initialize database
    db = DatabaseManager(DB_PATH)

    # Start config file watcher for hot-reload
    config_watcher = ConfigFileWatcher(db, check_interval=10)
    config_watcher.start()

    # Start metrics server
    start_metrics_server(port=8000)

    # Main polling loop
    try:
        while True:
            try:
                scrape_all_commanders(db)
                wait_seconds = POLL_INTERVAL
                logger.info(f"Completed scrape cycle. Waiting for {wait_seconds} seconds.")
                time.sleep(wait_seconds)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(60)  # Wait a minute before retrying
    finally:
        # Clean shutdown
        logger.info("Stopping config watcher...")
        config_watcher.stop()


if __name__ == '__main__':
    main()
