"""
Commander Password Management
Handles password changes for Verifone Commander devices via HTTP API.
Adapted from query_commander.py for webapp integration.
"""

import requests
import urllib3
import logging
import random
import string
import time
from lxml import etree

# Suppress InsecureRequestWarning for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


def validate_user_credentials(ip, username, password, timeout=30):
    """
    Validates user credentials without creating a session token.

    Args:
        ip: Commander IP address
        username: Username to validate
        password: Password to validate
        timeout: Request timeout in seconds

    Returns:
        bool: True if credentials are valid, False otherwise
    """
    logger.info(f"[{ip}] Validating credentials for user '{username}'...")
    url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={username}&passwd={password}"

    try:
        r = requests.get(url, verify=False, timeout=timeout)
        r.raise_for_status()

        try:
            root = etree.fromstring(r.content)

            # Check for error elements
            error_elem = root.find(".//error") or root.find(".//Error") or root.find(".//ERROR")
            if error_elem is not None:
                error_text = error_elem.text or etree.tostring(error_elem, encoding='unicode')
                logger.error(f"[{ip}] Credential validation failed: {error_text}")
                return False

            # Check for cookie/token - indicates successful validation
            token = root.findtext(".//cookie")
            if token:
                logger.info(f"[{ip}] Credential validation successful.")
                # Release the validation token immediately
                release_url = f"https://{ip}/cgi-bin/CGILink?cmd=releaseCredential&cookie={token}"
                try:
                    requests.get(release_url, verify=False, timeout=timeout)
                except:
                    pass  # Don't fail validation if release fails
                return True
            else:
                logger.error(f"[{ip}] No token in validation response.")
                return False

        except etree.XMLSyntaxError as xml_err:
            logger.error(f"[{ip}] Failed to parse validation response: {xml_err}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"[{ip}] Failed to validate credentials: {e}")
        return False


def get_token(ip, username, password, timeout=30):
    """
    Authenticate and retrieve session token.

    Args:
        ip: Commander IP address
        username: Username for authentication
        password: Password for authentication
        timeout: Request timeout in seconds

    Returns:
        str: Session token or None on failure
    """
    logger.info(f"[{ip}] Attempting to authenticate as user '{username}'...")
    url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={username}&passwd={password}"

    try:
        r = requests.get(url, verify=False, timeout=timeout)
        r.raise_for_status()

        try:
            root = etree.fromstring(r.content)

            # Check for error elements
            error_elem = root.find(".//error") or root.find(".//Error") or root.find(".//ERROR")
            if error_elem is not None:
                error_text = error_elem.text or etree.tostring(error_elem, encoding='unicode')
                logger.error(f"[{ip}] Authentication failed: {error_text}")
                return None

            # Look for token
            token = root.findtext(".//cookie")
            if not token:
                logger.error(f"[{ip}] No token found in response.")
                return None

            logger.info(f"[{ip}] Authentication successful.")
            return token

        except etree.XMLSyntaxError as xml_err:
            logger.error(f"[{ip}] Failed to parse token response: {xml_err}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"[{ip}] Failed to get token: {e}")
        return None


def release_credential(ip, token, timeout=30):
    """
    Release the session token.

    Args:
        ip: Commander IP address
        token: Session token to release
        timeout: Request timeout in seconds
    """
    if not token:
        return

    logger.info(f"[{ip}] Releasing session token...")
    url = f"https://{ip}/cgi-bin/CGILink?cmd=releaseCredential&cookie={token}"

    try:
        r = requests.get(url, verify=False, timeout=timeout)
        r.raise_for_status()
        logger.info(f"[{ip}] Token released successfully.")
    except requests.exceptions.RequestException as e:
        logger.warning(f"[{ip}] Failed to release token: {e}")


def generate_password(length):
    """
    Generates a random alphanumeric password of a specific length.

    Commander password constraints:
    - Length: 7-10 characters
    - Must contain both letters and digits

    Args:
        length: Desired password length (will be clamped to 7-10)

    Returns:
        str: Generated password
    """
    # Clamp length to Commander's 7-10 character requirement
    length = max(7, min(10, length))

    # Ensure password contains at least one letter and one digit
    while True:
        password = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))
        has_letter = any(c.isalpha() for c in password)
        has_digit = any(c.isdigit() for c in password)
        if has_letter and has_digit:
            return password


