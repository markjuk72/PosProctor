# POSProctor Developer Guide

This guide provides technical documentation for developers working on POSProctor.

## Table of Contents

- [Development Environment](#development-environment)
- [Architecture](#architecture)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Services](#services)
- [Adding Features](#adding-features)
- [Testing](#testing)
- [Deployment](#deployment)

## Development Environment

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+ (for local development)
- Git
- SQLite client
- Code editor (VS Code recommended)

### Local Setup

```bash
# Clone repository
git clone <repository-url>
cd posproctor

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access services
# Webapp: https://localhost
# Grafana: https://localhost:3000
# Prometheus: https://localhost:9090
```

### Development Workflow

#### Editing Code

1. Edit code in your editor
2. Rebuild specific service:
   ```bash
   docker-compose stop webapp
   docker-compose build webapp
   docker-compose up -d webapp
   ```

3. View logs:
   ```bash
   docker-compose logs -f webapp
   ```

#### Database Changes

```bash
# Access database
docker exec -it posproctor-webapp sqlite3 /app/data/database/posproctor.db

# Run SQL
sqlite> SELECT * FROM commanders;
sqlite> .schema commanders
sqlite> .quit
```

#### Hot Reload

For faster development, mount code as volume (edit docker-compose.yml):

```yaml
services:
  webapp:
    volumes:
      - ./webapp:/app  # Mount source code
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
```

## Architecture

### System Overview

```
POSProctor consists of 5 main services:

1. nginx - Reverse proxy with SSL termination
2. webapp - Flask web application (port 5000)
3. monitoring - Commander polling service (port 8000)
4. tlog - Transaction log service (port 8001)
5. bitwarden-serve - Password vault (port 8087)

Supporting services:
- prometheus - Metrics storage
- loki - Log aggregation
- vector - Syslog collector
- grafana - Dashboards
```

### Service Communication

```
nginx (443) ──┬──> webapp (5000)
              ├──> monitoring (8000)
              ├──> tlog (8001)
              ├──> grafana (3000)
              └──> prometheus (9090)

webapp ───────┬──> monitoring (health checks)
              ├──> tlog (TLOG operations)
              ├──> bitwarden (password ops)
              └──> SQLite database

monitoring ───┬──> Commanders (HTTPS API)
              ├──> SQLite database
              └──> Prometheus (metrics export)

tlog ─────────┬──> Commanders (HTTPS API)
              ├──> SQLite database
              └──> Filesystem (TLOG storage)
```

### Data Flow

**Commander Monitoring**:
```
monitoring service polls commanders every 5 minutes
    ↓
Parses XML responses
    ↓
Updates SQLite database
    ↓
Exports Prometheus metrics
    ↓
Grafana queries Prometheus
    ↓
Dashboards display data
```

**TLOG Download**:
```
User clicks "Download TLOG" in webapp
    ↓
Webapp calls TLOG service API
    ↓
TLOG service fetches from commander
    ↓
Parses TLOG XML
    ↓
Stores file in data/tlogs/
    ↓
Updates SQLite database
    ↓
Returns transaction data to webapp
    ↓
Webapp displays to user
```

## Database Schema

### Tables

#### commanders
Stores commander device configuration.

```sql
CREATE TABLE commanders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL,
    group_name TEXT,
    brand TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### settings
Application configuration settings.

```sql
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Common settings:
- `timeout_seconds` - API timeout (default: 30)
- `max_workers` - Thread pool size (default: 10)
- `grafana_port` - Grafana port (default: 3000)

#### tlog_files
Metadata for downloaded TLOG files.

```sql
CREATE TABLE tlog_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commander_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    period TEXT NOT NULL,  -- 'shift' or 'day'
    report_date TEXT,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (commander_id) REFERENCES commanders (id)
);
```

### Database Access

#### From Python Services

```python
import sqlite3

def get_db_connection():
    conn = sqlite3.connect('/app/data/database/posproctor.db')
    conn.row_factory = sqlite3.Row
    return conn

# Usage
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT * FROM commanders WHERE enabled = 1")
commanders = cursor.fetchall()
conn.close()
```

#### From Container

```bash
docker exec -it posproctor-webapp sqlite3 /app/data/database/posproctor.db
```

## API Reference

### Monitoring Service API

**Base URL**: http://localhost:8000

#### GET /health
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "service": "monitoring"
}
```

#### GET /metrics
Prometheus metrics export.

**Response**: Prometheus text format
```
# HELP posproctor_controller_status Controller online status
# TYPE posproctor_controller_status gauge
posproctor_controller_status{store="Store 001",ip="10.0.0.1",brand="BrandA"} 1.0
```

### TLOG Service API

**Base URL**: http://localhost:8001

#### GET /health
Health check endpoint.

#### POST /api/tlog/latest
Download latest TLOG for a commander.

**Request**:
```json
{
  "ip": "10.0.0.1",
  "period": "day"
}
```

**Response**:
```json
{
  "success": true,
  "filename": "10.0.0.1_day_2026-01-10.xml",
  "transactions": [...],
  "summary": {
    "total": 150,
    "fuel": 120,
    "inside": 30
  }
}
```

### Webapp API

**Base URL**: https://localhost

#### GET /api/commanders
Get all commanders.

**Response**:
```json
{
  "commanders": [
    {
      "id": 1,
      "ip": "10.0.0.1",
      "store_name": "Store 001",
      "enabled": 1
    }
  ]
}
```

#### POST /api/commanders
Add new commander.

**Request**:
```json
{
  "ip": "10.0.0.1",
  "store_name": "Store 001",
  "group_name": "Region A",
  "brand": "BrandA"
}
```

#### PUT /api/commanders/<id>/toggle
Enable/disable commander.

#### DELETE /api/commanders/<id>
Delete commander.

#### POST /api/password/dry-run
Test current Bitwarden password on all commanders.

**Request**:
```json
{
  "username": "posproctor"
}
```

**Response**:
```json
{
  "success": true,
  "succeeded": 1,
  "failed": 0,
  "total": 1,
  "results": [...]
}
```

#### POST /api/password/change
Change password on all commanders and update Bitwarden.

**Request**:
```json
{
  "username": "posproctor",
  "new_password": "SecurePass1"
}
```

## Services

### Webapp (Flask)

**Location**: `webapp/`

**Main Files**:
- `app.py` - Main Flask application
- `templates/` - Jinja2 HTML templates
- `static/` - CSS, JavaScript, images
- `lib/` - Shared libraries

**Key Libraries**:
- `lib/bitwarden_api_client.py` - Bitwarden integration
- `lib/commander_password.py` - Commander password management

**Routes**:
```python
@app.route('/')                    # Dashboard
@app.route('/commanders')          # Commander management
@app.route('/tlogs')               # TLOG viewer
@app.route('/passwords')           # Password management
@app.route('/config')              # Configuration
```

### Monitoring Service

**Location**: `monitoring/`

**Main Files**:
- `main.py` - Main monitoring loop
- `scraper.py` - Commander API client
- `metrics.py` - Prometheus metrics

**Flow**:
1. Load commanders from database
2. Poll each commander (multi-threaded)
3. Parse XML responses
4. Update database
5. Export Prometheus metrics
6. Sleep and repeat

### TLOG Service

**Location**: `tlog/`

**Main Files**:
- `main.py` - Flask API server
- `tlog_fetcher.py` - TLOG download logic
- `tlog_parser.py` - XML parsing

**Operations**:
- Download TLOG files from commanders
- Parse transaction XML
- Store files in `data/tlogs/`
- Update database metadata

### Bitwarden Service

**Location**: `bitwarden-serve/`

Runs Bitwarden CLI in serve mode for password vault access.

**Environment**:
- `BW_SESSION` - Unlock token
- `BW_CLIENTID` - API client ID
- `BW_CLIENTSECRET` - API client secret

## Adding Features

### Adding a New Webapp Page

1. Create route in `webapp/app.py`:
```python
@app.route('/mynewpage')
def mynewpage():
    return render_template('mynewpage.html')
```

2. Create template `webapp/templates/mynewpage.html`:
```html
{% extends "base.html" %}
{% block title %}My New Page{% endblock %}
{% block content %}
<h1>My New Page</h1>
{% endblock %}
```

3. Add navigation link in `webapp/templates/base.html`:
```html
<li class="nav-item">
    <a class="nav-link" href="{{ url_for('mynewpage') }}">
        <i class="fas fa-icon"></i> My Page
    </a>
</li>
```

4. Rebuild webapp:
```bash
docker-compose stop webapp
docker-compose build webapp
docker-compose up -d webapp
```

### Adding a New Metric

1. Add metric to `monitoring/metrics.py`:
```python
from prometheus_client import Gauge

new_metric = Gauge(
    'posproctor_new_metric',
    'Description of new metric',
    ['store', 'ip']
)
```

2. Export metric in scraper:
```python
new_metric.labels(store=store_name, ip=ip).set(value)
```

3. Add to Grafana dashboard:
   - Edit dashboard JSON
   - Add panel with query: `posproctor_new_metric`

### Adding Database Table

1. Create migration SQL file `migrations/001_add_table.sql`:
```sql
CREATE TABLE new_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

2. Run migration:
```bash
docker exec -it posproctor-webapp sqlite3 /app/data/database/posproctor.db < migrations/001_add_table.sql
```

3. Update code to use new table

## Testing

### Manual Testing

```bash
# Test commander connectivity
curl -k https://10.0.0.1/cgi-bin/CGI.EXE

# Test monitoring service
curl http://localhost:8000/health
curl http://localhost:8000/metrics

# Test TLOG service
curl http://localhost:8001/health

# Test webapp
curl https://localhost/
```

### Unit Testing

```bash
# Run Python tests
cd webapp
python -m pytest tests/

# Run with coverage
python -m pytest --cov=. tests/
```

### Integration Testing

```bash
# Start stack
docker-compose up -d

# Wait for health
sleep 30

# Run tests
./tests/integration_test.sh
```

## Deployment

### Production Checklist

- [ ] Set secure passwords in environment
- [ ] Configure SSL certificates
- [ ] Enable authentication
- [ ] Configure backup strategy
- [ ] Set up monitoring alerts
- [ ] Configure log rotation
- [ ] Test disaster recovery

### Environment Variables

Production environment should set:

```bash
# Security
GRAFANA_ADMIN_PASSWORD=<strong-password>
FLASK_SECRET_KEY=<random-hex>

# Bitwarden
BW_CLIENTID=<bitwarden-api-client-id>
BW_CLIENTSECRET=<bitwarden-api-client-secret>
BW_PASSWORD=<bitwarden-master-password>

# Commander
COMMANDER_USERNAME=admin
COMMANDER_PASSWORD=<stored-in-bitwarden>
```

### SSL Certificates

Place certificates in `config/ssl/`:

```
config/ssl/
├── cert.pem    # SSL certificate
└── key.pem     # Private key
```

Update `config/nginx.conf`:

```nginx
ssl_certificate /etc/nginx/ssl/cert.pem;
ssl_certificate_key /etc/nginx/ssl/key.pem;
```

### Backup Strategy

**Database**:
```bash
# Backup
docker exec posproctor-webapp sqlite3 /app/data/database/posproctor.db ".backup /app/data/database/backup.db"

# Restore
docker exec posproctor-webapp sqlite3 /app/data/database/posproctor.db ".restore /app/data/database/backup.db"
```

**TLOG Files**:
```bash
# Backup
tar -czf tlogs-backup.tar.gz data/tlogs/

# Restore
tar -xzf tlogs-backup.tar.gz
```

**Grafana Dashboards**:
Dashboards are in `grafana/provisioning/dashboards/` and version controlled.

### Monitoring

Monitor POSProctor itself:
- Service health endpoints
- Docker container status
- Disk space usage
- Database size growth
- Log file sizes

### Log Rotation

Configure log rotation in docker-compose.yml:

```yaml
services:
  webapp:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## Coding Standards

### Python

- Follow PEP 8
- Use type hints
- Document functions with docstrings
- Keep functions small and focused
- Use meaningful variable names

### SQL

- Use parameterized queries (prevent SQL injection)
- Index frequently queried columns
- Use transactions for multi-step operations

### Templates

- Extend base.html for consistency
- Use template inheritance
- Escape user input
- Use url_for() for URLs

### JavaScript

- Use modern ES6+ syntax
- Handle errors gracefully
- Provide user feedback
- Use fetch() for API calls

## Common Tasks

### Adding a New Commander Field

1. Add column to database:
```sql
ALTER TABLE commanders ADD COLUMN new_field TEXT;
```

2. Update webapp form in `templates/commanders.html`

3. Update insert/update queries in `app.py`

### Adding a New Grafana Dashboard

1. Create dashboard in Grafana UI
2. Export JSON
3. Save to `grafana/provisioning/dashboards/new_dashboard.json`
4. Commit to git

### Changing Default Settings

1. Update default in `webapp/app.py`:
```python
def get_setting(key, default):
    # Update default value here
    pass
```

2. Update database if needed:
```sql
INSERT OR REPLACE INTO settings (key, value) VALUES ('new_setting', 'default_value');
```

## Troubleshooting Development

### Container Won't Start

```bash
# Check logs
docker-compose logs <service>

# Check for port conflicts
netstat -tulpn | grep <port>

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Database Locked

```bash
# Stop all services
docker-compose down

# Remove lock files
rm data/database/*.db-shm
rm data/database/*.db-wal

# Restart
docker-compose up -d
```

### Code Changes Not Reflecting

```bash
# Full rebuild
docker-compose stop <service>
docker-compose build --no-cache <service>
docker-compose up -d <service>

# Check if volume mounted correctly
docker inspect posproctor-<service> | grep Mounts
```

## Resources

- [Flask Documentation](https://flask.palletsprojects.com/)
- [SQLite Documentation](https://sqlite.org/docs.html)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Docker Documentation](https://docs.docker.com/)

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Test thoroughly
4. Commit: `git commit -m "Add feature"`
5. Push: `git push origin feature/my-feature`
6. Create pull request

## License

MIT License - See LICENSE file for details
