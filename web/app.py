from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import yaml
import os
import csv
import subprocess
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'posproctor-web-interface-key'
app.config['UPLOAD_FOLDER'] = '/app/data'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# File paths - using shared volumes that both web interface and other services can access
CONFIG_FILE = '/app/data/config.yaml'
CREDENTIALS_FILE = '/app/data/credentials.yaml'
COMMANDERS_FILE = '/app/data/commanders.csv'  # This will be mounted as shared volume

def load_config():
    """Load configuration from YAML file"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}

def save_config(config):
    """Save configuration to YAML file"""
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def load_credentials():
    """Load credentials from YAML file"""
    try:
        with open(CREDENTIALS_FILE, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}

def save_credentials(credentials):
    """Save credentials to YAML file"""
    with open(CREDENTIALS_FILE, 'w') as f:
        yaml.dump(credentials, f, default_flow_style=False)

def load_commanders():
    """Load commanders from CSV file"""
    try:
        commanders = []
        with open(COMMANDERS_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                commanders.append(row)
        return commanders
    except FileNotFoundError:
        return []

@app.route('/')
def index():
    """Landing page with links to all services"""
    config = load_config()
    credentials = load_credentials()
    commanders = load_commanders()

    # Get service URLs using the current request host
    host = request.host.split(':')[0] if request.host else 'localhost'  # Remove port if present, fallback to localhost
    services = {
        'grafana': f'http://{host}:3000',
        'prometheus': f'http://{host}:9090',
        'metrics': f'http://{host}:8000/metrics',
        'loki_api': f'http://{host}:3100/ready'  # Loki readiness endpoint instead of web UI
    }

    stats = {
        'total_stores': len(commanders),
        'enabled_stores': len([c for c in commanders if c.get('enabled', '').lower() == 'true']),
        'groups': len(set(c.get('group', '') for c in commanders if c.get('group')))
    }

    return render_template('index.html', services=services, stats=stats, config=config)

@app.route('/config')
def config_page():
    """Configuration management page"""
    config = load_config()
    credentials = load_credentials()
    return render_template('config.html', config=config, credentials=credentials)

@app.route('/config', methods=['POST'])
def update_config():
    """Update configuration settings"""
    # Load existing config
    config = load_config()
    credentials = load_credentials()

    # Update config settings
    config['scrape_interval_minutes'] = int(request.form.get('scrape_interval_minutes', 6))
    config['timeout_seconds'] = int(request.form.get('timeout_seconds', 30))

    # Update loyalty program settings
    loyalty_names = request.form.get('loyalty_names', '').strip().split('\n')
    loyalty_names = [name.strip() for name in loyalty_names if name.strip()]
    config['loyalty_program'] = {'names': loyalty_names}

    # Update credentials
    credentials['credentials'] = {
        'username': request.form.get('username', ''),
        'password': request.form.get('password', '')
    }

    # Save both files
    save_config(config)
    save_credentials(credentials)

    flash('Configuration updated successfully!', 'success')
    return redirect(url_for('config_page'))

@app.route('/smtp')
def smtp_page():
    """SMTP configuration page"""
    return render_template('smtp.html')

@app.route('/smtp', methods=['POST'])
def update_smtp():
    """Update SMTP settings (these will be environment variables)"""
    smtp_settings = {
        'SMTP_HOST': request.form.get('smtp_host', ''),
        'SMTP_USER': request.form.get('smtp_user', ''),
        'SMTP_PASSWORD': request.form.get('smtp_password', ''),
        'SMTP_FROM': request.form.get('smtp_from', ''),
        'SMTP_FROM_NAME': request.form.get('smtp_from_name', ''),
        'ALERT_EMAIL': request.form.get('alert_email', '')
    }

    # Save to a separate file that can be sourced as env vars
    env_file = '/app/data/.env'
    with open(env_file, 'w') as f:
        for key, value in smtp_settings.items():
            if value:  # Only write non-empty values
                f.write(f'{key}={value}\n')

    flash('SMTP settings saved! You will need to restart the stack to apply changes.', 'success')
    return redirect(url_for('smtp_page'))

@app.route('/commanders')
def commanders_page():
    """Commanders management page"""
    commanders = load_commanders()
    return render_template('commanders.html', commanders=commanders)

@app.route('/commanders/upload', methods=['POST'])
def upload_commanders():
    """Upload commanders CSV file"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('commanders_page'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('commanders_page'))

    if file and file.filename.endswith('.csv'):
        # Save the uploaded file
        file.save(COMMANDERS_FILE)
        flash('Commanders file uploaded successfully!', 'success')
    else:
        flash('Please upload a CSV file', 'error')

    return redirect(url_for('commanders_page'))

@app.route('/api/status')
def api_status():
    """API endpoint for system status"""
    commanders = load_commanders()
    config = load_config()

    status = {
        'total_stores': len(commanders),
        'enabled_stores': len([c for c in commanders if c.get('enabled', '').lower() == 'true']),
        'scrape_interval': config.get('scrape_interval_minutes', 6),
        'services': {
            'grafana': True,  # Could add actual health checks here
            'prometheus': True,
            'posproctor': True
        }
    }

    return jsonify(status)

@app.route('/api/services')
def api_services():
    """API endpoint to get service URLs (for testing dynamic URLs)"""
    host = request.host.split(':')[0] if request.host else 'localhost'
    services = {
        'grafana': f'http://{host}:3000',
        'prometheus': f'http://{host}:9090',
        'metrics': f'http://{host}:8000/metrics',
        'loki_api': f'http://{host}:3100/ready',
        'web_interface': f'http://{host}:5000'
    }
    return jsonify({'request_host': request.host, 'detected_host': host, 'service_urls': services})

@app.route('/restart', methods=['POST'])
def restart_posproctor():
    """Display restart instructions"""
    flash('To restart POSProctor after configuration changes, run: docker-compose restart posproctor-app', 'info')
    return redirect(url_for('config_page'))

@app.route('/api/restart', methods=['POST'])
def api_restart_posproctor():
    """API endpoint with restart instructions"""
    return jsonify({
        'success': False,
        'message': 'Automatic restart not available. Please run: docker-compose restart posproctor-app',
        'instructions': 'docker-compose restart posproctor-app'
    })

if __name__ == '__main__':
    # Ensure data directory exists
    os.makedirs('/app/data', exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)