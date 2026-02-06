"""
Tank Data Parser - Transform Commander XML responses into report data structures
"""

import xml.etree.ElementTree as ET
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def get_fuel_color(product_code: str) -> str:
    """
    Map fuel product codes to chart colors.

    Args:
        product_code: Fuel product code (UNL, DSL, PRM, MID, etc.)

    Returns:
        Hex color code for charts
    """
    color_map = {
        'UNL': '#2ecc71',  # Green for Unleaded
        'DSL': '#3498db',  # Blue for Diesel
        'MID': '#e67e22',  # Orange for Mid-grade
        'PRM': '#e74c3c',  # Red for Premium
        'E00': '#9b59b6',  # Purple for Ethanol-free
        'E85': '#1abc9c',  # Teal for E85
    }

    # Check for partial matches (e.g., 'UNL' in 'UNL87')
    product_upper = product_code.upper()
    for key, color in color_map.items():
        if key in product_upper:
            return color

    # Default gray for unknown fuel types
    return '#95a5a6'


def parse_fuel_config_xml(xml_content: bytes) -> List[Dict]:
    """
    Parse fuel configuration XML to extract tank definitions.

    Expected XML structure:
    <fuelcfg:fuelConfig>
        <fuelTanks>
            <fuelTank sysid="1" name="DSL" NAXMLFuelProdID="0"/>
            <fuelTank sysid="5" name="UNL" NAXMLFuelProdID="0"/>
        </fuelTanks>
    </fuelcfg:fuelConfig>

    Args:
        xml_content: Raw XML bytes from vfuelcfg

    Returns:
        List of tank configuration dicts
    """
    if not xml_content:
        logger.warning("No fuel config XML data provided")
        return []

    try:
        root = ET.fromstring(xml_content)
        tanks = []

        # Find all fuelTank elements (namespace-aware)
        for child in root.iter():
            if 'fuelTank' in child.tag:
                sysid = child.get('sysid')
                name = child.get('name')

                # Skip placeholder tanks (tank02, tank03, etc.)
                if name and not name.startswith('tank'):
                    # Get full product name
                    full_name = name
                    if 'DSL' in name.upper():
                        full_name = 'Diesel'
                    elif 'UNL' in name.upper():
                        full_name = 'Unleaded'
                    elif 'PRM' in name.upper():
                        full_name = 'Premium'
                    elif 'MID' in name.upper():
                        full_name = 'Mid-Grade'
                    elif 'E00' in name.upper():
                        full_name = 'Ethanol-Free'
                    elif 'E85' in name.upper():
                        full_name = 'E85'

                    tanks.append({
                        'sysid': int(sysid) if sysid else 0,
                        'name': name,
                        'full_name': full_name,
                        'color': get_fuel_color(name)
                    })

        logger.info(f"Parsed {len(tanks)} fuel tanks from configuration")
        return tanks

    except ET.ParseError as e:
        logger.error(f"XML parse error in fuel config: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing fuel config XML: {e}")
        return []


def build_store_info(commander_ip: str, store_name: str, store_id: str,
                     brand: str = 'Unknown', xml_data: Optional[Dict] = None) -> Dict:
    """
    Build STORE_INFO dictionary from available data.

    Args:
        commander_ip: Commander IP address
        store_name: Store name from database
        store_id: Store ID
        brand: Store brand
        xml_data: Optional dict of XML responses

    Returns:
        STORE_INFO dict with store metadata
    """
    return {
        'store_id': store_id,
        'location': store_name or 'Unknown Location',
        'state_code': '',  # Should be configured per deployment
        'state_name': '',  # Should be configured per deployment
        'brand': brand,
        'ip': commander_ip,
        'tank_monitor': 'Veeder-Root TLS',
        'last_reading': datetime.now().strftime('%Y-%m-%d %H:%M:%S MST')
    }


