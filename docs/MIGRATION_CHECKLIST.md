# Packing Tool - Migration Checklist

## Overview

This guide helps you migrate to the new centralized architecture with ProfileManager, improved session management, and unified client profiles. Follow this checklist to ensure a smooth transition from local storage to the centralized file server system.

**Migration Scope**:
- Old system: Local storage in `~/.packers_assistant/`
- New system: Centralized file server with `ProfileManager`
- Affected: Client profiles, SKU mappings, session data, statistics

**Expected Downtime**: 30-60 minutes for complete migration

## Pre-Migration Checklist

### 1. System Requirements

- [ ] **Python 3.8+** installed on all warehouse PCs
- [ ] **PySide6** (Qt6) library installed
- [ ] **Windows OS** (required for file locking features)
- [ ] **Network Access** to file server
- [ ] **Permissions** to read/write on file server share

**Verify Requirements**:
```bash
# Check Python version
python --version
# Should show: Python 3.8.0 or higher

# Check PySide6
python -c "import PySide6; print(PySide6.__version__)"
# Should show version without errors

# Check network access
ping 192.168.88.101
# Should receive replies

# Test file server access
# In Windows Explorer, navigate to:
\\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment
# Should be able to create/delete test files
```

### 2. Backup Current Data

**CRITICAL**: Always backup before migration!

- [ ] **Backup Local Configuration**:
  ```bash
  # Copy entire local config directory
  Source: C:\Users\{Username}\.packers_assistant\
  Destination: C:\Backup\packers_assistant_backup_{DATE}\
  ```

- [ ] **Backup Items**:
  - [ ] `stats.json` (statistics history)
  - [ ] `sku_map.json` (SKU mappings)
  - [ ] `config.ini` (application config)
  - [ ] `logs/` directory (for troubleshooting)

- [ ] **Verify Backup**:
  - [ ] Check backup directory exists
  - [ ] Verify all files copied correctly
  - [ ] Check file sizes match originals

### 3. Document Current Setup

- [ ] **List All Clients**:
  ```
  Client ID | Client Name      | # Sessions | Last Used
  ──────────┼──────────────────┼────────────┼───────────
  M         | M Cosmetics      | 45         | 2025-11-03
  R         | R Fashion        | 32         | 2025-11-02
  A         | A Electronics    | 28         | 2025-11-01
  ```

- [ ] **List Active Sessions**:
  - Check for any incomplete sessions
  - Note which PC each session is on
  - Document session IDs and order counts

- [ ] **Export Current Statistics**:
  ```bash
  # Copy stats.json to Excel for reference
  # Note total orders, completion rates, etc.
  ```

### 4. Network Preparation

- [ ] **Setup File Server Share**:
  ```
  Share Name: PackerAssistant (or similar)
  Path: \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment
  Permissions:
    - Read: All warehouse users
    - Write: All warehouse users
    - Full Control: IT Admin
  ```

- [ ] **Create Directory Structure**:
  ```bash
  \\Server\Share\
  ├── Clients\
  ├── Sessions\
  ├── Stats\
  └── Logs\
  ```

- [ ] **Test Network Speed**:
  ```bash
  # Copy large test file to/from server
  # Should complete in < 5 seconds for 10MB file
  # Minimum acceptable: 10 Mbps
  ```

- [ ] **Map Network Drive** (Optional but Recommended):
  ```bash
  # Map Z: drive to \\Server\Share
  # Ensures consistent path across all PCs
  net use Z: \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment /persistent:yes
  ```

## Migration Steps

### Step 1: Install New Version

- [ ] **Download Latest Release**:
  ```bash
  # From Git repository or release server
  File: PackingTool_v2.0.0_Setup.exe
  ```

- [ ] **Backup Old Version**:
  ```bash
  # Rename existing installation
  C:\Program Files\PackingTool\  →  C:\Program Files\PackingTool_OLD\
  ```

- [ ] **Install New Version**:
  ```bash
  # Run installer on first PC (test PC)
  # Use default installation path
  # Do NOT run application yet
  ```

- [ ] **Verify Installation**:
  - [ ] Check version: `PackingTool.exe --version`
  - [ ] Verify all DLLs present
  - [ ] Check shortcut created

### Step 2: Configure File Server Connection

