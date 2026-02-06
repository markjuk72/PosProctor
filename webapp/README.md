# Web UI

The web interface provides a unified dashboard for managing commanders and viewing transaction logs.

## Features

- **Dashboard** - System statistics and service links
- **Commander Management** - Add, enable/disable, and delete commanders
- **TLOG Viewer** - Download and view transaction logs
- **Configuration** - Update system settings and credentials

## Files

- `app.py` - Flask web application
- `templates/` - HTML templates (base, index, commanders, tlogs, config)
- `Dockerfile` - Container build configuration
- `requirements.txt` - Python dependencies

## Routes

### Pages
- `GET /` - Dashboard
- `GET /commanders` - Commander management
- `GET /tlogs` - TLOG viewer
- `GET /config` - Configuration editor

### API Endpoints
- `POST /commanders/add` - Add new commander
- `POST /commanders/<id>/toggle` - Toggle enabled status
- `POST /commanders/<id>/delete` - Delete commander
- `POST /config/update` - Update configuration
- `POST /api/tlog/latest` - Download latest TLOG (proxy to TLOG service)
- `POST /api/tlog/list` - List available TLOGs (proxy to TLOG service)
- `GET /api/tlog/stored` - List stored TLOGs (proxy to TLOG service)
- `GET /health` - Health check

## Environment Variables

- `FLASK_SECRET_KEY` - Session secret key (default: auto-generated)
- `POSPROCTOR_DB_PATH` - Database path (default: `/app/data/database/posproctor.db`)
- `TLOG_SERVICE_URL` - TLOG service URL (default: `http://tlog:8001`)
- `MONITORING_SERVICE_URL` - Monitoring service URL (default: `http://monitoring:8000`)
- `PROMETHEUS_URL` - Prometheus URL (default: `http://prometheus:9090`)
- `GRAFANA_URL` - Grafana URL (default: `http://grafana:3000`)

## UI Features

### Dashboard
- Commander statistics (total, enabled, groups, brands)
- Quick links to Grafana, Prometheus, and other services
- Current configuration summary

### Commander Management
- Add new commanders with IP, store name, group, and brand
- Toggle enabled/disabled status
- Delete commanders
- View all configured commanders in a sortable table

### TLOG Viewer
- Select commander and report type (day/shift)
- Download latest transaction log
- View transaction summary (count, sales, fuel, revenue)
- List stored TLOG files

### Configuration
- Update timeout and max workers settings
- Update commander password
- Read-only view of username (managed in database)

## Building

```bash
docker build -t posproctor2-webapp .
```

## Running Standalone

```bash
docker run -d \
  -p 5000:5000 \
  -v ./data/database:/app/data/database \
  posproctor2-webapp
```

## Accessing the UI

Once running, access the web interface at:
- http://localhost:5000

## Integration

The webapp integrates with:
- **SQLite Database** - Commander configurations and settings
- **TLOG Service** - Transaction log downloads and parsing (via REST API)
- **Monitoring Service** - Metrics endpoint access
- **Prometheus** - External metrics queries
- **Grafana** - Dashboard links

All service integration is done via environment variables, making it easy to reconfigure for different deployments.

## Development

To run in development mode:

```bash
cd webapp
pip install -r requirements.txt
export POSPROCTOR_DB_PATH=../data/database/posproctor.db
export TLOG_SERVICE_URL=http://localhost:8001
export MONITORING_SERVICE_URL=http://localhost:8000
python app.py
```

## Troubleshooting

### Can't connect to services

Check that service URLs are correct:
```bash
docker-compose ps
curl http://monitoring:8000/health
curl http://tlog:8001/health
```

### Database errors

Ensure database exists and has correct schema:
```bash
docker exec posproctor2-monitoring ls -lh /app/data/database/
```

### TLOG downloads fail

Check TLOG service logs:
```bash
docker-compose logs tlog
```

Verify commander credentials are correct in configuration page.
