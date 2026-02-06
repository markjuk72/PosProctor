"""
Transaction Log Parser
Parses Verifone Commander XML transaction logs
"""

from lxml import etree
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def safe_text(element, default=''):
    """Safely get text from element."""
    return element.text if element is not None and element.text else default


def safe_attrib(element, attr, default=''):
    """Safely get attribute from element."""
    return element.get(attr, default) if element is not None else default


def parse_transaction(trans) -> Dict:
    """Parse a single transaction element into a flat dictionary."""
    trans_data = {
        'trans_type': trans.get('type', ''),
        'recalled': trans.get('recalled', ''),
        'rollback': trans.get('rollback', ''),
        'fuel_prepay': trans.get('fuelPrepay', ''),
        'fuel_prepay_completion': trans.get('fuelPrepayCompletion', '')
    }

    # Parse header information
    header = trans.find('trHeader')
    if header is not None:
        # Date/Time
        date_elem = header.find('date')
        trans_data['date'] = safe_text(date_elem)

        # Duration
        duration_elem = header.find('duration')
        trans_data['duration'] = safe_text(duration_elem)

        # Store number
        store_elem = header.find('storeNumber')
        trans_data['store_number'] = safe_text(store_elem)

        # POS/Register
        pos_elem = header.find('posNum')
        trans_data['pos_number'] = safe_text(pos_elem)

        # Physical register ID
        phys_reg = header.find('physicalRegisterID')
        trans_data['register_id'] = safe_text(phys_reg)

        # Till
        till_elem = header.find('till')
        trans_data['till'] = safe_text(till_elem)

        # Cashier
        cashier_elem = header.find('cashier')
        if cashier_elem is not None:
            trans_data['cashier'] = safe_text(cashier_elem)
            trans_data['cashier_id'] = cashier_elem.get('sysid', '')
            trans_data['cashier_emp_num'] = cashier_elem.get('empNum', '')

        # Transaction numbers
        ticket_num = header.find('trTickNum')
        if ticket_num is not None:
            trans_data['ticket_pos'] = safe_text(ticket_num.find('posNum'))
            trans_data['ticket_seq'] = safe_text(ticket_num.find('trSeq'))

        unique_sn = header.find('trUniqueSN')
        trans_data['unique_sn'] = safe_text(unique_sn)

        unique_id = header.find('uniqueID')
        trans_data['unique_id'] = safe_text(unique_id)

        # Period information
        periods = header.findall('period')
        for p in periods:
            level = p.get('level', '')
            if level == '0':
                trans_data['period_hour'] = p.get('seq', '')
            elif level == '1':
                trans_data['period_shift'] = p.get('seq', '')
            elif level == '2':
                trans_data['period_day'] = p.get('seq', '')

    # Parse value/totals
    value = trans.find('trValue')
    if value is not None:
        trans_data['total_no_tax'] = safe_text(value.find('trTotNoTax'))
        trans_data['total_with_tax'] = safe_text(value.find('trTotWTax'))
        trans_data['total_tax'] = safe_text(value.find('trTotTax'))
        trans_data['currency_total'] = safe_text(value.find('trCurrTot'))

    # Parse loyalty program information
    loyalty = trans.find('.//trLoyaltyProgram')
    if loyalty is not None:
        trans_data['loyalty_program'] = loyalty.get('programID', '')
        trans_data['loyalty_account'] = safe_text(loyalty.find('trloAccount'))
        trans_data['loyalty_subtotal'] = safe_text(loyalty.find('trloSubTotal'))
        trans_data['loyalty_discount'] = safe_text(loyalty.find('trloAutoDisc'))
    else:
        trans_data['loyalty_program'] = ''

    # Count line items and categorize as fuel vs inside (non-fuel)
    tr_lines = trans.find('trLines')
    fuel_item_count = 0
    inside_item_count = 0
    fuel_total = 0.0
    inside_total = 0.0

    if tr_lines is not None:
        line_items = tr_lines.findall('trLine')
        trans_data['line_item_count'] = len(line_items)

        # Get first item for reference
        if line_items:
            first_item = line_items[0]
            desc = first_item.find('trlDesc')
            trans_data['first_item_desc'] = safe_text(desc)

            upc = first_item.find('trlUPC')
            trans_data['first_item_upc'] = safe_text(upc)

        # Categorize each line item
        for line in line_items:
            dept = line.find('trlDept')
            cat = line.find('trlCat')
            line_total = line.find('trlLineTot')

            dept_type = dept.get('type', '') if dept is not None else ''
            cat_name = safe_text(cat)

            try:
                amount = float(safe_text(line_total) or '0')
            except (ValueError, TypeError):
                amount = 0.0

            # Fuel items have dept type="fuel" or category "FUEL"
            if dept_type == 'fuel' or cat_name == 'FUEL' or cat_name == 'FUEL DEPOSIT':
                fuel_item_count += 1
                fuel_total += amount
            else:
                inside_item_count += 1
                inside_total += amount

    trans_data['fuel_item_count'] = fuel_item_count
    trans_data['inside_item_count'] = inside_item_count
    trans_data['fuel_sales_total'] = round(fuel_total, 2)
    trans_data['inside_sales_total'] = round(inside_total, 2)

    # Determine sale type: fuel_only, inside_only, or mixed
    if fuel_item_count > 0 and inside_item_count > 0:
        trans_data['sale_type'] = 'mixed'
    elif fuel_item_count > 0:
        trans_data['sale_type'] = 'fuel_only'
    elif inside_item_count > 0:
        trans_data['sale_type'] = 'inside_only'
    else:
        trans_data['sale_type'] = 'unknown'

    # Parse payment information from trPaylines
    paylines = trans.find('trPaylines')
    if paylines is not None:
        payline_list = paylines.findall('trPayline')
        if payline_list:
            # Get first non-change payment
            for payline in payline_list:
                paycode_elem = payline.find('trpPaycode')
                if paycode_elem is not None:
                    payment_name = safe_text(paycode_elem)
                    # Skip "Change" entries
                    if payment_name.lower() != 'change':
                        trans_data['payment_method'] = payment_name
                        trans_data['payment_mop'] = paycode_elem.get('mop', '')
                        trans_data['payment_amount'] = safe_text(payline.find('trpAmt'))

                        # Card info if present
                        card_info = payline.find('trpCardInfo')
                        if card_info is not None:
                            trans_data['card_type'] = safe_text(card_info.find('trpcCCName'))
                            trans_data['card_entry'] = safe_text(card_info.find('trpcEntryMeth'))
                        break

    # Parse fuel information
    fuel = trans.find('trFuel')
    if fuel is not None:
        trans_data['fuel_pump'] = safe_text(fuel.find('fuelPump'))
        trans_data['fuel_grade'] = safe_text(fuel.find('fuelGrade'))
        trans_data['fuel_volume'] = safe_text(fuel.find('fuelVolume'))
        trans_data['fuel_price'] = safe_text(fuel.find('fuelPrice'))
        trans_data['fuel_total'] = safe_text(fuel.find('fuelTotal'))

    return trans_data


