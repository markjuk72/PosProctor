# POSProctor v2.3

A comprehensive, production-ready monitoring solution for POS systems. This Docker-based stack provides real-time metrics, performance analytics, centralized logging, and intelligent alerting across multiple POS deployments.

## 🚀 Features

### **Real-Time Monitoring**
- **Device Health**: Controllers, pumps, DCRs, fuel price displays, loyalty FEP status
- **Payment Processing**: Primary card processor monitoring (Phillips66, buypass, Chevron, nbs)
- **Performance Analytics**: Query response times, scrape cycle optimization, failure analysis
- **Fleet Overview**: Health percentages, success rates, stores requiring attention
- **System Resources**: Python process monitoring, garbage collection, CPU usage

### **Intelligent Alerting**
- **Email Notifications**: Configurable SMTP with customizable templates
- **Severity-Based Routing**: Critical/Warning/Info alerts with different repeat intervals
- **Rich Alert Context**: Detailed descriptions with direct links to POS system UIs

### **Centralized Logging**
- **Log Aggregation**: Syslog collection from all POS systems via Vector
- **IP-to-Store Mapping**: Automatic enrichment with store names and groups
- **Searchable Interface**: Loki-powered log exploration in Grafana

## 📊 Dashboard Suite

### **POS Fleet Monitor** (`/d/pos-fleet-monitor`)
- Fleet health overview with device availability percentages
- Card Processor health monitoring across all fuel brands
- Real-time device status trends over time
- Interactive table showing stores requiring immediate attention
- Template variables for filtering by geographic groups and fuel brands

### **POS Fleet Heatmap** (`/d/pos-fleet-heatmap`)
- Visual heatmap representation of all POS system statuses
- Color-coded device status across controllers, pumps, DCRs, and price displays
- Brand and group filtering with direct links to POS system UIs
- At-a-glance identification of problematic devices

### **Stack Health Monitor** (`/d/stack-health-monitor`)
- Monitoring application status and Prometheus health
- Filesystem usage monitoring with real-time disk space tracking
- Error breakdown analysis with visual pie charts showing failure types
- Performance metrics including scrape cycle analysis and query response times
- System resource monitoring: memory usage, disk I/O, and storage growth
- Database storage metrics with data ingestion rate tracking

### **Security Logs** (`/d/3-posproctor-security-logs`)
- Centralized security log analysis with store name enrichment
- Real-time syslog streaming from all POS systems via Vector
- Automatic IP-to-store mapping from commanders.csv
- RFC 3164 compliant syslog collection on UDP port 514
- Custom hyphen-delimited log format parsing and display

### **PosProctor Experimental** (`/d/posproctor-experimental`)
- Advanced analytics and correlation analysis across multiple sites
- Multi-site pattern detection and failure correlation
- Time-based health pattern analysis with percentile tracking
- Component failure distribution analysis
- Log correlation with system health metrics
- Interactive store health ranking and detailed status tables

## 🏗️ Architecture

### **Core Services**
- **`posproctor-app`**: Multi-threaded Python poller with Prometheus metrics (Port 8000)
- **`prometheus`**: Time-series metrics storage and querying (Port 9090) - v2.53.1
- **`grafana`**: Visualization platform with pre-configured dashboards (Port 3000) - v11.1.4
- **`node_exporter`**: Host system metrics for filesystem and resource monitoring (Port 9100) - v1.8.2
- **`vector`**: Log collection, enrichment, and forwarding pipeline - v0.39.0-alpine
- **`loki`**: High-performance log aggregation and storage (Port 3100) - v3.0.0

### **Data Flow**
```
POS Systems → posproctor-app → Prometheus → Grafana
     ↓ (syslog UDP:514)
   Vector (enrichment) → Loki → Grafana
```

**Log Enrichment Pipeline:**
1. POS systems send RFC 3164 syslog messages to Vector (UDP:514)
2. Vector extracts source IP and enriches with store metadata from commanders.csv
3. Enriched logs with store names, groups, and brands are sent to Loki
4. Grafana displays formatted logs with store context

## 🔧 Configuration Files

### **Core Configuration**
- `commanders.csv`: Target systems (IP, store, group, enabled status)
- `credentials.yaml`: API authentication for POS systems
- `config.yaml`: Application settings (timeout, scrape interval)
- `.env`: Environment variables for SMTP and alert configuration

### **Service Configuration** 
- `prometheus.yml`: Metrics scraping configuration
- `config_vector.yaml`: Log processing and enrichment pipeline
- `config_loki.yaml`: Log storage and retention policies
- `grafana-provisioning/`: Datasources, dashboards, and alerting rules

## 🚀 Quick Start

### **Prerequisites**
- Docker and Docker Compose
- SMTP server for email alerts (optional)