def parse_tank_monitor_xml(xml_content: bytes, store_info: Dict) -> List[Dict]:
    """
    Parse tankMonitor XML to extract current tank inventory.

    Expected XML structure:
    <report>
        <tank id="1" product="DSL">
            <level>56.11</level>
            <volume>10832</volume>
            <ullage>14267</ullage>
            <temperature>40.6</temperature>
            <water>0.0</water>
            <capacity>25099</capacity>
        </tank>
    </report>

    Args:
        xml_content: Raw XML bytes from vrubyrept reptname=tankMonitor
        store_info: Store info dict (for logging context)

    Returns:
        List of tank inventory dicts
    """
    if not xml_content:
        logger.warning(f"[{store_info.get('ip', 'unknown')}] No tankMonitor XML data provided")
        return []

    try:
        root = ET.fromstring(xml_content)
        tanks = []

        # Debug: Log the XML structure
        logger.debug(f"[{store_info.get('ip', 'unknown')}] tankMonitor XML root tag: {root.tag}")
        logger.debug(f"[{store_info.get('ip', 'unknown')}] tankMonitor XML sample: {ET.tostring(root, encoding='unicode')[:500]}")

        # Check if this is a Fault response
        fault_elem = root.find('.//{*}Fault')
        if fault_elem is not None:
            fault_string = fault_elem.findtext('.//{*}faultString', 'Unknown error')
            fault_message = fault_elem.findtext('.//{*}message', '')
            logger.warning(f"[{store_info.get('ip', 'unknown')}] tankMonitor returned fault: {fault_string} - {fault_message}")
            logger.info(f"[{store_info.get('ip', 'unknown')}] This usually indicates the tank monitoring equipment (Veeder-Root TLS) is offline or not responding")
            return []

        # Try multiple XML patterns - look for inventoryInfo elements
        tank_elements = root.findall('.//{*}inventoryInfo') or root.findall('.//inventoryInfo')
        logger.debug(f"[{store_info.get('ip', 'unknown')}] Found {len(tank_elements)} inventoryInfo elements")
        if not tank_elements:
            # Fallback to older structure
            tank_elements = root.findall('.//tank') or root.findall('.//Tank')
            logger.debug(f"[{store_info.get('ip', 'unknown')}] Fallback: Found {len(tank_elements)} tank elements")

        for tank_elem in tank_elements:
            try:
                # Build a dict of child tag name (without namespace) -> element
                child_map = {}
                for child in tank_elem:
                    tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    child_map[tag_name.lower()] = child

                # Get tank identification from fuelTank element using child_map
                fuel_tank_elem = child_map.get('fueltank')
                if fuel_tank_elem is not None:
                    tank_id = fuel_tank_elem.get('sysid') or fuel_tank_elem.get('id')
                    product = fuel_tank_elem.text.strip() if fuel_tank_elem.text else None
                    if not product:
                        product = f'tank{int(tank_id):02d}' if tank_id else f'tank{len(tanks)+1:02d}'
                else:
                    # Fallback to attributes on tank element
                    tank_id = tank_elem.get('id') or tank_elem.get('tankId') or tank_elem.get('sysid')
                    product = tank_elem.get('product') or tank_elem.get('productCode') or (f'tank{int(tank_id):02d}' if tank_id else f'tank{len(tanks)+1:02d}')

                # Extract elements - avoid using 'or' which can be problematic with XML elements
                level_elem = child_map.get('fuellvl')
                if level_elem is None:
                    level_elem = child_map.get('level')
                if level_elem is None:
                    level_elem = child_map.get('levelinches')

                volume_elem = child_map.get('fuelvolume')
                if volume_elem is None:
                    volume_elem = child_map.get('volume')
                if volume_elem is None:
                    volume_elem = child_map.get('volumegallons')

                ullage_elem = child_map.get('ullage')
                if ullage_elem is None:
                    ullage_elem = child_map.get('fuelullage')

                temp_elem = child_map.get('fueltemperature')
                if temp_elem is None:
                    temp_elem = child_map.get('temperature')
                if temp_elem is None:
                    temp_elem = child_map.get('temp')

                water_elem = child_map.get('waterlvl')
                if water_elem is None:
                    water_elem = child_map.get('water')
                if water_elem is None:
                    water_elem = child_map.get('waterinches')

                capacity_elem = child_map.get('fuelcapacity')
                if capacity_elem is None:
                    capacity_elem = child_map.get('capacity')

                level_in = float(level_elem.text) if level_elem is not None and level_elem.text else 0.0
                volume = float(volume_elem.text) if volume_elem is not None and volume_elem.text else 0.0
                ullage = float(ullage_elem.text) if ullage_elem is not None and ullage_elem.text else 0.0
                temp = float(temp_elem.text) if temp_elem is not None and temp_elem.text else 0.0
                water = float(water_elem.text) if water_elem is not None and water_elem.text else 0.0
                capacity = float(capacity_elem.text) if capacity_elem is not None and capacity_elem.text else 0.0

                # If capacity not in XML, calculate from volume + ullage
                if capacity == 0.0 and volume > 0 and ullage > 0:
                    capacity = volume + ullage

                # Get product full name
                full_name = product
                if 'DSL' in product.upper() or 'DIESEL' in product.upper():
                    full_name = 'Diesel'
                elif 'UNL' in product.upper() or 'UNLEAD' in product.upper():
                    full_name = 'Unleaded'
                elif 'PRM' in product.upper() or 'PREM' in product.upper():
                    full_name = 'Premium'
                elif 'MID' in product.upper():
                    full_name = 'Mid-Grade'

                tanks.append({
                    'id': int(tank_id) if tank_id and str(tank_id).isdigit() else len(tanks) + 1,
                    'name': product,
                    'full_name': full_name,
                    'level_in': round(level_in, 2),
                    'volume': round(volume, 0),
                    'temp': round(temp, 1),
                    'ullage': round(ullage, 0),
                    'water': round(water, 2),
                    'capacity': round(capacity, 0)
                })

            except (ValueError, AttributeError) as e:
                logger.error(f"[{store_info.get('ip', 'unknown')}] Error parsing tank element: {e}")
                continue

        logger.info(f"[{store_info.get('ip', 'unknown')}] Parsed {len(tanks)} tanks from tankMonitor XML")
        return tanks

    except ET.ParseError as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] XML parse error in tankMonitor: {e}")
        return []
    except Exception as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] Unexpected error parsing tankMonitor XML: {e}")
        return []


