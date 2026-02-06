# Grafana Dashboards Guide

This guide covers the Grafana dashboards included with POSProctor for monitoring Verifone Commander devices.

## Overview

Grafana is automatically configured with datasources and dashboards when POSProctor starts. The dashboards provide real-time visibility into:
- Commander fleet status
- Transaction log activity
- Service health and performance

## Accessing Grafana

After starting POSProctor with `docker-compose up -d`:

1. Open browser to: **https://localhost:3000**
2. Login credentials:
   - Username: `admin`
   - Password: Set via `GRAFANA_ADMIN_PASSWORD` in docker-compose environment

## Available Dashboards

### POSProctor Monitor (Main Dashboard)
**UID**: `posproctor_monitor`

This is the primary monitoring dashboard showing:

**Store Overview**:
- Total stores configured
- Stores online vs offline
- Store status by brand
- Geographic distribution (by group/location)

**Device Status**:
- Controller status (online/offline)
- Pump status by store
- DCR (dispenser card reader) status
- Price display status
- Payment processor (FEP) status
- Loyalty system status

**Performance Metrics**:
- Query response times per store
- Scrape success rates
- Data freshness indicators

**Alerts**:
- Stores offline > 5 minutes
- Payment processors down
- Multiple failures

### POSProctor Heatmap
**UID**: `posproctor_heatmap`

Visual heatmap showing device status across the entire fleet:
- Color-coded store status
- Quick identification of problem areas
- Sortable by brand, group, or location
- Time-series view of availability

### POSProctor Internal Health
**UID**: `posproctor_internal_health`

Monitors the health of POSProctor services themselves:

**Service Status**:
- Monitoring service uptime
- TLOG service uptime
- Webapp uptime
- Bitwarden vault connectivity

**Resource Usage**:
- CPU usage per service
- Memory usage per service
- Database size and growth
- Disk space utilization

**Performance**:
- API response times
- Database query performance
- Background job status

### POSProctor Security Logs
**UID**: `posproctor_security_logs`

Security and audit logging dashboard:
- Login attempts and failures
- Password change operations
- Configuration changes
- API access logs
- Bitwarden vault access

### POSProctor Experimental
**UID**: `posproctor_experimental`

Dashboard for testing new metrics and visualizations:
- Beta features
- Custom queries
- Development metrics

## Datasources

### Prometheus
- **URL**: http://prometheus:9090
- **Purpose**: Time-series metrics storage
- **Scrape Interval**: 15 seconds
- **Default**: Yes

### Loki
- **URL**: http://loki:3100
- **Purpose**: Log aggregation
- **Used for**: Service logs, security events

## Key Metrics

### Commander Status Metrics
```
posproctor_controller_status{store, ip, brand}      # Controller online (1) or offline (0)
posproctor_pump_status{store, ip, pump}             # Individual pump status
posproctor_dcr_status{store, ip, dcr}               # DCR status
posproctor_price_display_status{store, ip}          # Price display status
posproctor_primary_fep_status{store, ip}            # Payment processor status
posproctor_loyalty_fep_status{store, ip}            # Loyalty system status
```

### Performance Metrics
```
posproctor_query_duration_seconds{store, ip}        # API query response time
posproctor_scrape_success{store, ip}                # Scrape success (1) or failure (0)
posproctor_total_commanders                          # Total configured commanders
```

### TLOG Metrics
```
posproctor_tlog_downloads_total{store, ip}          # Total TLOG downloads
posproctor_tlog_transactions_parsed{store}          # Transactions parsed count
posproctor_tlog_download_duration_seconds{store}    # TLOG download time
posproctor_tlog_size_bytes{store}                   # TLOG file size
```

### Service Health Metrics
```
up{job="monitoring"}                                 # Monitoring service up/down
up{job="tlog"}                                       # TLOG service up/down
up{job="webapp"}                                     # Webapp up/down
process_cpu_seconds_total{job}                       # CPU usage
process_resident_memory_bytes{job}                   # Memory usage
```

## Alerting

### Configuring Alerts

Alerts are configured in the Grafana UI:

1. Navigate to **Alerting** > **Alert rules**
2. Click **New alert rule**
3. Configure query, threshold, and notification

### Recommended Alerts

**Commander Offline**:
- Query: `posproctor_controller_status == 0`
- Threshold: > 5 minutes
- Severity: Warning

