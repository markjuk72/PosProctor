import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import urllib3
from lxml import etree
import atexit
import time
from threading import Lock

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

class VerifoneAPIClient:
    # Class-level dictionary to track failed attempts per IP
    _failed_attempts = {}
    # Shared session with connection pooling
    _shared_session = None
    # Token cache with expiration tracking
    _token_cache = {}
    # Lock for thread-safe token operations
    _token_lock = Lock()
    # Default token TTL (20 minutes to account for inactivity timer)
    _default_token_ttl = 1200

    @classmethod
    def _get_shared_session(cls):
        """Get or create a shared session with connection pooling."""
        if cls._shared_session is None:
            cls._shared_session = requests.Session()
            retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
            adapter = HTTPAdapter(
                max_retries=retries,
                pool_connections=20,  # Number of connection pools to cache
                pool_maxsize=100      # Maximum number of connections to save in the pool
            )
            cls._shared_session.mount('https://', adapter)
            cls._shared_session.mount('http://', adapter)
            # Register cleanup on exit
            atexit.register(cls._cleanup_session)
        return cls._shared_session

    @classmethod
    def _cleanup_session(cls):
        """Clean up the shared session on application exit."""
        if cls._shared_session:
            cls._shared_session.close()
            cls._shared_session = None
        # Clean up token cache
        cls._token_cache.clear()

    @classmethod
    def _get_cached_token(cls, cache_key):
        """Get a cached token if it's still valid."""
        with cls._token_lock:
            if cache_key in cls._token_cache:
                token_data = cls._token_cache[cache_key]
                if time.time() < token_data['expires_at']:
                    logger.debug(f"Using cached token for {cache_key}")
                    return token_data['token']
                else:
                    # Token expired, remove from cache
                    logger.debug(f"Cached token expired for {cache_key}")
                    del cls._token_cache[cache_key]
            return None

    @classmethod
    def _cache_token(cls, cache_key, token, ttl=None):
        """Cache a token with expiration time."""
        if ttl is None:
            ttl = cls._default_token_ttl
        
        with cls._token_lock:
            # Implement basic cache size management (keep under 5 as per system limit)
            if len(cls._token_cache) >= 5:
                # Remove oldest token
                oldest_key = min(cls._token_cache.keys(), 
                               key=lambda k: cls._token_cache[k]['created_at'])
                logger.debug(f"Cache full, removing oldest token for {oldest_key}")
                del cls._token_cache[oldest_key]
            
            cls._token_cache[cache_key] = {
                'token': token,
                'created_at': time.time(),
                'expires_at': time.time() + ttl
            }
            logger.debug(f"Cached token for {cache_key} (expires in {ttl}s)")

    @classmethod
    def release_token(cls, cache_key):
        """Release a cached token when no longer required (best practice)."""
        with cls._token_lock:
            if cache_key in cls._token_cache:
                logger.debug(f"Releasing cached token for {cache_key}")
                del cls._token_cache[cache_key]

    def __init__(self, ip, username, password, timeout=30):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = self._get_shared_session()
        self.cache_key = f"{ip}:{username}"


    def get_token(self):
        """Authenticate and retrieve session token, with caching and failure tracking."""
        # Check for cached token first
        cached_token = self._get_cached_token(self.cache_key)
        if cached_token:
            return cached_token

        # Check if this IP has reached the failure limit
        if self._failed_attempts.get(self.ip, 0) >= 2:
            logger.warning(f"[{self.ip}] Skipping authentication: 2 failed attempts reached.")
            return None

        logger.debug(f"[{self.ip}] Attempting to authenticate")
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"
        logger.debug(f"[{self.ip}] Requesting URL: {url}")
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            logger.debug(f"[{self.ip}] Response status code: {r.status_code}")
            logger.debug(f"[{self.ip}] Response content: {r.content}")
            r.raise_for_status()
            token = etree.fromstring(r.content).findtext(".//cookie")
            if not token:
                logger.error(f"[{self.ip}] No token found in response.")
                self._failed_attempts[self.ip] = self._failed_attempts.get(self.ip, 0) + 1
                return None
            logger.debug(f"[{self.ip}] Token received: {token}")
            # Reset failure count on success
            self._failed_attempts[self.ip] = 0
            # Cache the token
            self._cache_token(self.cache_key, token)
            return token
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as e:
            logger.error(f"[{self.ip}] Connection timed out: {e}")
            self._failed_attempts[self.ip] = self._failed_attempts.get(self.ip, 0) + 1
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to get token: {e}")
            self._failed_attempts[self.ip] = self._failed_attempts.get(self.ip, 0) + 1
            return None

    def get_forecourt_diagnostics(self):
        """Fetch forecourt diagnostics from Verifone Commander API."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vforecourtdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return etree.fromstring(r.content)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch diagnostics: {e}")
            return None

    def get_loyalty_fep_status(self, loyalty_names=None):
        """Fetch loyalty FEP status from Verifone Commander API."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return self.parse_loyalty_fep_status(etree.fromstring(r.content), loyalty_names)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch loyalty FEP status: {e}")
            return None

    def get_primary_fep_status(self):
        """Fetch primary FEP status from Verifone Commander API."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return self.parse_primary_fep_status(etree.fromstring(r.content))
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch primary FEP status: {e}")
            return None

    def parse_diagnostics(self, xml_data):
        """Parse XML response to extract device statuses."""
        if xml_data is None:
            return None

        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        ns = {'diag': 'urn:vfi-sapphire:diagnostics.2017-01-17'}
        
        # Controller status
        controller_status_element = xml_data.find(".//controller")
        controller_status = 1 if controller_status_element is not None and controller_status_element.get('status') == 'Online' else 0

        pumps = []
        dcrs = []

        for fueling_point in xml_data.findall(".//fuelingPoint"):
            fp_id = fueling_point.get('sysid')
            if not fp_id:
                continue

            # Pumps
            pump_element = fueling_point.find(".//device[@type='Pump']")
            if pump_element is not None:
                pump_status = 1 if pump_element.get('status') == 'Online' and pump_element.get('isAvailable') == 'true' else 0
                pumps.append({'id': fp_id, 'status': pump_status})

            # DCRs
            dcr_element = fueling_point.find(".//device[@type='DCR']")
            if dcr_element is not None:
                dcr_status = 1 if dcr_element.get('status') == 'Online' and dcr_element.get('isAvailable') == 'true' else 0
                dcrs.append({'id': fp_id, 'status': dcr_status})
        
        # Fuel Price Displays
        price_displays = []
        for device in xml_data.findall(".//device[@type='Fuel Price Display']"):
            device_id = device.get('id')
            if not device_id:
                logger.warning("Fuel Price Display is missing an 'id' attribute, skipping.")
                continue
            status = 1 if device.get('status') == 'Online' and device.get('isAvailable') == 'true' else 0
            price_displays.append({'id': device_id, 'status': status})

        return {
            'controller_status': controller_status,
            'pumps': pumps,
            'dcrs': dcrs,
            'price_displays': price_displays
        }

    def parse_loyalty_fep_status(self, xml_data, loyalty_names=None):
        """Parse XML response to extract loyalty FEP connection status."""
        if xml_data is None:
            return None

        if loyalty_names is None:
            loyalty_names = ['rewards 2 go']  # Default fallback

        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        for fep in xml_data.findall(".//fepDetail"):
            fep_name = fep.get('fepName', '').lower()
            # Check if the FEP name matches any of the configured loyalty names
            if any(name.lower() == fep_name for name in loyalty_names):
                connection_status_text = fep.findtext("connectionStatus")
                if connection_status_text is not None:
                    connection_status = 1 if connection_status_text.lower() == 'true' else 0
                    return {"loyalty_status": connection_status}
        return None

    def parse_primary_fep_status(self, xml_data):
        """Parse XML response to extract primary FEP connection status."""
        if xml_data is None:
            return None

        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        for fep in xml_data.findall(".//fepDetail"):
            if fep.get('isPrimary', 'false').lower() == 'true':
                fep_name = fep.get('fepName', '')
                connection_status_text = fep.findtext("connectionStatus")
                if connection_status_text is not None:
                    # Handle special cases where status might be "Undetermined"
                    if connection_status_text.lower() == 'true':
                        connection_status = 1
                    elif connection_status_text.lower() == 'false':
                        connection_status = 0
                    else:
                        # For "Undetermined" or other values, treat as disconnected
                        connection_status = 0
                    return {
                        "primary_fep_name": fep_name,
                        "primary_fep_status": connection_status
                    }
        return None

    def release_my_token(self):
        """Release this instance's cached token when no longer required."""
        self.release_token(self.cache_key)

    @classmethod
    def reset_failed_attempts(cls):
        """Reset failed attempts counter for all IPs."""
        cls._failed_attempts.clear()
        logger.debug("Reset failed attempts counter for all commanders.")

    @classmethod
    def clear_token_cache(cls):
        """Clear all cached tokens (useful for cleanup or testing)."""
        with cls._token_lock:
            cls._token_cache.clear()
            logger.debug("Cleared all cached tokens.")