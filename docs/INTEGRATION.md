# Packing Tool - Integration Guide

## Table of Contents
1. [Overview](#overview)
2. [System Integration](#system-integration)
3. [Data Flow Workflow](#data-flow-workflow)
4. [File Formats](#file-formats)
5. [Integration Examples](#integration-examples)
6. [API Integration](#api-integration)
7. [Troubleshooting](#troubleshooting)

## Overview

The Packing Tool is designed to integrate seamlessly with the Shopify Export Tool, creating a unified fulfillment workflow from order export to packing completion. Both tools share:

- **Client Profiles**: Centralized configuration on file server
- **SKU Mappings**: Shared barcode-to-SKU translation tables
- **Statistics**: Unified tracking across both systems
- **Excel Format**: Compatible packing list structure

This document describes how the two systems work together and how to integrate them in your warehouse workflow.

## System Integration

### Architecture Overview

```
┌──────────────────────┐
│  Shopify Store       │
│  (Online Orders)     │
└──────────┬───────────┘
           │
           ▼ (API)
┌──────────────────────┐
│  Shopify Export Tool │
│  • Fetch orders      │
│  • Filter by status  │
│  • Export to Excel   │
│  • Generate metadata │
└──────────┬───────────┘
           │
           ▼ (Excel + JSON)
┌──────────────────────┐
│  File Server         │
│  \\Server\Share      │
│  • Client profiles   │
│  • Session data      │
│  • Statistics        │
└──────────┬───────────┘
           │
           ▼ (Load Excel)
┌──────────────────────┐
│  Packing Tool        │
│  • Generate barcodes │
│  • Track packing     │
│  • Complete orders   │
│  • Record stats      │
└──────────────────────┘
```

### Integration Points

#### 1. Client Profiles
Both tools read/write to the same client profile directory:
- Location: `\\Server\Share\Clients\CLIENT_{ID}/`
- File: `packer_config.json` (unified configuration)
- Contains: Client settings, SKU mappings, courier deadlines

#### 2. Excel Format
Standard column structure used by both tools:
- `Order_Number`: Unique order identifier
- `SKU`: Product SKU code
- `Product_Name`: Product description
- `Quantity`: Number of items
- `Courier`: Delivery service name

#### 3. Statistics
Shared global statistics file:
- Location: `\\Server\Share\Stats\stats.json`
- Tracks: Sessions, orders, items packed
- Enables: Cross-system performance analytics

## Data Flow Workflow

### End-to-End Process

```
Step 1: Export from Shopify
─────────────────────────────
Shopify Export Tool:
├─ User selects client
├─ User selects date range
├─ Tool fetches orders from Shopify API
├─ Tool filters by fulfillment status
├─ Tool generates Excel file
│  └─ packing_list_20251103_143045.xlsx
└─ Tool generates metadata (optional)
   └─ analysis_data.json

       ↓

Step 2: Store on File Server
─────────────────────────────
User saves files to:
├─ \\Server\Share\Sessions\CLIENT_M\
│  └─ (or any accessible location)

       ↓

Step 3: Import to Packing Tool
─────────────────────────────
Packing Tool:
├─ User selects client profile
├─ User clicks "Start Session"
├─ User browses to Excel file
├─ Tool validates columns
├─ Tool generates barcodes
│  └─ Creates session directory
│  └─ Generates ORDER-XXX.png files
└─ Tool displays order list

       ↓

Step 4: Packing Process
─────────────────────────────
Worker with barcode scanner:
├─ Scans order barcode → loads order items
├─ Scans SKU barcodes → marks items as packed
├─ Order complete → moves to next order
└─ Repeats until all orders packed

       ↓

Step 5: Session Completion
─────────────────────────────
Packing Tool:
├─ User clicks "End Session"
├─ Tool generates completion report
│  └─ packing_list_completed.xlsx
│  └─ session_summary.json
├─ Tool updates global stats
│  └─ Increments completed orders
│  └─ Records session metrics
└─ Tool releases session lock

       ↓

Step 6: Post-Processing (Future)
─────────────────────────────
Potential integrations:
├─ Upload completion data to Shopify
├─ Send notifications to clients
├─ Update inventory systems
└─ Generate shipping labels
```

### Typical Workflow Scenarios

#### Scenario A: Daily Order Processing
```
Morning:
1. Manager exports today's orders using Shopify Tool
2. Excel file saved to file server
3. Warehouse worker opens Packing Tool
4. Worker imports Excel, starts packing
5. Worker completes session, generates report

Afternoon:
6. Manager reviews completed session
7. Manager marks orders as fulfilled in Shopify
8. Customer receives tracking information
```

#### Scenario B: Multi-Client Processing
```
1. Manager exports orders for Client M
2. Manager exports orders for Client R
3. Worker A packs Client M orders on PC-1
4. Worker B packs Client R orders on PC-2 (simultaneously)
5. Both sessions tracked independently
6. Statistics aggregated for both clients
```

#### Scenario C: Crash Recovery
```
1. Worker starts packing session
2. PC crashes unexpectedly
3. Worker moves to PC-2
4. Worker opens Packing Tool
5. Tool detects incomplete session
6. Worker restores session, continues packing
7. No data lost, no duplicate work
```

## File Formats

### 1. Excel Packing List Format

**Filename Pattern**: `packing_list_YYYYMMDD_HHMMSS.xlsx`

**Required Columns**:
```
Order_Number | SKU        | Product_Name           | Quantity | Courier
─────────────┼────────────┼────────────────────────┼──────────┼─────────
ORDER-12345  | SKU-001    | Blue T-Shirt           | 2        | DHL
ORDER-12345  | SKU-002    | Red Jeans              | 1        | DHL
ORDER-12346  | SKU-003    | Green Shoes            | 1        | Speedy
ORDER-12347  | SKU-001    | Blue T-Shirt           | 3        | PostOne
```

**Excel Structure**:
- **Sheet Name**: Any (typically "Packing List" or "Orders")
- **Header Row**: Row 1 (must contain column names)
- **Data Rows**: Row 2 onwards
- **Encoding**: UTF-8 with BOM (for Excel compatibility)
- **Format**: .xlsx (Excel 2007+)

**Optional Columns** (ignored by Packing Tool):
- `Order_Date`
- `Customer_Name`
- `Shipping_Address`
- `Order_Total`
- `Notes`

**Column Mapping**:
If Excel file uses different column names, Packing Tool will prompt for mapping:
```
Required      →  Your File
─────────────────────────────────
Order_Number  →  OrderID
SKU           →  ProductCode
Product_Name  →  Description
Quantity      →  Qty
Courier       →  ShippingMethod
```

### 2. analysis_data.json (Optional)

Generated by Shopify Export Tool as metadata companion to Excel file.

**Location**: Same directory as Excel file
**Filename**: `analysis_data.json`

**Structure**:
```json
{
  "export_info": {
    "client_id": "M",
    "client_name": "M Cosmetics",
    "export_date": "2025-11-03T14:30:45",
    "exported_by": "manager@company.com",
    "date_range": {
      "start": "2025-11-01",
      "end": "2025-11-03"
    }
  },
  "summary": {
    "total_orders": 150,
    "total_items": 567,
    "unique_skus": 42,
    "couriers": ["DHL", "Speedy", "PostOne"]
  },
  "courier_breakdown": {
    "DHL": {
      "orders": 75,
      "items": 289,
      "deadline": "17:00"
    },
    "Speedy": {
      "orders": 50,
      "items": 198,
      "deadline": "16:00"
    },
    "PostOne": {
      "orders": 25,
      "items": 80,
      "deadline": "15:00"
    }
  },
  "top_products": [
    {
      "sku": "SKU-001",
      "name": "Blue T-Shirt",
      "quantity": 125,
      "orders": 78
    }
  ]
}
```

**Usage**:
- Packing Tool can optionally read this for enhanced UI
- Displays courier deadlines
- Shows expected workload
- Not required for basic functionality

### 3. session_info.json

Created by Packing Tool at session start, deleted on completion.

**Location**: `\\Server\Share\Sessions\CLIENT_{ID}\{SESSION_ID}\session_info.json`

**Structure**:
```json
{
  "client_id": "M",
  "packing_list_path": "C:\\Users\\Worker\\Downloads\\packing_list_20251103_143045.xlsx",
  "started_at": "2025-11-03T14:30:45",
  "pc_name": "PC-WAREHOUSE-1"
}
```

**Purpose**:
- Identifies incomplete sessions (crash recovery)
- Stores original Excel path for restoration
- Records which PC started the session

**Lifecycle**:
- Created: On session start
- Read: For session restoration
- Deleted: On graceful session end
- Present: Indicates incomplete session

### 4. packing_state.json

Tracks packing progress in real-time.

**Location**: `\\Server\Share\Sessions\CLIENT_{ID}\{SESSION_ID}\barcodes\packing_state.json`

**Structure**:
```json
{
  "version": "1.0",
  "timestamp": "2025-11-03T15:35:12",
  "client_id": "M",
  "data": {
    "in_progress": {
      "ORDER-12345": {
        "SKU-001": {
          "required": 2,
          "packed": 2,
          "normalized_sku": "sku-001"
        },
        "SKU-002": {
          "required": 1,
          "packed": 0,
          "normalized_sku": "sku-002"
        }
      },
      "ORDER-12346": {
        "SKU-003": {
          "required": 1,
          "packed": 1,
          "normalized_sku": "sku-003"
        }
      }
    },
    "completed_orders": [
      "ORDER-12346"
    ]
  }
}
```

**Purpose**:
- Saves progress after each scan
- Enables crash recovery
- Supports multi-PC session handoff (if lock released)

**Update Frequency**: After every successful SKU scan

### 5. session_summary.json

Generated at session end, permanent record.

**Location**: `\\Server\Share\Sessions\CLIENT_{ID}\{SESSION_ID}\output\session_summary.json`

**Structure**:
```json
{
  "version": "1.0",
  "session_id": "2025-11-03_14-30",
  "client_id": "M",
  "started_at": "2025-11-03T14:30:45",
  "completed_at": "2025-11-03T16:15:30",
  "duration_seconds": 6285,
  "duration_formatted": "1h 44m 45s",
  "packing_list_path": "C:\\Users\\Worker\\Downloads\\packing_list_20251103_143045.xlsx",
  "completed_file_path": "\\\\Server\\Share\\Sessions\\CLIENT_M\\2025-11-03_14-30\\output\\packing_list_completed.xlsx",
  "pc_name": "PC-WAREHOUSE-1",
  "user_name": "john.smith",
  "statistics": {
    "total_orders": 150,
    "completed_orders": 148,
    "in_progress_orders": 2,
    "total_items": 567,
    "items_packed": 560,
    "completion_rate": 98.67,
    "items_per_minute": 5.35,
    "orders_per_hour": 84.2
  }
}
```

**Purpose**:
- Permanent record of session
- Analytics and reporting
- Performance tracking
- Audit trail

### 6. stats.json (Global)

Centralized statistics across all clients and sessions.

**Location**: `\\Server\Share\Stats\stats.json`

**Structure**:
```json
{
  "version": "1.1",
  "processed_order_ids": [
    "ORDER-12345",
    "ORDER-12346",
    "..."
  ],
  "completed_order_ids": [
    "ORDER-12345",
    "..."
  ],
  "client_stats": {
    "M": {
      "total_sessions": 45,
      "total_orders": 6750,
      "total_items": 25530,
      "total_duration_seconds": 162000,
      "last_session_time": "2025-11-03T16:15:30"
    },
    "R": {
      "total_sessions": 32,
      "total_orders": 4800,
      "total_items": 18240,
      "total_duration_seconds": 115200,
      "last_session_time": "2025-11-02T15:30:20"
    }
  },
  "session_history": [
    {
      "session_id": "2025-11-03_14-30",
      "client_id": "M",
      "start_time": "2025-11-03T14:30:45",
      "end_time": "2025-11-03T16:15:30",
      "duration_seconds": 6285,
      "orders_completed": 148,
      "items_packed": 560
    }
  ]
}
```

**Purpose**:
- Track unique orders (prevent double-counting)
- Aggregate performance across all clients
- Dashboard analytics
- Historical trending

## Integration Examples

### Example 1: Basic Daily Workflow

**Morning Setup**:
```bash
# Manager runs Shopify Export Tool
1. Select Client: M Cosmetics
2. Date Range: Today
3. Export → packing_list_20251103_080000.xlsx

# Save to network share
Copy to: \\Server\Share\Sessions\CLIENT_M\
```

**Warehouse Floor**:
```bash
# Worker opens Packing Tool
1. Select Client: M
2. Click "Start Session"
3. Browse to: \\Server\Share\Sessions\CLIENT_M\packing_list_20251103_080000.xlsx
4. Tool generates barcodes
5. Tool shows 150 orders

# Worker packs orders
Loop:
  - Scan order barcode (displays items)
  - Scan each SKU barcode (marks packed)
  - Order complete → next order

# End of day
6. Click "End Session"
7. Tool generates: packing_list_completed.xlsx
8. Tool updates statistics
```

### Example 2: Multi-Client Parallel Processing

**PC-1** (Worker A):
```bash
# Morning shift - Client M
1. Open Packing Tool
2. Select Client: M
3. Import packing_list_M_20251103.xlsx
4. Pack 75 orders
5. End session at lunch

# Afternoon shift - Client R
6. Select Client: R
7. Import packing_list_R_20251103.xlsx
8. Pack 50 orders
9. End session
```

**PC-2** (Worker B) - Same Time:
```bash
# Morning shift - Client A
1. Open Packing Tool
2. Select Client: A
3. Import packing_list_A_20251103.xlsx
4. Pack 100 orders
5. End session

# Afternoon shift - Client M
6. Select Client: M (different orders than Worker A)
7. Import packing_list_M_afternoon_20251103.xlsx
8. Pack 80 orders
9. End session
```

**Result**: 4 independent sessions, all tracked separately, statistics aggregated correctly.

### Example 3: Crash Recovery

**Scenario**: PC crashes mid-session

```bash
# Session before crash
PC-1, 10:00 AM:
1. Worker starts session for Client M
2. Packs 75/150 orders
3. PC freezes, worker force-restarts
4. Session lock becomes stale after 2 minutes

# Recovery on different PC
PC-2, 10:15 AM:
1. Worker opens Packing Tool
2. Selects Client: M
3. Tool shows: "Incomplete session found: 2025-11-03_10-00"
4. Worker clicks "Restore Session"
5. Tool detects stale lock (PC-1 not responding)
6. Tool asks: "Session locked by PC-1. Force release? (Stale for 10 minutes)"
7. Worker clicks "Yes, Take Over"
8. Tool loads session with 75/150 orders completed
9. Worker continues from order 76
10. Worker completes remaining 75 orders
11. Worker ends session normally
12. No data lost, no duplicate work
```

### Example 4: SKU Mapping Integration

**Problem**: Product barcodes don't match SKUs in packing list

**Solution**: Use centralized SKU mapping

```bash
# Setup (one-time per client)
1. Open Packing Tool
2. Select Client: M
3. Click "Tools" → "SKU Mapping"
4. Add mappings:
   Product Barcode    →  Internal SKU
   ─────────────────────────────────
   8594123456789     →  SKU-001
   8594123456796     →  SKU-002

5. Click "Save"
6. Mapping stored in: \\Server\Share\Clients\CLIENT_M\packer_config.json

# Daily use
Worker scans product barcode: 8594123456789
↓
Tool looks up in SKU mapping
↓
Tool translates to: SKU-001
↓
Tool finds item in current order
↓
Tool marks item as packed
```

**Benefit**: Same mapping used by all PCs, all workers, all sessions.

## API Integration

### Python Integration Example

```python
from pathlib import Path
from profile_manager import ProfileManager
from session_manager import SessionManager
from session_lock_manager import SessionLockManager

# Initialize managers
profile_mgr = ProfileManager("config.ini")
lock_mgr = SessionLockManager(profile_mgr)
session_mgr = SessionManager("M", profile_mgr, lock_mgr)

# Start new session
excel_path = "C:\\path\\to\\packing_list.xlsx"
session_id = session_mgr.start_session(excel_path)

print(f"Session started: {session_id}")
print(f"Barcodes directory: {session_mgr.get_barcodes_dir()}")

# ... packing logic ...

# End session
session_mgr.end_session()
print("Session completed")
```

### Reading Session Data Programmatically

```python
import json
from pathlib import Path

# Read session summary
summary_path = Path(
    "\\\\Server\\Share\\Sessions\\CLIENT_M"
    "\\2025-11-03_14-30\\output\\session_summary.json"
)

with open(summary_path) as f:
    summary = json.load(f)

print(f"Orders completed: {summary['statistics']['completed_orders']}")
print(f"Duration: {summary['duration_formatted']}")
print(f"Items/minute: {summary['statistics']['items_per_minute']}")
```

### Global Statistics Access

```python
from statistics_manager import StatisticsManager

stats_mgr = StatisticsManager(profile_mgr)

# Get client performance
client_stats = stats_mgr.get_client_stats("M")
print(f"Total sessions: {client_stats['total_sessions']}")
print(f"Average orders/session: {client_stats['average_orders_per_session']}")

# Get recent performance
metrics = stats_mgr.get_performance_metrics(client_id="M", days=30)
print(f"Orders/hour (last 30 days): {metrics['orders_per_hour']}")
print(f"Items/hour (last 30 days): {metrics['items_per_hour']}")
```

## Troubleshooting

### Issue 1: "File Server Not Accessible"

**Symptoms**:
- Packing Tool shows error on startup
- Cannot load client profiles
- Network path timeout

**Solutions**:
```bash
1. Check network connection:
   - Ping file server: ping 192.168.88.101
   - Access via Windows Explorer: \\192.168.88.101\Share

2. Verify config.ini:
   [Network]
   FileServerPath = \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment
   ConnectionTimeout = 5

3. Check permissions:
   - Ensure user has read/write access to share
   - Test: Create test.txt in \\Server\Share\Clients\

4. Check firewall:
   - Ensure SMB/CIFS ports open (445, 139)
   - Temporarily disable firewall to test
```

### Issue 2: "Session Locked by Another Process"

**Symptoms**:
- Cannot start session
- Shows "Locked by PC-X"
- Heartbeat detected as active

**Solutions**:
```bash
1. Check if other PC actually using session:
   - Go to PC-X mentioned in error
   - Check if Packing Tool is running
   - Ask worker if they're using that session

2. If session truly abandoned:
   - Wait 2-3 minutes for lock to become stale
   - Packing Tool will offer "Force Release" option
   - Click "Force Release" to take over

3. If lock won't release:
   - Manually delete: \\Server\Share\Sessions\CLIENT_M\{SESSION}\.session.lock
   - Only do this if certain no other PC is using it!
```

### Issue 3: "SKU Not Found in Current Order"

**Symptoms**:
- Worker scans SKU barcode
- Error: "SKU not found in current order"
- SKU is correct according to product

**Solutions**:
```bash
1. Check if SKU mapping needed:
   - Product barcode might differ from internal SKU
   - Open Tools → SKU Mapping
   - Add mapping: ProductBarcode → InternalSKU

2. Check normalization:
   - SKUs normalized to lowercase, spaces removed
   - "SKU-001" becomes "sku-001"
   - " SKU 001 " becomes "sku001"
   - Ensure Excel file matches this format

3. Check if wrong order loaded:
   - Verify order barcode scanned correctly
   - Check displayed order number matches physical order
   - Scan order barcode again to reload
```

### Issue 4: "Column Mapping Dialog Appears Every Time"

**Symptoms**:
- Excel file imported
- Tool asks to map columns
- Happens every session even with same file

**Solutions**:
```bash
1. Standardize Excel column names:
   - Use exactly: Order_Number, SKU, Product_Name, Quantity, Courier
   - Case-sensitive!
   - No extra spaces

2. Create Excel template:
   - Save template with correct column names
   - Share with Shopify Tool operator
   - Ensure Shopify Tool exports with these names

3. Configure column mapping in packer_config.json:
   {
     "required_columns": {
       "order_number": "OrderID",      # Your custom column
       "sku": "ProductCode",            # Your custom column
       "product_name": "Description",   # Your custom column
       "quantity": "Qty",               # Your custom column
       "courier": "ShippingMethod"      # Your custom column
     }
   }
```

### Issue 5: Statistics Not Updating

**Symptoms**:
- Dashboard shows old data
- Session completed but stats unchanged
- Global stats.json not updating

**Solutions**:
```bash
1. Check file permissions:
   - Navigate to: \\Server\Share\Stats\stats.json
   - Right-click → Properties → Security
   - Ensure current user has "Modify" permission

2. Check for file locking:
   - Close all instances of Packing Tool on all PCs
   - Delete stats.json.lock if it exists
   - Restart Packing Tool

3. Manually trigger refresh:
   - Dashboard → Click "Refresh" button
   - Or restart Packing Tool (loads fresh stats)

4. Verify stats.json format:
   - Open stats.json in text editor
   - Check for JSON syntax errors
   - If corrupted, restore from backup or delete (will recreate)
```

### Issue 6: Barcodes Not Generating

**Symptoms**:
- Session starts
- No barcode images created
- Barcodes directory empty

**Solutions**:
```bash
1. Check Excel file format:
   - Must be .xlsx (not .xls or .csv)
   - Must have Order_Number column
   - Order numbers must not be empty

2. Check disk space:
   - Navigate to: \\Server\Share\Sessions\
   - Check available disk space
   - Need ~1MB per 100 orders for barcodes

3. Check python-barcode library:
   - Open command prompt
   - Run: python -c "import barcode; print(barcode.__version__)"
   - If error, reinstall: pip install python-barcode

4. Check logs:
   - Open: %USERPROFILE%\.packers_assistant\logs\
   - Check latest log file for barcode generation errors
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Authors**: Development Team
**Status**: Production
