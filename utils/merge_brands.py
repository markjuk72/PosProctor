#!/usr/bin/env python3
"""
Merge brands.csv with commanders.csv to add brand column.
Creates a new commanders.csv with brand information.
"""

import csv
import sys

def load_brands():
    """Load brand mappings from brands.csv"""
    brands = {}
    try:
        with open('brands.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    store_name = row[0].strip()
                    brand = row[1].strip()
                    brands[store_name] = brand
    except FileNotFoundError:
        print("Error: brands.csv not found")
        sys.exit(1)
    return brands

def merge_commanders_brands():
    """Merge commanders.csv with brand data"""
    brands = load_brands()
    
    # Read existing commanders
    commanders = []
    try:
        with open('commanders.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            commanders = list(reader)
    except FileNotFoundError:
        print("Error: commanders.csv not found")
        sys.exit(1)
    
    # Add brand column to each commander
    updated_commanders = []
    for commander in commanders:
        store_name = commander['store']
        brand = brands.get(store_name, 'Unknown')
        
        # Create new row with brand
        updated_commander = {
            'ip': commander['ip'],
            'store': commander['store'], 
            'group': commander['group'],
            'brand': brand,
            'enabled': commander['enabled']
        }
        updated_commanders.append(updated_commander)
    
    # Write updated commanders.csv
    with open('commanders.csv', 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['ip', 'store', 'group', 'brand', 'enabled']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_commanders)
    
    print(f"Successfully merged {len(updated_commanders)} commanders with brand data")
    
    # Show brand distribution
    brand_counts = {}
    for commander in updated_commanders:
        brand = commander['brand']
        brand_counts[brand] = brand_counts.get(brand, 0) + 1
    
    print("\nBrand distribution:")
    for brand, count in sorted(brand_counts.items()):
        print(f"  {brand}: {count} stores")

if __name__ == '__main__':
    merge_commanders_brands()