**Payment Processor Down**:
- Query: `posproctor_primary_fep_status == 0`
- Threshold: > 1 minute
- Severity: Critical

**Service Down**:
- Query: `up{job=~"monitoring|tlog|webapp"} == 0`
- Threshold: > 2 minutes
- Severity: Critical

**High Scrape Failure Rate**:
- Query: `rate(posproctor_scrape_success[5m]) < 0.8`
- Threshold: < 80% success rate
- Severity: Warning

### Notification Channels

Configure notification channels in Grafana:

1. Navigate to **Alerting** > **Contact points**
2. Add contact point (email, Slack, PagerDuty, etc.)
3. Test notification
4. Link to alert rules

## Customization

### Editing Dashboards

Dashboards can be edited directly in Grafana UI:

1. Open dashboard
2. Click **Dashboard settings** (gear icon)
3. Make changes
4. Save dashboard

Changes are automatically persisted.

### Exporting Dashboards

To save dashboard changes permanently:

1. Open dashboard
2. Click **Dashboard settings** > **JSON Model**
3. Copy JSON
4. Save to `grafana/provisioning/dashboards/<dashboard-name>.json`
5. Restart Grafana: `docker-compose restart grafana`

### Adding New Panels

1. Open dashboard
2. Click **Add panel**
3. Configure visualization and query
4. Save panel

### Creating New Dashboards

1. Click **+ Create** > **Dashboard**
2. Add panels
3. Configure variables (optional)
4. Save dashboard
5. Export JSON and save to `grafana/provisioning/dashboards/`

## Variables

Dashboards support variables for filtering:

### Available Variables

- `$store` - Filter by store name
- `$ip` - Filter by IP address
- `$brand` - Filter by brand
- `$group` - Filter by group/location

### Using Variables

In panel queries:
```
posproctor_controller_status{store="$store", brand="$brand"}
```

## Time Ranges

### Default Ranges
- **Last 6 hours** - Default view
- **Last 24 hours** - Daily overview
- **Last 7 days** - Weekly trends

### Auto-Refresh
- Default: 30 seconds
- Configurable per dashboard
- Can be paused via UI

## Troubleshooting

### Dashboards Not Appearing
```bash
# Check Grafana logs
docker-compose logs grafana

# Verify provisioning directory
docker exec posproctor-grafana ls -la /etc/grafana/provisioning/dashboards/

# Validate JSON syntax
cd grafana/provisioning/dashboards
jq . < posproctor_monitor.json
```

### No Data Showing
```bash
# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets

# Check metrics exist
curl http://localhost:8000/metrics | grep posproctor

# Verify time range includes data
# Adjust dashboard time range to "Last 24 hours"
```

### Slow Dashboard Loading
```bash
# Check Prometheus query performance
# Open Prometheus UI: http://localhost:9090
# Run query and check execution time

# Reduce time range
# Increase auto-refresh interval
# Simplify complex queries
```

### Logs Not Appearing in Loki
```bash
# Check Loki is running
docker-compose ps loki

# Verify Vector is collecting logs
docker-compose logs vector

# Test Loki datasource
curl http://localhost:3100/ready
```

## Best Practices

1. **Use Variables**: Makes dashboards reusable and reduces duplication
2. **Set Reasonable Refresh Intervals**: Balance freshness vs performance
3. **Document Custom Panels**: Add descriptions to panels
4. **Export Regularly**: Save dashboard JSON after significant changes
5. **Use Folders**: Organize dashboards into logical folders
6. **Configure Alerts**: Set up critical alerts for commander and service failures

## Advanced Features

### Template Variables

Create dynamic dashboards using template variables:

1. Dashboard Settings > Variables
2. Add variable (e.g., store list from Prometheus query)
3. Use in panel queries: `{store="$store"}`

### Annotations

Add event annotations to dashboards:

1. Dashboard Settings > Annotations
2. Add annotation query
3. Shows events as vertical lines on graphs

### Links

Add links between related dashboards:

1. Dashboard Settings > Links
2. Add dashboard link
3. Enables easy navigation

## Reference

- Grafana Documentation: https://grafana.com/docs/
- Prometheus Query Language: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Loki Query Language: https://grafana.com/docs/loki/latest/logql/