- [ ] **Create/Update config.ini**:
  ```ini
  # File: C:\Program Files\PackingTool\config.ini

  [Network]
  FileServerPath = \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment
  ConnectionTimeout = 5
  LocalCachePath =

  [Logging]
  LogLevel = INFO
  LogRetentionDays = 30
  MaxLogSizeMB = 10

  [General]
  Environment = production
  DebugMode = false

  [UI]
  RememberLastClient = true
  AutoRefreshInterval = 0
  ```

- [ ] **Test Configuration**:
  ```bash
  # Run Packing Tool
  # Should connect to file server
  # Should show "Network connection OK" in logs
  ```

- [ ] **Check Logs**:
  ```bash
  # Open: %USERPROFILE%\.packers_assistant\logs\
  # Look for: "ProfileManager initialized successfully"
  # Look for: "Base path: \\Server\Share"
  ```

### Step 3: Migrate Client Profiles

For **each client** (M, R, A, etc.):

#### 3.1 Create New Client Profile

- [ ] **Open Packing Tool**
- [ ] **Click "Create New Client"** (if not exists)
- [ ] **Fill in Details**:
  ```
  Client ID: M
  Client Name: M Cosmetics
  ```
- [ ] **Verify Creation**:
  ```bash
  # Check file server:
  \\Server\Share\Clients\CLIENT_M\
  ├── packer_config.json
  └── client_config.json
  ```

#### 3.2 Migrate SKU Mappings

- [ ] **Export Old SKU Mappings**:
  ```bash
  # From local storage:
  C:\Users\{Username}\.packers_assistant\sku_map.json

  # Open in text editor, copy contents
  ```

- [ ] **Import to New System**:
  ```bash
  # Option A: Via UI
  1. Open Packing Tool
  2. Select Client: M
  3. Tools → SKU Mapping
  4. Click "Import from File"
  5. Select old sku_map.json
  6. Click "Save"

  # Option B: Manual edit
  1. Open: \\Server\Share\Clients\CLIENT_M\packer_config.json
  2. Edit "sku_mapping" section:
     {
       "sku_mapping": {
         "barcode_12345": "SKU-001",
         "barcode_67890": "SKU-002"
       }
     }
  3. Save file
  ```

- [ ] **Verify Mappings**:
  ```bash
  # Restart Packing Tool
  # Select Client M
  # Tools → SKU Mapping
  # Should show all imported mappings
  ```

#### 3.3 Migrate Configuration Settings

- [ ] **Transfer Label Settings**:
  ```json
  # Edit: \\Server\Share\Clients\CLIENT_M\packer_config.json
  {
    "barcode_label": {
      "width_mm": 65,        # From old config
      "height_mm": 35,       # From old config
      "dpi": 203,            # Standard
      "show_quantity": false,
      "show_client_name": false,
      "font_size": 10
    }
  }
  ```

- [ ] **Transfer Courier Deadlines**:
  ```json
  {
    "courier_deadlines": {
      "PostOne": "15:00",
      "Speedy": "16:00",
      "DHL": "17:00"
    }
  }
  ```

- [ ] **Transfer Column Mappings** (if custom):
  ```json
  {
    "required_columns": {
      "order_number": "Order_Number",
      "sku": "SKU",
      "product_name": "Product_Name",
      "quantity": "Quantity",
      "courier": "Courier"
    }
  }
  ```

### Step 4: Migrate Historical Sessions

#### 4.1 Decide What to Migrate

- [ ] **Keep**: Completed sessions from last 90 days
- [ ] **Archive**: Sessions older than 90 days
- [ ] **Discard**: Incomplete/corrupted sessions

#### 4.2 Copy Session Directories

```bash
# For each completed session:
Source: C:\Users\{Username}\.packers_assistant\sessions\{CLIENT}\{DATE}\
Destination: \\Server\Share\Sessions\CLIENT_{ID}\{DATE}\

# Example:
C:\Users\Worker\.packers_assistant\sessions\M\2025-11-03_14-30\
  → \\Server\Share\Sessions\CLIENT_M\2025-11-03_14-30\
```

