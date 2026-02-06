"""
POSProctor 2.0 - Web Interface
Simplified web UI for commander management and TLOG viewing
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, send_file
from flask_login import login_user, logout_user, current_user
import sqlite3
import os
import requests
import logging
import concurrent.futures
import json
import io
from datetime import datetime
from lib.bitwarden_api_client import BitwardenService
from lib.commander_password import rotate_password_on_commander
from lib.credential_service import get_credential_service, get_commander_credentials
from auth import init_auth, get_msal_app, login_required_conditional, protected_route, get_auth_config, User, ENTRA_REDIRECT_URI

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'posproctor2-web-interface-key')

# Initialize authentication
init_auth(app)

# Make auth_config available to all templates
@app.context_processor
def inject_auth_config():
    return {'auth_config': get_auth_config()}

# Configuration
DB_PATH = os.getenv('POSPROCTOR_DB_PATH', '/app/data/database/posproctor.db')
# Internal service URLs (for backend API calls)
TLOG_SERVICE_URL = os.getenv('TLOG_SERVICE_URL', 'http://tlog:8001')
MONITORING_SERVICE_URL = os.getenv('MONITORING_SERVICE_URL', 'http://monitoring:8000')
BITWARDEN_SERVICE_URL = os.getenv('BITWARDEN_SERVICE_URL', 'http://bitwarden-serve:8087')

# External URLs (for frontend links - via nginx proxy or direct)
# Grafana runs on port 3000 (will be constructed client-side)
GRAFANA_PORT = os.getenv('GRAFANA_PORT', '3000')
PROMETHEUS_EXTERNAL_URL = os.getenv('PROMETHEUS_EXTERNAL_URL', '/prometheus/')
MONITORING_METRICS_URL = os.getenv('MONITORING_METRICS_URL', '/api/monitoring/metrics')
TLOG_HEALTH_URL = os.getenv('TLOG_HEALTH_URL', '/api/tlog/health')

# Bitwarden service instance
bitwarden_service = None


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def regenerate_commanders_csv():
    """
    Regenerate the commanders.csv file for Vector enrichment.
    This CSV maps IP addresses to store names for log enrichment.
    Format: ip,store (matching production grafanacommander setup)
    """
    csv_path = os.path.join(os.path.dirname(DB_PATH), 'commanders.csv')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ip, store_name
            FROM commanders
            WHERE enabled = 1
        """)
        rows = cursor.fetchall()
        conn.close()

        with open(csv_path, 'w') as f:
            f.write('ip,store\n')
            for row in rows:
                # Escape any commas in values
                ip = row['ip'] or ''
                store = (row['store_name'] or '').replace(',', ' ')
                f.write(f'{ip},{store}\n')

        logger.info(f"Regenerated commanders.csv with {len(rows)} entries")
    except Exception as e:
        logger.error(f"Failed to regenerate commanders.csv: {e}")


def get_commander_stats():
    """Get commander statistics from database."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Total commanders
        cursor.execute("SELECT COUNT(*) as total FROM commanders")
        total_stores = cursor.fetchone()['total']

        # Enabled commanders
        cursor.execute("SELECT COUNT(*) as enabled FROM commanders WHERE enabled = 1")
        enabled_stores = cursor.fetchone()['enabled']

        # Unique groups
        cursor.execute("SELECT COUNT(DISTINCT group_name) as groups FROM commanders WHERE enabled = 1")
        groups = cursor.fetchone()['groups']

        # Unique brands
        cursor.execute("SELECT COUNT(DISTINCT brand) as brands FROM commanders WHERE enabled = 1")
        brands = cursor.fetchone()['brands']

        return {
            'total_stores': total_stores,
            'enabled_stores': enabled_stores,
            'groups': groups,
            'brands': brands
        }
    finally:
        conn.close()


def get_settings():
    """Get settings from database."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT key, value, data_type
            FROM settings
        """)
        settings = {}
        for row in cursor.fetchall():
            key = row['key']
            value = row['value']
            data_type = row['data_type']

            # Convert value based on data_type
            if data_type == 'integer':
                settings[key] = int(value)
            elif data_type == 'boolean':
                settings[key] = value.lower() == 'true'
            else:
                settings[key] = value

        return settings
    finally:
        conn.close()


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'webapp',
        'version': '2.0'
    }), 200


@app.route('/api/system/health', methods=['GET'])
def system_health():
    """Aggregate health status of all backend services in one call."""
    import requests as http_requests
    import time as _time

    services_status = {}

    # --- Monitoring service ---
    try:
        resp = http_requests.get(f'{MONITORING_SERVICE_URL}/health', timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            uptime_s = data.get('uptime_seconds', 0)
            last_scrape = data.get('last_scrape', {})
            scrape_ts = last_scrape.get('timestamp')
            scrape_age = round(_time.time() - scrape_ts) if scrape_ts else None
            services_status['monitoring'] = {
                'status': 'online',
                'uptime_seconds': round(uptime_s),
                'poll_interval': data.get('poll_interval_seconds', 300),
                'last_scrape_age_seconds': scrape_age,
                'last_scrape_success': last_scrape.get('success_count', 0),
                'last_scrape_total': last_scrape.get('total_count', 0),
            }
        else:
            services_status['monitoring'] = {'status': 'degraded'}
    except Exception:
        services_status['monitoring'] = {'status': 'offline'}

    # --- TLOG service ---
    try:
        resp = http_requests.get(f'{TLOG_SERVICE_URL}/health', timeout=3)
        services_status['tlog'] = {
            'status': 'online' if resp.status_code == 200 else 'degraded'
        }
    except Exception:
        services_status['tlog'] = {'status': 'offline'}

    # --- Prometheus ---
    try:
        prometheus_url = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
        resp = http_requests.get(f'{prometheus_url}/-/healthy', timeout=3)
        services_status['prometheus'] = {
            'status': 'online' if resp.status_code == 200 else 'degraded'
        }
    except Exception:
        services_status['prometheus'] = {'status': 'offline'}

    # --- Grafana (uses HTTPS internally) ---
    try:
        grafana_url = os.getenv('GRAFANA_URL', 'https://grafana:3000')
        resp = http_requests.get(f'{grafana_url}/api/health', timeout=3, verify=False)
        services_status['grafana'] = {
            'status': 'online' if resp.status_code == 200 else 'degraded'
        }
    except Exception:
        services_status['grafana'] = {'status': 'offline'}

    # --- Bitwarden ---
    try:
        resp = http_requests.get(f'{BITWARDEN_SERVICE_URL}/status', timeout=3)
        services_status['bitwarden'] = {
            'status': 'online' if resp.status_code == 200 else 'degraded'
        }
    except Exception:
        services_status['bitwarden'] = {'status': 'offline'}

    # Webapp is always online if we got here
    services_status['webapp'] = {'status': 'online'}

    all_online = all(s['status'] == 'online' for s in services_status.values())

    return jsonify({
        'healthy': all_online,
        'services': services_status,
        'version': '2.0',
        'timestamp': _time.time()
    })


# ============================================
# Authentication Routes
# ============================================

@app.route('/login')
def login():
    """Login page - Only shown when AUTH_TYPE=entra"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    auth_config = get_auth_config()
    return render_template('login.html', auth_config=auth_config)


@app.route('/logout')
def logout():
    """Logout"""
    logout_user()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/auth/entra')
def entra_login():
    """Initiate Entra (Azure AD) login"""
    msal_app = get_msal_app()
    if not msal_app:
        flash('Microsoft Entra ID is not configured', 'error')
        return redirect(url_for('login'))

    redirect_uri = ENTRA_REDIRECT_URI or url_for('entra_callback', _external=True)
    auth_url = msal_app.get_authorization_request_url(
        scopes=["User.Read"],
        redirect_uri=redirect_uri
    )
    return redirect(auth_url)


@app.route('/auth/callback')
def entra_callback():
    """Handle Entra SSO callback"""
    msal_app = get_msal_app()
    if not msal_app:
        flash('Microsoft Entra ID is not configured', 'error')
        return redirect(url_for('login'))

    code = request.args.get('code')
    if not code:
        flash('Authentication failed', 'error')
        return redirect(url_for('login'))

    try:
        redirect_uri = ENTRA_REDIRECT_URI or url_for('entra_callback', _external=True)
        result = msal_app.acquire_token_by_authorization_code(
            code,
            scopes=["User.Read"],
            redirect_uri=redirect_uri
        )

        if "access_token" in result:
            # Get user info from Microsoft Graph
            graph_response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={'Authorization': 'Bearer ' + result['access_token']}
            )
            user_info = graph_response.json()
            username = user_info.get('userPrincipalName') or user_info.get('mail')

            user = User(id=username, username=username)
            login_user(user)
            session['username'] = username
            flash(f'Successfully logged in as {username}', 'success')
            return redirect(url_for('index'))
        else:
            flash('Authentication failed: ' + result.get("error_description", "Unknown error"), 'error')
            return redirect(url_for('login'))
    except Exception as e:
        logger.error(f"Entra auth error: {e}")
        flash(f'Authentication error: {str(e)}', 'error')
        return redirect(url_for('login'))


