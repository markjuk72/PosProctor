"""
Verifone Commander API Client
Handles authentication, metrics collection, and session management
"""

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
                pool_connections=20,
                pool_maxsize=100
            )
            cls._shared_session.mount('https://', adapter)
            cls._shared_session.mount('http://', adapter)
            atexit.register(cls._cleanup_session)
        return cls._shared_session

    @classmethod
    def _cleanup_session(cls):
        """Clean up the shared session on application exit."""
        if cls._shared_session:
            cls._shared_session.close()
            cls._shared_session = None
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
                    logger.debug(f"Cached token expired for {cache_key}")
                    del cls._token_cache[cache_key]
            return None

    @classmethod
    def _cache_token(cls, cache_key, token, ttl=None):
        """Cache a token with expiration time."""
        if ttl is None:
            ttl = cls._default_token_ttl

        with cls._token_lock:
            if len(cls._token_cache) >= 100:
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
        """Release a cached token."""
        with cls._token_lock:
            if cache_key in cls._token_cache:
                logger.debug(f"Releasing cached token for {cache_key}")
                del cls._token_cache[cache_key]

    def __init__(self, ip, username, password, timeout=30, store_name=None):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.store_name = store_name or ip
        self.session = self._get_shared_session()
        self.cache_key = f"{ip}:{username}"

    def get_token(self):
        """Authenticate and retrieve session token."""
        cached_token = self._get_cached_token(self.cache_key)
        if cached_token:
            return cached_token

        if self._failed_attempts.get(self.ip, 0) >= 2:
            logger.warning(f"[{self.ip}] Skipping authentication: 2 failed attempts reached.")
            return None

        logger.debug(f"[{self.ip}] Attempting to authenticate")
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"

        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            token = etree.fromstring(r.content).findtext(".//cookie")

            if not token:
                logger.error(f"[{self.ip}] No token found in response.")
                self._failed_attempts[self.ip] = self._failed_attempts.get(self.ip, 0) + 1
                return None

            logger.debug(f"[{self.ip}] Token received")
            self._failed_attempts[self.ip] = 0
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
        """Fetch forecourt diagnostics."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vforecourtdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            xml_data = etree.fromstring(r.content)

            fault = xml_data.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
            if fault is not None:
                fault_string = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}faultstring", "Unknown error")
                logger.warning(f"[{self.ip}] API returned fault: {fault_string}")
                self.release_token(self.cache_key)
                return None

            return xml_data
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch diagnostics: {e}")
            return None

    def get_primary_fep_status(self):
        """Fetch primary FEP status."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return etree.fromstring(r.content)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch primary FEP status: {e}")
            return None

    def parse_diagnostics(self, xml_data):
        """Parse XML response to extract device statuses."""
        if xml_data is None:
            return None

        ns = {'diag': 'urn:vfi-sapphire:diagnostics.2017-01-17'}

        # Controller status
        controller_status_element = xml_data.find(".//controller")
        if controller_status_element is None:
            controller_status_element = xml_data.find(".//diag:controller", ns)
        if controller_status_element is None:
            controller_status_element = xml_data.find(".//Controller")

        controller_status = 0
        if controller_status_element is not None:
            status_attr = controller_status_element.get('status', '')
            controller_status = 1 if status_attr.lower() == 'online' else 0

        pumps = []
        dcrs = []
        price_displays = []

        # Pumps and DCRs
        for fueling_point in xml_data.findall(".//fuelingPoint"):
            fp_id = fueling_point.get('sysid')
            if not fp_id:
                continue

            pump_element = fueling_point.find(".//device[@type='Pump']")
            if pump_element is not None:
                pump_status = 1 if pump_element.get('status', '').lower() == 'online' and pump_element.get('isAvailable', '').lower() == 'true' else 0
                pumps.append({'id': fp_id, 'status': pump_status})

            dcr_element = fueling_point.find(".//device[@type='DCR']")
            if dcr_element is not None:
                dcr_status = 1 if dcr_element.get('status', '').lower() == 'online' and dcr_element.get('isAvailable', '').lower() == 'true' else 0
                dcrs.append({'id': fp_id, 'status': dcr_status})

        # Fuel Price Displays
        for device in xml_data.findall(".//device[@type='Fuel Price Display']"):
            device_id = device.get('id')
            if device_id:
                status = 1 if device.get('status', '').lower() == 'online' and device.get('isAvailable', '').lower() == 'true' else 0
                price_displays.append({'id': device_id, 'status': status})

        return {
            'controller_status': controller_status,
            'pumps': pumps,
            'dcrs': dcrs,
            'price_displays': price_displays
        }

    def get_tank_monitor(self):
        """Fetch tank monitor data from vrubyrept endpoint."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vrubyrept&cookie={token}&reptname=tankMonitor&period=1&reptnum=1"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return r.content  # Return raw bytes for parsing
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch tank monitor: {e}")
            return None

    def parse_tank_monitor(self, xml_content):
        """
        Parse tank monitor XML to extract tank levels.

        Returns:
            List of dicts with tank data:
            [{
                'id': 1,
                'name': 'UNLEADED',
                'volume': 8130,
                'level': 71.74,
                'temperature': 42.5,
                'water': 0.0,
                'ullage': 5000,
                'capacity': 13130
            }]
        """
        if xml_content is None:
            return []

        try:
            xml_data = etree.fromstring(xml_content)
            tanks = []

            # Check for Fault response
            fault = xml_data.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
            if fault is not None:
                fault_string = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}faultstring", "Unknown")
                message = fault.findtext(".//{urn:vfi-sapphire:np.domain.2001-07-01}message", "")
                logger.warning(f"[{self.ip}] Tank monitor returned fault: {fault_string} - {message}")
                return []

            # Find all inventoryInfo elements (namespace-aware)
            for inv_info in xml_data.iter():
                if 'inventoryInfo' in inv_info.tag:
                    try:
                        # Build child map for easier access
                        child_map = {}
                        for child in inv_info:
                            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            child_map[tag_name.lower()] = child

                        # Get tank ID and name from fuelTank element
                        fuel_tank_elem = child_map.get('fueltank')
                        if fuel_tank_elem is not None:
                            tank_id = fuel_tank_elem.get('sysid') or fuel_tank_elem.get('id')
                            product = fuel_tank_elem.text.strip() if fuel_tank_elem.text else f'tank{tank_id}'
                        else:
                            continue

                        # Extract values
                        def get_float(keys):
                            for key in keys:
                                elem = child_map.get(key)
                                if elem is not None and elem.text:
                                    try:
                                        return float(elem.text)
                                    except ValueError:
                                        pass
                            return 0.0

                        volume = get_float(['fuelvolume', 'volume', 'volumegallons'])
                        level = get_float(['fuellvl', 'level', 'levelinches'])
                        temperature = get_float(['fueltemperature', 'temperature', 'temp'])
                        water = get_float(['waterlvl', 'water', 'waterinches'])
                        ullage = get_float(['ullage', 'fuelullage'])
                        capacity = get_float(['fuelcapacity', 'capacity'])

                        # Calculate capacity if not provided
                        if capacity == 0.0 and volume > 0 and ullage > 0:
                            capacity = volume + ullage

                        tanks.append({
                            'id': int(tank_id) if tank_id and str(tank_id).isdigit() else len(tanks) + 1,
                            'name': product,
                            'volume': round(volume, 0),
                            'level': round(level, 2),
                            'temperature': round(temperature, 1),
                            'water': round(water, 2),
                            'ullage': round(ullage, 0),
                            'capacity': round(capacity, 0)
                        })

                    except Exception as e:
                        logger.error(f"[{self.ip}] Error parsing tank element: {e}")
                        continue

            logger.debug(f"[{self.ip}] Parsed {len(tanks)} tanks from tank monitor")
            return tanks

        except etree.XMLSyntaxError as e:
            logger.error(f"[{self.ip}] XML parse error in tank monitor: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.ip}] Unexpected error parsing tank monitor: {e}")
            return []

    def parse_tank_alarms(self, xml_content):
        """
        Parse tank monitor XML to extract alarm status and history.

        Returns:
            Tuple of (alarm_status, alarm_history):
            - alarm_status: List of current alarm states per tank
            - alarm_history: List of historical alarm events
        """
        if xml_content is None:
            return [], []

        try:
            xml_data = etree.fromstring(xml_content)
            alarm_status = []
            alarm_history = []

            # Parse current alarm status from intTankAlarmStatus
            for tank_status in xml_data.iter():
                if 'intTankAlarmStatus' in tank_status.tag:
                    tank_id = None
                    tank_name = None
                    flags = {}

                    for child in tank_status:
                        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

                        if tag.lower() == 'fueltank':
                            tank_id = child.get('sysid')
                            tank_name = child.text.strip() if child.text else f'Tank {tank_id}'
                        elif tag.lower() == 'inttankflags':
                            for flag in child:
                                flag_tag = flag.tag.split('}')[-1] if '}' in flag.tag else flag.tag
                                flags[flag_tag.lower()] = (flag.text or 'OFF').upper() == 'ON'

                    if tank_id:
                        alarm_status.append({
                            'tank_id': tank_id,
                            'tank_name': tank_name,
                            'leak': flags.get('leak', False),
                            'high_water': flags.get('highwater', False),
                            'overfill': flags.get('overfill', False),
                            'low_limit': flags.get('lowlimit', False),
                            'theft': flags.get('theft', False)
                        })

            # Parse alarm history from internalTankAlarms
            for tank_alarms in xml_data.iter():
                if 'internalTankAlarms' in tank_alarms.tag:
                    tank_id = None
                    tank_name = None

                    for child in tank_alarms:
                        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

                        if tag.lower() == 'fueltank':
                            tank_id = child.get('sysid')
                            tank_name = child.text.strip() if child.text else f'Tank {tank_id}'
                        elif tag.lower() == 'internalalarm':
                            alarm_type = None
                            alarm_date = None
                            for alarm_child in child:
                                alarm_tag = alarm_child.tag.split('}')[-1] if '}' in alarm_child.tag else alarm_child.tag
                                if 'alarmtypedescription' in alarm_tag.lower():
                                    alarm_type = alarm_child.text
                                elif 'alarmdate' in alarm_tag.lower():
                                    alarm_date = alarm_child.text

                            if tank_id and alarm_type:
                                alarm_history.append({
                                    'tank_id': tank_id,
                                    'tank_name': tank_name,
                                    'alarm_type': alarm_type,
                                    'alarm_date': alarm_date
                                })

            logger.debug(f"[{self.ip}] Parsed {len(alarm_status)} tank alarm statuses, {len(alarm_history)} historical alarms")
            return alarm_status, alarm_history

        except etree.XMLSyntaxError as e:
            logger.error(f"[{self.ip}] XML parse error in tank alarms: {e}")
            return [], []
        except Exception as e:
            logger.error(f"[{self.ip}] Unexpected error parsing tank alarms: {e}")
            return [], []

    def get_payment_diagnostics(self):
        """Fetch payment diagnostics (primary FEP, loyalty FEP, pinpads) - single API call."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return etree.fromstring(r.content)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch payment diagnostics: {e}")
            return None

    def get_pos_diagnostics(self):
        """Fetch POS diagnostics (POS terminals)."""
        token = self.get_token()
        if not token:
            return None

        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vposdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            return etree.fromstring(r.content)
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch POS diagnostics: {e}")
            return None

    def parse_payment_diagnostics(self, xml_data, loyalty_names=None):
        """
        Parse all payment diagnostics data from a single vpaymentdiagnostics response.

        Returns dict with:
        - primary_fep: {fep_name, status} or None
        - loyalty_fep: {loyalty_name, status} or None
        - pinpads: [{id, status, workstation}, ...]
        """
        result = {
            'primary_fep': None,
            'loyalty_fep': None,
            'pinpads': []
        }

        if xml_data is None:
            return result

        if loyalty_names is None:
            loyalty_names = ['rewards 2 go']  # Default fallback

        # Parse all FEP details in a single pass
        for fep in xml_data.findall(".//fepDetail"):
            fep_name = fep.get('fepName', '')
            connection_status_text = fep.findtext("connectionStatus")

            if connection_status_text is not None:
                if connection_status_text.lower() == 'true':
                    status = 1
                else:
                    status = 0

                # Check if primary FEP
                if fep.get('isPrimary', 'false').lower() == 'true':
                    result['primary_fep'] = {
                        'fep_name': fep_name,
                        'status': status
                    }

                # Check if loyalty FEP
                if any(name.lower() == fep_name.lower() for name in loyalty_names):
                    result['loyalty_fep'] = {
                        'loyalty_name': fep_name,
                        'status': status
                    }

        # Parse pinpads
        for pinpad in xml_data.findall(".//pinpadDetail"):
            pinpad_id = pinpad.get('popID')
            workstation_name = pinpad.findtext('workstationName', 'Unknown')
            connection_status = pinpad.findtext('connectionStatus', '').lower()

            if pinpad_id:
                is_online = (connection_status == 'true')
                result['pinpads'].append({
                    'id': pinpad_id,
                    'status': 1 if is_online else 0,
                    'workstation': workstation_name
                })

        logger.debug(f"[{self.ip}] Parsed payment diagnostics: primary_fep={result['primary_fep'] is not None}, "
                    f"loyalty_fep={result['loyalty_fep'] is not None}, pinpads={len(result['pinpads'])}")
        return result

    def parse_pos_terminal_status(self, xml_data):
        """Parse XML response to extract POS terminal status from vposdiagnostics."""
        if xml_data is None:
            return []

        terminals = []

        for terminal in xml_data.findall(".//posTerminal"):
            terminal_id = terminal.get('sysid')
            terminal_type = terminal.get('type', 'Unknown')
            status = terminal.get('status', '').lower()

            if terminal_id:
                is_online = (status == 'online')
                terminals.append({
                    'id': terminal_id,
                    'status': 1 if is_online else 0,
                    'type': terminal_type
                })

        logger.debug(f"[{self.ip}] Parsed {len(terminals)} POS terminal(s)")
        return terminals

    def parse_tank_reconciliation(self, xml_content):
        """
        Parse tank monitor XML to extract reconciliation/variance data.

        Returns:
            List of dicts with reconciliation data:
            [{
                'tank_id': 1,
                'product': 'UNLEADED',
                'begin_volume': 8000,
                'end_volume': 7500,
                'dispensed': 520,
                'variance': 20,  # end - begin + dispensed (positive = gain, negative = loss)
                'variance_pct': 0.25  # as percentage of begin_volume
            }]
        """
        if xml_content is None:
            return []

        try:
            xml_data = etree.fromstring(xml_content)
            reconciliation = []

            # Find reconciliation data elements (intReconciliation or reconcInfo)
            for rec_elem in xml_data.iter():
                tag = rec_elem.tag.split('}')[-1] if '}' in rec_elem.tag else rec_elem.tag
                if 'intreconciliation' in tag.lower() or 'reconcinfo' in tag.lower():
                    try:
                        child_map = {}
                        for child in rec_elem:
                            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            child_map[child_tag.lower()] = child

                        # Get tank info
                        fuel_tank = child_map.get('fueltank')
                        if fuel_tank is None:
                            continue

                        tank_id = fuel_tank.get('sysid') or fuel_tank.get('id')
                        product = fuel_tank.text.strip() if fuel_tank.text else f'Tank {tank_id}'

                        # Extract reconciliation values
                        def get_float(keys):
                            for key in keys:
                                elem = child_map.get(key)
                                if elem is not None and elem.text:
                                    try:
                                        return float(elem.text)
                                    except ValueError:
                                        pass
                            return 0.0

                        begin_vol = get_float(['beginvolume', 'beginninginventory', 'startvolume'])
                        end_vol = get_float(['endvolume', 'endinginventory', 'currentvolume'])
                        dispensed = get_float(['totaldispensed', 'dispensed', 'sold'])

                        # Calculate variance: end - begin + dispensed
                        # If end = begin - dispensed, variance = 0 (perfect)
                        # Positive variance = gain (e.g., delivery or measurement error)
                        # Negative variance = loss (potential theft, leak, or measurement error)
                        variance = end_vol - begin_vol + dispensed

                        # Calculate variance percentage
                        variance_pct = (variance / begin_vol * 100) if begin_vol > 0 else 0.0

                        if tank_id:
                            reconciliation.append({
                                'tank_id': tank_id,
                                'product': product,
                                'begin_volume': round(begin_vol, 0),
                                'end_volume': round(end_vol, 0),
                                'dispensed': round(dispensed, 0),
                                'variance': round(variance, 0),
                                'variance_pct': round(variance_pct, 2)
                            })

                    except Exception as e:
                        logger.error(f"[{self.ip}] Error parsing reconciliation element: {e}")
                        continue

            logger.debug(f"[{self.ip}] Parsed {len(reconciliation)} tank reconciliation records")
            return reconciliation

        except etree.XMLSyntaxError as e:
            logger.error(f"[{self.ip}] XML parse error in tank reconciliation: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.ip}] Unexpected error parsing tank reconciliation: {e}")
            return []

    def parse_tank_deliveries(self, xml_content):
        """
        Parse tank monitor XML to extract delivery data.

        Returns:
            List of dicts with delivery data:
            [{
                'tank_id': 1,
                'product': 'UNLEADED',
                'delivery_volume': 5000,
                'delivery_date': '2026-01-23',
                'before_volume': 3000,
                'after_volume': 8000
            }]
        """
        if xml_content is None:
            return []

        try:
            xml_data = etree.fromstring(xml_content)
            deliveries = []

            # Find delivery elements (intDelivery or deliveryInfo)
            for del_elem in xml_data.iter():
                tag = del_elem.tag.split('}')[-1] if '}' in del_elem.tag else del_elem.tag
                if 'intdelivery' in tag.lower() or 'deliveryinfo' in tag.lower() or 'delivery' == tag.lower():
                    try:
                        child_map = {}
                        for child in del_elem:
                            child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                            child_map[child_tag.lower()] = child

                        # Get tank info
                        fuel_tank = child_map.get('fueltank')
                        tank_id = None
                        product = 'Unknown'

                        if fuel_tank is not None:
                            tank_id = fuel_tank.get('sysid') or fuel_tank.get('id')
                            product = fuel_tank.text.strip() if fuel_tank.text else f'Tank {tank_id}'
                        else:
                            # Try to get tank_id from attribute
                            tank_id = del_elem.get('tankId') or del_elem.get('sysid')

                        if tank_id is None:
                            continue

                        def get_float(keys):
                            for key in keys:
                                elem = child_map.get(key)
                                if elem is not None and elem.text:
                                    try:
                                        return float(elem.text)
                                    except ValueError:
                                        pass
                            return 0.0

                        def get_text(keys):
                            for key in keys:
                                elem = child_map.get(key)
                                if elem is not None and elem.text:
                                    return elem.text.strip()
                            return ''

                        delivery_vol = get_float(['deliveryvolume', 'volume', 'deliveredvolume', 'qty'])
                        before_vol = get_float(['beforevolume', 'startvolume', 'previousvolume'])
                        after_vol = get_float(['aftervolume', 'endvolume', 'newvolume'])
                        delivery_date = get_text(['deliverydate', 'date', 'datetime'])

                        # Calculate delivery volume if not directly available
                        if delivery_vol == 0 and after_vol > before_vol:
                            delivery_vol = after_vol - before_vol

                        if delivery_vol > 0:
                            deliveries.append({
                                'tank_id': tank_id,
                                'product': product,
                                'delivery_volume': round(delivery_vol, 0),
                                'delivery_date': delivery_date,
                                'before_volume': round(before_vol, 0),
                                'after_volume': round(after_vol, 0)
                            })

                    except Exception as e:
                        logger.error(f"[{self.ip}] Error parsing delivery element: {e}")
                        continue

            logger.debug(f"[{self.ip}] Parsed {len(deliveries)} tank deliveries")
            return deliveries

        except etree.XMLSyntaxError as e:
            logger.error(f"[{self.ip}] XML parse error in tank deliveries: {e}")
            return []
        except Exception as e:
            logger.error(f"[{self.ip}] Unexpected error parsing tank deliveries: {e}")
            return []

    def has_tls_data(self, xml_content):
        """
        Check if the tank monitor XML contains valid TLS data.
        Improved detection that matches webapp logic.

        Returns:
            Tuple of (has_tls: bool, tank_count: int)
        """
        if xml_content is None:
            return False, 0

        try:
            xml_data = etree.fromstring(xml_content)

            # Check for Fault response first
            fault = xml_data.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
            if fault is not None:
                return False, 0

            # Check for tankMonitorType (indicates TLS is configured)
            tls_type = None
            for elem in xml_data.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if tag.lower() == 'tankmonitortype':
                    tls_type = elem.text
                    break

            # Count inventory info elements (tanks with data)
            tank_count = 0
            for elem in xml_data.iter():
                tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
                if 'inventoryinfo' in tag.lower():
                    tank_count += 1

            # TLS is online if we have tank data OR if tankMonitorType exists with valid value
            has_tls = tank_count > 0 or (tls_type is not None and tls_type.strip() != '')

            return has_tls, tank_count

        except Exception as e:
            logger.error(f"[{self.ip}] Error checking TLS data: {e}")
            return False, 0

    @classmethod
    def reset_failed_attempts(cls):
        """Reset failed attempts counter for all IPs."""
        if cls._failed_attempts:
            blocked_count = sum(1 for v in cls._failed_attempts.values() if v >= 2)
            if blocked_count > 0:
                logger.info(f"Resetting failed attempts - {blocked_count} commander(s) were blocked")
            cls._failed_attempts.clear()
        logger.debug("Reset failed attempts counter for all commanders.")