- [ ] **Copy Session Files**:
  - [ ] `barcodes/*.png` (barcode images)
  - [ ] `output/packing_list_completed.xlsx` (completion report)
  - [ ] `output/session_summary.json` (metrics)
  - [ ] **Skip**: `packing_state.json` (no longer needed)
  - [ ] **Skip**: `session_info.json` (session is complete)
  - [ ] **Skip**: `.session.lock` (session is closed)

- [ ] **Verify Session Structure**:
  ```bash
  \\Server\Share\Sessions\CLIENT_M\2025-11-03_14-30\
  ├── barcodes\
  │   ├── ORDER-123.png
  │   ├── ORDER-456.png
  │   └── ...
  └── output\
      ├── packing_list_completed.xlsx
      └── session_summary.json
  ```

#### 4.3 Verify Historical Data

- [ ] **Open Session History** in Packing Tool
- [ ] **Verify All Sessions** Appear:
  ```
  Session ID       | Client | Orders | Duration | Date
  ─────────────────┼────────┼────────┼──────────┼───────────
  2025-11-03_14-30 | M      | 148    | 1h 44m   | 2025-11-03
  2025-11-02_10-15 | M      | 132    | 1h 32m   | 2025-11-02
  ...
  ```

- [ ] **Spot Check**: Open a few sessions, verify data integrity

### Step 5: Migrate Statistics

- [ ] **Backup Current Stats**:
  ```bash
  # Copy local stats.json to backup
  Source: C:\Users\{Username}\.packers_assistant\stats.json
  Destination: C:\Backup\stats_before_migration.json
  ```

- [ ] **Merge Statistics**:
  ```bash
  # Option A: Manual merge (recommended for accuracy)
  1. Open old stats.json (local)
  2. Open new stats.json (\\Server\Share\Stats\stats.json)
  3. Manually merge:
     - processed_order_ids (combine lists, remove duplicates)
     - completed_order_ids (combine lists, remove duplicates)
     - client_stats (add totals together)
     - session_history (append old sessions to new)

  # Option B: Let system rebuild (simpler but loses old data)
  1. Delete: \\Server\Share\Stats\stats.json
  2. Restart Packing Tool
  3. New stats.json created automatically
  4. Will only include sessions on file server
  ```

- [ ] **Verify Global Statistics**:
  ```bash
  # Open Dashboard in Packing Tool
  # Check totals match expected values:
  Total Sessions: {OLD_VALUE} + {NEW_VALUE}
  Total Orders: {OLD_VALUE} + {NEW_VALUE}
  ```

### Step 6: Test Migration on Single PC

- [ ] **Select Test PC**: Choose one PC for thorough testing
- [ ] **Complete Full Workflow**:
  1. [ ] Open Packing Tool
  2. [ ] Select migrated client (e.g., "M")
  3. [ ] Start new session with test Excel file
  4. [ ] Verify barcode generation
  5. [ ] Scan test order barcode
  6. [ ] Scan test SKU barcodes
  7. [ ] Complete test order
  8. [ ] End session
  9. [ ] Verify completion report generated
  10. [ ] Check session appears in history

- [ ] **Test Historical Data Access**:
  1. [ ] Open Session History
  2. [ ] Verify old sessions visible
  3. [ ] Open old session details
  4. [ ] Verify data intact

- [ ] **Test SKU Mappings**:
  1. [ ] Tools → SKU Mapping
  2. [ ] Verify all mappings present
  3. [ ] Add new test mapping
  4. [ ] Close and reopen tool
  5. [ ] Verify mapping persisted

- [ ] **Test Multi-PC Coordination**:
  1. [ ] Start session on Test PC
  2. [ ] Try to open same session on PC-2
  3. [ ] Should show "Session locked by Test PC"
  4. [ ] Verify lock info displayed correctly

- [ ] **Test Crash Recovery**:
  1. [ ] Start test session
  2. [ ] Pack a few orders
  3. [ ] Force-close application (Task Manager)
  4. [ ] Reopen Packing Tool
  5. [ ] Should show incomplete session
  6. [ ] Restore session
  7. [ ] Verify progress preserved

### Step 7: Roll Out to All PCs

For **each warehouse PC**:

- [ ] **Schedule Downtime**: During low-activity period
- [ ] **Install New Version**:
  ```bash
  # Use same installer as test PC
  PackingTool_v2.0.0_Setup.exe
  ```