# ============================================
# Main Application Routes
# ============================================

@app.route('/')
def index():
    """Dashboard page."""
    stats = get_commander_stats()
    settings = get_settings()

    # Service URLs (external, accessible from browser)
    services = {
        'grafana_port': GRAFANA_PORT,
        'prometheus': PROMETHEUS_EXTERNAL_URL,
        'monitoring': MONITORING_METRICS_URL,
        'tlog': TLOG_HEALTH_URL
    }

    return render_template('index.html',
                         stats=stats,
                         settings=settings,
                         services=services)


@app.route('/commanders')
@protected_route
def commanders_page():
    """Commander management page."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand, enabled
            FROM commanders
            ORDER BY store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]

        return render_template('commanders.html', commanders=commanders)
    finally:
        conn.close()


@app.route('/commanders/add', methods=['POST'])
@protected_route
def add_commander():
    """Add a new commander."""
    ip = request.form.get('ip')
    store_name = request.form.get('store_name')
    group_name = request.form.get('group_name', '')
    brand = request.form.get('brand', '')
    enabled = request.form.get('enabled', 'on') == 'on'

    if not ip or not store_name:
        flash('IP and Store Name are required', 'error')
        return redirect(url_for('commanders_page'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO commanders (ip, store_name, group_name, brand, enabled)
            VALUES (?, ?, ?, ?, ?)
        """, (ip, store_name, group_name, brand, 1 if enabled else 0))
        conn.commit()
        regenerate_commanders_csv()
        flash(f'Commander {store_name} added successfully', 'success')
    except sqlite3.IntegrityError:
        flash(f'Commander with IP {ip} already exists', 'error')
    finally:
        conn.close()

    return redirect(url_for('commanders_page'))


@app.route('/commanders/<int:commander_id>/toggle', methods=['POST'])
@protected_route
def toggle_commander(commander_id):
    """Toggle commander enabled status."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE commanders
            SET enabled = NOT enabled
            WHERE id = ?
        """, (commander_id,))
        conn.commit()
        regenerate_commanders_csv()
        flash('Commander status updated', 'success')
    finally:
        conn.close()

    return redirect(url_for('commanders_page'))


@app.route('/commanders/<int:commander_id>/update', methods=['POST'])
@protected_route
def update_commander(commander_id):
    """Update commander details (IP, store name, group, brand)."""
    ip = request.form.get('ip', '').strip()
    store_name = request.form.get('store_name', '').strip()
    group_name = request.form.get('group_name', '').strip()
    brand = request.form.get('brand', '').strip()

    if not ip or not store_name:
        flash('IP Address and Store Name are required', 'error')
        return redirect(url_for('commanders_page'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get old values for logging
        cursor.execute("SELECT ip, store_name FROM commanders WHERE id = ?", (commander_id,))
        old = cursor.fetchone()
        if not old:
            flash('Commander not found', 'error')
            return redirect(url_for('commanders_page'))

        old_ip = old['ip']
        old_name = old['store_name']

        # Update all fields
        cursor.execute("""
            UPDATE commanders
            SET ip = ?, store_name = ?, group_name = ?, brand = ?
            WHERE id = ?
        """, (ip, store_name, group_name, brand, commander_id))
        conn.commit()

        # Regenerate CSV for Vector enrichment
        regenerate_commanders_csv()

        # Build informative flash message
        changes = []
        if old_ip != ip:
            changes.append(f'IP: {old_ip} → {ip}')
        if old_name != store_name:
            changes.append(f'Name: {old_name} → {store_name}')
        if changes:
            flash(f'{store_name} updated: {", ".join(changes)}', 'success')
        else:
            flash(f'{store_name} updated', 'success')

        logger.info(f"Commander {commander_id} updated: {old_name} ({old_ip}) → {store_name} ({ip})")

    except sqlite3.IntegrityError:
        flash(f'Another commander already uses IP {ip}', 'error')
    except Exception as e:
        logger.error(f"Error updating commander {commander_id}: {e}")
        flash(f'Error updating commander: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('commanders_page'))


@app.route('/commanders/<int:commander_id>/delete', methods=['POST'])
@protected_route
def delete_commander(commander_id):
    """Delete a commander."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM commanders WHERE id = ?", (commander_id,))
        conn.commit()
        regenerate_commanders_csv()
        flash('Commander deleted', 'success')
    finally:
        conn.close()

    return redirect(url_for('commanders_page'))


@app.route('/commanders/bulk', methods=['POST'])
@protected_route
def bulk_commander_action():
    """Bulk enable/disable commanders."""
    action = request.form.get('action')
    commander_ids = request.form.getlist('commander_ids')

    if not commander_ids:
        flash('No commanders selected', 'warning')
        return redirect(url_for('commanders_page'))

    if action not in ['enable', 'disable']:
        flash('Invalid action', 'error')
        return redirect(url_for('commanders_page'))

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Convert to integers for safety
        safe_ids = [int(cid) for cid in commander_ids]
        placeholders = ','.join('?' * len(safe_ids))

        # Get commander names for flash message
        cursor.execute(f"SELECT store_name FROM commanders WHERE id IN ({placeholders})", safe_ids)
        store_names = [row[0] for row in cursor.fetchall()]

        # Update enabled status
        new_status = 1 if action == 'enable' else 0
        cursor.execute(
            f"UPDATE commanders SET enabled = ? WHERE id IN ({placeholders})",
            [new_status] + safe_ids
        )
        conn.commit()
        regenerate_commanders_csv()

        # Flash success message
        count = len(safe_ids)
        action_past = 'enabled' if action == 'enable' else 'disabled'
        if count <= 3:
            stores = ', '.join(store_names)
            flash(f'{count} commander(s) {action_past}: {stores}', 'success')
        else:
            flash(f'{count} commanders {action_past} successfully', 'success')

        logger.info(f"Bulk {action}: {count} commanders - {', '.join(store_names)}")

    except Exception as e:
        logger.error(f"Error in bulk action: {e}")
        flash(f'Error: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('commanders_page'))


@app.route('/config')
@protected_route
def config_page():
    """Configuration page."""
    settings = get_settings()

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM credentials WHERE is_default = 1 LIMIT 1")
        row = cursor.fetchone()
        username = row['username'] if row else ''

        return render_template('config.html',
                             settings=settings,
                             username=username)
    finally:
        conn.close()


@app.route('/config/update', methods=['POST'])
@protected_route
def update_config():
    """Update configuration settings."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Update settings
        timeout = request.form.get('timeout_seconds', 30, type=int)
        max_workers = request.form.get('max_workers', 10, type=int)
        xml_debug_enabled = 'xml_debug_enabled' in request.form
        xml_debug_retention = request.form.get('xml_debug_retention_minutes', 60, type=int)

        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, data_type)
            VALUES ('timeout_seconds', ?, 'integer')
        """, (str(timeout),))

        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, data_type)
            VALUES ('max_workers', ?, 'integer')
        """, (str(max_workers),))

        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, data_type)
            VALUES ('xml_debug_enabled', ?, 'boolean')
        """, ('true' if xml_debug_enabled else 'false',))

        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, data_type)
            VALUES ('xml_debug_retention_minutes', ?, 'integer')
        """, (str(xml_debug_retention),))

        conn.commit()
        flash('Configuration updated successfully', 'success')
    finally:
        conn.close()

    return redirect(url_for('config_page'))


