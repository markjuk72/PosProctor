"""
Verifone Commander TLOG Client
Handles authentication and transaction log downloads
"""

import requests
from lxml import etree
import logging
import urllib3
import gzip
import io

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class VerifoneClient:
    """Client for interacting with Verifone Commander TLOG API."""

    def __init__(self, ip, username, password, timeout=30):
        self.ip = ip
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

    def get_token(self):
        """Authenticate and retrieve session token."""
        logger.info(f"[{self.ip}] Authenticating...")
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"

        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()
            root = etree.fromstring(r.content)
            token = root.findtext(".//cookie")

            if not token:
                logger.error(f"[{self.ip}] No token found in response")
                return None

            logger.info(f"[{self.ip}] Authentication successful")
            return token

        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Authentication failed: {e}")
            return None

    def release_token(self, token):
        """Release authentication token."""
        if not token:
            return

        logger.debug(f"[{self.ip}] Releasing token")
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=release&cookie={token}"

        try:
            self.session.get(url, verify=False, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            logger.warning(f"[{self.ip}] Failed to release token: {e}")

    def get_report_list(self, token, period=None):
        """
        Get list of available transaction log reports.

        Uses vtlogpdlist command to get available TLOG periods.

        Args:
            token: Authentication token
            period: Filter by period type (1=shift, 2=day, None=all)

        Returns:
            List of report dictionaries with 'filename', 'period', 'size' keys
        """
        logger.info(f"[{self.ip}] Fetching report list (period filter: {period})")

        # Use vtlogpdlist command to list available TLOGs
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vtlogpdlist&cookie={token}"

        try:
            r = self.session.get(url, verify=False, timeout=self.timeout)
            r.raise_for_status()

            logger.debug(f"[{self.ip}] vtlogpdlist response (first 500 chars): {r.content[:500]}")

            root = etree.fromstring(r.content)

            # Check for fault
            fault = root.find(".//{urn:vfi-sapphire:np.domain.2001-07-01}Fault")
            if fault is None:
                fault = root.find(".//{*}Fault")

            if fault is not None:
                fault_string = fault.findtext(".//{*}faultstring", "") or fault.findtext(".//{*}message", "Unknown error")
                logger.error(f"[{self.ip}] API fault: {fault_string}")
                return []

            # Parse periodInfo elements from vtlogpdlist response
            # Example structure:
            # <periodInfo>
            #   <vs:period sysid="1"/>
            #   <name>2026-01-14.611</name>
            #   <desc>2026-01-14 (Shift-611)</desc>
            #   <reportParameters>
            #     <reportParameter name="period">1</reportParameter>
            #     <reportParameter name="filename">2026-01-14.611</reportParameter>
            #   </reportParameters>
            # </periodInfo>
            reports = []
            for period_elem in root.findall('.//{*}periodInfo'):
                name = period_elem.findtext('.//{*}name', '') or period_elem.findtext('.//name', '')
                desc = period_elem.findtext('.//{*}desc', '') or period_elem.findtext('.//desc', '')

                # Skip "current" as it's not a downloadable report
                if name == 'current':
                    continue

                # Extract period type from reportParameters
                report_period = '1'  # Default to shift
                for param in period_elem.findall('.//{*}reportParameter'):
                    param_name = param.get('name', '')
                    if param_name == 'period':
                        report_period = param.text or '1'

                # Apply period filter if specified
                # period=1 is shift, period=2 is day
                if period is not None and str(report_period) != str(period):
                    continue

                if name:
                    reports.append({
                        'filename': name,
                        'period': report_period,
                        'description': desc,
                        'size': 0  # vtlogpdlist doesn't provide size
                    })

            logger.info(f"[{self.ip}] Found {len(reports)} reports")
            return sorted(reports, key=lambda x: x['filename'], reverse=True)

        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Failed to fetch report list: {e}")
            return []

    def download_report(self, token, report):
        """
        Download a specific transaction log report.

        Uses vtransset command with filename and period parameters.

        Args:
            token: Authentication token
            report: Report dictionary from get_report_list()

        Returns:
            Decompressed XML content as bytes, or None on failure
        """
        filename = report['filename']
        period = report.get('period', '1')
        logger.info(f"[{self.ip}] Downloading report: {filename} (period={period})")

        # Use vtransset command with filename and period parameters
        url = f"https://{self.ip}/cgi-bin/CGILink?cmd=vtransset&cookie={token}&filename={filename}&period={period}"

        try:
            r = self.session.get(url, verify=False, timeout=300)  # Longer timeout for downloads
            r.raise_for_status()

            # Check if response is gzipped
            content_encoding = r.headers.get('Content-Encoding', '')
            content_type = r.headers.get('Content-Type', '')

            if 'gzip' in content_encoding or content_type == 'application/x-gzip':
                # Decompress gzip content
                logger.debug(f"[{self.ip}] Decompressing gzipped report")
                try:
                    decompressed = gzip.decompress(r.content)
                    logger.info(f"[{self.ip}] Download successful ({len(decompressed)} bytes)")
                    return decompressed
                except Exception as e:
                    logger.error(f"[{self.ip}] Failed to decompress: {e}")
                    return None
            else:
                # Return raw content
                logger.info(f"[{self.ip}] Download successful ({len(r.content)} bytes)")
                return r.content

        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.ip}] Download failed: {e}")
            return None
