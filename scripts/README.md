# POSProctor Scripts

Utility scripts for POSProctor administration and maintenance.

## Scripts

### start-vector.bat
Starts Vector syslog collector natively on Windows. Required because Docker Desktop NATs UDP packets, which breaks source IP enrichment.

**Usage:**
```cmd
# Run as Administrator (required for port 514)
scripts\start-vector.bat
```

### generate_commanders_csv.bat / .sh
Exports the commanders table from SQLite to CSV for Vector enrichment lookup.

**Usage:**
```cmd
# Windows
scripts\generate_commanders_csv.bat

# Linux/Mac
./scripts/generate_commanders_csv.sh
```

### commander_analyze.py
Standalone tool for one-off analysis of a Verifone Commander. Queries diagnostics and tank data.

**Setup:**
```cmd
pip install -r scripts\requirements.txt
```

**Usage:**
```cmd
python scripts\commander_analyze.py --ip 10.0.0.1 -u posproctor -p secret
python scripts\commander_analyze.py --ip 10.0.0.1 -u posproctor -p secret --json
python scripts\commander_analyze.py --ip 10.0.0.1 -u posproctor -p secret --raw
```

## Requirements

For Python scripts:
```cmd
pip install -r scripts\requirements.txt
```