def parse_fuel_totals_xml(xml_content: bytes, store_info: Dict) -> List[Dict]:
    """
    Parse vfueltotals XML to extract tank inventory data (fallback for tankMonitor).

    Expected XML structure:
    <fuelTotals>
        <fuelTank name="DSL" tankNumber="1">
            <levelInches>56.11</levelInches>
            <volumeGallons>10832</volumeGallons>
            <ullageGallons>14267</ullageGallons>
            <temperatureFahrenheit>40.6</temperatureFahrenheit>
            <waterInches>0.0</waterInches>
            <capacityGallons>25099</capacityGallons>
        </fuelTank>
    </fuelTotals>

    Args:
        xml_content: Raw XML bytes from vfueltotals
        store_info: Store info dict (for logging context)

    Returns:
        List of tank inventory dicts
    """
    if not xml_content:
        logger.warning(f"[{store_info.get('ip', 'unknown')}] No vfueltotals XML data provided")
        return []

    try:
        root = ET.fromstring(xml_content)
        tanks = []

        logger.debug(f"[{store_info.get('ip', 'unknown')}] vfueltotals XML root tag: {root.tag}")
        logger.debug(f"[{store_info.get('ip', 'unknown')}] vfueltotals XML sample: {ET.tostring(root, encoding='unicode')[:500]}")

        # Check if this is a Fault response
        fault_elem = root.find('.//{*}Fault')
        if fault_elem is not None:
            fault_string = fault_elem.findtext('.//{*}faultString', 'Unknown error')
            fault_message = fault_elem.findtext('.//{*}message', '')
            logger.warning(f"[{store_info.get('ip', 'unknown')}] vfueltotals returned fault: {fault_string} - {fault_message}")
            return []

        # Try multiple XML patterns for fuelTank elements
        tank_elements = root.findall('.//{*}fuelTank') or root.findall('.//fuelTank') or root.findall('.//tank')

        if not tank_elements:
            # Try looking for dispenser-level data and aggregate by product
            logger.debug(f"[{store_info.get('ip', 'unknown')}] No fuelTank elements found, trying dispenser aggregation")
            return []

        for tank_elem in tank_elements:
            try:
                tank_id = tank_elem.get('tankNumber') or tank_elem.get('id') or tank_elem.get('sysid')
                product = tank_elem.get('name') or tank_elem.get('product') or tank_elem.get('productCode', f'tank{tank_id:02d}')

                # Extract values with multiple possible tag names (namespace-aware)
                level_elem = (tank_elem.find('.//{*}levelInches') or tank_elem.find('.//{*}level') or
                             tank_elem.find('levelInches') or tank_elem.find('level'))
                volume_elem = (tank_elem.find('.//{*}volumeGallons') or tank_elem.find('.//{*}volume') or
                              tank_elem.find('volumeGallons') or tank_elem.find('volume'))
                ullage_elem = (tank_elem.find('.//{*}ullageGallons') or tank_elem.find('.//{*}ullage') or
                              tank_elem.find('ullageGallons') or tank_elem.find('ullage'))
                temp_elem = (tank_elem.find('.//{*}temperatureFahrenheit') or tank_elem.find('.//{*}temperature') or
                            tank_elem.find('.//{*}temp') or tank_elem.find('temperatureFahrenheit') or
                            tank_elem.find('temperature') or tank_elem.find('temp'))
                water_elem = (tank_elem.find('.//{*}waterInches') or tank_elem.find('.//{*}water') or
                             tank_elem.find('waterInches') or tank_elem.find('water'))
                capacity_elem = (tank_elem.find('.//{*}capacityGallons') or tank_elem.find('.//{*}capacity') or
                                tank_elem.find('capacityGallons') or tank_elem.find('capacity'))

                level_in = float(level_elem.text) if level_elem is not None and level_elem.text else 0.0
                volume = float(volume_elem.text) if volume_elem is not None and volume_elem.text else 0.0
                ullage = float(ullage_elem.text) if ullage_elem is not None and ullage_elem.text else 0.0
                temp = float(temp_elem.text) if temp_elem is not None and temp_elem.text else 0.0
                water = float(water_elem.text) if water_elem is not None and water_elem.text else 0.0
                capacity = float(capacity_elem.text) if capacity_elem is not None and capacity_elem.text else 0.0

                # Get product full name
                full_name = product
                if 'DSL' in product.upper():
                    full_name = 'Diesel'
                elif 'UNL' in product.upper():
                    full_name = 'Unleaded'
                elif 'PRM' in product.upper():
                    full_name = 'Premium'
                elif 'MID' in product.upper():
                    full_name = 'Mid-Grade'

                tanks.append({
                    'id': int(tank_id) if tank_id and tank_id.isdigit() else len(tanks) + 1,
                    'name': product,
                    'full_name': full_name,
                    'level_in': round(level_in, 2),
                    'volume': round(volume, 0),
                    'temp': round(temp, 1),
                    'ullage': round(ullage, 0),
                    'water': round(water, 2),
                    'capacity': round(capacity, 0)
                })

            except (ValueError, AttributeError) as e:
                logger.error(f"[{store_info.get('ip', 'unknown')}] Error parsing fuelTank element: {e}")
                continue

        logger.info(f"[{store_info.get('ip', 'unknown')}] Parsed {len(tanks)} tanks from vfueltotals XML")
        return tanks

    except ET.ParseError as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] XML parse error in vfueltotals: {e}")
        return []
    except Exception as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] Unexpected error parsing vfueltotals XML: {e}")
        return []


def parse_tank_reconciliation_for_inventory(xml_content: bytes, store_info: Dict, fuel_config: List[Dict] = None) -> List[Dict]:
    """
    Parse tankRec XML to extract ending inventory as fallback when tankMonitor fails.

    Expected XML structure:
    <tankRecPd>
        <tankInfo>
            <fuelTank sysid="1">DSL</fuelTank>
            <beginInventory>10500</beginInventory>
            <endInventory>8932</endInventory>
            <dispensed>2100</dispensed>
            <delivery>532</delivery>
        </tankInfo>
    </tankRecPd>

    Args:
        xml_content: Raw XML bytes from vrubyrept reptname=tankRec
        store_info: Store info dict (for logging context)
        fuel_config: Optional fuel config to get capacity data

    Returns:
        List of tank inventory dicts with volumes but no temp/water data
    """
    if not xml_content:
        logger.warning(f"[{store_info.get('ip', 'unknown')}] No tankRec XML data provided")
        return []

    try:
        root = ET.fromstring(xml_content)
        tanks = []

        logger.debug(f"[{store_info.get('ip', 'unknown')}] tankRec XML root tag: {root.tag}")
        logger.debug(f"[{store_info.get('ip', 'unknown')}] tankRec XML sample: {ET.tostring(root, encoding='unicode')[:500]}")

        # Check if this is a Fault response
        fault_elem = root.find('.//{*}Fault')
        if fault_elem is not None:
            fault_string = fault_elem.findtext('.//{*}faultString', 'Unknown error')
            fault_message = fault_elem.findtext('.//{*}message', '')
            logger.warning(f"[{store_info.get('ip', 'unknown')}] tankRec returned fault: {fault_string} - {fault_message}")
            return []

        # Look for endInventories elements (contains current inventory)
        end_inventory_elements = root.findall('.//{*}endInventories') or root.findall('.//endInventories')

        if not end_inventory_elements:
            logger.debug(f"[{store_info.get('ip', 'unknown')}] No endInventories elements found in tankRec")
            return []

        for tank_elem in end_inventory_elements:
            try:
                # Get tank identification from fuelTank element
                fuel_tank_elem = tank_elem.find('.//{*}fuelTank') or tank_elem.find('.//fuelTank')
                if fuel_tank_elem is None:
                    continue

                tank_id = fuel_tank_elem.get('sysid') or fuel_tank_elem.get('id')
                product = fuel_tank_elem.text or f'tank{tank_id:02d}'

                # Extract inventory volume from endInventories
                inv_volume_elem = (tank_elem.find('.//{*}inventoryVolume') or tank_elem.find('.//inventoryVolume') or
                                  tank_elem.find('.//{*}volume') or tank_elem.find('.//volume'))

                # Use inventory volume as current volume
                volume = float(inv_volume_elem.text) if inv_volume_elem is not None and inv_volume_elem.text else 0.0

                # Calculate ullage if we have capacity from fuel_config
                capacity = 0.0
                if fuel_config:
                    for config_tank in fuel_config:
                        if str(config_tank.get('sysid')) == str(tank_id):
                            capacity = config_tank.get('capacity', 0.0)
                            break

                ullage = capacity - volume if capacity > 0 else 0.0

                # Get product full name
                full_name = product
                if 'DSL' in product.upper() or 'DIESEL' in product.upper():
                    full_name = 'Diesel'
                elif 'UNL' in product.upper() or 'UNLEAD' in product.upper():
                    full_name = 'Unleaded'
                elif 'PRM' in product.upper() or 'PREM' in product.upper():
                    full_name = 'Premium'
                elif 'MID' in product.upper():
                    full_name = 'Mid-Grade'

                tanks.append({
                    'id': int(tank_id) if tank_id and str(tank_id).isdigit() else len(tanks) + 1,
                    'name': product,
                    'full_name': full_name,
                    'level_in': 0.0,  # Not available from tankRec
                    'volume': round(volume, 0),
                    'temp': 0.0,  # Not available from tankRec
                    'ullage': round(ullage, 0),
                    'water': 0.0,  # Not available from tankRec
                    'capacity': round(capacity, 0)
                })

            except (ValueError, AttributeError) as e:
                logger.error(f"[{store_info.get('ip', 'unknown')}] Error parsing tankInfo element: {e}")
                continue

        logger.info(f"[{store_info.get('ip', 'unknown')}] Parsed {len(tanks)} tanks from tankRec XML (limited data)")
        return tanks

    except ET.ParseError as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] XML parse error in tankRec: {e}")
        return []
    except Exception as e:
        logger.error(f"[{store_info.get('ip', 'unknown')}] Unexpected error parsing tankRec XML: {e}")
        return []