@app.route('/config/mcp', methods=['POST'])
@protected_route
def update_mcp_config():
    """Update MCP Server configuration settings."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get form values
        mcp_enabled = 'true' if request.form.get('mcp_enabled') == 'on' else 'false'

        # Update settings
        cursor.execute("""
            INSERT OR REPLACE INTO settings (key, value, data_type)
            VALUES ('mcp_enabled', ?, 'boolean')
        """, (mcp_enabled,))

        conn.commit()
        flash('MCP Server configuration updated successfully', 'success')
    finally:
        conn.close()

    return redirect(url_for('config_page'))


@app.route('/config/export')
@protected_route
def export_config():
    """Export configuration (settings and commanders) as JSON."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get all settings (excluding any that might contain secrets)
        cursor.execute("""
            SELECT key, value, data_type
            FROM settings
        """)
        settings = {}
        for row in cursor.fetchall():
            key = row['key']
            value = row['value']
            data_type = row['data_type']

            # Convert value based on data_type
            if data_type == 'integer':
                settings[key] = int(value)
            elif data_type == 'boolean':
                settings[key] = value.lower() == 'true'
            else:
                settings[key] = value

        # Get all commanders
        cursor.execute("""
            SELECT ip, store_name, group_name, brand, enabled
            FROM commanders
            ORDER BY store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]

        # Build export data
        export_data = {
            'export_version': '1.0',
            'export_date': datetime.utcnow().isoformat() + 'Z',
            'settings': settings,
            'commanders': commanders
        }

        # Create JSON file in memory
        json_str = json.dumps(export_data, indent=2)
        buffer = io.BytesIO(json_str.encode('utf-8'))
        buffer.seek(0)

        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'posproctor_config_{timestamp}.json'

        return send_file(
            buffer,
            mimetype='application/json',
            as_attachment=True,
            download_name=filename
        )

    finally:
        conn.close()


@app.route('/config/import', methods=['POST'])
@protected_route
def import_config():
    """Import configuration from uploaded JSON file."""
    if 'config_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('config_page'))

    file = request.files['config_file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('config_page'))

    if not file.filename.endswith('.json'):
        flash('File must be a JSON file', 'error')
        return redirect(url_for('config_page'))

    try:
        # Parse JSON
        content = file.read().decode('utf-8')
        data = json.loads(content)

        # Validate structure
        if 'export_version' not in data:
            flash('Invalid config file: missing export_version', 'error')
            return redirect(url_for('config_page'))

        conn = get_db_connection()
        cursor = conn.cursor()

        imported_settings = 0
        imported_commanders = 0
        skipped_commanders = 0

        # Import settings
        if 'settings' in data and isinstance(data['settings'], dict):
            for key, value in data['settings'].items():
                # Determine data type
                if isinstance(value, bool):
                    data_type = 'boolean'
                    db_value = 'true' if value else 'false'
                elif isinstance(value, int):
                    data_type = 'integer'
                    db_value = str(value)
                else:
                    data_type = 'string'
                    db_value = str(value)

                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, data_type, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (key, db_value, data_type))
                imported_settings += 1

        # Import commanders
        if 'commanders' in data and isinstance(data['commanders'], list):
            for cmd in data['commanders']:
                ip = cmd.get('ip')
                store_name = cmd.get('store_name')

                if not ip or not store_name:
                    continue

                group_name = cmd.get('group_name', '')
                brand = cmd.get('brand', '')
                enabled = 1 if cmd.get('enabled', True) else 0

                try:
                    cursor.execute("""
                        INSERT INTO commanders (ip, store_name, group_name, brand, enabled)
                        VALUES (?, ?, ?, ?, ?)
                    """, (ip, store_name, group_name, brand, enabled))
                    imported_commanders += 1
                except sqlite3.IntegrityError:
                    # Commander with this IP already exists, update it instead
                    cursor.execute("""
                        UPDATE commanders
                        SET store_name = ?, group_name = ?, brand = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE ip = ?
                    """, (store_name, group_name, brand, enabled, ip))
                    skipped_commanders += 1

        conn.commit()
        conn.close()

        # Regenerate CSV if commanders were modified
        if imported_commanders > 0 or skipped_commanders > 0:
            regenerate_commanders_csv()

        # Build success message
        msg_parts = []
        if imported_settings > 0:
            msg_parts.append(f'{imported_settings} settings')
        if imported_commanders > 0:
            msg_parts.append(f'{imported_commanders} new commanders')
        if skipped_commanders > 0:
            msg_parts.append(f'{skipped_commanders} commanders updated')

        if msg_parts:
            flash(f'Configuration imported successfully: {", ".join(msg_parts)}', 'success')
        else:
            flash('Configuration file was valid but contained no data to import', 'warning')

        logger.info(f"Config import: {imported_settings} settings, {imported_commanders} new commanders, {skipped_commanders} updated commanders")

    except json.JSONDecodeError as e:
        flash(f'Invalid JSON file: {str(e)}', 'error')
    except Exception as e:
        logger.error(f"Error importing config: {e}")
        flash(f'Error importing configuration: {str(e)}', 'error')

    return redirect(url_for('config_page'))


@app.route('/tlogs')
def tlogs_page():
    """TLOG viewer page."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name
            FROM commanders
            WHERE enabled = 1
            ORDER BY store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]

        return render_template('tlogs.html', commanders=commanders)
    finally:
        conn.close()


@app.route('/api/tlog/latest', methods=['POST'])
def get_latest_tlog():
    """Proxy request to TLOG service."""
    data = request.json

    try:
        response = requests.post(
            f"{TLOG_SERVICE_URL}/api/tlog/latest",
            json=data,
            timeout=60
        )
        return response.json(), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error fetching TLOG: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/list', methods=['POST'])
def list_tlogs():
    """Proxy request to TLOG service."""
    data = request.json

    try:
        response = requests.post(
            f"{TLOG_SERVICE_URL}/api/tlog/list",
            json=data,
            timeout=30
        )
        return response.json(), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error listing TLOGs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/stored')
def get_stored_tlogs():
    """Proxy request to TLOG service."""
    try:
        response = requests.get(
            f"{TLOG_SERVICE_URL}/api/tlog/stored",
            timeout=10
        )
        return response.json(), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error fetching stored TLOGs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/date', methods=['POST'])
def get_tlog_by_date():
    """Proxy request to TLOG service for date-based queries."""
    data = request.json

    try:
        response = requests.post(
            f"{TLOG_SERVICE_URL}/api/tlog/date",
            json=data,
            timeout=120  # Longer timeout for downloads
        )
        return response.json(), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error fetching TLOG by date: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tlog/availability')
def get_tlog_availability():
    """Proxy request to TLOG service for report availability matrix."""
    try:
        response = requests.get(
            f"{TLOG_SERVICE_URL}/api/tlog/availability",
            timeout=120  # Long timeout as this queries all commanders
        )
        return response.json(), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error fetching TLOG availability: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/passwords')
@protected_route
def password_manager_page():
    """Password manager page."""
    return render_template('password_manager.html')


def get_bitwarden_service():
    """Get or create Bitwarden service instance."""
    global bitwarden_service
    if bitwarden_service is None:
        bitwarden_service = BitwardenService(BITWARDEN_SERVICE_URL)
    return bitwarden_service


@app.route('/api/password/bitwarden/status')
def bitwarden_status():
    """Check Bitwarden service status."""
    try:
        bw = get_bitwarden_service()
        ready = bw.is_ready()
        return jsonify({
            'success': True,
            'ready': ready,
            'url': BITWARDEN_SERVICE_URL
        })
    except Exception as e:
        logger.error(f"Error checking Bitwarden status: {e}")
        return jsonify({
            'success': False,
            'ready': False,
            'message': str(e)
        })


@app.route('/api/password/bitwarden/sync', methods=['POST'])
def bitwarden_sync():
    """Sync Bitwarden vault."""
    try:
        bw = get_bitwarden_service()
        if bw.sync():
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Sync failed'})
    except Exception as e:
        logger.error(f"Error syncing Bitwarden: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/password/dry-run', methods=['POST'])
@protected_route
def password_dry_run():
    """Test current Bitwarden password on all enabled commanders without making changes."""
    data = request.json
    username = data.get('username')

    if not username:
        return jsonify({
            'success': False,
            'message': 'Username is required'
        }), 400

    # Get Bitwarden item name for this user
    item_name_map = {
        'admin': 'Commander - Admin',
        # Add additional Bitwarden item mappings here as needed
    }

    item_name = item_name_map.get(username)
    if not item_name:
        return jsonify({
            'success': False,
            'message': f'Unknown username: {username}'
        }), 400

    # Get current password from Bitwarden
    try:
        bw = get_bitwarden_service()
        actual_username, current_password = bw.get_credentials(item_name)

        if not current_password:
            return jsonify({
                'success': False,
                'message': f'Could not retrieve password from Bitwarden for {item_name}'
            }), 500

        logger.info(f"Dry run: Retrieved password for {username} from Bitwarden")

    except Exception as e:
        logger.error(f"Dry run: Error retrieving credentials from Bitwarden: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to connect to Bitwarden: {str(e)}'
        }), 500

    # Get all enabled commanders
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name
            FROM commanders
            WHERE enabled = 1
            ORDER BY store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not commanders:
        return jsonify({
            'success': False,
            'message': 'No enabled commanders found'
        }), 400

    # Test authentication on all commanders
    from lib.commander_password import get_token

    results = []
    succeeded = 0
    failed = 0

    def test_auth_worker(commander):
        """Worker function to test authentication on a single commander."""
        try:
            token = get_token(
                ip=commander['ip'],
                username=actual_username,
                password=current_password,
                timeout=30
            )

            if token:
                return {
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'success': True,
                    'message': 'Authentication successful'
                }
            else:
                return {
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'success': False,
                    'message': 'Authentication failed - check password'
                }
        except Exception as e:
            logger.error(f"Dry run: Error testing {commander['ip']}: {e}")
            return {
                'ip': commander['ip'],
                'store_name': commander['store_name'],
                'success': False,
                'message': f'Error: {str(e)}'
            }

    # Use thread pool to test authentication concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_commander = {
            executor.submit(test_auth_worker, cmd): cmd
            for cmd in commanders
        }

        for future in concurrent.futures.as_completed(future_to_commander):
            result = future.result()
            results.append(result)

            if result['success']:
                succeeded += 1
            else:
                failed += 1

    logger.info(f"Dry run complete for {username}: {succeeded} succeeded, {failed} failed out of {len(commanders)} total")

    return jsonify({
        'success': succeeded > 0,
        'succeeded': succeeded,
        'failed': failed,
        'total': len(commanders),
        'results': results
    })


