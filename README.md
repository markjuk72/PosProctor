# POSProctor 2.0

A comprehensive monitoring, transaction analysis, and tank management platform for Verifone Commander POS systems.

## Overview

POSProctor 2.0 is a complete observability stack for gas station/convenience store POS systems, featuring:

- **Real-time monitoring** of Verifone Commander systems
- **Transaction log (TLOG) management** with parsing and analysis
- **Tank monitoring** with inventory, delivery tracking, and alarm history
- **Unified web interface** for configuration and viewing
- **Grafana dashboards** for visualization and alerting
- **Password management** via Bitwarden integration
- **Optional Microsoft Entra ID authentication**

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Access to Verifone Commander device(s)
- Commander credentials (username/password)

### Installation

```bash
# 1. Clone the repository
cd posproctor

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Start all services
docker-compose up -d

# 4. Access the web interface
# Open browser to https://localhost
```

Default services will be available at:

| Service | URL | Description |
|---------|-----|-------------|
| **Web UI** | https://localhost | Main interface |
| **Grafana** | https://localhost:3000 | Dashboards |
| **Prometheus** | https://localhost:9090 | Metrics |

### Initial Configuration

1. Access the Web UI at https://localhost
2. Navigate to **Commanders** and add your devices
3. Navigate to **Passwords** to configure credentials via Bitwarden
4. Navigate to **Configuration** to adjust settings
5. View metrics in **Grafana** at https://localhost:3000

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                       nginx (443)                        │
│            Reverse Proxy with SSL/TLS                    │
└─────────────┬────────────────────────────────────────────┘
              │
    ┌─────────┴─────────┬──────────────┬─────────────┐
    │                   │              │             │
┌───▼────────┐  ┌──────▼──────┐  ┌───▼──────┐  ┌──▼───────┐
│  Web App   │  │ Monitoring  │  │   TLOG   │  │ Grafana  │
│  (Flask)   │  │   Service   │  │ Service  │  │  (3000)  │
│            │  │   (8000)    │  │  (8001)  │  │          │
└─────┬──────┘  └──────┬──────┘  └────┬─────┘  └────┬─────┘
      │                │              │             │
      └────────────────┴──────┬───────┴─────────────┘
                              │
                    ┌─────────▼──────────┐
                    │   SQLite Database  │
                    │  (posproctor.db)   │
                    └────────────────────┘