- [ ] **Copy config.ini**:
  ```bash
  # From test PC to each PC
  Source: {Test PC}\C:\Program Files\PackingTool\config.ini
  Destination: {This PC}\C:\Program Files\PackingTool\config.ini
  ```

- [ ] **Launch Application**:
  - [ ] Verify connects to file server
  - [ ] Verify sees all clients
  - [ ] Verify sees session history

- [ ] **Quick Test**:
  - [ ] Start test session
  - [ ] Scan test barcode
  - [ ] End session
  - [ ] Verify session appears in history

- [ ] **Train User**:
  - [ ] Show new client selection screen
  - [ ] Explain centralized profiles
  - [ ] Demonstrate session history
  - [ ] Show how to restore crashed sessions

### Step 8: Post-Migration Verification

- [ ] **Verify All PCs Connected**:
  ```bash
  # Check each PC can:
  - Access \\Server\Share
  - See all clients
  - Start sessions
  - View history
  ```

- [ ] **Verify Data Integrity**:
  - [ ] All clients migrated
  - [ ] All SKU mappings present
  - [ ] Historical sessions accessible
  - [ ] Statistics accurate

- [ ] **Verify Multi-PC Coordination**:
  - [ ] PC-1 starts session → PC-2 sees lock
  - [ ] PC-1 crashes → PC-2 detects stale lock
  - [ ] PC-2 force-releases → can restore session

- [ ] **Performance Check**:
  - [ ] Session start time: < 5 seconds
  - [ ] Barcode generation: < 10 seconds for 100 orders
  - [ ] SKU scan response: < 1 second
  - [ ] Session end: < 10 seconds

### Step 9: Cleanup

- [ ] **Remove Local Storage** (after 30 days of stable operation):
  ```bash
  # Delete old local data (keep backup!)
  C:\Users\{Username}\.packers_assistant_OLD\
  ```

- [ ] **Uninstall Old Version**:
  ```bash
  # Remove old installation
  C:\Program Files\PackingTool_OLD\
  ```

- [ ] **Update Documentation**:
  - [ ] Update user manuals with new screenshots
  - [ ] Update training materials
  - [ ] Update troubleshooting guides

- [ ] **Archive Old Backups**:
  ```bash
  # Move to long-term storage
  C:\Backup\packers_assistant_backup_{DATE}\
    → \\BackupServer\Archives\
  ```

## Setting Up First Client Profile

### For Warehouse Manager

If you're setting up a completely new client from scratch:

#### 1. Gather Information

- [ ] **Client Details**:
  ```
  Client ID: _____ (1-2 characters, e.g., "M", "R", "AB")
  Client Name: _____ (e.g., "M Cosmetics")
  ```

- [ ] **Barcode Label Requirements**:
  ```
  Label Size: _____ mm × _____ mm (default: 65mm × 35mm)
  DPI: _____ (default: 203 for thermal printers)
  Show Quantity on Label: Yes / No
  Show Client Name: Yes / No
  ```

- [ ] **Courier Information**:
  ```
  Courier 1: _____ (Deadline: _____)
  Courier 2: _____ (Deadline: _____)
  Courier 3: _____ (Deadline: _____)
  ```

- [ ] **Excel Column Names** (if custom):
  ```
  Order Number Column: _____ (default: Order_Number)
  SKU Column: _____ (default: SKU)
  Product Name Column: _____ (default: Product_Name)
  Quantity Column: _____ (default: Quantity)
  Courier Column: _____ (default: Courier)
  ```

#### 2. Create Profile

- [ ] **Open Packing Tool**
- [ ] **Click "Create New Client"**
- [ ] **Enter Client Details**:
  ```
  Client ID: M
  Client Name: M Cosmetics
  ```
- [ ] **Click "Create"**
- [ ] **Verify Success Message**

#### 3. Configure Profile

- [ ] **Open Client Configuration**:
  ```bash
  # Manually edit (advanced):
  \\Server\Share\Clients\CLIENT_M\packer_config.json

  # Or use UI (recommended):
  Tools → Client Settings
  ```

- [ ] **Set Barcode Label Options**:
  ```json
  "barcode_label": {
    "width_mm": 65,
    "height_mm": 35,
    "dpi": 203,
    "show_quantity": false,
    "show_client_name": false,
    "font_size": 10
  }
  ```

