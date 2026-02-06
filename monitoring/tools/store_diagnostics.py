#!/usr/bin/env python3
"""
Store Diagnostics Tool
======================
Query a specific store's commander and compare with Prometheus data.
Useful for troubleshooting stale/phantom pump data.

Usage:
    python store_diagnostics.py <store_number_or_ip>

Examples:
    python store_diagnostics.py 121
    python store_diagnostics.py 10.0.0.1
"""

import sys
import os
import json
import requests
import urllib3
from datetime import datetime

# Suppress SSL warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration
PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
DB_PATH = os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')

# Commander credentials from environment
COMMANDER_USER = os.getenv('COMMANDER_USERNAME', 'admin')
COMMANDER_PASS = os.getenv('COMMANDER_PASSWORD', '')


def get_store_from_db(store_query):
    """Look up store info from database by store number or IP."""
    import sqlite3

    if not os.path.exists(DB_PATH):
        print(f"[!] Database not found at {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Try matching by store number or IP
    if store_query.replace('.', '').isdigit() and '.' not in store_query:
        # It's a store number
        cursor.execute("""
            SELECT ip, store_name, group_name, brand
            FROM commanders
            WHERE store_name LIKE ? AND enabled = 1
        """, (f"%{store_query}%",))
    else:
        # It's an IP
        cursor.execute("""
            SELECT ip, store_name, group_name, brand
            FROM commanders
            WHERE ip = ? AND enabled = 1
        """, (store_query,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def get_commander_token(ip, username, password, timeout=10):
    """Authenticate and get token from commander."""
    url = f"https://{ip}/cgi-bin/CGILink?cmd=validate&user={username}&passwd={password}"
    try:
        r = requests.get(url, verify=False, timeout=timeout)
        if r.status_code == 200:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.content)
            token_el = root.find('.//cookie')
            if token_el is not None:
                return token_el.text
    except Exception as e:
        print(f"[!] Auth error: {e}")
    return None


def get_forecourt_diagnostics(ip, token, timeout=15):
    """Get forecourt diagnostics (pumps, DCRs) from commander."""
    url = f"https://{ip}/cgi-bin/CGILink?cmd=vforecourtdiagnostics&cookie={token}"
    try:
        r = requests.get(url, verify=False, timeout=timeout)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"[!] Forecourt diagnostics error: {e}")
    return None


def parse_forecourt_xml(xml_data):
    """Parse forecourt diagnostics XML and extract pump info."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"[!] XML parse error: {e}")
        return None

    pumps = []
    dcrs = []

    for fueling_point in root.findall(".//fuelingPoint"):
        fp_id = fueling_point.get('sysid')
        if not fp_id:
            continue

        pump_element = fueling_point.find(".//device[@type='Pump']")
        if pump_element is not None:
            pump_status_str = pump_element.get('status', 'unknown')
            is_available = pump_element.get('isAvailable', 'false')
            pump_status = 1 if pump_status_str.lower() == 'online' and is_available.lower() == 'true' else 0
            pumps.append({
                'id': fp_id,
                'status': pump_status,
                'status_str': pump_status_str,
                'available': is_available
            })

        dcr_element = fueling_point.find(".//device[@type='DCR']")
        if dcr_element is not None:
            dcr_status_str = dcr_element.get('status', 'unknown')
            is_available = dcr_element.get('isAvailable', 'false')
            dcr_status = 1 if dcr_status_str.lower() == 'online' and is_available.lower() == 'true' else 0
            dcrs.append({
                'id': fp_id,
                'status': dcr_status,
                'status_str': dcr_status_str,
                'available': is_available
            })

    return {'pumps': pumps, 'dcrs': dcrs}


def get_prometheus_pump_data(store_name):
    """Query Prometheus for pump status metrics for a store."""
    query = f'posproctor_pump_status{{store="{store_name}"}}'
    try:
        r = requests.get(f'{PROMETHEUS_URL}/api/v1/query', params={'query': query}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'success':
                results = data.get('data', {}).get('result', [])
                pumps = {}
                for item in results:
                    fp_id = item.get('metric', {}).get('fueling_point_id', 'unknown')
                    value = int(float(item.get('value', [0, 0])[1]))
                    timestamp = item.get('value', [0, 0])[0]
                    pumps[fp_id] = {
                        'status': value,
                        'timestamp': timestamp,
                        'age_seconds': datetime.now().timestamp() - timestamp
                    }
                return pumps
    except Exception as e:
        print(f"[!] Prometheus query error: {e}")
    return {}


def get_prometheus_dcr_data(store_name):
    """Query Prometheus for DCR status metrics for a store."""
    query = f'posproctor_dcr_status{{store="{store_name}"}}'
    try:
        r = requests.get(f'{PROMETHEUS_URL}/api/v1/query', params={'query': query}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('status') == 'success':
                results = data.get('data', {}).get('result', [])
                dcrs = {}
                for item in results:
                    fp_id = item.get('metric', {}).get('fueling_point_id', 'unknown')
                    value = int(float(item.get('value', [0, 0])[1]))
                    timestamp = item.get('value', [0, 0])[0]
                    dcrs[fp_id] = {
                        'status': value,
                        'timestamp': timestamp,
                        'age_seconds': datetime.now().timestamp() - timestamp
                    }
                return dcrs
    except Exception as e:
        print(f"[!] Prometheus query error: {e}")
    return {}


def print_comparison(commander_data, prometheus_data, data_type="Pumps"):
    """Compare commander vs prometheus data and highlight differences."""
    commander_ids = {p['id'] for p in commander_data}
    prometheus_ids = set(prometheus_data.keys())

    all_ids = sorted(commander_ids | prometheus_ids, key=lambda x: int(x) if x.isdigit() else float('inf'))

    print(f"\n{'='*60}")
    print(f" {data_type} Comparison")
    print(f"{'='*60}")
    print(f"{'ID':<6} {'Commander':<20} {'Prometheus':<20} {'Match':<8}")
    print(f"{'-'*60}")

    mismatches = []
    phantoms = []
    missing = []

    for fp_id in all_ids:
        cmd_pump = next((p for p in commander_data if p['id'] == fp_id), None)
        prom_pump = prometheus_data.get(fp_id)

        if cmd_pump and prom_pump:
            cmd_status = "Online" if cmd_pump['status'] == 1 else "Offline"
            prom_status = "Online" if prom_pump['status'] == 1 else "Offline"
            match = "✓" if cmd_pump['status'] == prom_pump['status'] else "✗"
            if cmd_pump['status'] != prom_pump['status']:
                mismatches.append(fp_id)
            print(f"{fp_id:<6} {cmd_status:<20} {prom_status:<20} {match:<8}")
        elif cmd_pump and not prom_pump:
            cmd_status = "Online" if cmd_pump['status'] == 1 else "Offline"
            missing.append(fp_id)
            print(f"{fp_id:<6} {cmd_status:<20} {'[NOT IN PROM]':<20} {'?':<8}")
        elif prom_pump and not cmd_pump:
            prom_status = "Online" if prom_pump['status'] == 1 else "Offline"
            age = prom_pump.get('age_seconds', 0)
            phantoms.append((fp_id, age))
            print(f"{fp_id:<6} {'[PHANTOM]':<20} {prom_status:<20} {'⚠':<8}")

    # Summary
    print(f"\n{'-'*60}")
    print(f"Commander {data_type.lower()}: {len(commander_ids)} | Prometheus: {len(prometheus_ids)}")

    if phantoms:
        print(f"\n⚠️  PHANTOM {data_type.upper()} (in Prometheus but NOT in Commander):")
        for fp_id, age in phantoms:
            print(f"   - {data_type[:-1]} {fp_id}: last seen {age:.0f}s ago")
        print(f"\n   These are STALE metrics. They will auto-expire from Prometheus")
        print(f"   after the staleness period (default 5 minutes).")

    if mismatches:
        print(f"\n⚠️  STATUS MISMATCHES: {data_type} {', '.join(mismatches)}")

    if missing:
        print(f"\n⚠️  MISSING FROM PROMETHEUS: {data_type} {', '.join(missing)}")

    return phantoms


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    store_query = sys.argv[1]
    print(f"\n{'#'*60}")
    print(f"# Store Diagnostics Tool")
    print(f"# Query: {store_query}")
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*60}")

    # Look up store in database
    store_info = get_store_from_db(store_query)
    if not store_info:
        print(f"\n[!] Store '{store_query}' not found in database")
        # If it looks like an IP, try to use it directly
        if '.' in store_query:
            store_info = {'ip': store_query, 'store_name': f'Unknown ({store_query})'}
        else:
            sys.exit(1)

    ip = store_info['ip']
    store_name = store_info['store_name']
    print(f"\n📍 Store: {store_name}")
    print(f"   IP: {ip}")
    print(f"   Group: {store_info.get('group_name', 'N/A')}")
    print(f"   Brand: {store_info.get('brand', 'N/A')}")

    # Get commander credentials
    if not COMMANDER_PASS:
        print(f"\n[!] COMMANDER_PASSWORD not set. Skipping commander query.")
        commander_data = None
    else:
        # Authenticate with commander
        print(f"\n🔐 Authenticating with commander...")
        token = get_commander_token(ip, COMMANDER_USER, COMMANDER_PASS)
        if not token:
            print(f"[!] Failed to authenticate with commander")
            commander_data = None
        else:
            print(f"   ✓ Got token")

            # Get forecourt diagnostics
            print(f"\n📊 Fetching forecourt diagnostics from commander...")
            xml_data = get_forecourt_diagnostics(ip, token)
            if xml_data:
                commander_data = parse_forecourt_xml(xml_data)
                if commander_data:
                    print(f"   ✓ Found {len(commander_data['pumps'])} pumps, {len(commander_data['dcrs'])} DCRs")
                else:
                    print(f"   [!] Failed to parse XML")
                    commander_data = None
            else:
                print(f"   [!] Failed to get forecourt diagnostics")
                commander_data = None

    # Get Prometheus data
    print(f"\n📈 Querying Prometheus for metrics...")
    prom_pumps = get_prometheus_pump_data(store_name)
    prom_dcrs = get_prometheus_dcr_data(store_name)
    print(f"   ✓ Found {len(prom_pumps)} pump metrics, {len(prom_dcrs)} DCR metrics")

    # Compare data
    if commander_data:
        pump_phantoms = print_comparison(commander_data['pumps'], prom_pumps, "Pumps")
        dcr_phantoms = print_comparison(commander_data['dcrs'], prom_dcrs, "DCRs")

        # Final diagnosis
        print(f"\n{'='*60}")
        print(f" DIAGNOSIS")
        print(f"{'='*60}")

        if pump_phantoms or dcr_phantoms:
            print(f"\n🔍 Found phantom metrics in Prometheus!")
            print(f"   These are stale time series that no longer exist on the commander.")
            print(f"   They will auto-expire after the Prometheus staleness period.")
            print(f"\n   To force immediate cleanup, you can:")
            print(f"   1. Restart the monitoring container (metrics will be re-scraped fresh)")
            print(f"   2. Use Prometheus Admin API to delete stale series (if enabled)")
            print(f"   3. Wait for automatic expiry (~5 minutes)")
        else:
            print(f"\n✅ Commander and Prometheus data match!")
    else:
        print(f"\n[!] Could not compare - commander data unavailable")
        print(f"\nPrometheus-only data:")
        print(f"  Pumps: {sorted(prom_pumps.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))}")
        print(f"  DCRs: {sorted(prom_dcrs.keys(), key=lambda x: int(x) if x.isdigit() else float('inf'))}")


if __name__ == '__main__':
    main()