@app.route('/api/password/change-all', methods=['POST'])
@protected_route
def change_password_all():
    """Change password on all enabled commanders."""
    data = request.json
    username = data.get('username')
    new_password = data.get('password')

    if not username or not new_password:
        return jsonify({
            'success': False,
            'message': 'Username and password are required'
        }), 400

    # Get Bitwarden item name for this user
    item_name_map = {
        'admin': 'Commander - Admin',
        # Add additional Bitwarden item mappings here as needed
    }

    item_name = item_name_map.get(username)
    if not item_name:
        return jsonify({
            'success': False,
            'message': f'Unknown username: {username}'
        }), 400

    # Get current password from Bitwarden
    try:
        bw = get_bitwarden_service()
        current_username, current_password = bw.get_credentials(item_name)

        if not current_password:
            return jsonify({
                'success': False,
                'message': f'Could not retrieve current password from Bitwarden for {item_name}'
            }), 500

        logger.info(f"Retrieved current password for {username} from Bitwarden")

    except Exception as e:
        logger.error(f"Error retrieving credentials from Bitwarden: {e}")
        return jsonify({
            'success': False,
            'message': f'Failed to connect to Bitwarden: {str(e)}'
        }), 500

    # Get all enabled commanders
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name
            FROM commanders
            WHERE enabled = 1
            ORDER BY store_name
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    if not commanders:
        return jsonify({
            'success': False,
            'message': 'No enabled commanders found'
        }), 400

    # Change passwords in parallel
    results = []
    succeeded = 0
    failed = 0

    def change_password_worker(commander):
        """Worker function to change password on a single commander."""
        try:
            result = rotate_password_on_commander(
                ip=commander['ip'],
                username=username,
                current_password=current_password,
                new_password=new_password,
                timeout=30
            )

            return {
                'ip': commander['ip'],
                'store_name': commander['store_name'],
                'success': result['success'],
                'message': result['message']
            }
        except Exception as e:
            logger.error(f"Error changing password on {commander['ip']}: {e}")
            return {
                'ip': commander['ip'],
                'store_name': commander['store_name'],
                'success': False,
                'message': f'Exception: {str(e)}'
            }

    # Use thread pool to change passwords concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_commander = {
            executor.submit(change_password_worker, cmd): cmd
            for cmd in commanders
        }

        for future in concurrent.futures.as_completed(future_to_commander):
            result = future.result()
            results.append(result)

            if result['success']:
                succeeded += 1
            else:
                failed += 1

    # If all succeeded, update Bitwarden and local credential cache
    if succeeded > 0 and failed == 0:
        try:
            if bw.update_password(item_name, new_password):
                logger.info(f"Updated password in Bitwarden for {item_name}")

                # Also update the local credential cache
                credential_service = get_credential_service()
                credential_service.update_cached_password(username, new_password)
                logger.info(f"Updated local credential cache for {username}")
            else:
                logger.warning(f"Failed to update password in Bitwarden for {item_name}")
                # Don't fail the whole operation if Bitwarden update fails
        except Exception as e:
            logger.error(f"Error updating Bitwarden: {e}")

    return jsonify({
        'success': succeeded > 0,
        'succeeded': succeeded,
        'failed': failed,
        'total': len(commanders),
        'results': results
    })


# ============================================
# Tank Analysis Routes
# ============================================

@app.route('/tanks')
def tanks_page():
    """Tank analysis page (unauthenticated)."""
    import re

    def extract_store_number(store_name):
        """Extract numeric store number from store name for sorting."""
        match = re.search(r'(\d+)', store_name or '')
        return int(match.group(1)) if match else float('inf')

    # Get list of enabled commanders
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand
            FROM commanders
            WHERE enabled = 1
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
        # Sort by store number extracted from store_name
        commanders.sort(key=lambda c: extract_store_number(c.get('store_name', '')))
    finally:
        conn.close()

    return render_template('tanks.html', commanders=commanders)


