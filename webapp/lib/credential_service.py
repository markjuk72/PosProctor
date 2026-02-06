"""
POSProctor Unified Credential Service

Provides consistent credential management across all POSProctor services.
Credential priority:
1. Bitwarden (source of truth) - fetched and cached
2. Local database cache (encrypted)
3. Environment variables (fallback for initial setup only)

This module should be copied to each service that needs credentials.
"""

import os
import sqlite3
import hashlib
import base64
import time
import logging
import requests
from threading import Lock
from datetime import datetime
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# Credential cache TTL in seconds (5 minutes)
CREDENTIAL_CACHE_TTL = 300

# Bitwarden item name mapping
BITWARDEN_ITEM_MAP = {
    'admin': 'Commander - Admin',
    # Add additional Bitwarden item mappings here as needed
    # 'username': 'Commander - Username',
}


class CredentialService:
    """
    Unified credential management service.

    Provides a single source of truth for Commander credentials across
    all POSProctor services (monitoring, tlog, webapp).
    """

    # Class-level cache for credentials
    _credential_cache: Dict[str, Dict] = {}
    _cache_lock = Lock()

    def __init__(
        self,
        db_path: str = None,
        bitwarden_url: str = None,
        default_username: str = 'posproctor'
    ):
        """
        Initialize the credential service.

        Args:
            db_path: Path to SQLite database for credential caching
            bitwarden_url: URL of the Bitwarden serve API
            default_username: Default Commander username to use
        """
        self.db_path = db_path or os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')
        self.bitwarden_url = bitwarden_url or os.getenv('BITWARDEN_URL', 'http://bitwarden-serve:8087')
        self.default_username = default_username
        self._ensure_credential_table()

    def _ensure_credential_table(self):
        """Ensure the credential cache table exists in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS credential_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_encrypted TEXT NOT NULL,
                    source TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_verified TIMESTAMP,
                    bitwarden_item_name TEXT
                )
            ''')
            conn.commit()
            conn.close()
            logger.debug("Credential cache table ready")
        except Exception as e:
            logger.error(f"Failed to create credential cache table: {e}")

    def _get_encryption_key(self) -> bytes:
        """
        Get the encryption key for credential storage.
        Uses a combination of environment-based secret and machine ID.
        """
        secret = os.getenv('FLASK_SECRET_KEY', os.getenv('CREDENTIAL_ENCRYPTION_KEY', 'default-key'))
        machine_id = os.getenv('HOSTNAME', 'posproctor')
        combined = f"{secret}:{machine_id}"
        return hashlib.sha256(combined.encode()).digest()

    def _encrypt_password(self, password: str) -> str:
        """Simple XOR-based encryption for password storage."""
        key = self._get_encryption_key()
        encrypted = bytes(a ^ b for a, b in zip(password.encode(), key * (len(password) // len(key) + 1)))
        return base64.b64encode(encrypted).decode()

    def _decrypt_password(self, encrypted: str) -> str:
        """Decrypt a stored password."""
        key = self._get_encryption_key()
        decoded = base64.b64decode(encrypted.encode())
        decrypted = bytes(a ^ b for a, b in zip(decoded, key * (len(decoded) // len(key) + 1)))
        return decrypted.decode()

    def _hash_password(self, password: str) -> str:
        """Create a hash of the password for change detection."""
        return hashlib.sha256(password.encode()).hexdigest()[:16]

    def _get_cached_credential(self, username: str) -> Optional[Tuple[str, str]]:
        """
        Get credential from in-memory cache.

        Returns:
            Tuple of (username, password) if valid cache exists, None otherwise
        """
        with self._cache_lock:
            cache_entry = self._credential_cache.get(username)
            if cache_entry:
                if time.time() - cache_entry['timestamp'] < CREDENTIAL_CACHE_TTL:
                    logger.debug(f"Using in-memory cached credential for {username}")
                    return cache_entry['username'], cache_entry['password']
                else:
                    del self._credential_cache[username]
        return None

    def _set_cached_credential(self, username: str, password: str):
        """Store credential in in-memory cache."""
        with self._cache_lock:
            self._credential_cache[username] = {
                'username': username,
                'password': password,
                'timestamp': time.time()
            }

    def _get_db_credential(self, username: str) -> Optional[Tuple[str, str]]:
        """
        Get credential from database cache.

        Returns:
            Tuple of (username, password) if exists, None otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, password_encrypted, last_updated
                FROM credential_cache
                WHERE username = ?
            ''', (username,))
            row = cursor.fetchone()
            conn.close()

            if row:
                stored_username, encrypted_password, last_updated = row
                password = self._decrypt_password(encrypted_password)
                logger.debug(f"Retrieved credential for {username} from database cache (updated: {last_updated})")
                return stored_username, password
            return None
        except Exception as e:
            logger.error(f"Failed to get credential from database: {e}")
            return None

    def _set_db_credential(self, username: str, password: str, source: str, bitwarden_item: str = None):
        """Store credential in database cache."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            encrypted = self._encrypt_password(password)
            password_hash = self._hash_password(password)

            cursor.execute('''
                INSERT OR REPLACE INTO credential_cache
                (username, password_hash, password_encrypted, source, last_updated, bitwarden_item_name)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (username, password_hash, encrypted, source, bitwarden_item))

            conn.commit()
            conn.close()
            logger.info(f"Stored credential for {username} in database cache (source: {source})")
        except Exception as e:
            logger.error(f"Failed to store credential in database: {e}")

    def _fetch_from_bitwarden(self, username: str) -> Optional[Tuple[str, str]]:
        """
        Fetch credential from Bitwarden vault.

        Args:
            username: The Commander username (e.g., 'posproctor')

        Returns:
            Tuple of (username, password) if found, None otherwise
        """
        item_name = BITWARDEN_ITEM_MAP.get(username)
        if not item_name:
            logger.warning(f"No Bitwarden item mapping for username: {username}")
            return None

        try:
            # Check if Bitwarden service is available
            health_url = f"{self.bitwarden_url}/status"
            response = requests.get(health_url, timeout=5)
            if response.status_code != 200:
                logger.warning("Bitwarden service not available")
                return None

            # Fetch all items and find the matching one
            items_url = f"{self.bitwarden_url}/list/object/items"
            response = requests.get(items_url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Failed to list Bitwarden items: {response.status_code}")
                return None

            items = response.json().get('data', {}).get('data', [])

            for item in items:
                if item.get('name') == item_name:
                    login = item.get('login', {})
                    bw_username = login.get('username')
                    bw_password = login.get('password')

                    if bw_username and bw_password:
                        logger.info(f"Retrieved credential for {username} from Bitwarden ({item_name})")
                        return bw_username, bw_password
                    else:
                        logger.error(f"Bitwarden item '{item_name}' has no login credentials")
                        return None

            logger.warning(f"Bitwarden item not found: {item_name}")
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to connect to Bitwarden: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching from Bitwarden: {e}")
            return None

    def _get_env_credential(self) -> Optional[Tuple[str, str]]:
        """
        Get credential from environment variables.
        This is the fallback for initial setup or when other sources unavailable.

        Returns:
            Tuple of (username, password) if env vars set, None otherwise
        """
        username = os.getenv('COMMANDER_USERNAME')
        password = os.getenv('COMMANDER_PASSWORD')

        if username and password:
            logger.debug(f"Using credential from environment variables for {username}")
            return username, password
        return None

    def get_commander_credentials(self, username: str = None) -> Optional[Dict[str, str]]:
        """
        Get Commander credentials using priority-based retrieval.

        Priority order:
        1. In-memory cache (if not expired)
        2. Bitwarden (source of truth)
        3. Database cache (if Bitwarden unavailable)
        4. Environment variables (fallback)

        Args:
            username: Optional username override (defaults to posproctor)

        Returns:
            Dict with 'username' and 'password' keys, or None if not found
        """
        target_username = username or self.default_username

        # 1. Check in-memory cache
        cached = self._get_cached_credential(target_username)
        if cached:
            return {'username': cached[0], 'password': cached[1], 'source': 'cache'}

        # 2. Try Bitwarden (source of truth)
        bitwarden_cred = self._fetch_from_bitwarden(target_username)
        if bitwarden_cred:
            bw_user, bw_pass = bitwarden_cred
            # Update caches
            self._set_cached_credential(bw_user, bw_pass)
            self._set_db_credential(bw_user, bw_pass, 'bitwarden', BITWARDEN_ITEM_MAP.get(target_username))
            return {'username': bw_user, 'password': bw_pass, 'source': 'bitwarden'}

        # 3. Try database cache
        db_cred = self._get_db_credential(target_username)
        if db_cred:
            db_user, db_pass = db_cred
            self._set_cached_credential(db_user, db_pass)
            return {'username': db_user, 'password': db_pass, 'source': 'database'}

        # 4. Fallback to environment variables
        env_cred = self._get_env_credential()
        if env_cred:
            env_user, env_pass = env_cred
            # Store in caches for next time
            self._set_cached_credential(env_user, env_pass)
            self._set_db_credential(env_user, env_pass, 'environment')
            return {'username': env_user, 'password': env_pass, 'source': 'environment'}

        logger.error(f"No credentials found for {target_username}")
        return None

    def refresh_credentials(self, username: str = None) -> bool:
        """
        Force refresh credentials from Bitwarden.

        Args:
            username: Optional username to refresh (defaults to posproctor)

        Returns:
            True if refresh successful, False otherwise
        """
        target_username = username or self.default_username

        # Clear in-memory cache
        with self._cache_lock:
            if target_username in self._credential_cache:
                del self._credential_cache[target_username]

        # Fetch fresh from Bitwarden
        bitwarden_cred = self._fetch_from_bitwarden(target_username)
        if bitwarden_cred:
            bw_user, bw_pass = bitwarden_cred
            self._set_cached_credential(bw_user, bw_pass)
            self._set_db_credential(bw_user, bw_pass, 'bitwarden', BITWARDEN_ITEM_MAP.get(target_username))
            logger.info(f"Refreshed credentials for {target_username} from Bitwarden")
            return True

        logger.warning(f"Failed to refresh credentials for {target_username} from Bitwarden")
        return False

    def update_cached_password(self, username: str, new_password: str):
        """
        Update the locally cached password after a password rotation.
        Called after successful password change on all commanders.

        Args:
            username: The username whose password was changed
            new_password: The new password
        """
        # Update in-memory cache
        self._set_cached_credential(username, new_password)

        # Update database cache
        self._set_db_credential(username, new_password, 'rotation', BITWARDEN_ITEM_MAP.get(username))

        logger.info(f"Updated cached password for {username} after rotation")

    def clear_cache(self, username: str = None):
        """
        Clear credential cache.

        Args:
            username: Optional username to clear (clears all if not specified)
        """
        with self._cache_lock:
            if username:
                if username in self._credential_cache:
                    del self._credential_cache[username]
            else:
                self._credential_cache.clear()

        logger.info(f"Cleared credential cache {'for ' + username if username else '(all)'}")


# Singleton instance for easy access
_credential_service: Optional[CredentialService] = None


def get_credential_service() -> CredentialService:
    """Get the singleton credential service instance."""
    global _credential_service
    if _credential_service is None:
        _credential_service = CredentialService()
    return _credential_service


def get_commander_credentials(username: str = None) -> Optional[Dict[str, str]]:
    """
    Convenience function to get Commander credentials.

    Args:
        username: Optional username (defaults to posproctor)

    Returns:
        Dict with 'username' and 'password' keys, or None
    """
    service = get_credential_service()
    return service.get_commander_credentials(username)