- [ ] **Set Courier Deadlines**:
  ```json
  "courier_deadlines": {
    "PostOne": "15:00",
    "Speedy": "16:00",
    "DHL": "17:00"
  }
  ```

- [ ] **Set Column Mappings** (if needed):
  ```json
  "required_columns": {
    "order_number": "OrderID",      # If Excel uses "OrderID"
    "sku": "ProductCode",            # If Excel uses "ProductCode"
    "product_name": "Description",   # If Excel uses "Description"
    "quantity": "Qty",               # If Excel uses "Qty"
    "courier": "ShippingMethod"      # If Excel uses "ShippingMethod"
  }
  ```

#### 4. Set Up SKU Mappings (If Needed)

Only needed if product barcodes differ from Excel SKUs.

- [ ] **Identify Mapping Requirements**:
  ```
  # Example scenario:
  Physical product barcode: 8594123456789
  Excel SKU: SKU-001

  # Need mapping: 8594123456789 → SKU-001
  ```

- [ ] **Add Mappings**:
  ```bash
  1. Open Packing Tool
  2. Select Client: M
  3. Tools → SKU Mapping
  4. Click "Add"
  5. Enter:
     Product Barcode: 8594123456789
     Internal SKU: SKU-001
  6. Click "Save"
  7. Repeat for all products
  ```

- [ ] **Test Mapping**:
  ```bash
  1. Start test session
  2. Scan order barcode
  3. Scan product barcode (e.g., 8594123456789)
  4. Should mark SKU-001 as packed
  5. If not working, check mapping case-sensitivity
  ```

#### 5. Test First Session

- [ ] **Prepare Test Excel File**:
  ```
  # Create small test file with 3-5 orders
  Order_Number | SKU     | Product_Name  | Quantity | Courier
  ORDER-001    | SKU-001 | Test Item 1   | 1        | DHL
  ORDER-001    | SKU-002 | Test Item 2   | 2        | DHL
  ORDER-002    | SKU-001 | Test Item 1   | 1        | Speedy
  ```

- [ ] **Run Test Session**:
  1. [ ] Open Packing Tool
  2. [ ] Select Client: M
  3. [ ] Start Session
  4. [ ] Import test Excel file
  5. [ ] Verify barcodes generated
  6. [ ] Scan test order barcode
  7. [ ] Scan test SKU barcodes
  8. [ ] Complete test orders
  9. [ ] End session
  10. [ ] Verify completion report

- [ ] **Verify Output**:
  ```bash
  \\Server\Share\Sessions\CLIENT_M\{DATE}\
  ├── barcodes\
  │   ├── ORDER-001.png  ✓
  │   └── ORDER-002.png  ✓
  └── output\
      ├── packing_list_completed.xlsx  ✓
      └── session_summary.json  ✓
  ```

#### 6. Go Live

- [ ] **Train Workers**:
  - [ ] Show how to select Client M
  - [ ] Demonstrate barcode scanning
  - [ ] Explain order completion workflow
  - [ ] Show how to handle errors

- [ ] **Monitor First Real Session**:
  - [ ] Be present for first live session
  - [ ] Watch for any issues
  - [ ] Note worker feedback
  - [ ] Adjust settings if needed

- [ ] **Review Performance**:
  ```bash
  # After first session, check:
  - Session duration
  - Items per minute
  - Error rate
  - Worker satisfaction
  ```

## Troubleshooting Migration Issues

### Issue: "File Server Not Accessible"

**Cause**: Network configuration or permissions issue

**Solution**:
```bash
1. Test network connectivity:
   ping 192.168.88.101

2. Test SMB access:
   # In Windows Explorer:
   \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment

3. Check config.ini path:
   FileServerPath = \\192.168.88.101\Z_GreenDelivery\WAREHOUSE\0UFulfilment

4. Verify user permissions:
   - Right-click on share → Properties → Security
   - Ensure user has "Modify" access

5. Check firewall:
   - Ensure ports 445 and 139 open
   - Test: Temporarily disable firewall
```

### Issue: "Client Not Found After Migration"

**Cause**: Client directory not created or named incorrectly

**Solution**:
```bash
1. Check client directory exists:
   \\Server\Share\Clients\CLIENT_M\

2. Verify naming:
   - Must be: CLIENT_M (not CLIENT_m or M)
   - Case-sensitive on some systems

3. Check files present:
   - packer_config.json
   - client_config.json

4. Recreate if missing:
   - Open Packing Tool
   - Click "Create New Client"
   - Enter Client ID: M
```