def enrich_tank_inventory_with_capacity(tank_inventory: List[Dict], fuel_config: List[Dict]) -> None:
    """
    Add capacity information from fuel config to tank inventory.
    Modifies tank_inventory in place.

    Args:
        tank_inventory: List of tank dicts to enrich
        fuel_config: List of fuel config dicts with capacity data
    """
    if not fuel_config:
        return

    # Create lookup by tank ID/name
    capacity_map = {}
    for config_tank in fuel_config:
        sysid = config_tank.get('sysid')
        name = config_tank.get('name', '')
        capacity = config_tank.get('capacity', 0.0)

        if sysid:
            capacity_map[str(sysid)] = capacity
        if name:
            capacity_map[name.upper()] = capacity

    # Enrich tanks
    for tank in tank_inventory:
        # Skip if already has capacity
        if tank.get('capacity', 0) > 0:
            continue

        # Try to find capacity by ID or name
        tank_id = str(tank.get('id', ''))
        tank_name = tank.get('name', '').upper()

        if tank_id in capacity_map:
            tank['capacity'] = capacity_map[tank_id]
            # Recalculate ullage with new capacity
            if tank.get('volume', 0) > 0:
                tank['ullage'] = tank['capacity'] - tank['volume']
        elif tank_name in capacity_map:
            tank['capacity'] = capacity_map[tank_name]
            # Recalculate ullage with new capacity
            if tank.get('volume', 0) > 0:
                tank['ullage'] = tank['capacity'] - tank['volume']


def parse_sales_xml(xml_content: bytes) -> List[Dict]:
    """
    Parse tank sales report XML to extract sales by product.

    Expected XML structure:
    <report>
        <product code="UNL" name="Unleaded E10">
            <transactions>112</transactions>
            <revenue>3550.94</revenue>
            <volume>1275.006</volume>
        </product>
    </report>

    Args:
        xml_content: Raw XML bytes from vrubyrept reptname=tank

    Returns:
        List of sales data dicts
    """
    if not xml_content:
        logger.warning("No sales XML data provided")
        return []

    # Log raw XML size for diagnostics
    logger.info(f"Sales XML received: {len(xml_content)} bytes")

    try:
        root = ET.fromstring(xml_content)
        sales = []

        # Log the XML structure at INFO level for diagnostics
        logger.info(f"Sales XML root tag: {root.tag}")
        logger.debug(f"Sales XML sample: {ET.tostring(root, encoding='unicode')[:500]}")

        # Try multiple XML patterns for product sales
        # Pattern 1: tankPd structure with tankTotal elements
        tank_totals = root.findall('.//{*}tankTotal') or root.findall('.//tankTotal')
        logger.info(f"Found {len(tank_totals)} tankTotal elements in sales XML")

        if tank_totals:
            # Verifone Ruby/Sapphire format
            for i, tank_elem in enumerate(tank_totals):
                try:
                    logger.debug(f"Processing tankTotal #{i+1}: {ET.tostring(tank_elem, encoding='unicode')[:200]}")

                    # Extract fuel tank name from fuelTank element (handle namespace)
                    # The element is <ns0:fuelTank> which requires proper namespace handling
                    fuel_tank_elem = None
                    for child in tank_elem:
                        if 'fuelTank' in child.tag:
                            fuel_tank_elem = child
                            break

                    logger.debug(f"  fuelTank element: {fuel_tank_elem}")
                    if fuel_tank_elem is not None:
                        product_code = fuel_tank_elem.text.strip() if fuel_tank_elem.text else 'UNKNOWN'
                        logger.debug(f"  product_code: {product_code}")
                    else:
                        logger.debug(f"  No fuelTank element found, skipping")
                        continue

                    # Extract fuelInfo element with sales data (handle namespace)
                    fuel_info_elem = None
                    for child in tank_elem:
                        if 'fuelInfo' in child.tag:
                            fuel_info_elem = child
                            break

                    logger.debug(f"  fuelInfo element: {fuel_info_elem}")
                    if fuel_info_elem is None:
                        logger.debug(f"  No fuelInfo element found, skipping")
                        continue

                    # Extract count, amount, volume from fuelInfo children
                    count_elem = None
                    amount_elem = None
                    volume_elem = None
                    for child in fuel_info_elem:
                        if 'count' in child.tag:
                            count_elem = child
                        elif 'amount' in child.tag:
                            amount_elem = child
                        elif 'volume' in child.tag:
                            volume_elem = child

                    transactions = int(count_elem.text) if count_elem is not None and count_elem.text else 0
                    revenue = float(amount_elem.text) if amount_elem is not None and amount_elem.text else 0.0
                    volume = float(volume_elem.text) if volume_elem is not None and volume_elem.text else 0.0

                    # Get full product name
                    product_name = product_code
                    if 'DSL' in product_code.upper():
                        product_name = 'Diesel'
                    elif 'UNL' in product_code.upper():
                        product_name = 'Unleaded'
                    elif 'PRM' in product_code.upper():
                        product_name = 'Premium'
                    elif 'MID' in product_code.upper():
                        product_name = 'Mid-Grade'

                    # Only include products with actual sales
                    if transactions > 0 or volume > 0:
                        sales.append({
                            'tank': product_code,
                            'full_name': product_name,
                            'transactions': transactions,
                            'revenue': round(revenue, 2),
                            'volume': round(volume, 3),
                            'color': get_fuel_color(product_code)
                        })
                        logger.info(f"  Product {product_code}: {transactions} txns, ${revenue:.2f}, {volume:.1f} gal")
                    else:
                        logger.debug(f"  Product {product_code}: Excluded (zero transactions and volume)")

                except (ValueError, AttributeError) as e:
                    logger.error(f"Error parsing tankTotal element: {e}")
                    continue
        else:
            # Pattern 2: Legacy product structure
            product_elements = root.findall('.//product') or root.findall('.//Product')

            for prod_elem in product_elements:
                try:
                    product_code = prod_elem.get('code') or prod_elem.get('productCode', 'UNKNOWN')
                    product_name = prod_elem.get('name') or prod_elem.get('productName', product_code)

                    # Extract sales metrics
                    txn_elem = prod_elem.find('transactions') or prod_elem.find('Transactions') or prod_elem.find('count')
                    rev_elem = prod_elem.find('revenue') or prod_elem.find('Revenue') or prod_elem.find('sales')
                    vol_elem = prod_elem.find('volume') or prod_elem.find('Volume') or prod_elem.find('volumeGallons')

                    transactions = int(txn_elem.text) if txn_elem is not None and txn_elem.text else 0
                    revenue = float(rev_elem.text) if rev_elem is not None and rev_elem.text else 0.0
                    volume = float(vol_elem.text) if vol_elem is not None and vol_elem.text else 0.0

                    # Only include products with actual sales
                    if transactions > 0 or volume > 0:
                        sales.append({
                            'tank': product_code,
                            'full_name': product_name,
                            'transactions': transactions,
                            'revenue': round(revenue, 2),
                            'volume': round(volume, 3),
                            'color': get_fuel_color(product_code)
                        })

                except (ValueError, AttributeError) as e:
                    logger.error(f"Error parsing product sales element: {e}")
                    continue

        total_revenue = sum(s['revenue'] for s in sales)
        total_volume = sum(s['volume'] for s in sales)
        total_txns = sum(s['transactions'] for s in sales)
        logger.info(f"Parsed {len(sales)} product sales records: {total_txns} total txns, ${total_revenue:.2f} revenue, {total_volume:.1f} gal")
        return sales

    except ET.ParseError as e:
        logger.error(f"XML parse error in sales data: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing sales XML: {e}")
        return []


