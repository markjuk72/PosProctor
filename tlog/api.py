"""
POSProctor 2.0 - TLOG Service API
Flask REST API for transaction log operations
"""

from flask import Flask, request, jsonify
import logging
import os
import sqlite3
import json
from datetime import datetime
from verifone_client import VerifoneClient
from parser import parse_tlog_xml, get_transaction_summary, extract_top_items
from credential_service import get_commander_credentials

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
DB_PATH = os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')
TLOG_STORAGE_PATH = os.getenv('TLOG_STORAGE_PATH', '/app/data/tlogs')
DEFAULT_TIMEOUT = int(os.getenv('TLOG_TIMEOUT', '300'))

# Ensure storage directory exists
os.makedirs(TLOG_STORAGE_PATH, exist_ok=True)


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_commander_by_ip(ip):
    """Get commander configuration from database."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand
            FROM commanders
            WHERE ip = ? AND enabled = 1
        """, (ip,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_credentials():
    """Get Commander credentials using unified credential service.

    Priority:
    1. Bitwarden (source of truth)
    2. Local database cache
    3. Environment variables (fallback)

    This ensures consistency with other services in the stack.
    """
    creds = get_commander_credentials()
    if creds:
        logger.debug(f"Using Commander credentials for {creds['username']} (source: {creds.get('source', 'unknown')})")
        return {'username': creds['username'], 'password': creds['password']}
    return None


def save_tlog(commander_ip, store_name, report_filename, xml_content):
    """Save TLOG to storage directory."""
    # Extract date from report filename (e.g., 2025-12-30.123)
    date_part = report_filename.split('.')[0]

    # Create filename: STORE{store_number}_{date}.xml
    import re
    store_match = re.search(r'\d+', store_name)
    if store_match:
        store_number = store_match.group()
        filename = f"STORE{store_number}_{date_part}.xml"
    else:
        filename = f"{commander_ip}_{date_part}.xml"

    filepath = os.path.join(TLOG_STORAGE_PATH, filename)

    with open(filepath, 'wb') as f:
        f.write(xml_content)

    logger.info(f"Saved TLOG to {filename}")
    return filename


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'tlog',
        'version': '2.0',
        'storage_path': TLOG_STORAGE_PATH
    }), 200