def parse_tlog_xml(xml_content: bytes, include_journal: bool = False) -> List[Dict]:
    """
    Parse a Verifone transaction log XML file.

    Args:
        xml_content: XML content as bytes
        include_journal: Include journal events (default: False)
                        Journal events are system events and not financially interesting.
                        Set to True for debugging purposes.

    Returns:
        List of transaction dictionaries
    """
    try:
        root = etree.fromstring(xml_content)

        # Get period information
        period_info = {
            'period_id': root.get('periodID', ''),
            'period_name': root.get('periodname', ''),
            'short_id': root.get('shortId', ''),
            'site': root.get('site', ''),
            'opened_time': safe_text(root.find('openedTime')),
            'closed_time': safe_text(root.find('closedTime'))
        }

        # Find all transactions
        transactions = []
        journal_count = 0
        for trans in root.xpath('.//trans'):
            trans_data = parse_transaction(trans)

            # Filter out journal events unless explicitly requested
            if trans_data.get('trans_type') == 'journal':
                journal_count += 1
                if not include_journal:
                    continue

            # Add period info to each transaction
            trans_data.update(period_info)
            transactions.append(trans_data)

        if journal_count > 0 and not include_journal:
            logger.info(f"Filtered out {journal_count} journal events (system events)")

        logger.info(f"Parsed {len(transactions)} transactions from TLOG")
        return transactions

    except etree.XMLSyntaxError as e:
        logger.error(f"XML parsing error: {e}")
        return []
    except Exception as e:
        logger.error(f"Error parsing TLOG: {e}")
        return []