@app.route('/api/tanks/generate', methods=['GET'])
def generate_tank_report():
    """Generate tank report for a specific store (unauthenticated)."""
    store_id = request.args.get('store_id')
    commander_ip = request.args.get('commander_ip')
    embed_mode = request.args.get('embed', '0') == '1'
    output_format = request.args.get('format', 'html')

    if not commander_ip:
        return "Commander IP is required", 400

    try:
        # Import tank analysis modules
        from lib.tank_commander_client import CommanderClient
        from lib import tank_report_generator

        # Get commander credentials using unified credential service
        # Priority: Bitwarden -> Database cache -> Environment variables
        creds = get_commander_credentials()
        if not creds:
            return jsonify({
                'success': False,
                'message': 'Commander credentials not configured (tried Bitwarden, database, and environment)'
            }), 500

        username = creds['username']
        password = creds['password']
        logger.info(f"Using credentials for {username} (source: {creds.get('source', 'unknown')})")

        # Query tank data from the commander
        logger.info(f"Querying tank data from {commander_ip}...")
        client = CommanderClient(commander_ip, username, password)

        if not client.authenticate():
            return jsonify({
                'success': False,
                'message': 'Failed to authenticate with commander'
            }), 401

        # Get store metadata from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT store_name, brand FROM commanders WHERE ip = ?", (commander_ip,))
        store_row = cursor.fetchone()
        conn.close()

        store_name = store_row['store_name'] if store_row else f'Store {store_id}'
        brand = store_row['brand'] if store_row else 'Unknown'

        # Query critical tank data endpoints
        logger.info(f"Querying forecourt diagnostics from {commander_ip}...")
        diagnostics_xml = client.query_endpoint('vforecourtdiagnostics')

        logger.info(f"Querying tank level sensor config from {commander_ip}...")
        tls_config_xml = client.query_endpoint('vtlssite')

        logger.info(f"Querying fuel configuration from {commander_ip}...")
        fuel_config_xml = client.query_endpoint('vfuelcfg')

        logger.info(f"Querying tank monitor data from {commander_ip}...")
        tank_monitor_xml = client.query_endpoint('vrubyrept', {'reptname': 'tankMonitor', 'period': 1, 'reptnum': 1})

        # If tankMonitor failed or returned fault, try vfueltotals as fallback
        fuel_totals_xml = None
        if not tank_monitor_xml or b'Fault' in tank_monitor_xml:
            logger.warning(f"tankMonitor failed or returned fault, trying vfueltotals fallback...")
            try:
                fuel_totals_xml = client.query_endpoint('vfueltotals', {'period': 1, 'reptnum': 1})
                if fuel_totals_xml:
                    logger.info(f"Successfully retrieved vfueltotals data (fallback)")
            except Exception as e:
                logger.error(f"vfueltotals fallback also failed: {e}")

        logger.info(f"Querying sales data from {commander_ip}...")
        # Try current period first (reptnum=1), then fall back to last closed period (reptnum=2) if no data
        sales_xml = client.query_endpoint('vrubyrept', {'reptname': 'tank', 'period': 1, 'reptnum': 1})
        logger.info(f"Current period sales XML: {len(sales_xml) if sales_xml else 0} bytes")
        sales_xml_closed = None
        # Also query the last closed period for more complete data
        try:
            sales_xml_closed = client.query_endpoint('vrubyrept', {'reptname': 'tank', 'period': 1, 'reptnum': 2})
            logger.info(f"Last closed period sales XML: {len(sales_xml_closed) if sales_xml_closed else 0} bytes")
        except Exception as e:
            logger.debug(f"Could not query closed period sales: {e}")

        # Optional: Query delivery history (may timeout on some commanders)
        deliveries_xml = None
        try:
            logger.info(f"Querying delivery history from {commander_ip}...")
            deliveries_xml = client.query_endpoint('vrubyrept', {'reptname': 'tankRec', 'period': 1, 'reptnum': 1})
        except Exception as e:
            logger.warning(f"Could not query delivery history: {e}")

        # Parse XML into data structures
        from lib.tank_data_parser import (
            parse_tank_monitor_xml,
            parse_tank_reconciliation_for_inventory,
            enrich_tank_inventory_with_capacity,
            parse_sales_xml,
            parse_delivery_history_xml,
            parse_deliveries_from_tank_monitor,
            parse_alarm_history_from_tank_monitor,
            parse_reconciliation_from_tank_monitor,
            parse_fuel_config_xml,
            parse_diagnostics_xml,
            build_store_info
        )

        # Parse diagnostics to check equipment status
        equipment_status = parse_diagnostics_xml(diagnostics_xml) if diagnostics_xml else {}

        # Parse fuel config first (needed for capacity enrichment)
        fuel_config = parse_fuel_config_xml(fuel_config_xml) if fuel_config_xml else []

        # Build store info
        store_info = build_store_info(
            commander_ip=commander_ip,
            store_name=store_name,
            store_id=store_id,
            brand=brand,
            xml_data={'tank_monitor': tank_monitor_xml}
        )
        # Ensure store_name is available in store_info for template
        store_info['store_name'] = store_name

        # Parse XML responses - Multi-endpoint hybrid approach for maximum data availability
        tank_inventory = []
        tank_data_source = None

        # Step 1: Try tankMonitor first (best data - includes temp, water, alarms)
        if tank_monitor_xml and b'Fault' not in tank_monitor_xml:
            tank_inventory = parse_tank_monitor_xml(tank_monitor_xml, store_info)
            if tank_inventory:
                tank_data_source = 'tankMonitor'
                logger.info(f"Got {len(tank_inventory)} tanks from tankMonitor (full data with temp/water)")

        # Step 2: If tankMonitor failed, try tankRec fallback (volumes only, no temp/water)
        if not tank_inventory and deliveries_xml:
            logger.warning(f"tankMonitor unavailable, trying tankRec for inventory data...")
            tank_inventory = parse_tank_reconciliation_for_inventory(deliveries_xml, store_info, fuel_config)
            if tank_inventory:
                tank_data_source = 'tankRec'
                logger.info(f"Got {len(tank_inventory)} tanks from tankRec (limited data - no temp/water)")

        # Step 3: Enrich with capacity from vfuelcfg if needed
        if tank_inventory and fuel_config:
            enrich_tank_inventory_with_capacity(tank_inventory, fuel_config)
            logger.debug(f"Enriched tank inventory with capacity data from vfuelcfg")

        # Parse remaining data - try current period first, then fallback to closed period
        logger.info(f"Parsing current period (reptnum=1) sales data...")
        sales_data = parse_sales_xml(sales_xml) if sales_xml else []
        sales_source = "current period (reptnum=1)"

        # If current period has no sales, use last closed period instead
        if not sales_data and sales_xml_closed:
            logger.info(f"Current period has no sales, trying last closed period (reptnum=2)...")
            sales_data = parse_sales_xml(sales_xml_closed)
            sales_source = "last closed period (reptnum=2)"

        logger.info(f"Final sales data from {sales_source}: {len(sales_data)} products, ${sum(s['revenue'] for s in sales_data):.2f} revenue")

        # Parse deliveries and alarms from tankMonitor XML (comprehensive data)
        delivery_list, delivery_summary = [], {}
        alarm_history, alarm_status = [], []
        reconciliation = []

        if tank_monitor_xml and b'Fault' not in tank_monitor_xml:
            delivery_list, delivery_summary = parse_deliveries_from_tank_monitor(tank_monitor_xml)
            alarm_history, alarm_status = parse_alarm_history_from_tank_monitor(tank_monitor_xml)
            reconciliation = parse_reconciliation_from_tank_monitor(tank_monitor_xml, tank_inventory)
            logger.info(f"Parsed from tankMonitor: {len(delivery_list)} deliveries, {len(alarm_history)} alarms, {len(reconciliation)} reconciliation records")

        # Legacy deliveries format (for backwards compatibility)
        deliveries = parse_delivery_history_xml(deliveries_xml) if deliveries_xml else {}
        alarms = alarm_history  # Use parsed alarm history

        # Check if we have tank data (store may not have Veeder-Root)
        if not tank_inventory:
            logger.warning(f"No tank inventory data for Store {store_id} - may not have tank monitoring equipment")
            # Still generate report with available data
            tank_inventory = []

        # Calculate summary statistics
        summary = {
            'total_revenue': sum(s['revenue'] for s in sales_data),
            'total_transactions': sum(s['transactions'] for s in sales_data),
            'total_volume': sum(s['volume'] for s in sales_data),
            'product_count': len(sales_data)
        }

        # Add raw XML data for debugging/display
        raw_data = {
            'diagnostics': diagnostics_xml.decode('utf-8', errors='ignore')[:3000] if diagnostics_xml else None,
            'tls_config': tls_config_xml.decode('utf-8', errors='ignore')[:2000] if tls_config_xml else None,
            'fuel_config': fuel_config_xml.decode('utf-8', errors='ignore')[:2000] if fuel_config_xml else None,
            'tank_monitor': tank_monitor_xml.decode('utf-8', errors='ignore')[:3000] if tank_monitor_xml else None,
            'tank_rec': deliveries_xml.decode('utf-8', errors='ignore')[:3000] if deliveries_xml else None,
            'sales': sales_xml.decode('utf-8', errors='ignore')[:2000] if sales_xml else None,
            'fuel_totals': fuel_totals_xml.decode('utf-8', errors='ignore')[:3000] if fuel_totals_xml else None
        }

        # Render HTML report
        logger.info(f"Rendering HTML report for Store {store_name}...")

        # Check if PDF output is requested
        if output_format == 'pdf':
            # Generate PDF using WeasyPrint or similar
            try:
                from weasyprint import HTML, CSS
                html_content = render_template('tank_report.html',
                    store_info=store_info,
                    tank_inventory=tank_inventory,
                    tank_data_source=tank_data_source,
                    sales_data=sales_data,
                    deliveries=deliveries,
                    delivery_list=delivery_list,
                    delivery_summary=delivery_summary,
                    alarms=alarms,
                    alarm_history=alarm_history,
                    alarm_status=alarm_status,
                    reconciliation=reconciliation,
                    fuel_config=fuel_config,
                    summary=summary,
                    raw_data=raw_data,
                    embed=False  # Use full template for PDF
                )
                pdf = HTML(string=html_content, base_url=request.url_root).write_pdf()
                response = make_response(pdf)
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename=Tank_Report_{store_name.replace(" ", "_")}.pdf'
                return response
            except ImportError:
                logger.warning("WeasyPrint not available, returning HTML instead")
            except Exception as e:
                logger.error(f"Error generating PDF: {e}")
                # Fall back to HTML

        # Choose template based on embed mode
        template_name = 'tank_report.html'  # Always use full template with charts

        return render_template(template_name,
            store_info=store_info,
            tank_inventory=tank_inventory,
            tank_data_source=tank_data_source,
            sales_data=sales_data,
            deliveries=deliveries,
            delivery_list=delivery_list,
            delivery_summary=delivery_summary,
            alarms=alarms,
            alarm_history=alarm_history,
            alarm_status=alarm_status,
            reconciliation=reconciliation,
            fuel_config=fuel_config,
            summary=summary,
            raw_data=raw_data,
            embed=embed_mode
        )

    except Exception as e:
        import traceback
        logger.error(f"Error generating tank report: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/api/tanks/fleet-status', methods=['GET'])
def fleet_tls_status():
    """
    Get TLS status for all commanders.

    First tries to get data from Prometheus (populated by monitoring service).
    Falls back to direct scanning only if Prometheus is unavailable or force_scan=true.
    This avoids conflicting API calls between webapp and monitoring service.
    """
    import concurrent.futures
    import re
    import requests as http_requests

    force_scan = request.args.get('force_scan', 'false').lower() == 'true'

    def extract_store_number(store_name):
        """Extract numeric store number from store name for sorting."""
        match = re.search(r'(\d+)', store_name or '')
        return int(match.group(1)) if match else float('inf')

    def get_status_from_prometheus():
        """Try to get TLS status from Prometheus (monitoring service data)."""
        try:
            prometheus_url = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')

            # Query tank monitor status metric
            query = 'posproctor_tank_monitor_status'
            resp = http_requests.get(
                f'{prometheus_url}/api/v1/query',
                params={'query': query},
                timeout=5
            )
            if resp.status_code != 200:
                return None, None

            data = resp.json()
            if data.get('status') != 'success':
                return None, None

            results = data.get('data', {}).get('result', [])
            if not results:
                return None, None

            # Get the timestamp from the first result (all should be from same scrape)
            last_scrape_timestamp = None
            if results and len(results) > 0:
                # Prometheus returns [timestamp, value] in the value field
                last_scrape_timestamp = results[0].get('value', [None])[0]

            # Also get tank count per store
            tank_query = 'count by (store, ip, group, brand) (posproctor_tank_volume_gallons)'
            tank_resp = http_requests.get(
                f'{prometheus_url}/api/v1/query',
                params={'query': tank_query},
                timeout=5
            )
            tank_counts = {}
            if tank_resp.status_code == 200:
                tank_data = tank_resp.json()
                if tank_data.get('status') == 'success':
                    for item in tank_data.get('data', {}).get('result', []):
                        metric = item.get('metric', {})
                        store = metric.get('store', '')
                        tank_counts[store] = int(float(item.get('value', [0, 0])[1]))

            # Build status from Prometheus data
            status_by_store = {}
            for item in results:
                metric = item.get('metric', {})
                store = metric.get('store', '')
                ip = metric.get('ip', '')
                group = metric.get('group', '')
                brand = metric.get('brand', '')
                value = int(float(item.get('value', [0, 0])[1]))

                status_by_store[store] = {
                    'store_name': store,
                    'ip': ip,
                    'group_name': group,
                    'brand': brand,
                    'tls_status': 'online' if value == 1 else 'no_tls',
                    'tank_count': tank_counts.get(store, 0),
                    'source': 'prometheus'
                }

            return status_by_store if status_by_store else None, last_scrape_timestamp

        except Exception as e:
            logger.warning(f"Could not get TLS status from Prometheus: {e}")
            return None, None

    # Try Prometheus first (unless force_scan requested)
    if not force_scan:
        prometheus_data, last_scrape_ts = get_status_from_prometheus()
        if prometheus_data:
            # Get commander list to include offline ones not in Prometheus
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, ip, store_name, group_name, brand
                    FROM commanders
                    WHERE enabled = 1
                """)
                commanders = [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

            # Merge Prometheus data with commander list
            results = []
            for cmd in commanders:
                store = cmd['store_name']
                if store in prometheus_data:
                    prom_status = prometheus_data[store]
                    prom_status['id'] = cmd['id']
                    results.append(prom_status)
                else:
                    # Commander not in Prometheus - likely offline or never scraped
                    results.append({
                        'id': cmd['id'],
                        'ip': cmd['ip'],
                        'store_name': store,
                        'brand': cmd.get('brand', 'Unknown'),
                        'group_name': cmd.get('group_name', ''),
                        'tls_status': 'offline',
                        'tank_count': 0,
                        'source': 'prometheus'
                    })

            # Sort by store number
            results.sort(key=lambda x: extract_store_number(x.get('store_name', '')))

            return jsonify({
                'success': True,
                'stores': results,
                'source': 'prometheus',
                'last_scrape_timestamp': last_scrape_ts,
                'summary': {
                    'total': len(results),
                    'online': len([r for r in results if r['tls_status'] == 'online']),
                    'no_tls': len([r for r in results if r['tls_status'] == 'no_tls']),
                    'offline': len([r for r in results if r['tls_status'] == 'offline'])
                }
            })

    # Fall back to direct scanning
    logger.info("Using direct scan for TLS status (Prometheus unavailable or force_scan=true)")

    def check_tls_status(commander):
        """Check TLS status for a single commander with robust retry logic."""
        import xml.etree.ElementTree as ET
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        import urllib3
        import time
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        result = {
            'id': commander['id'],
            'ip': commander['ip'],
            'store_name': commander['store_name'],
            'brand': commander.get('brand', 'Unknown'),
            'group_name': commander.get('group_name', ''),
            'tls_status': 'offline',  # default
            'tank_count': 0,
            'active_alarms': 0
        }

        try:
            creds = get_commander_credentials()
            if not creds:
                result['tls_status'] = 'offline'
                result['error'] = 'No credentials'
                return result

            ip = commander['ip']
            base_url = f"https://{ip}/cgi-bin/CGILink"
            timeout = 20  # Longer timeout for reliability
            max_retries = 3  # Up to 3 attempts

            # Create a session with retry strategy built-in
            session = requests.Session()
            retry_strategy = Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("https://", adapter)

            # Authenticate with retry
            auth_url = f"{base_url}?cmd=validate&user={creds['username']}&passwd={creds['password']}"
            cookie = None
            last_error = None
            for attempt in range(max_retries):
                try:
                    auth_resp = session.get(auth_url, verify=False, timeout=timeout)
                    if auth_resp.status_code != 200:
                        last_error = f'HTTP {auth_resp.status_code}'
                        if attempt < max_retries - 1:
                            time.sleep(2)  # Longer delay between retries
                            continue
                        result['error'] = last_error
                        return result

                    root = ET.fromstring(auth_resp.content)
                    cookie = root.findtext('.//cookie')
                    if cookie:
                        break
                    else:
                        last_error = 'No cookie in response'
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                except requests.Timeout:
                    last_error = 'Auth timeout'
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                except requests.exceptions.ConnectionError as e:
                    last_error = 'Connection error'
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                except Exception as e:
                    last_error = str(e)[:50]
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue

            if not cookie:
                result['error'] = last_error or 'No cookie after retries'
                return result

            # Query tankMonitor with retry - this is the reliable way to check TLS status
            tank_url = f"{base_url}?cmd=vrubyrept&cookie={cookie}&reptname=tankMonitor&period=1&reptnum=1"
            tank_monitor_xml = None
            for attempt in range(max_retries):
                try:
                    tank_resp = session.get(tank_url, verify=False, timeout=timeout)
                    if tank_resp.status_code == 200:
                        tank_monitor_xml = tank_resp.content
                        break
                    else:
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                except requests.Timeout:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    # Timeout on tank query - mark as offline since we can't determine status
                    result['tls_status'] = 'offline'
                    result['error'] = 'Query timeout'
                    session.close()
                    return result
                except requests.exceptions.ConnectionError:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    result['tls_status'] = 'offline'
                    result['error'] = 'Connection error'
                    session.close()
                    return result
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    break

            # Close session when done
            session.close()

            if tank_monitor_xml:
                # Check for Fault response (means no TLS configured)
                if b'Fault' in tank_monitor_xml or b'fault' in tank_monitor_xml:
                    result['tls_status'] = 'no_tls'
                    logger.debug(f"[{commander['ip']}] tankMonitor returned Fault - no TLS configured")
                else:
                    try:
                        root = ET.fromstring(tank_monitor_xml)

                        # Look for tank/inventory elements - multiple possible structures
                        # Some use <tank>, others use <inventoryInfo> for each tank
                        tanks = (root.findall('.//tank') or
                                root.findall('.//Tank') or
                                root.findall('.//{*}tank') or
                                root.findall('.//inventoryInfo') or
                                root.findall('.//{*}inventoryInfo'))

                        # Also check for tankMonitorType element which indicates TLS is configured
                        tls_type = root.findtext('.//tankMonitorType') or root.findtext('.//{*}tankMonitorType')

                        if tanks and len(tanks) > 0:
                            result['tls_status'] = 'online'
                            result['tank_count'] = len(tanks)
                            logger.debug(f"[{commander['ip']}] TLS online with {len(tanks)} tanks")
                        elif tls_type:
                            # TLS configured but no tank data returned
                            result['tls_status'] = 'online'
                            result['tank_count'] = 0
                            logger.debug(f"[{commander['ip']}] TLS configured ({tls_type}) but no tank data")
                        else:
                            # Got a response but no tank elements - likely no TLS
                            result['tls_status'] = 'no_tls'
                            logger.debug(f"[{commander['ip']}] tankMonitor response but no tank elements")

                    except ET.ParseError as e:
                        logger.warning(f"[{commander['ip']}] XML parse error: {e}")
                        result['tls_status'] = 'no_tls'
            else:
                # No response at all - commander might be slow or endpoint not available
                result['tls_status'] = 'no_tls'
                logger.debug(f"[{commander['ip']}] No tankMonitor response")

        except Exception as e:
            logger.error(f"Error checking TLS status for {commander['ip']}: {e}")
            result['tls_status'] = 'offline'
            result['error'] = str(e)

        return result

    # Get all enabled commanders
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand
            FROM commanders
            WHERE enabled = 1
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    # Check TLS status in parallel with staggered starts to prevent thundering herd
    # Using max 3 workers to reduce contention, with staggered submission
    import time as time_module
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for i, cmd in enumerate(commanders):
            # Stagger submissions by 0.5 seconds to prevent all hitting network at once
            if i > 0 and i % 3 == 0:
                time_module.sleep(0.5)
            futures.append((executor.submit(check_tls_status, cmd), cmd))

        for future, commander in futures:
            try:
                result = future.result(timeout=60)  # 60 second timeout per commander
                results.append(result)
            except concurrent.futures.TimeoutError:
                results.append({
                    'id': commander['id'],
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'brand': commander.get('brand', 'Unknown'),
                    'group_name': commander.get('group_name', ''),
                    'tls_status': 'offline',
                    'error': 'Scan timeout'
                })
            except Exception as e:
                results.append({
                    'id': commander['id'],
                    'ip': commander['ip'],
                    'store_name': commander['store_name'],
                    'brand': commander.get('brand', 'Unknown'),
                    'group_name': commander.get('group_name', ''),
                    'tls_status': 'offline',
                    'error': str(e)
                })

    # Sort results by store number
    results.sort(key=lambda x: extract_store_number(x.get('store_name', '')))

    return jsonify({
        'success': True,
        'stores': results,
        'source': 'direct_scan',
        'summary': {
            'total': len(results),
            'online': len([r for r in results if r['tls_status'] == 'online']),
            'no_tls': len([r for r in results if r['tls_status'] == 'no_tls']),
            'offline': len([r for r in results if r['tls_status'] == 'offline'])
        }
    })


@app.route('/api/fleet/status', methods=['GET'])
def fleet_commander_status():
    """
    Get commander reachability status for all enabled stores.
    Uses posproctor_scrape_success metric from Prometheus.
    Merges with DB commander list so offline stores still appear.
    """
    import requests as http_requests
    import re

    def extract_store_number(store_name):
        match = re.search(r'(\d+)', store_name or '')
        return int(match.group(1)) if match else float('inf')

    def get_scrape_status_from_prometheus():
        """Get commander reachability from posproctor_scrape_success metric."""
        try:
            prometheus_url = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
            resp = http_requests.get(
                f'{prometheus_url}/api/v1/query',
                params={'query': 'posproctor_scrape_success'},
                timeout=5
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get('status') != 'success':
                return None

            results = data.get('data', {}).get('result', [])
            if not results:
                return None

            status_by_store = {}
            for item in results:
                metric = item.get('metric', {})
                store = metric.get('store', '')
                ip = metric.get('ip', '')
                group = metric.get('group', '')
                brand = metric.get('brand', '')
                value = int(float(item.get('value', [0, 0])[1]))

                status_by_store[store] = {
                    'store_name': store,
                    'ip': ip,
                    'group_name': group,
                    'brand': brand,
                    'status': 'online' if value == 1 else 'offline'
                }

            return status_by_store
        except Exception as e:
            logger.warning(f"Could not get scrape status from Prometheus: {e}")
            return None

    # Get Prometheus data
    prometheus_data = get_scrape_status_from_prometheus()

    # Get all enabled commanders from DB
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ip, store_name, group_name, brand
            FROM commanders
            WHERE enabled = 1
        """)
        commanders = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    # Merge: DB list with Prometheus status overlay
    # IMPORTANT: Always use DB values for ip/group/brand - DB is the source of truth
    # Prometheus metrics may have stale labels until the old time series expires
    results = []
    for cmd in commanders:
        store = cmd['store_name']
        # Get online/offline status from Prometheus, but use DB for all other fields
        if prometheus_data and store in prometheus_data:
            prom = prometheus_data[store]
            status = prom['status']
        else:
            status = 'offline'

        results.append({
            'id': cmd['id'],
            'ip': cmd['ip'],  # Always use DB IP - it's the source of truth
            'store_name': store,
            'group_name': cmd.get('group_name', ''),
            'brand': cmd.get('brand', ''),
            'status': status
        })

    results.sort(key=lambda x: extract_store_number(x.get('store_name', '')))

    online_count = len([r for r in results if r['status'] == 'online'])
    offline_count = len([r for r in results if r['status'] == 'offline'])

    return jsonify({
        'success': True,
        'stores': results,
        'summary': {
            'total': len(results),
            'online': online_count,
            'offline': offline_count
        }
    })


