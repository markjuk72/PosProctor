"""
Tank Commander Client - Simplified client for querying Verifone Commander
"""

import requests
import xml.etree.ElementTree as ET
import urllib3
import logging

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class CommanderClient:
    """Simple client for querying Verifone Commander tank data endpoints"""

    def __init__(self, ip, username, password, timeout=30):
        self.ip = ip
        self.base_url = f"https://{ip}/cgi-bin/CGILink"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.cookie = None
        self.session = requests.Session()
        self.session.verify = False
        # Configure connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        self.session.mount('https://', adapter)

    def authenticate(self):
        """Get authentication cookie from Commander"""
        url = f"{self.base_url}?cmd=validate&user={self.username}&passwd={self.password}"
        logger.info(f"Authenticating to {self.ip} with username: {self.username}")
        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                logger.debug(f"Authentication response from {self.ip}: {response.content[:500]}")
                root = ET.fromstring(response.content)
                self.cookie = root.findtext('.//cookie')
                if self.cookie:
                    logger.info(f"Successfully authenticated to {self.ip}")
                    return True
                else:
                    logger.error(f"No cookie in authentication response from {self.ip}")
                    logger.error(f"Response XML: {ET.tostring(root, encoding='unicode')[:500]}")
            else:
                logger.error(f"Authentication failed for {self.ip}: HTTP {response.status_code}")
                logger.error(f"Response: {response.text[:500]}")
        except Exception as e:
            logger.error(f"Authentication exception for {self.ip}: {e}")
        return False

    def query_endpoint(self, cmd, params=None):
        """Query a Commander endpoint

        Args:
            cmd: Command to execute (e.g., 'vtlssite', 'vfuelcfg', 'vrubyrept')
            params: Optional dict of additional parameters

        Returns:
            Response content as bytes, or None if failed
        """
        if not self.cookie:
            logger.error(f"No authentication cookie for {self.ip}, call authenticate() first")
            return None

        url = f"{self.base_url}?cmd={cmd}&cookie={self.cookie}"
        if params:
            for key, value in params.items():
                url += f"&{key}={value}"

        try:
            response = self.session.get(url, timeout=self.timeout)
            if response.status_code == 200:
                return response.content
            else:
                logger.error(f"Query failed for {self.ip} endpoint {cmd}: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Query exception for {self.ip} endpoint {cmd}: {e}")
            return None

    def query_endpoint_xml(self, cmd, params=None):
        """Query a Commander endpoint and return parsed XML

        Args:
            cmd: Command to execute
            params: Optional dict of additional parameters

        Returns:
            ET.Element root node, or None if failed
        """
        content = self.query_endpoint(cmd, params)
        if content:
            try:
                return ET.fromstring(content)
            except ET.ParseError as e:
                logger.error(f"XML parse error for {self.ip} endpoint {cmd}: {e}")
                return None
        return None
