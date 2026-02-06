#!/usr/bin/env python3
"""
Optimized Multi-Store Tank Data Collector
Uses parallel processing for efficient data collection from multiple stores
"""

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import json
import yaml
import time
import ssl
from concurrent.futures import ThreadPoolExecutor
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AsyncCommanderClient:
    """Async client for Verifone Commander API"""

    def __init__(self, store_id, ip, username, password, session):
        self.store_id = store_id
        self.ip = ip
        self.username = username
        self.password = password
        self.session = session
        self.cookie = None
        self.base_url = f"https://{ip}/cgi-bin/CGILink"

    async def authenticate(self):
        """Authenticate and get session cookie"""
        url = f"{self.base_url}?cmd=validate&user={self.username}&passwd={self.password}"
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as response:
                if response.status == 200:
                    content = await response.read()
                    root = ET.fromstring(content)
                    self.cookie = root.findtext('.//cookie')
                    return self.cookie is not None
        except Exception as e:
            logger.error(f"Store {self.store_id} ({self.ip}): Auth failed - {e}")
        return False

    async def query_endpoint(self, cmd, params=None):
        """Query a specific endpoint"""
        if not self.cookie:
            return None

        url = f"{self.base_url}?cmd={cmd}&cookie={self.cookie}"
        if params:
            for key, value in params.items():
                url += f"&{key}={value}"

        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=8), ssl=False) as response:
                if response.status == 200:
                    return await response.read()
        except asyncio.TimeoutError:
            logger.warning(f"Store {self.store_id}: Timeout on {cmd}")
        except Exception as e:
            logger.error(f"Store {self.store_id}: Error on {cmd} - {e}")
        return None

    async def release_credential(self):
        """Release the session cookie"""
        if self.cookie:
            try:
                url = f"{self.base_url}?cmd=releaseCredential&cookie={self.cookie}"
                await self.session.get(url, timeout=aiohttp.ClientTimeout(total=5), ssl=False)
            except:
                pass

    async def collect_all_data(self):
        """Collect all necessary data for this store"""
        start_time = time.time()

        # Authenticate
        if not await self.authenticate():
            return {
                'store_id': self.store_id,
                'ip': self.ip,
                'success': False,
                'error': 'Authentication failed',
                'elapsed': time.time() - start_time
            }

        # Define endpoints to query (only essential ones)
        queries = [
            ('vtlssite', None, 'tls_config'),
            ('vfuelcfg', None, 'fuel_config'),
            ('vrubyrept', {'reptname': 'tankMonitor', 'period': 1, 'reptnum': 1}, 'tank_monitor'),
            # DISABLED: Tank Reconciliation endpoint (11.9s - 42% of total time)
            # Not used in current reports, can re-enable if variance analysis needed
            # ('vrubyrept', {'reptname': 'tankRec', 'period': 1, 'reptnum': 1}, 'tank_rec'),
        ]

        # Execute queries concurrently
        tasks = [self.query_endpoint(cmd, params) for cmd, params, _ in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Release credential
        await self.release_credential()

        elapsed = time.time() - start_time

        # Package results
        data = {
            'store_id': self.store_id,
            'ip': self.ip,
            'success': True,
            'elapsed': elapsed,
            'data': {}
        }

        for (cmd, params, name), result in zip(queries, results):
            if isinstance(result, Exception):
                logger.error(f"Store {self.store_id}: Error in {name} - {result}")
                data['data'][name] = None
            elif result:
                data['data'][name] = result
                data['data'][f'{name}_size'] = len(result)

        logger.info(f"Store {self.store_id} ({self.ip}): Complete in {elapsed:.2f}s")
        return data


class MultiStoreCollector:
    """Manages parallel data collection from multiple stores"""

    def __init__(self, stores_config, credentials, max_concurrent=20):
        self.stores_config = stores_config
        self.credentials = credentials
        self.max_concurrent = max_concurrent
        self.results = []

    async def collect_store_data(self, store, session):
        """Collect data for a single store"""
        client = AsyncCommanderClient(
            store['store_id'],
            store['ip'],
            self.credentials['username'],
            self.credentials['password'],
            session
        )
        return await client.collect_all_data()

    async def collect_all_stores(self):
        """Collect data from all stores in parallel"""
        logger.info(f"Starting collection from {len(self.stores_config)} stores")
        logger.info(f"Max concurrent connections: {self.max_concurrent}")

        start_time = time.time()

        # Create SSL context that doesn't verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Configure connection limits
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent,
            limit_per_host=2,  # Max 2 concurrent connections per store
            ttl_dns_cache=300,
            ssl=ssl_context
        )

        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Create tasks with concurrency limit
            semaphore = asyncio.Semaphore(self.max_concurrent)

            async def bounded_collect(store):
                async with semaphore:
                    return await self.collect_store_data(store, session)

            tasks = [bounded_collect(store) for store in self.stores_config]
            self.results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # Process results
        successful = sum(1 for r in self.results if isinstance(r, dict) and r.get('success', False))
        failed = len(self.results) - successful

        logger.info(f"\n{'='*80}")
        logger.info(f"COLLECTION COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Total stores: {len(self.stores_config)}")
        logger.info(f"Successful: {successful}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Total time: {elapsed:.2f}s")
        logger.info(f"Average time per store: {elapsed/len(self.stores_config):.2f}s")
        logger.info(f"Stores per minute: {len(self.stores_config)/(elapsed/60):.1f}")

        return self.results

    def save_results(self, output_dir='data'):
        """Save collected data to disk"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        for result in self.results:
            if isinstance(result, dict) and result.get('success'):
                store_id = result['store_id']
                filename = output_path / f"store_{store_id}_{timestamp}.json"

                # Convert binary data to base64 for JSON serialization
                save_data = {
                    'store_id': result['store_id'],
                    'ip': result['ip'],
                    'timestamp': timestamp,
                    'elapsed': result['elapsed'],
                    'data_sizes': {k: v for k, v in result['data'].items() if k.endswith('_size')}
                }

                with open(filename, 'w') as f:
                    json.dump(save_data, f, indent=2)

        logger.info(f"Results saved to {output_dir}/")


async def main():
    """Main execution function"""

    # Load credentials
    with open('credentials.yaml', 'r') as f:
        creds = yaml.safe_load(f)
        credentials = creds['credentials']

    # Example: Load stores configuration
    # In production, load from CSV or database
    stores_config = [
        {'store_id': 1, 'ip': '10.0.0.1', 'state': ''},
        # Add more stores here
    ]

    # For demo: replicate store to simulate 80 stores
    demo_stores = []
    for i in range(80):
        demo_stores.append({
            'store_id': 100 + i,
            'ip': '10.0.0.1',  # All pointing to same store for demo
            'state': ''
        })

    print(f"""
{'='*80}
MULTI-STORE TANK DATA COLLECTOR
{'='*80}
Stores to process: {len(demo_stores)}
Max concurrent: 20 workers
Estimated time: ~{28 * len(demo_stores) / 20 / 60:.1f} minutes
{'='*80}
    """)

    # Get user confirmation
    response = input("Start collection? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Collection cancelled")
        return

    # Create collector and run
    collector = MultiStoreCollector(demo_stores, credentials, max_concurrent=20)
    results = await collector.collect_all_stores()

    # Save results
    collector.save_results()

    print("\nCollection complete! Check the 'data/' directory for results.")


if __name__ == "__main__":
    asyncio.run(main())
