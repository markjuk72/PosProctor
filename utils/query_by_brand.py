#!/usr/bin/env python3

import requests
import yaml
import csv
import sys
import os
from lxml import etree
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from collections import defaultdict

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BrandAnalyzer:
    def __init__(self, credentials_file, commanders_file):
        with open(credentials_file, 'r') as f:
            creds = yaml.safe_load(f)
            self.username = creds['credentials']['username']
            self.password = creds['credentials']['password']

        # Setup session
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        # Load commanders grouped by brand
        self.commanders_by_brand = defaultdict(list)
        with open(commanders_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['enabled'].lower() == 'true':
                    self.commanders_by_brand[row['brand']].append(row)

    def get_token(self, ip, timeout=5):
        """Get authentication token."""
        url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"
        try:
            r = self.session.get(url, verify=False, timeout=timeout)
            r.raise_for_status()
            token = etree.fromstring(r.content).findtext(".//cookie")
            return token
        except Exception as e:
            print(f"Failed to get token for {ip}: {e}")
            return None

    def get_vpayment_xml(self, ip, token, timeout=8):
        """Get vpayment diagnostics XML."""
        url = f"https://{ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"Failed to get vpayment XML for {ip}: {e}")
            return None

    def extract_feps(self, xml_content):
        """Extract FEP information from XML."""
        try:
            parsed_xml = etree.fromstring(xml_content)
            feps = []
            for fep in parsed_xml.findall(".//fepDetail"):
                fep_info = {
                    'name': fep.get('fepName', ''),
                    'is_primary': fep.get('isPrimary', 'false').lower() == 'true',
                    'connected': fep.findtext("connectionStatus", "").lower() == 'true'
                }
                feps.append(fep_info)
            return feps
        except Exception as e:
            print(f"Error parsing XML: {e}")
            return []

    def analyze_by_brand(self, max_per_brand=1):
        """Query commanders from each brand to identify FEP patterns."""

        print("=" * 80)
        print("PRIMARY PAYMENT PROCESSOR ANALYSIS BY FUEL BRAND")
        print("=" * 80)

        brand_fep_summary = {}

        for brand, stores in self.commanders_by_brand.items():
            if not stores:
                continue

            print(f"\n{'='*20} {brand.upper()} BRAND {'='*20}")

            brand_primary_feps = []
            brand_all_feps = []

            # Query up to max_per_brand stores from this brand
            stores_to_query = stores[:max_per_brand]

            for store in stores_to_query:
                ip = store['ip']
                store_name = store['store']

                print(f"\nQuerying {store_name} ({ip})...")

                # Get token and XML
                token = self.get_token(ip)
                if not token:
                    print(f"  ❌ Authentication failed")
                    continue

                xml_content = self.get_vpayment_xml(ip, token)
                if not xml_content:
                    print(f"  ❌ Failed to get payment diagnostics")
                    continue

                # Extract FEPs
                feps = self.extract_feps(xml_content)
                if not feps:
                    print(f"  ❌ No FEPs found")
                    continue

                print(f"  ✅ Found {len(feps)} FEPs:")
                for fep in feps:
                    status = "🟢 CONNECTED" if fep['connected'] else "🔴 DISCONNECTED"
                    role = "PRIMARY" if fep['is_primary'] else "SECONDARY"
                    print(f"    - {fep['name']:<25} [{role:<9}] {status}")

                    brand_all_feps.append(fep['name'])
                    if fep['is_primary']:
                        brand_primary_feps.append(fep['name'])

            # Summarize for this brand
            unique_primaries = list(set(brand_primary_feps))
            unique_all = list(set(brand_all_feps))

            brand_fep_summary[brand] = {
                'primary_feps': unique_primaries,
                'all_feps': unique_all,
                'stores_queried': len(stores_to_query)
            }

            print(f"\n{brand} SUMMARY:")
            print(f"  Primary FEPs: {', '.join(unique_primaries) if unique_primaries else 'None found'}")
            print(f"  All FEPs: {', '.join(unique_all)}")

        # Overall summary
        print("\n" + "="*80)
        print("OVERALL BRAND-TO-PRIMARY-FEP MAPPING")
        print("="*80)

        all_primary_feps = set()

        for brand, info in brand_fep_summary.items():
            primaries = info['primary_feps']
            all_primary_feps.update(primaries)

            primary_str = ', '.join(primaries) if primaries else 'No primary FEP found'
            print(f"{brand:<15} : {primary_str}")

        print(f"\n📊 UNIQUE PRIMARY FEPS ACROSS ALL BRANDS:")
        for fep in sorted(all_primary_feps):
            brands_using = [brand for brand, info in brand_fep_summary.items() if fep in info['primary_feps']]
            print(f"  - {fep:<25} (Used by: {', '.join(brands_using)})")

        return brand_fep_summary

def main():
    if not os.path.exists('credentials.yaml'):
        print("Error: credentials.yaml not found")
        sys.exit(1)

    if not os.path.exists('commanders.csv'):
        print("Error: commanders.csv not found")
        sys.exit(1)

    analyzer = BrandAnalyzer('credentials.yaml', 'commanders.csv')
    analyzer.analyze_by_brand(max_per_brand=2)

if __name__ == "__main__":
    main()