### **Setup**
1. **Clone and Configure**:
   ```bash
   git clone <your-repo-url>
   cd posproctor
   cp .env.example .env  # Configure SMTP settings
   ```

2. **Configure POS Systems**:
   ```bash
   # Edit commanders.csv with your POS system details
   # Format: ip,store,group,enabled
   172.17.129.182,Store 102,Idaho,true
   ```

3. **Launch Stack**:
   ```bash
   docker-compose up -d
   ```

4. **Configure Email Alerts** (optional):
   ```bash
   # Set your email and run setup script
   ALERT_EMAIL=admin@company.com ./setup-alerts.sh
   ```

### **Access Points**
- **Grafana**: http://localhost:3000 (admin/your-password)
- **Prometheus**: http://localhost:9090  
- **Metrics Endpoint**: http://localhost:8000/metrics
- **Loki**: http://localhost:3100

## 📈 Performance Metrics

The monitoring application exposes comprehensive metrics for optimization:

### **Query Performance**
- `posproctor_query_duration_seconds`: Response times per POS system and endpoint
- `posproctor_query_failures_total`: Failure counts classified by error type
- `posproctor_scrape_cycle_duration_seconds`: Full cycle timing for interval tuning

### **Health Indicators**
- `posproctor_scrape_success`: Success/failure status per POS system
- `posproctor_primary_fep_status`: Primary card processor connectivity by brand
- `posproctor_loyalty_fep_status`: Loyalty system connectivity
- `posproctor_total_systems`: Count of enabled/disabled systems
- `posproctor_concurrent_queries`: Real-time active query tracking

### **Error Classification**
- `posproctor_auth_failures_total`: Authentication issues
- `posproctor_timeout_errors_total`: Network timeout tracking
- `posproctor_connection_errors_total`: Connectivity problems

## 🔔 Alert Configuration

### **Severity Levels**
- **🔴 Critical**: Controller/POS system offline, Primary card processor down (30min repeat)
- **🟡 Warning**: Individual device offline (1hr repeat)
- **🔵 Info**: Loyalty system issues (4hr repeat)

### **SMTP Configuration**
Supports major email providers:
- **Gmail**: Use app passwords for authentication
- **Office 365**: Standard SMTP configuration  
- **SendGrid/Mailgun**: API-based sending
- **Custom SMTP**: Any RFC-compliant server

## 📊 Scaling Guidance

### **Performance Tuning**
- **Scrape Interval Coordination**:
  - Primary: `config.yaml` - Controls how often the Python app polls POS systems
  - Secondary: `prometheus.yml` - Set to `(app_interval + 30s)` to avoid scraping stale data
  - Example: App polls every 6 minutes → Prometheus scrapes every 6m30s
- **Concurrent Workers**: Adjust based on network capacity and Commander load
- **Timeout Settings**: Optimize based on network latency patterns

### **Capacity Planning**
- **Current Scale**: Tested with 81 stores across 6 states
- **Resource Usage**: ~280 seconds cycle time for 47 active POS systems
- **Network Load**: ~3.5 seconds per POS system query with 10 concurrent workers

## 📝 Production Deployment Notes

### **Deployment Stability**
- All Docker images pinned to specific stable versions for consistent deployments
- Grafana v11.1.4, Prometheus v2.53.1, node_exporter v1.8.2
- Vector v0.39.0-alpine, Loki v3.0.0 for reliable log processing
- No more "latest" tag surprises during stack rebuilds

### **Enhanced Monitoring**
- Real-time filesystem monitoring with disk usage alerts
- Comprehensive error analysis with breakdown by failure type
- Storage growth tracking to prevent disk space issues
- System resource monitoring including memory and I/O performance

### **Security Considerations**
- Set strong Grafana admin password in `.env` file
- Secure POS system credentials in `credentials.yaml`
- Use environment variables for sensitive SMTP settings
- Configure firewall rules for service ports

### **Monitoring Best Practices**
- Set up automated backups for Grafana configurations
- Monitor disk usage for Prometheus and Loki data retention
- Regularly review alert thresholds and notification policies
- Test email delivery and escalation procedures

### **Open Source Deployment**
For deploying this stack in different environments:
1. Update datasource UIDs in dashboards after first startup
2. Configure SMTP settings for your email infrastructure
3. Modify `commanders.csv` with your POS system IP addresses
4. Coordinate scrape intervals:
   - Set primary polling interval in `config.yaml`
   - Update Prometheus scrape interval in `prometheus.yml` to `(app_interval + 30s)`
   - Restart both services after changes

## 🤝 Contributing

This monitoring stack is designed for production use and open source distribution. When contributing:
- Follow existing code patterns and conventions
- Test changes with representative Commander loads
- Update documentation for new features or configuration changes
- Ensure compatibility across different deployment environments
