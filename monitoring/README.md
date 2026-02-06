# Monitoring Service

The monitoring service polls Verifone Commander APIs and exports metrics to Prometheus.

## Features

- **Multi-threaded polling** of Commander systems
- **Token caching** to reduce authentication overhead
- **Prometheus metrics export** on port 8000
- **Health check endpoint** at `/health`
- **SQLite database** for configuration
- **Automatic failover** for failed commanders

## Files

- `main.py` - Main polling loop and metrics server
- `verifone_api.py` - Verifone Commander API client
- `database.py` - SQLite database manager
- `Dockerfile` - Container build configuration
- `requirements.txt` - Python dependencies

## Metrics Exported

### Device Status Metrics
- `posproctor_controller_status` - Controller online/offline (1/0)
- `posproctor_pump_status` - Individual pump status per fueling point
- `posproctor_dcr_status` - DCR status per fueling point
- `posproctor_price_display_status` - Price display status
- `posproctor_primary_fep_status` - Payment processor connection status

### Performance Metrics
- `posproctor_scrape_success` - Scrape success/failure indicator
- `posproctor_query_duration_seconds` - API query duration histogram
- `posproctor_scrape_cycle_duration_seconds` - Full cycle duration
- `posproctor_total_commanders` - Number of commanders monitored

## Environment Variables

- `POSPROCTOR_DB_PATH` - Database path (default: `/app/data/database/posproctor.db`)
- `POLL_INTERVAL` - Polling interval in seconds (default: `300`)
- `WORKER_THREADS` - Max concurrent workers (default: `10`)
- `REQUEST_TIMEOUT` - API request timeout (default: `30`)
- `COMMANDER_USERNAME` - Default Commander username
- `COMMANDER_PASSWORD` - Default Commander password
- `DEV_MODE` - Enable development mode filtering (default: `false`)
- `DEV_STORE_FILTER` - Comma-separated store names to filter (dev mode only)

## Endpoints

- `http://localhost:8000/metrics` - Prometheus metrics
- `http://localhost:8000/health` - Health check JSON

## Database Schema

The service uses SQLite for configuration storage:

### commanders
- `id` - Auto-increment primary key
- `ip` - Commander IP address (unique)
- `store_name` - Store display name
- `group_name` - Grouping for metrics
- `brand` - Brand label (e.g., BrandA, Chevron)
- `enabled` - Enable/disable monitoring

### credentials
- `id` - Auto-increment primary key
- `username` - Commander API username
- `password` - Commander API password
- `is_default` - Default credential flag

### settings
- `key` - Setting name (primary key)
- `value` - Setting value
- `data_type` - Type (string, integer, boolean)

## Development Mode

Enable dev mode to test with a subset of stores:

```bash
DEV_MODE=true
DEV_STORE_FILTER="Store 001,Store 002"
```

This reduces API load during development/testing.

## Building

```bash
docker build -t posproctor2-monitoring .
```

## Running Standalone

```bash
docker run -d \
  -p 8000:8000 \
  -v ./data/database:/app/data/database \
  -e COMMANDER_USERNAME=posproctor \
  -e COMMANDER_PASSWORD=yourpassword \
  -e POLL_INTERVAL=300 \
  posproctor2-monitoring
```

## Adding Commanders

Use the web UI or directly insert into the database:

```sql
INSERT INTO commanders (ip, store_name, group_name, brand, enabled)
VALUES ('10.0.0.1', 'Store 001', 'Group A', 'BrandA', 1);
```

## Troubleshooting

### Check health status
```bash
curl http://localhost:8000/health
```

### View logs
```bash
docker logs -f posproctor2-monitoring
```

### Verify metrics
```bash
curl http://localhost:8000/metrics | grep posproctor
```

### Common Issues

**No commanders found**
- Check database exists at `POSPROCTOR_DB_PATH`
- Verify commanders table has enabled entries
- Check DEV_MODE filter if enabled

**Authentication failures**
- Verify COMMANDER_USERNAME and COMMANDER_PASSWORD
- Check credentials in database
- Review token cache (automatic expiration)

**High memory usage**
- Reduce MAX_WORKERS
- Increase POLL_INTERVAL
- Check for commander connectivity issues causing retries
