# POSProctor Monitoring Stack Overview

## Summary

This project provides a scalable, containerized solution for monitoring the real-time operational status of POS systems. It ensures high availability of critical services by collecting, visualizing, and alerting on key health metrics, including Fuel Price Sign status and "REWARDS 2 GO" Loyalty FEP connectivity.

## Architecture & Technology

The solution is a Docker Compose-based stack that orchestrates a data pipeline:

1.  **Data Collection (`posproctor-app`)**: A multi-threaded Python application polls POS system APIs in parallel for high performance and scalability.
2.  **Metrics Storage (`Prometheus`)**: A time-series database scrapes and stores the metrics exposed by the Python application.
3.  **Visualization (`Grafana`)**: A pre-configured dashboard provides rich, interactive visualizations of the collected data.

This architecture is designed for high performance and easy deployment, capable of scaling to monitor a large number of POS systems efficiently. Configuration is externalized via YAML files for easy management of credentials and target systems.
