@echo off
REM Start Vector for POSProctor syslog collection
REM Run this script as Administrator to bind to port 514

echo Starting Vector for POSProctor...
echo.
echo Press Ctrl+C to stop
echo.

"C:\Program Files\Vector\bin\Vector.exe" --config "%~dp0..\config\vector-windows.yaml"
