# Vector Native Windows Setup

On Windows Docker Desktop, UDP syslog packets lose their source IP due to NAT translation. All packets appear to come from the Docker gateway IP (e.g., `192.168.1.1`), which breaks the CSV enrichment lookup that maps source IPs to store names.

The solution is to run Vector natively on Windows, outside of Docker.

## Installation

### 1. Download Vector for Windows

Download the latest Vector release for Windows from:
https://vector.dev/releases/

Or use PowerShell:

```powershell
# Download Vector (adjust version as needed)
Invoke-WebRequest -Uri "https://packages.timber.io/vector/0.39.0/vector-0.39.0-x86_64-pc-windows-msvc.zip" -OutFile "vector.zip"

# Extract to Program Files
Expand-Archive -Path "vector.zip" -DestinationPath "C:\Program Files\Vector"
```

### 2. Add Vector to PATH

```powershell
# Add to system PATH (run as Administrator)
$env:Path += ";C:\Program Files\Vector\bin"
[Environment]::SetEnvironmentVariable("Path", $env:Path, [EnvironmentVariableTarget]::Machine)
```

### 3. Open Firewall for Syslog

```powershell
# Allow UDP 514 for syslog (run as Administrator)
New-NetFirewallRule -DisplayName "Vector Syslog UDP" -Direction Inbound -Protocol UDP -LocalPort 514 -Action Allow
```

### 4. Test Vector

```powershell
# Test with the Windows config
cd C:\path\to\posproctor
vector --config config\vector-windows.yaml
```

You should see JSON output in the console when syslog messages arrive. Verify that `nat_ip` shows the actual commander IPs (172.x.x.x) and `pos_name` shows the store names.

## Running as a Windows Service

### Using NSSM (Non-Sucking Service Manager)

1. Download NSSM from https://nssm.cc/download

2. Install Vector as a service:

```powershell
# Install service
nssm install Vector "C:\Program Files\Vector\bin\vector.exe" "--config C:\path\to\posproctor\config\vector-windows.yaml"

# Set working directory
nssm set Vector AppDirectory "C:\path\to\posproctor"

# Set to auto-start
nssm set Vector Start SERVICE_AUTO_START

# Start the service
nssm start Vector
```

### Managing the Service

```powershell
# Check status
nssm status Vector

# Stop service
nssm stop Vector

# Start service
nssm start Vector

# Remove service
nssm remove Vector confirm
```

## Configuration

The Windows configuration file is at:
```
config\vector-windows.yaml
```

Key differences from the Docker configuration:
- Uses Windows file paths for the CSV enrichment table
- Connects to Loki at `localhost:3100` (exposed from Docker)

### Updating the CSV Path

If your POSProctor installation is in a different location, update the path in `vector-windows.yaml`:

```yaml
enrichment_tables:
  store_mapping:
    type: file
    file:
      path: "C:\\path\\to\\your\\PosProctor\\data\\database\\commanders.csv"
```

## Verifying Enrichment

1. Check Vector console output for incoming logs
2. Verify `nat_ip` shows actual commander IPs (not 192.168.1.1)
3. Verify `pos_name` shows store names (not "unknown")

Example good output:
```json
{
  "nat_ip": "10.0.0.1",
  "pos_name": "Store 001",
  "message": "WARN security - USER: posproctor - validate..."
}
```

## Troubleshooting

### Logs showing "unknown" for pos_name

1. Check that the CSV file exists and is readable:
   ```powershell
   Get-Content "C:\path\to\posproctor\data\database\commanders.csv"
   ```

2. Verify the source IP in logs matches an IP in the CSV

3. Check Vector logs for enrichment table errors:
   ```powershell
   vector --config config\vector-windows.yaml 2>&1 | Select-String "error"
   ```

### Vector can't connect to Loki

1. Ensure Docker stack is running:
   ```powershell
   docker compose ps
   ```

2. Verify Loki port is exposed:
   ```powershell
   netstat -an | findstr 3100
   ```

3. Test Loki connectivity:
   ```powershell
   curl http://localhost:3100/ready
   ```

### Syslog not arriving

1. Check Windows Firewall allows UDP 514:
   ```powershell
   Get-NetFirewallRule -DisplayName "*Syslog*"
   ```

2. Verify commanders are configured to send syslog to this host's IP

3. Test with netcat or similar:
   ```powershell
   # In another terminal, send a test syslog message
   echo "<14>Test message" | ncat -u localhost 514
   ```

## Docker Compose Changes

The docker-compose.yml has been updated:
- Vector container is commented out (for Windows)
- Loki port 3100 is exposed for native Vector access

To revert to Docker-based Vector (for Linux hosts), uncomment the Vector service in docker-compose.yml and change Loki back to `expose` instead of `ports`.