@app.route('/api/fleet/https-check', methods=['GET'])
def fleet_https_check():
    """
    Perform server-side HTTPS reachability checks for all enabled commanders.
    This is faster and more reliable than client-side checks because:
    1. We can disable SSL verification for self-signed certs
    2. No CORS restrictions
    Returns: { success: bool, checks: { ip: bool, ... } }
    """
    import requests as http_requests
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import urllib3

    # Suppress SSL warnings since commanders use self-signed certs
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def check_single_commander(ip):
        """Check if a single commander is reachable via HTTPS."""
        try:
            resp = http_requests.head(
                f'https://{ip}/',
                timeout=3,
                verify=False,  # Allow self-signed certs
                allow_redirects=True
            )
            # Any response (even 401/403) means it's alive
            return ip, True
        except Exception:
            return ip, False

    # Get all enabled commander IPs from DB
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ip FROM commanders WHERE enabled = 1")
        ips = [row['ip'] for row in cursor.fetchall()]
    finally:
        conn.close()

    # Run checks in parallel (max 20 concurrent)
    results = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(check_single_commander, ip): ip for ip in ips}
        for future in as_completed(futures):
            try:
                ip, is_reachable = future.result()
                results[ip] = is_reachable
            except Exception:
                results[futures[future]] = False

    return jsonify({
        'success': True,
        'checks': results
    })


