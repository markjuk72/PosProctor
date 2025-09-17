import time
import logging
import csv
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from prometheus_client import start_http_server, Gauge, Counter, Histogram, Info
from verifone_api import VerifoneAPIClient
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Prometheus Metrics
price_display_status = Gauge('posproctor_price_display_status', 'Status of fuel price displays (1=online, 0=offline)', ['store', 'ip', 'display_id', 'group', 'brand'])
loyalty_fep_status = Gauge(
    'posproctor_loyalty_fep_status',
    'Status of the loyalty FEP (1 = Online, 0 = Offline)',
    ['store', 'ip', 'group', 'brand']
)
primary_fep_status = Gauge(
    'posproctor_primary_fep_status',
    'Status of the primary card processor FEP (1 = Online, 0 = Offline)',
    ['store', 'ip', 'group', 'brand', 'fep_name']
)
scrape_success = Gauge('posproctor_scrape_success', 'Indicates if the scrape for a commander was successful', ['store', 'ip', 'group', 'brand'])
controller_status = Gauge('posproctor_controller_status', 'Status of the forecourt controller (1=online, 0=offline)', ['store', 'ip', 'group', 'brand'])
pump_status = Gauge('posproctor_pump_status', 'Status of individual pumps (1=online, 0=offline)', ['store', 'ip', 'fueling_point_id', 'group', 'brand'])
dcr_status = Gauge('posproctor_dcr_status', 'Status of individual DCRs (1=online, 0=offline)', ['store', 'ip', 'fueling_point_id', 'group', 'brand'])

# Performance and Health Metrics
query_duration = Histogram('posproctor_query_duration_seconds', 'Time spent querying commander APIs', ['store', 'ip', 'group', 'brand', 'endpoint'])
query_failures = Counter('posproctor_query_failures_total', 'Number of failed queries per commander', ['store', 'ip', 'group', 'brand', 'error_type'])
scrape_cycle_duration = Histogram('posproctor_scrape_cycle_duration_seconds', 'Total time to complete a scrape cycle', ['workers'])
concurrent_queries = Gauge('posproctor_concurrent_queries', 'Number of currently running queries')
total_commanders = Gauge('posproctor_total_commanders', 'Total number of commanders configured', ['enabled'])
app_info = Info('posproctor_app', 'Application information')
last_scrape_timestamp = Gauge('posproctor_last_scrape_timestamp', 'Timestamp of last completed scrape cycle')
thread_pool_active = Gauge('posproctor_thread_pool_active', 'Number of active threads in the pool')
auth_failures = Counter('posproctor_auth_failures_total', 'Authentication failures per commander', ['store', 'ip', 'group', 'brand'])
timeout_errors = Counter('posproctor_timeout_errors_total', 'Timeout errors per commander', ['store', 'ip', 'group', 'brand'])
connection_errors = Counter('posproctor_connection_errors_total', 'Connection errors per commander', ['store', 'ip', 'group', 'brand'])

# Error State and Debugging Metrics
commander_error_state = Info('posproctor_commander_error_state', 'Current error state and last error message for each commander', ['store', 'ip', 'group', 'brand'])
last_successful_connection = Gauge('posproctor_last_successful_connection_timestamp', 'Timestamp of last successful connection', ['store', 'ip', 'group', 'brand'])
consecutive_failures = Gauge('posproctor_consecutive_failures', 'Number of consecutive failures for each commander', ['store', 'ip', 'group', 'brand'])

# Global failure tracking for consecutive errors
_consecutive_failures_tracker = {}

