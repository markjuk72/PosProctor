import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import urllib3
from lxml import etree
import atexit
import time
from threading import Lock

# Optional xml_debug import (only available in monitoring service)
try:
    from xml_debug import xml_debug
    XML_DEBUG_AVAILABLE = True
except ImportError:
    XML_DEBUG_AVAILABLE = False
    xml_debug = None

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
            # Implement basic cache size management (keep under 100 to support all commanders)
            if len(cls._token_cache) >= 100:
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

    def __init__(self, ip, username, password, timeout=30, store_name=None):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.store_name = store_name or ip  # Fallback to IP if no store name
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
            xml_data = etree.fromstring(r.content)

            # Check for Fault response - API returned an error instead of data
            fault = xml_data.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
            if fault is not None:
                fault_string = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}faultstring", "Unknown error")
                logger.warning(f"[{self.ip}] API returned fault: {fault_string}")
                # Save fault response for debugging
                if XML_DEBUG_AVAILABLE:
                    xml_debug.save_response(self.ip, self.store_name, 'diagnostics', xml_data, is_fault=True)
                # Release cached token - fault may indicate session expired
                self.release_token(self.cache_key)
                return None

            # Save successful response for debugging
            if XML_DEBUG_AVAILABLE:
                xml_debug.save_response(self.ip, self.store_name, 'diagnostics', xml_data)
            return xml_data
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
            xml_data = etree.fromstring(r.content)
            # Save response for debugging
            if XML_DEBUG_AVAILABLE:
                xml_debug.save_response(self.ip, self.store_name, 'loyalty', xml_data)
            return self.parse_loyalty_fep_status(xml_data, loyalty_names)
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
            xml_data = etree.fromstring(r.content)
            # Save response for debugging
            if XML_DEBUG_AVAILABLE:
                xml_debug.save_response(self.ip, self.store_name, 'fep', xml_data)
            return self.parse_primary_fep_status(xml_data)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch primary FEP status: {e}")
            return None

    def get_pos_terminal_status(self):
        """Fetch POS terminal status from Verifone Commander API."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vposdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            xml_data = etree.fromstring(r.content)
            # Save response for debugging
            if XML_DEBUG_AVAILABLE:
                xml_debug.save_response(self.ip, self.store_name, 'pos', xml_data)
            return self.parse_pos_terminal_status(xml_data)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch POS terminal status: {e}")
            return None

    def get_pinpad_status(self):
        """Fetch pinpad status from Verifone Commander API."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            xml_data = etree.fromstring(r.content)
            # Save response for debugging
            if XML_DEBUG_AVAILABLE:
                xml_debug.save_response(self.ip, self.store_name, 'pinpad', xml_data)
            return self.parse_pinpad_status(xml_data)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch pinpad status: {e}")
            return None

    def parse_diagnostics(self, xml_data):
        """Parse XML response to extract device statuses."""
        if xml_data is None:
            return None

        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        ns = {'diag': 'urn:vfi-sapphire:diagnostics.2017-01-17'}
        
        # Controller status - try multiple search patterns
        controller_status_element = xml_data.find(".//controller")

        # If not found, try with namespace
        if controller_status_element is None:
            controller_status_element = xml_data.find(".//diag:controller", ns)

        # If still not found, try looking for Controller (capitalized)
        if controller_status_element is None:
            controller_status_element = xml_data.find(".//Controller")

        if controller_status_element is not None:
            status_attr = controller_status_element.get('status', '')
            logger.debug(f"[{self.ip}] Controller element found. Status attribute: '{status_attr}' (all attrs: {controller_status_element.attrib})")
            controller_status = 1 if status_attr.lower() == 'online' else 0
        else:
            # Log more details to help debug
            root_tag = xml_data.tag if hasattr(xml_data, 'tag') else 'unknown'
            child_tags = [child.tag for child in xml_data][:5] if len(xml_data) > 0 else []
            logger.warning(f"[{self.ip}] No controller element found in XML. Root: {root_tag}, Children: {child_tags}")
            controller_status = 0

        pumps = []
        dcrs = []

        for fueling_point in xml_data.findall(".//fuelingPoint"):
            fp_id = fueling_point.get('sysid')
            if not fp_id:
                continue

            # Pumps
            pump_element = fueling_point.find(".//device[@type='Pump']")
            if pump_element is not None:
                pump_status = 1 if pump_element.get('status', '').lower() == 'online' and pump_element.get('isAvailable', '').lower() == 'true' else 0
                pumps.append({'id': fp_id, 'status': pump_status})

            # DCRs
            dcr_element = fueling_point.find(".//device[@type='DCR']")
            if dcr_element is not None:
                dcr_status = 1 if dcr_element.get('status', '').lower() == 'online' and dcr_element.get('isAvailable', '').lower() == 'true' else 0
                dcrs.append({'id': fp_id, 'status': dcr_status})
        
        # Fuel Price Displays
        price_displays = []
        for device in xml_data.findall(".//device[@type='Fuel Price Display']"):
            device_id = device.get('id')
            if not device_id:
                logger.warning("Fuel Price Display is missing an 'id' attribute, skipping.")
                continue
            status = 1 if device.get('status', '').lower() == 'online' and device.get('isAvailable', '').lower() == 'true' else 0
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

    def parse_pos_terminal_status(self, xml_data):
        """Parse XML response to extract POS terminal status information from vposdiagnostics."""
        if xml_data is None:
            return None

        logger.debug("Parsing POS terminal status from vposdiagnostics")
        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        terminals = []

        # Parse <posTerminal> elements from vposdiagnostics
        for terminal in xml_data.findall(".//posTerminal"):
            terminal_id = terminal.get('sysid')
            terminal_type = terminal.get('type', 'Unknown')
            status = terminal.get('status', '').lower()

            if terminal_id:
                # Determine if terminal is online
                is_online = (status == 'online')

                terminals.append({
                    'id': terminal_id,
                    'status': 1 if is_online else 0,
                    'type': terminal_type
                })
                logger.debug(f"Found POS terminal {terminal_id} ({terminal_type}): {'Online' if is_online else 'Offline'}")

        if terminals:
            logger.info(f"[{self.ip}] Found {len(terminals)} POS terminal(s)")
            return {'terminals': terminals}
        else:
            logger.warning(f"[{self.ip}] No POS terminal information found in vposdiagnostics response")
            return None

    def parse_pinpad_status(self, xml_data):
        """Parse XML response to extract pinpad status information from vpaymentdiagnostics."""
        if xml_data is None:
            return None

        logger.debug("Parsing pinpad status from vpaymentdiagnostics")
        logger.debug(etree.tostring(xml_data, pretty_print=True).decode())

        pinpads = []

        # Parse <pinpadDetail> elements from vpaymentdiagnostics
        for pinpad in xml_data.findall(".//pinpadDetail"):
            pinpad_id = pinpad.get('popID')
            workstation_name = pinpad.findtext('workstationName', 'Unknown')
            connection_status = pinpad.findtext('connectionStatus', '').lower()

            if pinpad_id:
                # Determine if pinpad is online
                is_online = (connection_status == 'true')

                pinpads.append({
                    'id': pinpad_id,
                    'status': 1 if is_online else 0,
                    'workstation': workstation_name
                })
                logger.debug(f"Found pinpad {pinpad_id} ({workstation_name}): {'Online' if is_online else 'Offline'}")

        if pinpads:
            logger.info(f"[{self.ip}] Found {len(pinpads)} pinpad(s)")
            return {'pinpads': pinpads}
        else:
            logger.debug(f"[{self.ip}] No pinpad information found in vpaymentdiagnostics response")
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