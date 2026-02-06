"""
Database Manager for POSProctor 2.0
Simple SQLite database for configuration storage
"""

import sqlite3
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._ensure_database()

    def _ensure_database(self):
        """Create database and tables if they don't exist."""
        db_exists = Path(self.db_path).exists()

        # Create directory if needed
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        if not db_exists:
            logger.info(f"Creating new database at {self.db_path}")
            self._create_tables()
            self._insert_defaults()
        else:
            logger.info(f"Using existing database at {self.db_path}")

    def _create_tables(self):
        """Create database schema."""
        cursor = self.conn.cursor()

        # Commanders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commanders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                store_name TEXT NOT NULL,
                group_name TEXT,
                brand TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Credentials table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                description TEXT,
                is_default BOOLEAN DEFAULT 0
            )
        ''')

        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                data_type TEXT DEFAULT 'string',
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.commit()
        logger.info("Database tables created")

    def _insert_defaults(self):
        """Insert default settings and credentials."""
        cursor = self.conn.cursor()

        # Default credentials from environment
        username = os.getenv('COMMANDER_USERNAME', 'posproctor')
        password = os.getenv('COMMANDER_PASSWORD', 'changeme')

        cursor.execute('''
            INSERT INTO credentials (username, password, description, is_default)
            VALUES (?, ?, ?, 1)
        ''', (username, password, 'Default Commander credentials'))

        # Default settings
        settings = [
            ('scrape_interval_minutes', str(os.getenv('POLL_INTERVAL', '300')), 'integer', 'Polling interval in seconds'),
            ('timeout_seconds', str(os.getenv('REQUEST_TIMEOUT', '30')), 'integer', 'API request timeout'),
            ('max_workers', str(os.getenv('WORKER_THREADS', '10')), 'integer', 'Max concurrent workers'),
            ('xml_debug_enabled', str(os.getenv('XML_DEBUG_ENABLED', 'false')).lower(), 'boolean', 'Enable XML debug storage'),
            ('xml_debug_retention_minutes', str(os.getenv('XML_DEBUG_RETENTION_MINUTES', '60')), 'integer', 'XML debug retention period'),
        ]

        cursor.executemany('''
            INSERT INTO settings (key, value, data_type, description)
            VALUES (?, ?, ?, ?)
        ''', settings)

        self.conn.commit()
        logger.info("Default settings and credentials inserted")

    def get_commanders(self, enabled_only: bool = True) -> List[Dict]:
        """Get all commanders from database."""
        cursor = self.conn.cursor()

        if enabled_only:
            cursor.execute('SELECT * FROM commanders WHERE enabled = 1')
        else:
            cursor.execute('SELECT * FROM commanders')

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_default_credentials(self) -> Optional[Dict]:
        """Get default credentials."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM credentials WHERE is_default = 1 LIMIT 1')
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_setting(self, key: str, default=None):
        """Get a setting value."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value, data_type FROM settings WHERE key = ?', (key,))
        row = cursor.fetchone()

        if not row:
            return default

        value = row['value']
        data_type = row['data_type']

        # Convert based on data type
        if data_type == 'integer':
            return int(value)
        elif data_type == 'boolean':
            return value.lower() in ('true', '1', 'yes')
        else:
            return value

    def add_commander(self, ip: str, store_name: str, group_name: str = None, brand: str = None) -> int:
        """Add a new commander."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO commanders (ip, store_name, group_name, brand)
            VALUES (?, ?, ?, ?)
        ''', (ip, store_name, group_name, brand))
        self.conn.commit()
        return cursor.lastrowid

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
