#!/usr/bin/env python3
"""
Bitwarden Service Manager
Manages the bw serve process for backend service integration.
"""

import subprocess
import time
import os
import sys
import signal
import logging
import requests
import atexit
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BitwardenServiceManager:
    """Manages the bw serve background process."""

    def __init__(self, port=8087, hostname="localhost"):
        """
        Initialize service manager.

        Args:
            port: Port for bw serve to listen on
            hostname: Hostname to bind to
        """
        self.port = port
        self.hostname = hostname
        self.base_url = f"http://{hostname}:{port}"
        self.process = None
        self.pidfile = Path("/tmp/bw_serve.pid")
        self.session_token = None

        # Register cleanup on exit
        atexit.register(self.cleanup)

    def authenticate(self):
        """
        Authenticate with Bitwarden and get session token.
        Requires BW_CLIENTID, BW_CLIENTSECRET, and BW_PASSWORD environment variables.

        Returns:
            str: Session token or None on failure
        """
        client_id = os.getenv('BW_CLIENTID')
        client_secret = os.getenv('BW_CLIENTSECRET')
        password = os.getenv('BW_PASSWORD')
        server = os.getenv('BW_SERVER', 'https://vault.bitwarden.com')

        if not all([client_id, client_secret, password]):
            logger.error("Missing Bitwarden credentials. Set BW_CLIENTID, BW_CLIENTSECRET, and BW_PASSWORD")
            return None

        try:
            # Configure server if not default
            if server != 'https://vault.bitwarden.com':
                logger.info(f"Configuring Bitwarden server: {server}")
                subprocess.run(
                    ['bw', 'config', 'server', server],
                    check=True,
                    capture_output=True,
                    timeout=30
                )

            # Login with API credentials
            logger.info("Logging in to Bitwarden...")
            result = subprocess.run(
                ['bw', 'login', '--apikey'],
                input=f"{client_id}\n{client_secret}\n",
                text=True,
                capture_output=True,
                timeout=30
            )

            # Already logged in is OK
            if result.returncode != 0 and "already logged in" not in result.stderr.lower():
                logger.error(f"Login failed: {result.stderr}")
                return None

            # Unlock vault and get session token
            logger.info("Unlocking vault...")
            result = subprocess.run(
                ['bw', 'unlock', password, '--raw'],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Unlock failed: {result.stderr}")
                return None

            session_token = result.stdout.strip()
            logger.info("Successfully authenticated with Bitwarden")
            return session_token

        except subprocess.TimeoutExpired:
            logger.error("Authentication timed out")
            return None
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None

    def start(self):
        """
        Start the bw serve process.

        Returns:
            bool: True if started successfully, False otherwise
        """
        # Check if already running
        if self.is_running():
            logger.info("Bitwarden serve is already running")
            return True

        # Authenticate first
        logger.info("Authenticating with Bitwarden...")
        self.session_token = self.authenticate()
        if not self.session_token:
            logger.error("Failed to authenticate. Cannot start service.")
            return False

        # Start bw serve
        try:
            logger.info(f"Starting bw serve on {self.hostname}:{self.port}...")

            # Set session token in environment
            env = os.environ.copy()
            env['BW_SESSION'] = self.session_token

            # Start serve process in background
            self.process = subprocess.Popen(
                ['bw', 'serve', '--hostname', self.hostname, '--port', str(self.port)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Write PID file
            self.pidfile.write_text(str(self.process.pid))
            logger.info(f"Started bw serve with PID {self.process.pid}")

            # Wait for service to be ready
            if self.wait_for_ready(timeout=10):
                logger.info(f"Bitwarden service is ready at {self.base_url}")
                return True
            else:
                logger.error("Service failed to become ready")
                self.stop()
                return False

        except Exception as e:
            logger.error(f"Failed to start service: {e}")
            return False

    def wait_for_ready(self, timeout=10):
        """
        Wait for the service to be ready to accept connections.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            bool: True if service is ready, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/status", timeout=2)
                if response.status_code == 200:
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(0.5)
        return False

    def is_running(self):
        """
        Check if bw serve is currently running.

        Returns:
            bool: True if running, False otherwise
        """
        # Check by attempting connection
        try:
            response = requests.get(f"{self.base_url}/status", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def stop(self):
        """Stop the bw serve process."""
        if self.process:
            logger.info(f"Stopping bw serve (PID {self.process.pid})...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate, killing...")
                self.process.kill()
                self.process.wait()
            logger.info("Service stopped")

        # Clean up PID file
        if self.pidfile.exists():
            self.pidfile.unlink()

        self.process = None

    def restart(self):
        """Restart the service."""
        logger.info("Restarting Bitwarden service...")
        self.stop()
        time.sleep(1)
        return self.start()

    def cleanup(self):
        """Cleanup on exit."""
        if self.process:
            self.stop()

    def status(self):
        """
        Get service status.

        Returns:
            dict: Status information
        """
        running = self.is_running()
        return {
            'running': running,
            'url': self.base_url if running else None,
            'pid': self.process.pid if self.process else None
        }


def main():
    """CLI interface for service management."""
    if len(sys.argv) < 2:
        print("Usage: python bitwarden_service.py {start|stop|restart|status}")
        sys.exit(1)

    command = sys.argv[1].lower()
    port = int(os.getenv('BW_SERVE_PORT', '8087'))
    hostname = os.getenv('BW_SERVE_HOSTNAME', 'localhost')

    manager = BitwardenServiceManager(port=port, hostname=hostname)

    if command == 'start':
        if manager.start():
            logger.info("Service started successfully")
            # Keep running in foreground
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                manager.stop()
        else:
            logger.error("Failed to start service")
            sys.exit(1)

    elif command == 'stop':
        manager.stop()

    elif command == 'restart':
        if manager.restart():
            logger.info("Service restarted successfully")
        else:
            logger.error("Failed to restart service")
            sys.exit(1)

    elif command == 'status':
        status = manager.status()
        if status['running']:
            print(f"Status: Running")
            print(f"URL: {status['url']}")
            print(f"PID: {status['pid']}")
        else:
            print("Status: Not running")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
