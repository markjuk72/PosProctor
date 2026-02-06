"""
Bitwarden REST API Client for bw serve
Provides service-based access to Bitwarden vault for backend applications.
"""

import requests
import json
import base64
import logging

logger = logging.getLogger(__name__)


class BitwardenAPIClient:
    """Client for interacting with Bitwarden via bw serve REST API."""

    def __init__(self, base_url="http://localhost:8087"):
        """
        Initialize Bitwarden API client.

        Args:
            base_url: Base URL of the bw serve instance (default: http://localhost:8087)
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def health_check(self):
        """
        Check if the Bitwarden serve API is running and responsive.

        Returns:
            bool: True if service is healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"Bitwarden service status: {data.get('data', {}).get('template', {}).get('status')}")
                return True
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return False

    def sync(self):
        """
        Sync the vault with Bitwarden servers.

        Returns:
            bool: True if sync successful, False otherwise
        """
        try:
            response = self.session.post(f"{self.base_url}/sync", timeout=30)
            if response.status_code == 200:
                logger.info("Vault synced successfully")
                return True
            else:
                logger.error(f"Sync failed with status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Sync error: {e}")
            return False

    def list_items(self):
        """
        List all items in the vault.

        Returns:
            list: List of vault items, or None on error
        """
        try:
            response = self.session.get(f"{self.base_url}/list/object/items", timeout=30)
            if response.status_code == 200:
                data = response.json()
                items = data.get('data', {}).get('data', [])
                logger.info(f"Retrieved {len(items)} items from vault")
                return items
            else:
                logger.error(f"Failed to list items: {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing items: {e}")
            return None

    def get_item(self, item_identifier):
        """
        Get a specific item by ID or name.

        Args:
            item_identifier: Item ID (UUID) or item name

        Returns:
            dict: Item data, or None on error
        """
        try:
            response = self.session.get(
                f"{self.base_url}/object/item/{item_identifier}",
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                # For single item endpoint, data is directly under 'data' key
                # (unlike list endpoint which has data.data structure)
                item = data.get('data', {})
                logger.info(f"Retrieved item: {item.get('name')}")
                return item
            else:
                logger.error(f"Failed to get item '{item_identifier}': {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting item '{item_identifier}': {e}")
            return None

    def get_credentials(self, item_identifier):
        """
        Get username and password from a vault item.

        Args:
            item_identifier: Item ID or name

        Returns:
            tuple: (username, password) or (None, None) on error
        """
        item = self.get_item(item_identifier)
        if not item:
            return None, None

        login = item.get('login', {})
        username = login.get('username')
        password = login.get('password')

        if not username or not password:
            logger.error(f"Item '{item_identifier}' does not contain login credentials")
            return None, None

        logger.info(f"Retrieved credentials for user: {username}")
        return username, password

    def update_item(self, item_identifier, item_data):
        """
        Update an existing vault item.

        Args:
            item_identifier: Item ID (UUID) or name
            item_data: Complete item data dict (must include all fields)

        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            # First get the item to ensure we have the ID
            existing_item = self.get_item(item_identifier)
            if not existing_item:
                logger.error(f"Cannot update item '{item_identifier}': item not found")
                return False

            item_id = existing_item.get('id')
            if not item_id:
                logger.error(f"Item '{item_identifier}' has no ID")
                return False

            # Encode the item data as base64 (matching CLI behavior)
            item_json = json.dumps(item_data)
            encoded = base64.b64encode(item_json.encode('utf-8')).decode('utf-8')

            # Send update request
            response = self.session.put(
                f"{self.base_url}/object/item/{item_id}",
                data=encoded,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )

            if response.status_code == 200:
                logger.info(f"Successfully updated item: {item_data.get('name')}")
                return True
            else:
                logger.error(f"Failed to update item: {response.status_code}")
                logger.debug(f"Response: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating item: {e}")
            return False

    def update_password(self, item_identifier, new_password):
        """
        Update the password for a vault item.

        Args:
            item_identifier: Item ID or name
            new_password: New password value

        Returns:
            bool: True if update successful, False otherwise
        """
        # Get the current item
        item = self.get_item(item_identifier)
        if not item:
            logger.error(f"Cannot update password for '{item_identifier}': item not found")
            return False

        # Update the password field
        if 'login' not in item:
            logger.error(f"Item '{item_identifier}' is not a login item")
            return False

        item['login']['password'] = new_password

        # Update the item
        if self.update_item(item_identifier, item):
            logger.info(f"Password updated for item: {item.get('name')}")
            # Sync changes to server
            self.sync()
            return True
        else:
            return False


class BitwardenService:
    """
    Manages the Bitwarden serve process and provides a high-level interface.
    This class is designed for use in backend services like Flask apps.
    """

    def __init__(self, base_url="http://localhost:8087"):
        """
        Initialize Bitwarden service interface.

        Args:
            base_url: URL where bw serve is running
        """
        self.client = BitwardenAPIClient(base_url)

    def is_ready(self):
        """Check if the Bitwarden service is ready."""
        return self.client.health_check()

    def get_credentials(self, item_name):
        """
        Get credentials from Bitwarden vault.

        Args:
            item_name: Name of the vault item

        Returns:
            tuple: (username, password) or (None, None)
        """
        return self.client.get_credentials(item_name)

    def update_password(self, item_name, new_password):
        """
        Update password in Bitwarden vault.

        Args:
            item_name: Name of the vault item
            new_password: New password value

        Returns:
            bool: True if successful, False otherwise
        """
        return self.client.update_password(item_name, new_password)

    def sync(self):
        """Sync vault with Bitwarden servers."""
        return self.client.sync()