def parse_alarm_history_from_tank_monitor(xml_content: bytes) -> Tuple[List[Dict], List[Dict]]:
    """
    Parse alarm history and current alarm status from tankMonitor XML.

    Expected XML structure:
    <alarmHistory>
        <externalAlarms>
            <alarmTypeDescription>EXT INPUT ON</alarmTypeDescription>
            <alarmDate>1999-06-04T11:51:00-06:00</alarmDate>
        </externalAlarms>
        <internalTankAlarms>
            <fuelTank sysid="4">DSL1</fuelTank>
            <internalAlarm>
                <alarmTypeDescription>THEFT</alarmTypeDescription>
                <alarmDate>2016-09-01T18:03:00-06:00</alarmDate>
            </internalAlarm>
        </internalTankAlarms>
    </alarmHistory>
    <alarmStatus>
        <intTankAlarmStatus>
            <fuelTank sysid="1">UNLEAD</fuelTank>
            <intTankFlags>
                <leak>OFF</leak>
                <highWater>OFF</highWater>
                <overFill>OFF</overFill>
                <lowLimit>OFF</lowLimit>
                <theft>OFF</theft>
            </intTankFlags>
        </intTankAlarmStatus>
    </alarmStatus>

    Args:
        xml_content: Raw XML bytes from tankMonitor

    Returns:
        Tuple of (alarm_history, alarm_status) lists
    """
    if not xml_content:
        logger.debug("No tankMonitor XML data provided for alarm parsing")
        return [], []

    try:
        root = ET.fromstring(xml_content)
        alarm_history = []
        alarm_status = []
        seen_alarms = set()  # For deduplication

        # Parse alarm history
        alarm_history_elem = root.find('.//{*}alarmHistory')
        if alarm_history_elem is not None:
            # External alarms
            for ext_alarm in alarm_history_elem.findall('.//{*}externalAlarms'):
                alarm_type = ext_alarm.findtext('.//{*}alarmTypeDescription', 'Unknown')
                alarm_date = ext_alarm.findtext('.//{*}alarmDate', '')

                # Parse date for formatting
                date_display = alarm_date[:10] if alarm_date else 'Unknown'
                try:
                    dt = datetime.fromisoformat(alarm_date.replace('Z', '+00:00'))
                    date_display = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass

                key = ('EXTERNAL', alarm_type, alarm_date[:10] if alarm_date else '')
                if key not in seen_alarms:
                    seen_alarms.add(key)
                    alarm_history.append({
                        'tank_id': 'EXT',
                        'tank_name': 'External',
                        'alarm_type': alarm_type,
                        'alarm_date': alarm_date,
                        'date_display': date_display,
                        'category': 'external',
                        'severity': get_alarm_severity(alarm_type)
                    })

            # Internal tank alarms
            for tank_alarms in alarm_history_elem.findall('.//{*}internalTankAlarms'):
                fuel_tank_elem = tank_alarms.find('.//{*}fuelTank')
                tank_id = fuel_tank_elem.get('sysid') if fuel_tank_elem is not None else 'Unknown'
                tank_name = fuel_tank_elem.text if fuel_tank_elem is not None and fuel_tank_elem.text else f'Tank {tank_id}'

                for internal in tank_alarms.findall('.//{*}internalAlarm'):
                    alarm_type = internal.findtext('.//{*}alarmTypeDescription', 'Unknown')
                    alarm_date = internal.findtext('.//{*}alarmDate', '')

                    # Parse date for formatting
                    date_display = alarm_date[:10] if alarm_date else 'Unknown'
                    try:
                        dt = datetime.fromisoformat(alarm_date.replace('Z', '+00:00'))
                        date_display = dt.strftime('%Y-%m-%d %H:%M')
                    except:
                        pass

                    # Deduplicate based on tank, type, date (ignore time)
                    key = (tank_id, alarm_type, alarm_date[:10] if alarm_date else '')
                    if key not in seen_alarms:
                        seen_alarms.add(key)
                        alarm_history.append({
                            'tank_id': tank_id,
                            'tank_name': tank_name,
                            'alarm_type': alarm_type,
                            'alarm_date': alarm_date,
                            'date_display': date_display,
                            'category': 'internal',
                            'severity': get_alarm_severity(alarm_type)
                        })

        # Parse current alarm status
        for tank_status in root.findall('.//{*}intTankAlarmStatus'):
            fuel_tank_elem = tank_status.find('.//{*}fuelTank')
            tank_id = fuel_tank_elem.get('sysid') if fuel_tank_elem is not None else 'Unknown'
            tank_name = fuel_tank_elem.text if fuel_tank_elem is not None and fuel_tank_elem.text else f'Tank {tank_id}'

            flags_elem = tank_status.find('.//{*}intTankFlags')
            if flags_elem is not None:
                status = {
                    'tank_id': tank_id,
                    'tank_name': tank_name,
                    'leak': flags_elem.findtext('leak', 'OFF') == 'ON',
                    'high_water': flags_elem.findtext('highWater', 'OFF') == 'ON',
                    'overfill': flags_elem.findtext('overFill', 'OFF') == 'ON',
                    'low_limit': flags_elem.findtext('lowLimit', 'OFF') == 'ON',
                    'theft': flags_elem.findtext('theft', 'OFF') == 'ON',
                }
                # Calculate if any alarm is active
                status['has_active_alarm'] = any([
                    status['leak'], status['high_water'], status['overfill'],
                    status['low_limit'], status['theft']
                ])
                status['active_alarms'] = [
                    name for name, active in [
                        ('LEAK', status['leak']),
                        ('HIGH WATER', status['high_water']),
                        ('OVERFILL', status['overfill']),
                        ('LOW LIMIT', status['low_limit']),
                        ('THEFT', status['theft'])
                    ] if active
                ]
                alarm_status.append(status)

        # Sort alarm history by date (newest first)
        alarm_history.sort(key=lambda x: x['alarm_date'], reverse=True)

        logger.info(f"Parsed {len(alarm_history)} unique alarm history records, {len(alarm_status)} tank status records")
        return alarm_history, alarm_status

    except ET.ParseError as e:
        logger.error(f"XML parse error in alarm parsing: {e}")
        return [], []
    except Exception as e:
        logger.error(f"Unexpected error parsing alarms: {e}")
        return [], []


