#!/bin/bash
# Generate commanders.csv from SQLite database for Vector enrichment
# This should be run whenever commanders are added/changed

DB_PATH="${1:-./data/database/posproctor.db}"
CSV_PATH="${2:-./data/database/commanders.csv}"

if [ ! -f "$DB_PATH" ]; then
    echo "Error: Database not found at $DB_PATH"
    exit 1
fi

# Export commanders to CSV with header (ip,store format for Vector enrichment)
echo "ip,store" > "$CSV_PATH"
sqlite3 -csv "$DB_PATH" "SELECT ip, store_name FROM commanders WHERE enabled = 1" >> "$CSV_PATH"

echo "Generated $CSV_PATH with $(( $(wc -l < "$CSV_PATH") - 1 )) commanders"
