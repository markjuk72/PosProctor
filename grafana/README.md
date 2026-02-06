# Grafana Provisioning

This directory contains Grafana provisioning configuration for POSProctor 2.0. Grafana is automatically configured with data sources and dashboards when the container starts.

## Directory Structure

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── datasources.yaml          # Prometheus and Loki configuration
│   ├── dashboards/
│   │   ├── dashboard-provider.yaml   # Dashboard auto-loading config
│   │   ├── commander_fleet.json      # Fleet monitoring dashboard
│   │   ├── tlog_activity.json        # TLOG activity dashboard
│   │   └── service_health.json       # Service health dashboard
└── README.md
```

## Data Sources

### Prometheus (prometheus-posproctor2)
- **URL**: http://prometheus:9090
- **Purpose**: Time-series metrics storage
- **Default**: Yes

### Loki (loki-posproctor2)
- **URL**: http://loki:3100
- **Purpose**: Log aggregation and querying

## Dashboards

### 1. POSProctor 2.0 - Fleet Monitor
**UID**: `posproctor2-fleet`

Monitors the fleet of Commander devices:
- **Total Commanders**: Count of configured devices
- **Controller Status**: Online/offline status for each device
- **Average Query Duration**: Performance metrics per store
- **Scrape Success**: Success/failure of monitoring scrapes

**Metrics Used**:
- `posproctor_total_commanders`
- `posproctor_controller_status`
- `posproctor_query_duration_seconds`
- `posproctor_scrape_success`

### 2. POSProctor 2.0 - TLOG Activity
**UID**: `posproctor2-tlog`

Monitors transaction log download and parsing:
- **TLOG Download Rate**: Rate of downloads per store
- **Transactions Parsed**: Count of transactions parsed
- **Average TLOG Download Duration**: Performance metrics
- **TLOG File Size**: Size of downloaded transaction logs

**Metrics Used**:
- `posproctor_tlog_downloads_total`
- `posproctor_tlog_transactions_parsed`
- `posproctor_tlog_download_duration_seconds`
- `posproctor_tlog_size_bytes`

### 3. POSProctor 2.0 - Service Health
**UID**: `posproctor2-health`

Monitors the health of POSProctor services:
- **Monitoring Service**: Up/down status
- **TLOG Service**: Up/down status
- **Webapp**: Up/down status
- **Service Logs**: Live log viewer with Loki
- **CPU Usage**: CPU consumption per service
- **Memory Usage**: Memory consumption per service

**Metrics Used**:
- `up{job=~"monitoring|tlog|webapp"}`
- `process_cpu_seconds_total`
- `process_resident_memory_bytes`

**Logs**:
- `{job=~"monitoring|tlog|webapp"}` via Loki

## Configuration

All dashboards are configured with:
- **Refresh**: 30 seconds
- **Time Range**: Last 6 hours
- **Auto-reload**: Enabled (60 second interval for provider)
- **UI Updates**: Allowed

## Access

After starting the stack with `docker-compose up -d`:

1. **Grafana UI**: http://localhost:3000
2. **Default Credentials**:
   - Username: `admin`
   - Password: `admin` (change on first login)
3. **Dashboards**: Available in the "POSProctor" folder

## Customization

Dashboards can be edited directly in the Grafana UI. Changes are allowed via `allowUiUpdates: true` in the provider configuration.

To make permanent changes:
1. Edit the dashboard in Grafana UI
2. Export the dashboard JSON
3. Replace the corresponding `.json` file in `provisioning/dashboards/`
4. Restart Grafana container to reload

## Adding New Dashboards

1. Create a new `.json` file in `provisioning/dashboards/`
2. Set a unique `uid` field
3. Dashboards are automatically loaded within 60 seconds
4. No restart required

## Troubleshooting

**Dashboards not appearing:**
- Check Grafana logs: `docker-compose logs grafana`
- Verify JSON syntax: `jq . < dashboard.json`
- Check provisioning status in Grafana UI: Configuration > Data Sources

**Data not showing:**
- Verify Prometheus is scraping: http://localhost:9090/targets
- Check metric names match exactly
- Verify time range includes recent data

**Logs not appearing:**
- Verify Loki is running: `docker-compose ps loki`
- Check Loki data source configuration
- Verify log labels match query in dashboard