def get_alarm_severity(alarm_type: str) -> str:
    """
    Get severity level for an alarm type.

    Returns: 'critical', 'warning', or 'info'
    """
    alarm_upper = alarm_type.upper()

    critical_alarms = ['LEAK', 'OVERFILL', 'HIGH WATER']
    warning_alarms = ['THEFT', 'LOW LIMIT', 'SUDDEN LOSS']
    info_alarms = ['EXT INPUT', 'DELIVERY']

    for pattern in critical_alarms:
        if pattern in alarm_upper:
            return 'critical'

    for pattern in warning_alarms:
        if pattern in alarm_upper:
            return 'warning'

    return 'info'


def parse_alarm_history_xml(xml_content: bytes) -> List[Dict]:
    """
    Parse alarm history XML to extract tank alarms (legacy function).

    Args:
        xml_content: Raw XML bytes from alarm history endpoint

    Returns:
        List of alarm dicts, or empty list if not available
    """
    if not xml_content:
        logger.debug("No alarm history XML data provided")
        return []

    # Try new tankMonitor format first
    alarm_history, _ = parse_alarm_history_from_tank_monitor(xml_content)
    if alarm_history:
        return alarm_history

    # Legacy format fallback
    try:
        root = ET.fromstring(xml_content)
        alarms = []

        alarm_elements = root.findall('.//alarm') or root.findall('.//Alarm')

        for alarm_elem in alarm_elements:
            try:
                tank = alarm_elem.get('tank') or alarm_elem.get('tankId', 'Unknown')
                alarm_type = alarm_elem.get('type') or alarm_elem.get('alarmType', 'Unknown')
                date = alarm_elem.get('date') or alarm_elem.get('timestamp', 'Unknown')

                alarms.append({
                    'tank': tank,
                    'type': alarm_type,
                    'date': date
                })

            except (ValueError, AttributeError) as e:
                logger.error(f"Error parsing alarm element: {e}")
                continue

        logger.info(f"Parsed {len(alarms)} alarm records")
        return alarms

    except ET.ParseError as e:
        logger.error(f"XML parse error in alarm history: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing alarm XML: {e}")
        return []