┌────────────────┐   ┌──────────────┐
│  Prometheus    │   │     Loki     │
│  Metrics DB    │   │  Log Storage │
│  (Port 9090)   │   │  (Port 3100) │
└────────────────┘   └──────────────┘
```

## Features

### Monitoring Service
- Multi-threaded polling of Verifone Commander devices
- Real-time status monitoring (controllers, pumps, DCRs, displays, payment processors)
- Prometheus metrics export
- Health checks and availability tracking
- Configurable polling intervals

### Transaction Log (TLOG) Service
- Download and parse transaction logs (shift and day reports)
- Historical data access (90-day retention)
- CSV export capabilities
- Advanced filtering (transaction type, payment method, amount, etc.)

### Tank Monitoring
- Real-time tank inventory with volume, temperature, and water levels
- Delivery history tracking
- Alarm history and active alert status
- Tank reconciliation reporting
- Support for Veeder-Root tank level sensors

### Web Interface
- Commander configuration management
- Password management with Bitwarden integration
- TLOG viewer with real-time filtering
- Tank analysis reports
- System configuration and settings
- **Configuration export/import** for easy deployment to new hosts
- Responsive Bootstrap UI

### Observability Stack
- **Grafana dashboards** - Pre-configured POSProctor monitoring dashboards
- **Prometheus** - Metrics storage and querying
- **Loki** - Log aggregation from POS systems
- **Vector** - Syslog collection and routing
### Password Management
- Centralized credential storage in Bitwarden
- Multiple user account management
- Dry-run testing before password changes
- Bulk password rotation across all commanders
- Automatic Bitwarden vault updates

### Authentication
- **None** (default) - All routes publicly accessible
- **Microsoft Entra ID** - Azure AD SSO with partial authentication model
  - Public routes: Dashboard, Transactions, Tank Reports
  - Protected routes: Commanders, Passwords, Configuration

## Documentation

Detailed documentation is available in the `docs/` directory:

- **[docs/AUTHENTICATION.md](docs/AUTHENTICATION.md)** - Authentication setup and Entra ID configuration
- **[docs/GRAFANA.md](docs/GRAFANA.md)** - Grafana dashboards and alerting
- **[docs/DEVELOPERS.md](docs/DEVELOPERS.md)** - Development guide and API reference
- **[docs/URL_Reference.md](docs/URL_Reference.md)** - Verifone Commander API reference

## Configuration

### Environment Variables

Key configuration is managed via the `.env` file and the webapp Configuration page:

- **Timeout** - Commander API request timeout (default: 30 seconds)
- **Max Workers** - Concurrent polling threads (default: 10)
- **Authentication** - AUTH_TYPE (none or entra)

### Adding Commanders

Via Web UI:
1. Navigate to **Commanders** page
2. Click **Add Commander**
3. Enter IP address, store name, group, and brand
4. Click **Add**
5. Enable/disable as needed

### Configuration Export/Import

To migrate configuration to a new POSProctor instance:

1. On source host: Navigate to **Configuration** > **Export Configuration**
2. Download the JSON file (contains settings and commanders, excludes secrets)
3. On target host: Navigate to **Configuration** > **Import Configuration**
4. Upload the JSON file
5. Configure credentials separately (Bitwarden or environment variables)

### Managing Passwords

Via Passwords page:
1. Navigate to **Passwords** page
2. Select user account
3. Click **Dry Run Test** to verify current password works
4. Generate or enter new password
5. Click **Change Password** to update all commanders and Bitwarden

## Troubleshooting

### Check Service Status

```bash
docker-compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f webapp
docker-compose logs -f monitoring
docker-compose logs -f tlog
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart webapp
```

### Database Access

```bash
docker exec -it posproctor-webapp sqlite3 /app/data/database/posproctor.db
```

## Development

See **[docs/DEVELOPERS.md](docs/DEVELOPERS.md)** for:
- Development environment setup
- API documentation
- Database schema
- Adding new features

## Project Structure

```
posproctor/
├── config/                 # Configuration files
│   ├── nginx.conf          # Nginx reverse proxy config
│   ├── prometheus.yml      # Prometheus scrape config
│   ├── loki.yaml           # Loki log aggregation config
│   ├── schema.sql          # Database schema
│   └── vector.yaml         # Vector syslog config
├── grafana/                # Grafana provisioning
│   └── provisioning/       # Dashboards and datasources
├── monitoring/             # Monitoring service
│   ├── Dockerfile
│   └── main.py             # Main monitoring loop
├── tlog/                   # TLOG service
│   ├── Dockerfile
│   └── main.py             # Main TLOG service
├── webapp/                 # Web UI
│   ├── Dockerfile
│   ├── app.py              # Flask application
│   ├── auth.py             # Authentication module
│   ├── templates/          # HTML templates
│   ├── static/             # CSS, JS, images
│   └── lib/                # Shared libraries
├── bitwarden-serve/        # Bitwarden password vault
│   └── Dockerfile
├── data/                   # Persistent data (gitignored)
│   ├── database/           # SQLite database
│   ├── tlogs/              # Transaction log files
│   └── xml_debug/          # XML debug logs
├── docs/                   # Documentation
│   ├── AUTHENTICATION.md   # Auth setup guide
│   ├── GRAFANA.md          # Grafana guide
│   ├── DEVELOPERS.md       # Developer guide
│   └── URL_Reference.md    # Commander API reference
├── docker-compose.yml      # Service orchestration
├── .env.example            # Environment template
└── README.md               # This file
```

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions:
- Check the documentation in `docs/`
- Review service-specific READMEs
- See `docs/DEVELOPERS.md` for development guidance
