# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is POSProctor - a containerized monitoring stack for POS systems. The architecture consists of a custom Python application (`posproctor-app`) that polls Commander APIs for diagnostic data, exposing metrics to Prometheus for storage and visualization in Grafana. The stack also includes Vector for log collection/enrichment and Loki for centralized log storage.

## Architecture

- **Python Application** (`app/`): Multi-threaded poller that fetches diagnostic data from POS systems via API calls and exposes Prometheus metrics on port 8000
- **Docker Compose Stack**: Orchestrates Prometheus (metrics), Grafana (visualization), Vector (log processing), and Loki (log storage)
- **Configuration**: POS system targets defined in `commanders.csv` with IP, store name, group, and enabled status
- **Dashboards**: Pre-configured Grafana dashboard for scalable monitoring using template variables

## Key Development Commands

### Running the Stack
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f posproctor-app

# Stop services
docker-compose down
```

### Container Management
```bash
# IMPORTANT: Always rebuild with --no-cache when code changes are made
docker-compose build --no-cache posproctor-app
docker-compose up -d

# Full stack rebuild (when significant changes are made)
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Python Application Development
```bash
# Install dependencies (for local development)
cd app && pip install -r requirements.txt

# Run application locally (requires config files)
python app/main.py
```

### Accessing Services
- Grafana: http://localhost:3000 (admin/IdahoFalls123)
- Prometheus: http://localhost:9090
- Metrics endpoint: http://localhost:8000/metrics

## Configuration Files

- `commanders.csv`: Target systems (IP, store, group, enabled status)
- `credentials.yaml`: API authentication for POS systems
- `config.yaml`: Application settings (timeout, scrape interval)
- `prometheus.yml`: Prometheus scrape configuration
- `config_vector.yaml`: Vector log processing pipeline
- `config_loki.yaml`: Loki log storage configuration
- `grafana-provisioning/`: Grafana datasources and dashboard definitions

## Code Structure

- `app/main.py`: Main application loop with Prometheus metrics collection
- `app/verifone_api.py`: API client for POS system integration
- `app/config.py`: Configuration management and environment variables
- `app/requirements.txt`: Python dependencies
- `docker-compose.yml`: Service orchestration and networking

## Important Notes

- The Python application uses multi-threading for parallel POS system polling
- Metrics are exposed using the `prometheus_client` library
- Vector enriches logs by mapping IP addresses to store names using `commanders.csv`
- The Grafana dashboard uses template variables for scalable monitoring across groups
- All services run in Docker containers with persistent data volumes
- **CRITICAL**: Always use `--no-cache` when rebuilding containers after code changes to ensure new code is included