@app.route('/api/tanks/query', methods=['GET'])
def tank_query_api():
    """
    Query tank data for a specific store and return tabular data suitable for display and CSV export.
    Returns inventory levels, reconciliation data, deliveries, and sales.
    Uses the existing tank_data_parser module for consistent parsing.
    """
    commander_ip = request.args.get('commander_ip')
    period = request.args.get('period', '2')  # Default to day report
    report_date = request.args.get('date')

    if not commander_ip:
        return jsonify({'success': False, 'error': 'Commander IP is required'}), 400

    try:
        from lib.tank_commander_client import CommanderClient
        from lib import tank_data_parser
        import xml.etree.ElementTree as ET

        creds = get_commander_credentials()
        if not creds:
            return jsonify({
                'success': False,
                'error': 'Commander credentials not configured'
            }), 500

        client = CommanderClient(commander_ip, creds['username'], creds['password'], timeout=30)

        if not client.authenticate():
            return jsonify({
                'success': False,
                'error': 'Failed to authenticate with commander'
            }), 401

        # Get store metadata
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT store_name, brand FROM commanders WHERE ip = ?", (commander_ip,))
        store_row = cursor.fetchone()
        conn.close()

        store_name = store_row['store_name'] if store_row else 'Unknown Store'
        brand = store_row['brand'] if store_row else 'Unknown'

        # Build store info for parser
        store_info = tank_data_parser.build_store_info(commander_ip, store_name, '', brand)

        # Query tank data
        logger.info(f"Querying tank data from {commander_ip} for period {period}...")
        tank_monitor_xml = client.query_endpoint('vrubyrept', {'reptname': 'tankMonitor', 'period': period, 'reptnum': 1})
        fuel_config_xml = client.query_endpoint('vfuelcfg')
        sales_xml = client.query_endpoint('vrubyrept', {'reptname': 'tank', 'period': period, 'reptnum': 1})

        # Initialize data containers
        inventory = []
        reconciliation = []
        deliveries = []
        sales = []
        alarms = []
        alarm_status = []
        has_tls = False

        # Use the existing tank_data_parser module for consistent parsing
        # Parse tank inventory from tankMonitor
        if tank_monitor_xml and b'Fault' not in tank_monitor_xml:
            has_tls = True

            # Parse inventory using existing parser
            parsed_tanks = tank_data_parser.parse_tank_monitor_xml(tank_monitor_xml, store_info)
            for tank in parsed_tanks:
                fill_pct = (tank['volume'] / tank['capacity'] * 100) if tank.get('capacity', 0) > 0 else 0
                inventory.append({
                    'tank_id': str(tank.get('id', '')),
                    'product': tank.get('name', ''),
                    'full_name': tank.get('full_name', ''),
                    'volume': round(tank.get('volume', 0), 0),
                    'capacity': round(tank.get('capacity', 0), 0),
                    'ullage': round(tank.get('ullage', 0), 0),
                    'fill_percent': round(fill_pct, 1),
                    'water': round(tank.get('water', 0), 2),
                    'temperature': round(tank.get('temp', 0), 1),
                    'height': round(tank.get('level_in', 0), 2)
                })

            # Parse reconciliation using existing parser
            parsed_reconciliation = tank_data_parser.parse_reconciliation_from_tank_monitor(tank_monitor_xml, parsed_tanks)
            for rec in parsed_reconciliation:
                reconciliation.append({
                    'tank_id': str(rec.get('tank_id', '')),
                    'product': rec.get('tank_name', ''),
                    'full_name': rec.get('full_name', ''),
                    'begin_volume': round(rec.get('begin_volume', 0), 0),
                    'end_volume': round(rec.get('end_volume', 0), 0),
                    'dispensed': round(rec.get('dispensed', 0), 1),
                    'variance': round(rec.get('variance', 0), 1),
                    'variance_percent': round(rec.get('variance_pct', 0), 2),
                    'begin_date': rec.get('begin_display', ''),
                    'end_date': rec.get('end_display', '')
                })

            # Parse deliveries using existing parser
            parsed_deliveries, delivery_summary = tank_data_parser.parse_deliveries_from_tank_monitor(tank_monitor_xml)
            for del_rec in parsed_deliveries:
                deliveries.append({
                    'tank_id': str(del_rec.get('tank_id', '')),
                    'product': del_rec.get('tank_name', ''),
                    'full_name': del_rec.get('full_name', ''),
                    'delivery_volume': round(del_rec.get('delivered_gallons', 0), 0),
                    'start_volume': round(del_rec.get('start_volume', 0), 0),
                    'end_volume': round(del_rec.get('end_volume', 0), 0),
                    'date': del_rec.get('start_display', ''),
                    'end_date': del_rec.get('end_display', ''),
                    'duration_minutes': del_rec.get('duration_minutes', 0)
                })

            # Parse alarms using existing parser
            parsed_alarm_history, parsed_alarm_status = tank_data_parser.parse_alarm_history_from_tank_monitor(tank_monitor_xml)
            for alarm in parsed_alarm_history:
                alarms.append({
                    'tank_id': str(alarm.get('tank_id', '')),
                    'tank_name': alarm.get('tank_name', ''),
                    'alarm_type': alarm.get('alarm_type', ''),
                    'date': alarm.get('date_display', ''),
                    'severity': alarm.get('severity', 'info'),
                    'category': alarm.get('category', '')
                })

            for status in parsed_alarm_status:
                alarm_status.append({
                    'tank_id': str(status.get('tank_id', '')),
                    'tank_name': status.get('tank_name', ''),
                    'has_active_alarm': status.get('has_active_alarm', False),
                    'active_alarms': status.get('active_alarms', []),
                    'leak': status.get('leak', False),
                    'high_water': status.get('high_water', False),
                    'overfill': status.get('overfill', False),
                    'low_limit': status.get('low_limit', False),
                    'theft': status.get('theft', False)
                })

        # Parse sales data using existing parser
        if sales_xml and b'Fault' not in sales_xml:
            parsed_sales = tank_data_parser.parse_sales_xml(sales_xml)
            for sale in parsed_sales:
                sales.append({
                    'grade': sale.get('tank', ''),
                    'full_name': sale.get('full_name', ''),
                    'volume': round(sale.get('volume', 0), 1),
                    'amount': round(sale.get('revenue', 0), 2),
                    'transactions': sale.get('transactions', 0)
                })

        # Count active alarms
        active_alarm_count = sum(1 for s in alarm_status if s.get('has_active_alarm', False))

        return jsonify({
            'success': True,
            'store_name': store_name,
            'store_ip': commander_ip,
            'brand': brand,
            'period': period,
            'date': report_date,
            'has_tls': has_tls,
            'inventory': inventory,
            'reconciliation': reconciliation,
            'deliveries': deliveries,
            'sales': sales,
            'alarms': alarms,
            'alarm_status': alarm_status,
            'summary': {
                'tank_count': len(inventory),
                'total_volume': sum(t['volume'] for t in inventory),
                'total_capacity': sum(t['capacity'] for t in inventory),
                'delivery_count': len(deliveries),
                'total_delivered': sum(d['delivery_volume'] for d in deliveries),
                'total_sales_volume': sum(s['volume'] for s in sales),
                'total_sales_amount': sum(s['amount'] for s in sales),
                'total_transactions': sum(s.get('transactions', 0) for s in sales),
                'alarm_count': len(alarms),
                'active_alarms': active_alarm_count
            }
        })

    except Exception as e:
        import traceback
        logger.error(f"Error querying tank data: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tanks/analysis', methods=['GET'])
def tank_analysis_api():
    """Get detailed tank analysis data for a specific store."""
    commander_ip = request.args.get('commander_ip')

    if not commander_ip:
        return jsonify({'success': False, 'error': 'Commander IP is required'}), 400

    try:
        from lib.tank_commander_client import CommanderClient

        creds = get_commander_credentials()
        if not creds:
            return jsonify({
                'success': False,
                'error': 'Commander credentials not configured'
            }), 500

        client = CommanderClient(commander_ip, creds['username'], creds['password'], timeout=30)

        if not client.authenticate():
            return jsonify({
                'success': False,
                'error': 'Failed to authenticate with commander'
            }), 401

        # Get store metadata
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT store_name, brand FROM commanders WHERE ip = ?", (commander_ip,))
        store_row = cursor.fetchone()
        conn.close()

        store_name = store_row['store_name'] if store_row else 'Unknown Store'

        # Query tank data
        tank_monitor_xml = client.query_endpoint('vrubyrept', {'reptname': 'tankMonitor', 'period': 1, 'reptnum': 1})
        fuel_config_xml = client.query_endpoint('vfuelcfg')
        sales_xml = client.query_endpoint('vrubyrept', {'reptname': 'tank', 'period': 1, 'reptnum': 1})

        # Parse data
        tanks = []
        sales = []
        deliveries = []
        alarms = []
        active_alarms = 0

        import xml.etree.ElementTree as ET

        # Parse tank inventory from tankMonitor
        if tank_monitor_xml and b'Fault' not in tank_monitor_xml:
            try:
                root = ET.fromstring(tank_monitor_xml)

                # Parse tank inventory
                for tank_elem in root.findall('.//tankInventory/tank') or root.findall('.//TankInventory//Tank') or []:
                    tank_id = tank_elem.findtext('tankId') or tank_elem.findtext('TankId') or tank_elem.get('id', '')
                    product = tank_elem.findtext('productName') or tank_elem.findtext('ProductName') or ''
                    volume_str = tank_elem.findtext('volume') or tank_elem.findtext('Volume') or '0'
                    capacity_str = tank_elem.findtext('capacity') or tank_elem.findtext('Capacity') or '0'

                    try:
                        volume = float(volume_str.replace(',', ''))
                    except:
                        volume = 0
                    try:
                        capacity = float(capacity_str.replace(',', ''))
                    except:
                        capacity = 0

                    tanks.append({
                        'tank_id': tank_id,
                        'product': product,
                        'volume': volume,
                        'capacity': capacity
                    })

                # Parse alarms
                for alarm_elem in root.findall('.//alarmStatus/alarm') or root.findall('.//AlarmStatus//Alarm') or []:
                    is_active = alarm_elem.findtext('active', '0') == '1' or alarm_elem.findtext('Active', '0') == '1'
                    if is_active:
                        active_alarms += 1
                    alarms.append({
                        'tank_id': alarm_elem.findtext('tankId') or alarm_elem.findtext('TankId') or '',
                        'description': alarm_elem.findtext('description') or alarm_elem.findtext('Description') or '',
                        'time': alarm_elem.findtext('time') or alarm_elem.findtext('Time') or '',
                        'active': is_active
                    })

                # Parse deliveries
                for del_elem in root.findall('.//deliveryHistory/delivery') or root.findall('.//DeliveryHistory//Delivery') or []:
                    deliveries.append({
                        'tank_id': del_elem.findtext('tankId') or del_elem.findtext('TankId') or '',
                        'date': del_elem.findtext('date') or del_elem.findtext('Date') or '',
                        'volume': float(del_elem.findtext('volume') or del_elem.findtext('Volume') or '0')
                    })

            except ET.ParseError as e:
                logger.error(f"Error parsing tank monitor XML: {e}")

        # Parse sales data
        if sales_xml:
            try:
                root = ET.fromstring(sales_xml)
                for product_elem in root.findall('.//product') or root.findall('.//Product') or []:
                    grade = product_elem.findtext('productName') or product_elem.findtext('ProductName') or ''
                    volume_str = product_elem.findtext('volume') or product_elem.findtext('Volume') or '0'
                    try:
                        volume = float(volume_str.replace(',', ''))
                    except:
                        volume = 0
                    if volume > 0:
                        sales.append({
                            'grade': grade,
                            'volume': volume
                        })
            except ET.ParseError:
                pass

        return jsonify({
            'success': True,
            'store_name': store_name,
            'tanks': tanks,
            'sales': sales,
            'deliveries': deliveries[-10:],  # Last 10 deliveries
            'alarms': alarms,
            'active_alarms': active_alarms
        })

    except Exception as e:
        import traceback
        logger.error(f"Error getting tank analysis: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/tanks/download/<filename>')
def download_tank_report(filename):
    """Download generated tank report (unauthenticated)."""
    from pathlib import Path
    import os

    # Sanitize filename to prevent directory traversal
    filename = os.path.basename(filename)
    report_dir = Path(os.getenv('TANK_REPORTS_PATH', '/app/data/tank_reports'))
    file_path = report_dir / filename

    if not file_path.exists():
        return jsonify({'error': 'Report not found'}), 404

    from flask import send_file
    return send_file(
        file_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


if __name__ == '__main__':
    logger.info("Starting POSProctor Web Interface...")
    logger.info(f"Database: {DB_PATH}")
    logger.info(f"TLOG Service: {TLOG_SERVICE_URL}")
    logger.info(f"Monitoring Service: {MONITORING_SERVICE_URL}")

    # Generate commanders.csv on startup for Vector enrichment
    regenerate_commanders_csv()

    app.run(host='0.0.0.0', port=5000, debug=False)
