@echo off
REM Generate commanders.csv from SQLite database for Vector enrichment
REM This should be run whenever commanders are added/changed

setlocal

set DB_PATH=%~dp0..\data\database\posproctor.db
set CSV_PATH=%~dp0..\data\database\commanders.csv

if not exist "%DB_PATH%" (
    echo Error: Database not found at %DB_PATH%
    exit /b 1
)

echo Generating commanders.csv...
echo ip,store > "%CSV_PATH%"
sqlite3 -csv "%DB_PATH%" "SELECT ip, store_name FROM commanders WHERE enabled = 1" >> "%CSV_PATH%"

echo Generated %CSV_PATH%
