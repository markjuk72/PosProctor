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
import argparse

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CommanderAnalyzer:
    def __init__(self, credentials_file, commanders_file):
        with open(credentials_file, 'r') as f:
            creds = yaml.safe_load(f)
            self.username = creds['credentials']['username']
            self.password = creds['credentials']['password']

        # Setup session with retry strategy
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount('https://', adapter)
        self.session.mount('http://', adapter)

        # Load commander list
        self.commanders = []
        with open(commanders_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['enabled'].lower() == 'true':
                    self.commanders.append(row)

    def get_token(self, ip, timeout=10):
        """Get authentication token for a commander."""
        url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={self.username}&passwd={self.password}"
        try:
            r = self.session.get(url, verify=False, timeout=timeout)
            r.raise_for_status()
            token = etree.fromstring(r.content).findtext(".//cookie")
            return token
        except Exception as e:
            print(f"Failed to get token for {ip}: {e}")
            return None

    def get_vpayment_xml(self, ip, token, timeout=15):
        """Get raw XML from vpaymentdiagnostics API."""
        url = f"https://{ip}/cgi-bin/CGILink?cmd=vpaymentdiagnostics&cookie={token}"
        try:
            r = self.session.get(url, verify=False, timeout=timeout)
            r.raise_for_status()
            return r.content
        except Exception as e:
            print(f"Failed to get vpayment XML for {ip}: {e}")
            return None

    def analyze_commanders(self, max_commanders=5, output_dir="vpayment_xml_dumps"):
        """Query multiple commanders and save raw XML responses."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        successful_queries = 0

        for commander in self.commanders[:max_commanders]:
            ip = commander['ip']
            store = commander['store']

            print(f"\n=== Analyzing {store} ({ip}) ===")

            # Get token
            token = self.get_token(ip)
            if not token:
                print(f"Could not authenticate to {store}")
                continue

            # Get XML
            xml_content = self.get_vpayment_xml(ip, token)
            if not xml_content:
                print(f"Could not retrieve XML from {store}")
                continue

            # Save raw XML to file
            filename = f"{output_dir}/{store.replace(' ', '_')}_{ip}.xml"
            with open(filename, 'wb') as f:
                f.write(xml_content)

            print(f"Saved raw XML to: {filename}")

            # Also pretty print to console for immediate analysis
            try:
                parsed_xml = etree.fromstring(xml_content)
                pretty_xml = etree.tostring(parsed_xml, pretty_print=True, encoding='unicode')
                print(f"Raw XML content preview (first 2000 chars):")
                print("-" * 50)
                print(pretty_xml[:2000])
                if len(pretty_xml) > 2000:
                    print(f"... (truncated, full content in {filename})")
                print("-" * 50)
            except Exception as e:
                print(f"Could not parse XML: {e}")
                print("Raw content:")
                print(xml_content.decode('utf-8', errors='ignore')[:1000])

            successful_queries += 1

        print(f"\nSuccessfully queried {successful_queries} commanders")
        if successful_queries > 0:
            print(f"XML files saved in: {output_dir}/")

def main():
    parser = argparse.ArgumentParser(description='Analyze vpaymentdiagnostics XML from Verifone Commanders')
    parser.add_argument('--max-commanders', '-n', type=int, default=5,
                       help='Maximum number of commanders to query (default: 5)')
    parser.add_argument('--output-dir', '-o', default='vpayment_xml_dumps',
                       help='Output directory for XML files (default: vpayment_xml_dumps)')

    args = parser.parse_args()

    # Check for required files
    if not os.path.exists('credentials.yaml'):
        print("Error: credentials.yaml not found")
        sys.exit(1)

    if not os.path.exists('commanders.csv'):
        print("Error: commanders.csv not found")
        sys.exit(1)

    analyzer = CommanderAnalyzer('credentials.yaml', 'commanders.csv')
    analyzer.analyze_commanders(max_commanders=args.max_commanders, output_dir=args.output_dir)

if __name__ == "__main__":
    main()