# TLOG Service

The TLOG service downloads and parses Verifone Commander transaction logs, providing a REST API for accessing transaction data.

## Features

- **Transaction log downloads** from Verifone Commanders
- **XML parsing** with detailed transaction extraction
- **Storage management** for downloaded TLOGs
- **REST API** for programmatic access
- **Transaction summaries** with revenue and payment statistics
- **Period filtering** (shift vs day reports)

## Files

- `api.py` - Flask REST API server
- `verifone_client.py` - Commander API client for TLOG downloads
- `parser.py` - XML transaction parser
- `Dockerfile` - Container build configuration
- `requirements.txt` - Python dependencies

## API Endpoints

### Download Latest TLOG
```http
POST /api/tlog/latest
Content-Type: application/json

{
  "ip": "10.0.0.1",
  "period": 2,  // Optional: 1=shift, 2=day, null=all
  "include_journal": false  // Optional: Include journal events (default: false)
}
```

**Note:** Journal events are system events (not financially interesting) and are filtered out by default. Set `include_journal: true` for debugging purposes.

**Response:**
```json
{
  "success": true,
  "commander": {
    "ip": "10.0.0.1",
    "store_name": "Store 001",
    "group": "Group A",
    "brand": "BrandA"
  },
  "report": {
    "filename": "2025-12-30.123",
    "period": "2",
    "size": 125000,
    "saved_as": "STORE116_2025-12-30.xml"
  },
  "summary": {
    "total_transactions": 1247,
    "sale_count": 1150,
    "fuel_count": 789,
    "total_revenue": 18456.23,
    "transaction_types": {...},
    "payment_methods": {...}
  },
  "transactions": [...]
}
```

### Download TLOG by Date
```http
POST /api/tlog/date
Content-Type: application/json

{
  "ip": "10.0.0.1",
  "date": "2025-12-30",
  "period": 2,
  "include_journal": false  // Optional: Include journal events (default: false)
}
```

### List Available Reports
```http
POST /api/tlog/list
Content-Type: application/json

{
  "ip": "10.0.0.1",
  "period": 2
}
```

**Response:**
```json
{
  "success": true,
  "commander": {
    "ip": "10.0.0.1",
    "store_name": "Store 001"
  },
  "report_count": 15,
  "reports": [
    {
      "filename": "2025-12-30.123",
      "period": "2",
      "size": 125000
    }
  ]
}
```

### List Stored TLOGs
```http
GET /api/tlog/stored
```

**Response:**
```json
{
  "success": true,
  "count": 45,
  "files": [
    {
      "filename": "STORE116_2025-12-30.xml",
      "size": 125000,
      "modified": "2025-12-30T14:32:15"
    }
  ]
}
```

### Get Stored TLOG
```http
GET /api/tlog/stored/STORE116_2025-12-30.xml?include_journal=false
```

Returns parsed transactions from a stored TLOG file.

**Query Parameters:**
- `include_journal` - Include journal events (default: false)

### Health Check
```http
GET /health
```

## Journal Event Filtering

**By default, journal events are excluded** from parsed transactions because they are system events (e.g., "Cashier Login", "Shift Open", "Till Close") and not financially interesting.

**Why filter journal events?**
- They don't represent customer transactions
- They don't contribute to revenue calculations
- They inflate transaction counts unnecessarily
- They clutter analytics and reports

**When to include journal events:**
- Debugging system issues
- Auditing cashier/shift activity
- Analyzing operational patterns
- Troubleshooting POS behavior

**How to include journal events:**

Via API:
```json
{
  "ip": "10.0.0.1",
  "include_journal": true
}
```

Via query parameter:
```
GET /api/tlog/stored/STORE116_2025-12-30.xml?include_journal=true
```

The service will log how many journal events were filtered:
```
INFO: Filtered out 42 journal events (system events)
INFO: Parsed 1247 transactions from TLOG
```

## Transaction Fields Extracted

### Header Fields
- `date` - Transaction timestamp
- `store_number` - Store identifier
- `register_id` - Physical register ID
- `pos_number` - POS terminal number
- `cashier` - Cashier name
- `cashier_emp_num` - Employee number
- `unique_sn` - Unique sequence number
- `unique_id` - Unique transaction ID

### Transaction Details
- `trans_type` - Transaction type (sale, void, nosale, journal, etc.)
- `rollback` - Rollback flag
- `recalled` - Recalled transaction flag
- `fuel_prepay` - Fuel prepay flag
- `fuel_prepay_completion` - Prepay completion flag

### Financial Fields
- `total_with_tax` - Total including tax
- `total_no_tax` - Total before tax
- `total_tax` - Tax amount
- `currency_total` - Currency total
- `line_item_count` - Number of line items

### Payment Information
- `payment_method` - Payment method name
- `payment_mop` - Method of payment code
- `payment_amount` - Payment amount
- `card_type` - Card type (if card payment)
- `card_entry` - Card entry method

### Fuel Information
- `fuel_pump` - Pump number
- `fuel_grade` - Fuel grade
- `fuel_volume` - Gallons/liters dispensed
- `fuel_price` - Price per gallon/liter
- `fuel_total` - Total fuel amount

### Period Information
- `period_hour` - Hour period sequence
- `period_shift` - Shift period sequence
- `period_day` - Day period sequence
- `period_name` - Period name
- `opened_time` - Period start time
- `closed_time` - Period end time

## Transaction Summary

The API provides automatic transaction summaries including:

- **Total transactions** - Count of all transactions
- **Sale count** - Number of sale transactions
- **Fuel count** - Number of fuel transactions
- **Total revenue** - Sum of all sales
- **Transaction type breakdown** - Count by transaction type
- **Payment method breakdown** - Count by payment method
- **Period information** - Report period details

## Environment Variables

- `POSPROCTOR_DB_PATH` - Database path (default: `/app/data/database/posproctor.db`)
- `TLOG_STORAGE_PATH` - TLOG storage directory (default: `/app/data/tlogs`)
- `TLOG_TIMEOUT` - Download timeout in seconds (default: `300`)

## Storage

Downloaded TLOGs are stored in `/app/data/tlogs` with the naming convention:

```
STORE{store_number}_{date}.xml
```

Example: `STORE116_2025-12-30.xml`

## Integration with Monitoring Service

The TLOG service reads commander configurations and credentials from the same SQLite database used by the monitoring service, ensuring consistency across services.

## Building

```bash
docker build -t posproctor2-tlog .
```

## Running Standalone

```bash
docker run -d \
  -p 8001:8001 \
  -v ./data/database:/app/data/database:ro \
  -v ./data/tlogs:/app/data/tlogs \
  posproctor2-tlog
```

## Troubleshooting

### Check health status
```bash
curl http://localhost:8001/health
```

### Download latest TLOG
```bash
curl -X POST http://localhost:8001/api/tlog/latest \
  -H "Content-Type: application/json" \
  -d '{"ip": "10.0.0.1", "period": 2}'
```

### List stored TLOGs
```bash
curl http://localhost:8001/api/tlog/stored
```

### Common Issues

**No credentials configured**
- Check that the monitoring service has populated the credentials table
- Verify database path is correct

**Authentication failed**
- Verify commander IP is correct and reachable
- Check credentials in database are valid
- Review commander API access permissions

**No reports available**
- Commander may not have closed any periods yet
- Try different period filter (shift vs day)
- Check commander has transaction data

**Failed to parse report**
- Check XML file is valid and not corrupted
- Review logs for specific parsing errors
- Verify report was downloaded completely
