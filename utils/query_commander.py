import requests
import yaml
from lxml import etree
import urllib3
import logging

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_credentials(file_path='credentials.yaml'):
    """Loads credentials from a YAML file."""
    try:
        with open(file_path, 'r') as f:
            credentials = yaml.safe_load(f)
            return credentials['credentials']['username'], credentials['credentials']['password']
    except (FileNotFoundError, KeyError) as e:
        logger.error(f"Error loading credentials from {file_path}: {e}")
        return None, None

def get_token(ip, username, password, timeout=30):
    """Authenticate and retrieve session token."""
    logger.info(f"[{ip}] Attempting to authenticate...")
    url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={username}&passwd={password}"
    try:
        r = requests.get(url, verify=False, timeout=timeout)
        r.raise_for_status()
        token = etree.fromstring(r.content).findtext(".//cookie")
        if not token:
            logger.error(f"[{ip}] No token found in response. Authentication failed.")
            return None
        logger.info(f"[{ip}] Authentication successful. Token received.")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"[{ip}] Failed to get token: {e}")
        return None

def query_api(ip, token, api_command, timeout=30):
    """Query the specified API command."""
    logger.info(f"[{ip}] Querying API command: {api_command}")
    url = f"https://{ip}/cgi-bin/CGILink?cmd={api_command}&cookie={token}"
    try:
        r = requests.get(url, verify=False, timeout=timeout)
        r.raise_for_status()
        return r.content
    except requests.exceptions.RequestException as e:
        logger.error(f"[{ip}] Failed to query API: {e}")
        return None

def main():
    """Main function to run the script."""
    username, password = load_credentials()
    if not username or not password:
        return

    ip = input("Enter the Commander IP address: ")
    api_command = input("Enter the API command (e.g., vforecourtdiagnostics): ")

    token = get_token(ip, username, password)

    if token:
        xml_data = query_api(ip, token, api_command)
        if xml_data:
            output_filename = f"sample_data/{api_command}.xml"
            try:
                with open(output_filename, 'wb') as f:
                    f.write(xml_data)
                logger.info(f"Successfully wrote XML output to {output_filename}")
            except IOError as e:
                logger.error(f"Failed to write to file {output_filename}: {e}")

if __name__ == "__main__":
    main()