def is_revenue_transaction(trans: Dict) -> bool:
    """
    Determine if a transaction should be counted for revenue calculations.

    Excludes:
    - Rollback transactions (cancelled/reversed)
    - Prepay transactions (money collected but fuel not yet dispensed)

    Includes:
    - Normal sales
    - Network sales
    - Prepay completions (actual fuel dispensed after prepay)
    - Refunds (negative revenue)

    This prevents double-counting when a customer does a prepay:
    1. PREPAY transaction - customer pays $20 (excluded from revenue)
    2. COMPLETION transaction - fuel dispensed for $20 (included in revenue)

    The COMPLETION transaction represents the actual sale.
    """
    # Rollback transactions are cancelled - never count
    if trans.get('rollback') == 'true':
        return False

    # Prepay transactions are just deposits - don't count until completion
    if trans.get('fuel_prepay') == 'true':
        return False

    # All other sale types count (including prepay completions)
    trans_type = trans.get('trans_type', '')
    return trans_type in ['sale', 'network sale', 'refund sale']


def extract_top_items(xml_content: bytes, limit: int = 10) -> Dict:
    """
    Extract top selling items from raw XML content.

    Returns:
        Dictionary with 'fuel_items' and 'inside_items' lists,
        each containing items sorted by transaction count.
    """
    try:
        root = etree.fromstring(xml_content)

        fuel_items = {}
        inside_items = {}

        for trans in root.xpath('.//trans'):
            # Skip rollbacks and prepays for analysis (they're not real sales)
            if trans.get('rollback') == 'true' or trans.get('fuelPrepay') == 'true':
                continue

            # Only count sale-type transactions
            trans_type = trans.get('type', '')
            if trans_type not in ['sale', 'network sale']:
                continue

            tr_lines = trans.find('trLines')
            if tr_lines is None:
                continue

            for line in tr_lines.findall('trLine'):
                desc_elem = line.find('trlDesc')
                dept_elem = line.find('trlDept')
                cat_elem = line.find('trlCat')
                qty_elem = line.find('trlQty')
                total_elem = line.find('trlLineTot')

                desc = desc_elem.text if desc_elem is not None and desc_elem.text else 'Unknown'
                dept_type = dept_elem.get('type', '') if dept_elem is not None else ''
                dept_name = dept_elem.text if dept_elem is not None and dept_elem.text else ''
                cat = cat_elem.text if cat_elem is not None and cat_elem.text else ''

                # Skip rounding adjustments (penny rounding for cash transactions)
                # These have dept type "neg" or dept names like "Round Down/Up"
                if dept_type == 'neg' or 'round' in dept_name.lower():
                    continue

                # Skip lottery items (both purchases and payouts)
                if 'lottery' in dept_name.lower() or 'lottery' in desc.lower() or 'payout' in desc.lower():
                    continue

                try:
                    qty = float(qty_elem.text) if qty_elem is not None and qty_elem.text else 1
                except (ValueError, TypeError):
                    qty = 1

                try:
                    total = float(total_elem.text) if total_elem is not None and total_elem.text else 0
                except (ValueError, TypeError):
                    total = 0

                # Categorize as fuel or inside item
                if dept_type == 'fuel' or cat in ['FUEL', 'FUEL DEPOSIT']:
                    # For fuel, normalize the description to get fuel grade
                    # e.g., "REGULAR CA #02" -> "REGULAR"
                    fuel_grade = desc.split()[0] if desc else 'Unknown'
                    if fuel_grade not in fuel_items:
                        fuel_items[fuel_grade] = {'count': 0, 'qty': 0.0, 'revenue': 0.0}
                    fuel_items[fuel_grade]['count'] += 1
                    fuel_items[fuel_grade]['qty'] += qty
                    fuel_items[fuel_grade]['revenue'] += total
                else:
                    if desc not in inside_items:
                        inside_items[desc] = {'count': 0, 'qty': 0, 'revenue': 0.0}
                    inside_items[desc]['count'] += 1
                    inside_items[desc]['qty'] += int(qty)
                    inside_items[desc]['revenue'] += total

        # Sort and limit results
        sorted_fuel = sorted(
            [{'name': k, **v} for k, v in fuel_items.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:limit]

        sorted_inside = sorted(
            [{'name': k, **v} for k, v in inside_items.items()],
            key=lambda x: x['count'],
            reverse=True
        )[:limit]

        # Round revenue values
        for item in sorted_fuel:
            item['revenue'] = round(item['revenue'], 2)
            item['qty'] = round(item['qty'], 1)
        for item in sorted_inside:
            item['revenue'] = round(item['revenue'], 2)

        return {
            'fuel_items': sorted_fuel,
            'inside_items': sorted_inside
        }

    except Exception as e:
        logger.error(f"Error extracting top items: {e}")
        return {'fuel_items': [], 'inside_items': []}


def get_transaction_summary(transactions: List[Dict]) -> Dict:
    """
    Generate summary statistics from transactions.

    Revenue calculations exclude:
    - Rollback transactions (cancelled)
    - Prepay transactions (deposit only, counted when completed)

    This ensures accurate revenue totals without double-counting prepays.
    """
    if not transactions:
        return {}

    # Count transaction types
    type_counts = {}
    total_revenue = 0
    sale_count = 0
    fuel_count = 0
    payment_methods = {}

    # Track prepay/rollback stats
    prepay_count = 0
    rollback_count = 0
    completion_count = 0

    # Track loyalty program usage
    loyalty_programs = {}
    loyalty_transaction_count = 0

    # Track sale types (fuel vs inside)
    sale_types = {'fuel_only': 0, 'inside_only': 0, 'mixed': 0, 'unknown': 0}
    total_fuel_sales = 0.0
    total_inside_sales = 0.0

    for trans in transactions:
        trans_type = trans.get('trans_type', 'unknown')
        type_counts[trans_type] = type_counts.get(trans_type, 0) + 1

        # Track special transaction flags
        if trans.get('rollback') == 'true':
            rollback_count += 1
        if trans.get('fuel_prepay') == 'true':
            prepay_count += 1
        if trans.get('fuel_prepay_completion') == 'true':
            completion_count += 1

        # Only count revenue transactions for statistics
        if is_revenue_transaction(trans):
            # Revenue from sales (excluding prepays and rollbacks)
            if trans_type in ['sale', 'network sale', 'refund sale']:
                sale_count += 1
                total = trans.get('total_with_tax', '') or trans.get('currency_total', '')
                if total:
                    try:
                        total_revenue += float(total)
                    except (ValueError, TypeError):
                        pass

            # Loyalty program tracking
            loyalty_program = trans.get('loyalty_program', '')
            if loyalty_program:
                loyalty_programs[loyalty_program] = loyalty_programs.get(loyalty_program, 0) + 1
                loyalty_transaction_count += 1

            # Sale type tracking (fuel vs inside)
            sale_type = trans.get('sale_type', 'unknown')
            if sale_type in sale_types:
                sale_types[sale_type] += 1

            # Fuel and inside sales totals
            try:
                total_fuel_sales += float(trans.get('fuel_sales_total', 0) or 0)
                total_inside_sales += float(trans.get('inside_sales_total', 0) or 0)
            except (ValueError, TypeError):
                pass

            # Payment methods (only for revenue transactions)
            payment = trans.get('payment_method')
            if payment:
                payment_methods[payment] = payment_methods.get(payment, 0) + 1

        # Fuel transactions (actual dispensed fuel, not prepay deposits)
        if trans.get('fuel_pump') or trans.get('fuel_prepay_completion') == 'true':
            if trans.get('rollback') != 'true' and trans.get('fuel_prepay') != 'true':
                fuel_count += 1

    return {
        'total_transactions': len(transactions),
        'sale_count': sale_count,
        'fuel_count': fuel_count,
        'total_revenue': round(total_revenue, 2),
        'transaction_types': type_counts,
        'payment_methods': payment_methods,
        'prepay_count': prepay_count,
        'rollback_count': rollback_count,
        'completion_count': completion_count,
        'loyalty_programs': loyalty_programs,
        'loyalty_transaction_count': loyalty_transaction_count,
        'sale_types': sale_types,
        'total_fuel_sales': round(total_fuel_sales, 2),
        'total_inside_sales': round(total_inside_sales, 2),
        'period_info': {
            'period_name': transactions[0].get('period_name', ''),
            'site': transactions[0].get('site', ''),
            'opened_time': transactions[0].get('opened_time', ''),
            'closed_time': transactions[0].get('closed_time', '')
        }
    }