def parse_deliveries_from_tank_monitor(xml_content: bytes) -> Tuple[List[Dict], Dict]:
    """
    Parse delivery records from tankMonitor XML.

    Expected XML structure:
    <deliveryInfo>
        <fuelTank sysid="1">UNLEAD</fuelTank>
        <deliveryRecords>
            <startDate>2026-01-12T14:11:00-07:00</startDate>
            <endDate>2026-01-12T14:17:00-07:00</endDate>
            <startVolume>8408</startVolume>
            <startTemperature>0.00392</startTemperature>
            <endVolume>9264</endVolume>
            <endTemperature>0.00391</endTemperature>
        </deliveryRecords>
    </deliveryInfo>

    Args:
        xml_content: Raw XML bytes from tankMonitor

    Returns:
        Tuple of (delivery_list, delivery_summary)
        - delivery_list: List of all delivery records
        - delivery_summary: Dict with aggregated stats by tank and overall
    """
    if not xml_content:
        logger.debug("No tankMonitor XML data provided for delivery parsing")
        return [], {}

    try:
        root = ET.fromstring(xml_content)
        deliveries = []

        for delivery_info in root.findall('.//{*}deliveryInfo'):
            # Get tank info
            fuel_tank_elem = delivery_info.find('.//{*}fuelTank')
            tank_id = fuel_tank_elem.get('sysid') if fuel_tank_elem is not None else 'Unknown'
            tank_name = fuel_tank_elem.text if fuel_tank_elem is not None and fuel_tank_elem.text else f'Tank {tank_id}'

            # Get full product name
            full_name = tank_name
            if 'DSL' in tank_name.upper() or 'DIESEL' in tank_name.upper():
                full_name = 'Diesel'
            elif 'UNL' in tank_name.upper() or 'UNLEAD' in tank_name.upper():
                full_name = 'Unleaded'
            elif 'PRM' in tank_name.upper() or 'PREM' in tank_name.upper():
                full_name = 'Premium'
            elif 'MID' in tank_name.upper():
                full_name = 'Mid-Grade'

            # Parse each delivery record
            for record in delivery_info.findall('.//{*}deliveryRecords'):
                start_date = record.findtext('.//{*}startDate', '')
                end_date = record.findtext('.//{*}endDate', '')
                start_vol = float(record.findtext('.//{*}startVolume', '0') or '0')
                end_vol = float(record.findtext('.//{*}endVolume', '0') or '0')
                start_temp = float(record.findtext('.//{*}startTemperature', '0') or '0')
                end_temp = float(record.findtext('.//{*}endTemperature', '0') or '0')

                # Calculate delivery volume
                delivered = end_vol - start_vol

                # Parse dates
                start_display = start_date[:10] if start_date else 'Unknown'
                end_display = end_date[:10] if end_date else 'Unknown'
                try:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    start_display = start_dt.strftime('%Y-%m-%d %H:%M')
                    end_display = end_dt.strftime('%Y-%m-%d %H:%M')
                    duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
                except:
                    duration_minutes = 0

                deliveries.append({
                    'tank_id': tank_id,
                    'tank_name': tank_name,
                    'full_name': full_name,
                    'start_date': start_date,
                    'end_date': end_date,
                    'start_display': start_display,
                    'end_display': end_display,
                    'start_volume': round(start_vol, 0),
                    'end_volume': round(end_vol, 0),
                    'delivered_gallons': round(delivered, 0),
                    'start_temp': start_temp,
                    'end_temp': end_temp,
                    'duration_minutes': duration_minutes,
                    'color': get_fuel_color(tank_name)
                })

        # Sort by date descending
        deliveries.sort(key=lambda x: x['start_date'], reverse=True)

        # Calculate summary statistics
        summary = {
            'total_deliveries': len(deliveries),
            'total_gallons': sum(d['delivered_gallons'] for d in deliveries),
            'by_tank': {},
            'recent_30_days': [],
            'monthly_totals': {}
        }

        # Group by tank
        for d in deliveries:
            tank_name = d['tank_name']
            if tank_name not in summary['by_tank']:
                summary['by_tank'][tank_name] = {
                    'full_name': d['full_name'],
                    'count': 0,
                    'total_gallons': 0,
                    'deliveries': [],
                    'color': d['color']
                }
            summary['by_tank'][tank_name]['count'] += 1
            summary['by_tank'][tank_name]['total_gallons'] += d['delivered_gallons']
            summary['by_tank'][tank_name]['deliveries'].append(d)

        # Calculate monthly totals for charting
        for d in deliveries:
            try:
                dt = datetime.fromisoformat(d['start_date'].replace('Z', '+00:00'))
                month_key = dt.strftime('%Y-%m')
                if month_key not in summary['monthly_totals']:
                    summary['monthly_totals'][month_key] = {
                        'month': dt.strftime('%b %Y'),
                        'total_gallons': 0,
                        'count': 0,
                        'by_tank': {}
                    }
                summary['monthly_totals'][month_key]['total_gallons'] += d['delivered_gallons']
                summary['monthly_totals'][month_key]['count'] += 1

                tank_name = d['tank_name']
                if tank_name not in summary['monthly_totals'][month_key]['by_tank']:
                    summary['monthly_totals'][month_key]['by_tank'][tank_name] = 0
                summary['monthly_totals'][month_key]['by_tank'][tank_name] += d['delivered_gallons']
            except:
                pass

        logger.info(f"Parsed {len(deliveries)} delivery records totaling {summary['total_gallons']:,.0f} gallons")
        return deliveries, summary

    except ET.ParseError as e:
        logger.error(f"XML parse error in delivery parsing: {e}")
        return [], {}
    except Exception as e:
        logger.error(f"Unexpected error parsing deliveries: {e}")
        return [], {}