@app.route('/api/tlog/latest', methods=['POST'])
def get_latest_tlog():
    """
    Download the latest transaction log from a commander.

    Request body:
    {
        "ip": "10.0.0.1",
        "period": 2,  # Optional: 1=shift, 2=day, null=all
        "include_journal": false  # Optional: Include journal events (default: false)
    }
    """
    data = request.json
    ip = data.get('ip')
    period = data.get('period')
    include_journal = data.get('include_journal', False)

    if not ip:
        return jsonify({'error': 'Missing required field: ip'}), 400

    # Get commander from database
    commander = get_commander_by_ip(ip)
    if not commander:
        return jsonify({'error': f'Commander {ip} not found or disabled'}), 404

    # Get credentials
    creds = get_credentials()
    if not creds:
        return jsonify({'error': 'No credentials configured'}), 500

    try:
        # Create client and authenticate
        client = VerifoneClient(
            ip=ip,
            username=creds['username'],
            password=creds['password'],
            timeout=DEFAULT_TIMEOUT
        )

        token = client.get_token()
        if not token:
            return jsonify({'error': f'Authentication failed for {ip}'}), 401

        try:
            # Get report list
            reports = client.get_report_list(token, period=period)
            if not reports:
                period_name = 'shift' if period == 1 else 'day' if period == 2 else 'any'
                return jsonify({'error': f'No {period_name} reports available'}), 404

            # Download latest report
            latest_report = reports[0]
            xml_content = client.download_report(token, latest_report)

            if not xml_content:
                return jsonify({'error': 'Failed to download report'}), 500

            # Parse transactions
            transactions = parse_tlog_xml(xml_content, include_journal=include_journal)

            if not transactions:
                return jsonify({'error': 'Failed to parse report or no transactions found'}), 500

            # Save to storage
            saved_filename = save_tlog(
                ip,
                commander['store_name'],
                latest_report['filename'],
                xml_content
            )

            # Generate summary
            summary = get_transaction_summary(transactions)

            # Extract top selling items
            top_items = extract_top_items(xml_content)

            return jsonify({
                'success': True,
                'commander': {
                    'ip': ip,
                    'store_name': commander['store_name'],
                    'group': commander['group_name'],
                    'brand': commander['brand']
                },
                'report': {
                    'filename': latest_report['filename'],
                    'period': latest_report['period'],
                    'size': latest_report['size'],
                    'saved_as': saved_filename
                },
                'summary': summary,
                'top_items': top_items,
                'transactions': transactions
            }), 200

        finally:
            client.release_token(token)

    except Exception as e:
        logger.error(f"Error fetching TLOG: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/date', methods=['POST'])
def get_tlog_by_date():
    """
    Download transaction log for a specific date.

    Request body:
    {
        "ip": "10.0.0.1",
        "date": "2025-12-30",
        "period": 2,  # Optional: 1=shift, 2=day
        "include_journal": false  # Optional: Include journal events (default: false)
    }
    """
    data = request.json
    ip = data.get('ip')
    date_str = data.get('date')
    period = data.get('period')
    include_journal = data.get('include_journal', False)

    if not ip or not date_str:
        return jsonify({'error': 'Missing required fields: ip, date'}), 400

    # Validate date format
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    # Get commander from database
    commander = get_commander_by_ip(ip)
    if not commander:
        return jsonify({'error': f'Commander {ip} not found or disabled'}), 404

    # Get credentials
    creds = get_credentials()
    if not creds:
        return jsonify({'error': 'No credentials configured'}), 500

    try:
        # Create client and authenticate
        client = VerifoneClient(
            ip=ip,
            username=creds['username'],
            password=creds['password'],
            timeout=DEFAULT_TIMEOUT
        )

        token = client.get_token()
        if not token:
            return jsonify({'error': f'Authentication failed for {ip}'}), 401

        try:
            # Get report list
            reports = client.get_report_list(token, period=period)
            if not reports:
                return jsonify({'error': 'No reports available'}), 404

            # Find report matching the date
            matching_report = None
            for report in reports:
                if report['filename'].startswith(date_str):
                    matching_report = report
                    break

            if not matching_report:
                period_name = f" (period {period})" if period else ""
                return jsonify({'error': f'No report found for {date_str}{period_name}'}), 404

            # Download report
            xml_content = client.download_report(token, matching_report)

            if not xml_content:
                return jsonify({'error': 'Failed to download report'}), 500

            # Parse transactions
            transactions = parse_tlog_xml(xml_content, include_journal=include_journal)

            if not transactions:
                return jsonify({'error': 'Failed to parse report or no transactions found'}), 500

            # Save to storage
            saved_filename = save_tlog(
                ip,
                commander['store_name'],
                matching_report['filename'],
                xml_content
            )

            # Generate summary
            summary = get_transaction_summary(transactions)

            # Extract top selling items
            top_items = extract_top_items(xml_content)

            return jsonify({
                'success': True,
                'commander': {
                    'ip': ip,
                    'store_name': commander['store_name'],
                    'group': commander['group_name'],
                    'brand': commander['brand']
                },
                'report': {
                    'filename': matching_report['filename'],
                    'period': matching_report['period'],
                    'size': matching_report['size'],
                    'saved_as': saved_filename
                },
                'summary': summary,
                'top_items': top_items,
                'transactions': transactions
            }), 200

        finally:
            client.release_token(token)

    except Exception as e:
        logger.error(f"Error fetching TLOG: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/list', methods=['POST'])
def list_available_reports():
    """
    List available reports from a commander without downloading.

    Request body:
    {
        "ip": "10.0.0.1",
        "period": 2  # Optional: 1=shift, 2=day, null=all
    }
    """
    data = request.json
    ip = data.get('ip')
    period = data.get('period')

    if not ip:
        return jsonify({'error': 'Missing required field: ip'}), 400

    # Get commander from database
    commander = get_commander_by_ip(ip)
    if not commander:
        return jsonify({'error': f'Commander {ip} not found or disabled'}), 404

    # Get credentials
    creds = get_credentials()
    if not creds:
        return jsonify({'error': 'No credentials configured'}), 500

    try:
        # Create client and authenticate
        client = VerifoneClient(
            ip=ip,
            username=creds['username'],
            password=creds['password'],
            timeout=DEFAULT_TIMEOUT
        )

        token = client.get_token()
        if not token:
            return jsonify({'error': f'Authentication failed for {ip}'}), 401

        try:
            # Get report list
            reports = client.get_report_list(token, period=period)

            return jsonify({
                'success': True,
                'commander': {
                    'ip': ip,
                    'store_name': commander['store_name']
                },
                'report_count': len(reports),
                'reports': reports
            }), 200

        finally:
            client.release_token(token)

    except Exception as e:
        logger.error(f"Error listing reports: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/stored', methods=['GET'])
def list_stored_tlogs():
    """List TLOGs stored in the storage directory."""
    try:
        files = []
        for filename in os.listdir(TLOG_STORAGE_PATH):
            if filename.endswith('.xml'):
                filepath = os.path.join(TLOG_STORAGE_PATH, filename)
                stat = os.stat(filepath)

                files.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        # Sort by filename (most recent first)
        files.sort(key=lambda x: x['filename'], reverse=True)

        return jsonify({
            'success': True,
            'count': len(files),
            'files': files
        }), 200

    except Exception as e:
        logger.error(f"Error listing stored TLOGs: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/stored/<filename>', methods=['GET'])
def get_stored_tlog(filename):
    """
    Parse and return a stored TLOG file.

    Query parameters:
        include_journal: Include journal events (default: false)
    """
    try:
        # Get query parameter
        include_journal = request.args.get('include_journal', 'false').lower() == 'true'

        # Sanitize filename to prevent directory traversal
        filename = os.path.basename(filename)
        if not filename.endswith('.xml'):
            filename += '.xml'

        filepath = os.path.join(TLOG_STORAGE_PATH, filename)

        if not os.path.exists(filepath):
            return jsonify({'error': 'File not found'}), 404

        # Read and parse file
        with open(filepath, 'rb') as f:
            xml_content = f.read()

        transactions = parse_tlog_xml(xml_content, include_journal=include_journal)

        if not transactions:
            return jsonify({'error': 'Failed to parse file or no transactions found'}), 500

        # Generate summary
        summary = get_transaction_summary(transactions)

        # Extract top selling items
        top_items = extract_top_items(xml_content)

        return jsonify({
            'success': True,
            'filename': filename,
            'summary': summary,
            'top_items': top_items,
            'transactions': transactions
        }), 200

    except Exception as e:
        logger.error(f"Error reading stored TLOG: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/availability', methods=['GET'])
def get_report_availability():
    """
    Check report availability across all enabled commanders.
    Returns a matrix of store -> date -> report availability.

    This queries each commander in parallel to check what reports are available.
    Results show the last 7 days of report availability per store.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import timedelta

    def check_store_availability(commander):
        """Check report availability for a single commander."""
        store_result = {
            'ip': commander['ip'],
            'store_name': commander['store_name'],
            'brand': commander.get('brand', 'Other'),
            'group_name': commander.get('group_name', ''),
            'status': 'unknown',
            'reports': {}
        }

        creds = get_credentials()
        if not creds:
            store_result['status'] = 'error'
            store_result['error'] = 'No credentials configured'
            return store_result

        try:
            client = VerifoneClient(
                ip=commander['ip'],
                username=creds['username'],
                password=creds['password'],
                timeout=30  # Shorter timeout for availability checks
            )

            token = client.get_token()
            if not token:
                store_result['status'] = 'offline'
                return store_result

            try:
                # Get all available reports
                reports = client.get_report_list(token, period=None)
                store_result['status'] = 'online'

                # Organize reports by date
                for report in reports:
                    filename = report.get('filename', '')
                    period = report.get('period', '1')

                    # Extract date from filename (e.g., "2026-01-15.123")
                    if '.' in filename:
                        date_part = filename.split('.')[0]
                        if len(date_part) == 10:  # YYYY-MM-DD
                            if date_part not in store_result['reports']:
                                store_result['reports'][date_part] = {}
                            if period == '1':
                                store_result['reports'][date_part]['shift'] = True
                            elif period == '2':
                                store_result['reports'][date_part]['day'] = True

            finally:
                client.release_token(token)

        except Exception as e:
            store_result['status'] = 'error'
            store_result['error'] = str(e)
            logger.warning(f"Error checking availability for {commander['ip']}: {e}")

        return store_result

    # Get all enabled commanders
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand
            FROM commanders
            WHERE enabled = 1
            ORDER BY brand, store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not commanders:
        return jsonify({
            'success': True,
            'stores': [],
            'message': 'No enabled commanders configured'
        }), 200

    # Check availability in parallel
    results = []
    max_workers = min(10, len(commanders))  # Limit parallel connections

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_commander = {
            executor.submit(check_store_availability, cmd): cmd
            for cmd in commanders
        }

        for future in as_completed(future_to_commander):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                cmd = future_to_commander[future]
                logger.error(f"Error checking {cmd['ip']}: {e}")
                results.append({
                    'ip': cmd['ip'],
                    'store_name': cmd['store_name'],
                    'brand': cmd.get('brand', 'Other'),
                    'status': 'error',
                    'error': str(e),
                    'reports': {}
                })

    # Sort results by brand, then store name
    results.sort(key=lambda x: (x.get('brand', ''), x.get('store_name', '')))

    return jsonify({
        'success': True,
        'stores': results,
        'checked_at': datetime.now().isoformat()
    }), 200


if __name__ == '__main__':
    logger.info("Starting TLOG service API...")
    logger.info(f"Database path: {DB_PATH}")
    logger.info(f"Storage path: {TLOG_STORAGE_PATH}")
    app.run(host='0.0.0.0', port=8001, debug=False)