def change_password(ip, token, username, old_password, new_password, timeout=30):
    """
    Changes the password for the current user using Verifone's XML format.

    Args:
        ip: Commander IP address
        token: Valid session token
        username: Username to change password for
        old_password: Current password
        new_password: New password
        timeout: Request timeout in seconds

    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"[{ip}] Attempting to change password for user '{username}'...")
    url = f"https://{ip}/cgi-bin/CGIUplink?cmd=changepasswd&cookie={token}"

    # Use the official Verifone XML format
    xml_payload = f"<?xml version='1.0' encoding='UTF-8' ?><domain:passwdConfig xmlns:domain='urn:vfi-sapphire:np.domain.2001-07-01'><user name='{username}'><passwd oldValue='{old_password}' newValue='{new_password}'/></user></domain:passwdConfig>"

    logger.debug(f"[{ip}] Sending XML payload")

    headers = {'Content-Type': 'application/xml'}

    try:
        r = requests.post(url, data=xml_payload.encode('utf-8'), headers=headers, verify=False, timeout=timeout)

        logger.info(f"[{ip}] Password change request sent. HTTP Status: {r.status_code}")

        response_content = r.content.decode(errors='ignore').strip()

        if response_content:
            try:
                root = etree.fromstring(r.content)

                # Check for various error elements
                error_elem = (root.find(".//error") or root.find(".//Error") or
                             root.find(".//ERROR") or root.find(".//fault") or
                             root.find(".//exception"))
                if error_elem is not None:
                    error_text = error_elem.text or etree.tostring(error_elem, encoding='unicode')
                    logger.error(f"[{ip}] XML contains error: {error_text}")
                    return False

                # Check for status elements indicating failure
                status_elem = root.find(".//status") or root.find(".//Status")
                if status_elem is not None:
                    status_text = status_elem.text or etree.tostring(status_elem, encoding='unicode')
                    if status_text and any(fail_word in status_text.lower() for fail_word in ['fail', 'error', 'invalid', 'denied']):
                        logger.error(f"[{ip}] Status indicates failure: {status_text}")
                        return False

            except etree.XMLSyntaxError as xml_err:
                logger.error(f"[{ip}] Failed to parse XML response: {xml_err}")

        # Enhanced status code handling
        if r.status_code == 200:
            if response_content and 'error' in response_content.lower():
                logger.error(f"[{ip}] HTTP 200 but response contains error")
                return False
            logger.info(f"[{ip}] Password change appears successful (HTTP 200)")
            return True
        elif r.status_code == 401:
            logger.error(f"[{ip}] Unauthorized (401) - token may be invalid")
            return False
        elif r.status_code == 403:
            logger.error(f"[{ip}] Forbidden (403) - insufficient permissions")
            return False
        elif r.status_code == 500:
            logger.error(f"[{ip}] Internal Server Error (500)")
            return False
        else:
            logger.error(f"[{ip}] Password change failed. Status: {r.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"[{ip}] Failed to change password: {e}")
        return False


def rotate_password_on_commander(ip, username, current_password, new_password=None, timeout=30):
    """
    Complete password rotation workflow for a single commander.

    Args:
        ip: Commander IP address
        username: Username to change password for
        current_password: Current password
        new_password: New password (generated if not provided)
        timeout: Request timeout in seconds

    Returns:
        dict: Result with 'success' (bool), 'new_password' (str), 'message' (str)
    """
    logger.info(f"Starting password rotation for user '{username}' on Commander {ip}")

    # Step 1: Get session token with current password
    token = get_token(ip, username, current_password, timeout)
    if not token:
        return {
            'success': False,
            'new_password': None,
            'message': 'Authentication failed with current password'
        }

    # Step 2: Generate new password if not provided
    if not new_password:
        new_password = generate_password(len(current_password))
        logger.info(f"Generated new password of length {len(new_password)}")

    # Step 3: Change password
    if not change_password(ip, token, username, current_password, new_password, timeout):
        release_credential(ip, token, timeout)
        return {
            'success': False,
            'new_password': None,
            'message': 'Password change request failed on commander'
        }

    # Release old session
    release_credential(ip, token, timeout)

    # Step 4: Verify new password
    new_token = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(0.5 * attempt)
        new_token = get_token(ip, username, new_password, timeout)
        if new_token:
            break

    if not new_token:
        return {
            'success': False,
            'new_password': new_password,
            'message': 'Password may have been changed but verification failed'
        }

    # Clean up
    release_credential(ip, new_token, timeout)

    logger.info(f"Password rotation completed successfully for {username}@{ip}")
    return {
        'success': True,
        'new_password': new_password,
        'message': 'Password changed and verified successfully'
    }