### Issue: "SKU Mappings Not Working After Migration"

**Cause**: Mappings not imported correctly or format changed

**Solution**:
```bash
1. Check mappings exist:
   # Open: \\Server\Share\Clients\CLIENT_M\packer_config.json
   # Look for: "sku_mapping": {...}

2. Verify format:
   {
     "sku_mapping": {
       "product_barcode": "internal_sku"
     }
   }

3. Check case-sensitivity:
   - Barcodes normalized to lowercase
   - "SKU-001" becomes "sku-001"

4. Re-import if needed:
   - Tools → SKU Mapping
   - Click "Import from File"
   - Select old sku_map.json
```

### Issue: "Statistics Not Showing Historical Data"

**Cause**: Statistics not migrated or merge failed

**Solution**:
```bash
1. Check stats.json exists:
   \\Server\Share\Stats\stats.json

2. Verify structure:
   {
     "processed_order_ids": [...],
     "completed_order_ids": [...],
     "client_stats": {...},
     "session_history": [...]
   }

3. Manually merge if needed:
   # From backup:
   C:\Backup\stats_before_migration.json

   # Combine with new stats.json
   # Use JSON merge tool or manual copy-paste

4. Restart Packing Tool to reload stats
```

### Issue: "Sessions Locked After Migration"

**Cause**: Old lock files not cleaned up

**Solution**:
```bash
1. Close Packing Tool on all PCs

2. Delete all lock files:
   \\Server\Share\Sessions\**\.session.lock

3. Delete session_info.json for completed sessions:
   \\Server\Share\Sessions\**\session_info.json
   (Only delete if session is actually complete!)

4. Restart Packing Tool
```

### Issue: "Permission Denied When Saving Configuration"

**Cause**: Insufficient file server permissions

**Solution**:
```bash
1. Check current user permissions:
   # Right-click on file → Properties → Security

2. Request admin to grant permissions:
   - Share permissions: Read + Write
   - NTFS permissions: Modify

3. Test with different user:
   # Login as admin
   # Try operation again
   # If works, it's a permissions issue

4. Add user to correct security group:
   # Domain Admins or Warehouse_Users
```

## Rollback Plan

If migration fails and you need to revert:

### Emergency Rollback Steps

1. [ ] **Stop all Packing Tool instances** on all PCs
2. [ ] **Restore from backup**:
   ```bash
   # Copy backup back to local storage
   C:\Backup\packers_assistant_backup_{DATE}\
     → C:\Users\{Username}\.packers_assistant\
   ```

3. [ ] **Reinstall old version**:
   ```bash
   # Uninstall new version
   # Reinstall from: C:\Program Files\PackingTool_OLD\
   ```

4. [ ] **Verify rollback**:
   - [ ] Open old version
   - [ ] Check clients visible
   - [ ] Check session history
   - [ ] Test session start/end

5. [ ] **Document issues**:
   - [ ] What failed?
   - [ ] Error messages?
   - [ ] Which PC(s) affected?
   - [ ] Contact support with details

## Post-Migration Support

### Getting Help

- **Documentation**: See `/docs/` directory for detailed guides
  - `ARCHITECTURE.md` - System design and structure
  - `API.md` - Technical API reference
  - `INTEGRATION.md` - Integration workflow guide

- **Logs**: Check logs for troubleshooting:
  ```
  %USERPROFILE%\.packers_assistant\logs\
  ```

- **Support Contact**: [Your support contact info]

### Training Resources

- [ ] **User Manual**: `docs/USER_GUIDE.md`
- [ ] **Video Tutorials**: [Link to videos]
- [ ] **FAQ**: `docs/FAQ.md`
- [ ] **Training Sessions**: Schedule with IT team

---

**Document Version**: 1.0
**Last Updated**: 2025-11-05
**Authors**: Development Team
**Status**: Production

**Migration Tested On**:
- Windows 10 / Windows 11
- Python 3.8, 3.9, 3.10, 3.11
- File servers: Windows Server 2016+, Samba 4.x+
- Network: 10 Mbps minimum, 100 Mbps recommended