def _update_error_state(store, ip, group, brand, error_type, error_message, is_success=False):
    """Update error state tracking for a commander."""
    key = f"{ip}:{store}"
    
    if is_success:
        # Reset consecutive failures on success
        _consecutive_failures_tracker[key] = 0
        consecutive_failures.labels(store=store, ip=ip, group=group, brand=brand).set(0)
        last_successful_connection.labels(store=store, ip=ip, group=group, brand=brand).set(time.time())
        commander_error_state.labels(store=store, ip=ip, group=group, brand=brand).info({
            'status': 'healthy',
            'last_error_type': '',
            'last_error_message': '',
            'last_success_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        })
    else:
        # Increment consecutive failures
        current_failures = _consecutive_failures_tracker.get(key, 0) + 1
        _consecutive_failures_tracker[key] = current_failures
        consecutive_failures.labels(store=store, ip=ip, group=group, brand=brand).set(current_failures)
        
        # Update error state with detailed information
        commander_error_state.labels(store=store, ip=ip, group=group, brand=brand).info({
            'status': 'error',
            'last_error_type': error_type,
            'last_error_message': error_message,
            'consecutive_failures': str(current_failures),
            'last_error_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        })

def fetch_commander_metrics(commander):
    """Fetches metrics for a single commander and updates Prometheus gauges."""
    store = commander['store']
    ip = commander['ip']
    group = commander['group']
    brand = commander.get('brand', 'Unknown')
    logger.info(f"Fetching metrics for commander: {store} ({ip}) - {brand}")
    
    start_time = time.time()
    concurrent_queries.inc()
    
    try:
        client = VerifoneAPIClient(
            ip=ip,
            username=Config.USERNAME,
            password=Config.PASSWORD,
            timeout=Config.TIMEOUT
        )
        
        # Fetch and process forecourt diagnostics
        diagnostics_start = time.time()
        xml_data = client.get_forecourt_diagnostics()
        query_duration.labels(store=store, ip=ip, group=group, brand=brand, endpoint='diagnostics').observe(time.time() - diagnostics_start)
        
        has_diagnostics = False
        has_loyalty = False
        
        if xml_data is not None:
            diagnostics = client.parse_diagnostics(xml_data)
            
            # Controller
            controller_status.labels(store=store, ip=ip, group=group, brand=brand).set(diagnostics['controller_status'])

            # Pumps
            for pump in diagnostics['pumps']:
                pump_status.labels(store=store, ip=ip, fueling_point_id=pump['id'], group=group, brand=brand).set(pump['status'])

            # DCRs
            for dcr in diagnostics['dcrs']:
                dcr_status.labels(store=store, ip=ip, fueling_point_id=dcr['id'], group=group, brand=brand).set(dcr['status'])

            # Price Displays
            for display in diagnostics['price_displays']:
                price_display_status.labels(store=store, ip=ip, display_id=display['id'], group=group, brand=brand).set(display['status'])
            
            has_diagnostics = True
        else:
            logger.warning(f"[{store}] No diagnostics data retrieved.")
            query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='no_data').inc()

        # Fetch and process loyalty FEP status
        loyalty_start = time.time()
        loyalty_status_data = client.get_loyalty_fep_status(Config.LOYALTY_NAMES)
        query_duration.labels(store=store, ip=ip, group=group, brand=brand, endpoint='loyalty').observe(time.time() - loyalty_start)

        if loyalty_status_data:
            loyalty_fep_status.labels(store=store, ip=ip, group=group, brand=brand).set(loyalty_status_data['loyalty_status'])
            has_loyalty = True
        else:
            logger.warning(f"[{store}] No loyalty status data retrieved.")
            query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='no_loyalty_data').inc()

        # Fetch and process primary FEP status
        primary_fep_start = time.time()
        primary_fep_data = client.get_primary_fep_status()
        query_duration.labels(store=store, ip=ip, group=group, brand=brand, endpoint='primary_fep').observe(time.time() - primary_fep_start)

        if primary_fep_data:
            fep_name = primary_fep_data['primary_fep_name']
            fep_status = primary_fep_data['primary_fep_status']
            primary_fep_status.labels(store=store, ip=ip, group=group, brand=brand, fep_name=fep_name).set(fep_status)
            logger.debug(f"[{store}] Primary FEP {fep_name}: {'Connected' if fep_status else 'Disconnected'}")
        else:
            logger.warning(f"[{store}] No primary FEP status data retrieved.")
            query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='no_primary_fep_data').inc()
        
        # Only consider success if we got at least diagnostics data (loyalty is optional)
        if has_diagnostics:
            scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(1)
            _update_error_state(store, ip, group, brand, '', '', is_success=True)
            logger.info(f"Successfully fetched metrics for {store} ({ip})")
        else:
            scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
            error_msg = "No diagnostics data retrieved from commander. Check commander status and API connectivity."
            _update_error_state(store, ip, group, brand, 'no_data', error_msg)
            logger.error(f"Failed to fetch diagnostics for {store} ({ip}): {error_msg}")

    except requests.exceptions.Timeout as e:
        timeout_errors.labels(store=store, ip=ip, group=group, brand=brand).inc()
        query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='timeout').inc()
        error_msg = f"Connection timeout after {Config.TIMEOUT}s"
        logger.error(f"Timeout error for commander {store} ({ip}): {error_msg}")
        _update_error_state(store, ip, group, brand, 'timeout', error_msg)
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
    except requests.exceptions.ConnectionError as e:
        connection_errors.labels(store=store, ip=ip, group=group, brand=brand).inc()
        query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='connection').inc()
        error_msg = f"Cannot connect to commander at {ip}. Check network connectivity and commander status."
        logger.error(f"Connection error for commander {store} ({ip}): {error_msg}")
        _update_error_state(store, ip, group, brand, 'connection', error_msg)
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            auth_failures.labels(store=store, ip=ip, group=group, brand=brand).inc()
            query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='auth').inc()
            error_msg = f"Authentication failed. Check credentials for {ip}."
        else:
            query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='http_error').inc()
            error_msg = f"HTTP {e.response.status_code}: {e.response.reason}"
        logger.error(f"HTTP error for commander {store} ({ip}): {error_msg}")
        _update_error_state(store, ip, group, brand, 'http_error', error_msg)
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
    except Exception as e:
        logger.error(f"Error fetching metrics for commander {store} ({ip}): {e}")
        query_failures.labels(store=store, ip=ip, group=group, brand=brand, error_type='unknown').inc()
        error_msg = f"Unexpected error: {str(e)}"
        _update_error_state(store, ip, group, brand, 'unknown', error_msg)
        scrape_success.labels(store=store, ip=ip, group=group, brand=brand).set(0)
    finally:
        concurrent_queries.dec()