def parse_reconciliation_from_tank_monitor(xml_content: bytes, tank_inventory: List[Dict] = None) -> List[Dict]:
    """
    Parse tank reconciliation totals from tankMonitor XML.

    Expected XML structure:
    <tankRecTotals>
        <tankRecRecord>
            <fuelTank sysid="1"/>
            <beginInventories>
                <inventoryDate>2026-01-14T01:37:00-07:00</inventoryDate>
                <inventoryVolume>7493</inventoryVolume>
            </beginInventories>
            <endInventories>
                <inventoryDate>2026-01-14T16:49:00-07:00</inventoryDate>
                <inventoryVolume>7065</inventoryVolume>
            </endInventories>
            <dispensedVolume>408.505</dispensedVolume>
        </tankRecRecord>
    </tankRecTotals>

    Args:
        xml_content: Raw XML bytes from tankMonitor
        tank_inventory: Optional tank inventory list to get tank names

    Returns:
        List of reconciliation records
    """
    if not xml_content:
        logger.debug("No tankMonitor XML data provided for reconciliation parsing")
        return []

    try:
        root = ET.fromstring(xml_content)
        reconciliation = []

        # Create tank name lookup from inventory
        tank_names = {}
        if tank_inventory:
            for tank in tank_inventory:
                tank_names[str(tank.get('id', ''))] = tank.get('name', f'Tank {tank.get("id", "")}')

        for rec_record in root.findall('.//{*}tankRecRecord'):
            fuel_tank_elem = rec_record.find('.//{*}fuelTank')
            tank_id = fuel_tank_elem.get('sysid') if fuel_tank_elem is not None else 'Unknown'
            tank_name = tank_names.get(str(tank_id), f'Tank {tank_id}')

            # Get full product name
            full_name = tank_name
            if 'DSL' in tank_name.upper() or 'DIESEL' in tank_name.upper():
                full_name = 'Diesel'
            elif 'UNL' in tank_name.upper() or 'UNLEAD' in tank_name.upper():
                full_name = 'Unleaded'
            elif 'PRM' in tank_name.upper() or 'PREM' in tank_name.upper():
                full_name = 'Premium'
            elif 'MID' in tank_name.upper():
                full_name = 'Mid-Grade'

            # Parse begin inventory
            begin_inv = rec_record.find('.//{*}beginInventories')
            begin_date = ''
            begin_vol = 0.0
            if begin_inv is not None:
                begin_date = begin_inv.findtext('.//{*}inventoryDate', '')
                begin_vol = float(begin_inv.findtext('.//{*}inventoryVolume', '0') or '0')

            # Parse end inventory
            end_inv = rec_record.find('.//{*}endInventories')
            end_date = ''
            end_vol = 0.0
            if end_inv is not None:
                end_date = end_inv.findtext('.//{*}inventoryDate', '')
                end_vol = float(end_inv.findtext('.//{*}inventoryVolume', '0') or '0')

            # Get dispensed volume
            dispensed = float(rec_record.findtext('.//{*}dispensedVolume', '0') or '0')

            # Calculate variance (should be close to 0 if no deliveries)
            expected_end = begin_vol - dispensed
            variance = end_vol - expected_end

            # Format dates
            begin_display = begin_date[:10] if begin_date else 'Unknown'
            end_display = end_date[:10] if end_date else 'Unknown'
            try:
                begin_dt = datetime.fromisoformat(begin_date.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                begin_display = begin_dt.strftime('%Y-%m-%d %H:%M')
                end_display = end_dt.strftime('%Y-%m-%d %H:%M')
            except:
                pass

            reconciliation.append({
                'tank_id': tank_id,
                'tank_name': tank_name,
                'full_name': full_name,
                'begin_date': begin_date,
                'begin_display': begin_display,
                'begin_volume': round(begin_vol, 0),
                'end_date': end_date,
                'end_display': end_display,
                'end_volume': round(end_vol, 0),
                'dispensed': round(dispensed, 1),
                'expected_end': round(expected_end, 0),
                'variance': round(variance, 1),
                'variance_pct': round((variance / begin_vol * 100) if begin_vol > 0 else 0, 2),
                'color': get_fuel_color(tank_name)
            })

        logger.info(f"Parsed reconciliation for {len(reconciliation)} tanks")
        return reconciliation

    except ET.ParseError as e:
        logger.error(f"XML parse error in reconciliation parsing: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing reconciliation: {e}")
        return []


def parse_delivery_history_xml(xml_content: bytes) -> Dict[str, List[Tuple[float, float]]]:
    """
    Parse delivery reconciliation XML to extract delivery history (legacy format).

    Args:
        xml_content: Raw XML bytes from vrubyrept reptname=tankRec

    Returns:
        Dict mapping tank names to list of (before, after) tuples
    """
    if not xml_content:
        logger.debug("No delivery history XML data provided")
        return {}

    # Try new tankMonitor format first
    deliveries, _ = parse_deliveries_from_tank_monitor(xml_content)
    if deliveries:
        # Convert to legacy format
        result = {}
        for d in deliveries:
            tank_name = d['tank_name']
            if tank_name not in result:
                result[tank_name] = []
            result[tank_name].append((d['start_volume'], d['end_volume']))
        return result

    # Legacy format fallback
    try:
        root = ET.fromstring(xml_content)
        deliveries = {}

        delivery_elements = root.findall('.//delivery') or root.findall('.//Delivery')

        for delivery_elem in delivery_elements:
            try:
                tank_id = delivery_elem.get('tank') or delivery_elem.get('tankId')
                tank_name = delivery_elem.get('tankName') or f'Tank {tank_id}'

                before_elem = delivery_elem.find('before') or delivery_elem.find('Before') or delivery_elem.find('volumeBefore')
                after_elem = delivery_elem.find('after') or delivery_elem.find('After') or delivery_elem.find('volumeAfter')

                if before_elem is not None and after_elem is not None:
                    before_vol = float(before_elem.text) if before_elem.text else 0.0
                    after_vol = float(after_elem.text) if after_elem.text else 0.0

                    if tank_name not in deliveries:
                        deliveries[tank_name] = []

                    deliveries[tank_name].append((round(before_vol, 0), round(after_vol, 0)))

            except (ValueError, AttributeError) as e:
                logger.error(f"Error parsing delivery element: {e}")
                continue

        logger.info(f"Parsed delivery history for {len(deliveries)} tanks")
        return deliveries

    except ET.ParseError as e:
        logger.error(f"XML parse error in delivery history: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error parsing delivery XML: {e}")
        return {}


def parse_diagnostics_xml(xml_content: bytes) -> Dict:
    """
    Parse forecourt diagnostics XML to extract equipment status.

    Expected XML structure:
    <diag:diagnostics time="2026-01-13T13:58:54-07:00" siteId="119">
        <forecourtDiagnostics>
            <controller status="Online" type="controller">
                <diag:peripherals>
                    <device type="Tank Level Sensor" status="Online" isAvailable="true"/>
                    <device id="Channel 1" type="Fuel Price Display" status="Online" isAvailable="true"/>
                </diag:peripherals>
            </controller>
        </forecourtDiagnostics>
    </diag:diagnostics>

    Args:
        xml_content: Raw XML bytes from vforecourtdiagnostics

    Returns:
        Dict with equipment status:
        {
            'controller_status': 'Online',
            'tank_monitor': {
                'status': 'Online',
                'available': True,
                'type': 'Tank Level Sensor'
            },
            'pumps_online': 10,
            'pumps_total': 10
        }
    """
    if not xml_content:
        logger.debug("No diagnostics XML data provided")
        return {}

    try:
        root = ET.fromstring(xml_content)
        result = {
            'controller_status': 'Unknown',
            'tank_monitor': None,
            'pumps_online': 0,
            'pumps_total': 0
        }

        # Get controller status
        controller = root.find('.//{*}controller')
        if controller is not None:
            result['controller_status'] = controller.get('status', 'Unknown')

            # Find Tank Level Sensor device
            for device in root.iter():
                if 'device' in device.tag:
                    device_type = device.get('type', '')

                    if 'Tank Level Sensor' in device_type or 'TLS' in device_type:
                        result['tank_monitor'] = {
                            'status': device.get('status', 'Unknown'),
                            'available': device.get('isAvailable', 'false').lower() == 'true',
                            'type': device_type
                        }

                    # Count pumps
                    if device_type == 'Pump':
                        result['pumps_total'] += 1
                        if device.get('status', '').lower() == 'online':
                            result['pumps_online'] += 1

        logger.info(f"Parsed diagnostics: Controller={result['controller_status']}, "
                   f"Tank Monitor={result['tank_monitor']['status'] if result['tank_monitor'] else 'Not Found'}, "
                   f"Pumps={result['pumps_online']}/{result['pumps_total']}")

        return result

    except ET.ParseError as e:
        logger.error(f"XML parse error in diagnostics: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error parsing diagnostics XML: {e}")
        return {}
