#!/usr/bin/env python3

import os
import csv
from collections import defaultdict, Counter
from lxml import etree

def analyze_fep_patterns():
    """Analyze FEP connection patterns across all collected XML files."""

    xml_dir = "vpayment_xml_dumps"
    if not os.path.exists(xml_dir):
        print(f"Directory {xml_dir} not found")
        return

    # Load store mapping for context
    store_mapping = {}
    with open('commanders.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            store_mapping[row['ip']] = {
                'store': row['store'],
                'brand': row['brand'],
                'group': row['group']
            }

    fep_by_store = {}
    fep_counts = Counter()
    brand_fep_mapping = defaultdict(set)
    primary_feps = Counter()
    connection_status_summary = defaultdict(list)

    # Process all XML files
    for filename in os.listdir(xml_dir):
        if not filename.endswith('.xml'):
            continue

        filepath = os.path.join(xml_dir, filename)

        # Extract IP from filename
        ip = filename.split('_')[-1].replace('.xml', '')
        store_info = store_mapping.get(ip, {'store': 'Unknown', 'brand': 'Unknown', 'group': 'Unknown'})

        try:
            with open(filepath, 'rb') as f:
                xml_content = f.read()

            parsed_xml = etree.fromstring(xml_content)

            store_feps = []
            for fep in parsed_xml.findall(".//fepDetail"):
                fep_name = fep.get('fepName', '')
                is_primary = fep.get('isPrimary', 'false').lower() == 'true'
                connection_status = fep.findtext("connectionStatus", "").lower() == 'true'

                store_feps.append({
                    'name': fep_name,
                    'is_primary': is_primary,
                    'connected': connection_status
                })

                # Count occurrences
                fep_counts[fep_name] += 1
                brand_fep_mapping[store_info['brand']].add(fep_name)

                if is_primary:
                    primary_feps[fep_name] += 1

                # Track connection status
                connection_status_summary[fep_name].append(connection_status)

            fep_by_store[f"{store_info['store']} ({store_info['brand']})"] = store_feps

        except Exception as e:
            print(f"Error processing {filename}: {e}")

    # Print analysis results
    print("=" * 80)
    print("FEP CONNECTION ANALYSIS ACROSS COMMANDERS")
    print("=" * 80)

    print(f"\nTotal stores analyzed: {len(fep_by_store)}")
    print(f"Unique FEP types found: {len(fep_counts)}")

    print("\n" + "=" * 50)
    print("FEP FREQUENCY ANALYSIS")
    print("=" * 50)

    print("\nFEP occurrences across all stores:")
    for fep_name, count in fep_counts.most_common():
        connected_count = sum(1 for status in connection_status_summary[fep_name] if status)
        total_count = len(connection_status_summary[fep_name])
        connection_rate = (connected_count / total_count * 100) if total_count > 0 else 0

        print(f"  {fep_name:<25} : {count:>2} stores ({connection_rate:>5.1f}% connected)")

    print("\n" + "=" * 50)
    print("PRIMARY FEP ANALYSIS")
    print("=" * 50)

    print("\nFEPs configured as PRIMARY:")
    for fep_name, count in primary_feps.most_common():
        print(f"  {fep_name:<25} : {count} stores")

    print("\n" + "=" * 50)
    print("BRAND-SPECIFIC FEP MAPPING")
    print("=" * 50)

    for brand in sorted(brand_fep_mapping.keys()):
        feps = sorted(brand_fep_mapping[brand])
        print(f"\n{brand}:")
        for fep in feps:
            primary_count = primary_feps.get(fep, 0)
            total_count = fep_counts.get(fep, 0)
            primary_indicator = " (PRIMARY)" if primary_count > 0 else ""
            print(f"  - {fep}{primary_indicator}")

    print("\n" + "=" * 50)
    print("RECOMMENDED GLOBAL FEP METRICS")
    print("=" * 50)

    # Identify common FEPs worth tracking globally
    common_threshold = 3  # FEPs that appear in 3+ stores
    common_feps = [fep for fep, count in fep_counts.items() if count >= common_threshold]

    print(f"\nFEPs appearing in {common_threshold}+ stores (recommended for global monitoring):")
    for fep in sorted(common_feps):
        count = fep_counts[fep]
        is_primary = fep in primary_feps
        primary_note = " [Often PRIMARY]" if is_primary else " [Secondary]"
        print(f"  - {fep} ({count} stores){primary_note}")

    print("\nFEPs appearing in <3 stores (brand/location specific):")
    rare_feps = [fep for fep, count in fep_counts.items() if count < common_threshold]
    for fep in sorted(rare_feps):
        count = fep_counts[fep]
        print(f"  - {fep} ({count} store{'s' if count > 1 else ''})")

    print("\n" + "=" * 50)
    print("DETAILED STORE BREAKDOWN")
    print("=" * 50)

    for store, feps in sorted(fep_by_store.items()):
        print(f"\n{store}:")
        for fep in feps:
            status = "CONNECTED" if fep['connected'] else "DISCONNECTED"
            primary = "PRIMARY" if fep['is_primary'] else "SECONDARY"
            print(f"  - {fep['name']:<25} : {primary:<9} | {status}")

if __name__ == "__main__":
    analyze_fep_patterns()