def load_commanders():
    """Loads commanders from the CSV file."""
    commanders = []
    try:
        with open('/app/commanders.csv', mode='r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row.get('enabled', 'false').lower() == 'true':
                    commanders.append(row)
    except FileNotFoundError:
        logger.error("commanders.csv file not found. Please ensure it is mounted in /app/commanders.csv")
    return commanders

def fetch_all_commanders_parallel(commanders, max_workers=10):
    """Fetch metrics for all commanders in parallel using ThreadPoolExecutor."""
    logger.info(f"Starting parallel fetch for {len(commanders)} commanders with {max_workers} workers")
    
    cycle_start_time = time.time()
    
    with scrape_cycle_duration.labels(workers=str(max_workers)).time():
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Update thread pool metrics
            thread_pool_active.set(max_workers)
            
            # Submit all tasks
            future_to_commander = {
                executor.submit(fetch_commander_metrics, commander): commander 
                for commander in commanders
            }
            
            # Process completed tasks as they finish
            completed = 0
            for future in as_completed(future_to_commander):
                commander = future_to_commander[future]
                try:
                    future.result()  # This will raise any exception that occurred
                    completed += 1
                    if completed % 5 == 0:  # Log progress every 5 completions
                        logger.info(f"Completed {completed}/{len(commanders)} commanders")
                except Exception as e:
                    logger.error(f"Exception occurred for commander {commander['store']} ({commander['ip']}): {e}")
    
    # Update metrics
    last_scrape_timestamp.set(time.time())
    thread_pool_active.set(0)
    
    cycle_duration = time.time() - cycle_start_time
    logger.info(f"Parallel fetch completed for all {len(commanders)} commanders in {cycle_duration:.2f}s")

def main():
    """Main function to start the monitoring loop."""
    logger.info("Starting Verifone monitoring")
    
    # Initialize app info
    app_info.info({
        'version': '2.2',
        'scrape_interval': str(Config.SCRAPE_INTERVAL),
        'timeout': str(Config.TIMEOUT),
        'max_workers': '10'
    })
    
    time.sleep(5)
    start_http_server(8000)
    logger.info("Prometheus metrics server started on port 8000")

    while True:
        commanders = load_commanders()
        all_commanders = []
        
        # Load all commanders for total count metrics
        try:
            with open('/app/commanders.csv', mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    all_commanders.append(row)
        except FileNotFoundError:
            logger.error("commanders.csv file not found")
        
        # Update commander count metrics
        enabled_count = len([c for c in all_commanders if c.get('enabled', 'false').lower() == 'true'])
        disabled_count = len(all_commanders) - enabled_count
        
        total_commanders.labels(enabled='true').set(enabled_count)
        total_commanders.labels(enabled='false').set(disabled_count)
        
        if not commanders:
            logger.warning("No enabled commanders found in commanders.csv. Nothing to monitor.")
        else:
            VerifoneAPIClient.reset_failed_attempts()
            fetch_all_commanders_parallel(commanders, max_workers=10)
        
        logger.info(f"Completed scrape cycle. Waiting for {Config.SCRAPE_INTERVAL} minutes.")
        time.sleep(Config.SCRAPE_INTERVAL * 60)

if __name__ == "__main__":
    main()
