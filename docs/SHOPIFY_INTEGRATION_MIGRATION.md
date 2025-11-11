# Shopify Integration Migration Guide

This guide explains the changes made to integrate Packing Tool with Shopify Tool and how to migrate from the old workflow to the new unified workflow.

## Table of Contents

- [Overview](#overview)
- [What Changed](#what-changed)
- [Why It Changed](#why-it-changed)
- [Migration Steps](#migration-steps)
- [New Workflow](#new-workflow)
- [Directory Structure Changes](#directory-structure-changes)
- [API Changes](#api-changes)
- [Backward Compatibility](#backward-compatibility)
- [Troubleshooting](#troubleshooting)

## Overview

The Packing Tool has been enhanced to work seamlessly with Shopify Tool, enabling a unified workflow from order analysis to packing completion. All data is now stored in a single, well-organized directory structure that both tools can access.

### Version Information

- **Old Workflow:** v1.2.x and earlier (Excel-only workflow)
- **New Workflow:** v1.3.0+ (Unified Shopify + Excel workflow)

## What Changed

### 1. Unified Work Directory Structure

**Old Behavior:**
- Packing Tool created isolated session directories: `OrdersFulfillment_YYYY-MM-DD_N/`
- Each session was independent with no connection to order source
- Manual Excel file selection required

**New Behavior:**
- Sessions can be created from Shopify Tool analysis
- Work directories are nested within Shopify sessions: `Sessions/CLIENT/DATE/packing/LIST_NAME/`
- Multiple packing lists can be worked simultaneously
- Clear connection between Shopify analysis and packing results

### 2. Session Loading

**Old Behavior:**
```python
# Only one way to start a session
session_manager.start_session(excel_file_path)
```

**New Behavior:**
```python
# Two ways to start a session:

# 1. Traditional Excel workflow (still supported)
session_manager.start_session(excel_file_path)

# 2. Load from Shopify session (new)
packer_logic.load_from_shopify_analysis(shopify_session_dir)
```

### 3. Data Storage Location

**Old Structure:**
```
OrdersFulfillment_2025-11-10_1/
├── packing_state.json
├── barcodes/
│   └── ORDER-001.png
└── OrdersFulfillment_2025-11-10_1_completed.xlsx
```

**New Structure (when using Shopify integration):**
```
Sessions/CLIENT_M/2025-11-10_1/
├── session_info.json
├── analysis/
│   └── analysis_data.json          # From Shopify Tool
├── packing_lists/                  # From Shopify Tool
│   ├── DHL_Orders.json
│   └── PostOne_Orders.json
└── packing/                        # Packing Tool work
    ├── DHL_Orders/
    │   ├── barcodes/
    │   ├── packing_state.json
    │   └── reports/
    └── PostOne_Orders/
        ├── barcodes/
        ├── packing_state.json
        └── reports/
```

### 4. Required Field Validation

**Old Behavior:**
- Missing `courier` field would use "Unknown" as default
- Lenient validation allowed incomplete data

**New Behavior:**
- Strict validation of required fields: `order_number`, `courier`
- ValueError raised if required fields are missing
- Better data quality enforcement

### 5. Session Progress Tracking

**Old Behavior:**
- Progress tracked only in `packing_state.json`
- No session-level metadata

**New Behavior:**
- Progress tracked in both `packing_state.json` and `session_info.json`
- Session metadata includes packing progress statistics
- Better visibility across both tools

## Why It Changed

### Business Drivers

1. **Eliminate Manual Steps:** Shopify orders can flow directly to packing without manual Excel export/import
2. **Audit Trail:** Complete history from Shopify order to packed shipment in one place
3. **Multi-Courier Support:** Work on different courier lists simultaneously without confusion
4. **Data Integrity:** All session data in one location prevents file mismatches

### Technical Drivers

1. **Unified Data Model:** Both tools share the same session structure
2. **Better State Management:** Session-level tracking enables better crash recovery
3. **Scalability:** Support for multiple concurrent packing lists
4. **Maintainability:** Single source of truth for order data

## Migration Steps

### For Existing Users

If you have existing packing sessions created with the old workflow, they will continue to work. No migration is required.

**Option 1: Continue with Excel Workflow (No Changes)**
- Keep using "Start Session" with Excel files
- All existing functionality remains unchanged
- Session directories created as before

**Option 2: Adopt Shopify Integration (Recommended)**
1. Set up Shopify Tool (see Shopify Tool documentation)
2. Configure client directories in Shopify Tool
3. Use Shopify Tool to analyze orders and create sessions
4. Use "Load from Shopify Session" in Packing Tool
5. Select the session and packing list to work on

### For Developers

If you have custom code that interacts with Packing Tool:

1. **Update imports:**
   ```python
   # Old - still works
   from packer_logic import PackerLogic

   # New methods available
   logic = PackerLogic(...)
   logic.load_from_shopify_analysis(session_dir)
   ```

2. **Update session paths:**
   ```python
   # Old path structure
   session_dir = "OrdersFulfillment_2025-11-10_1/"

   # New path structure (for Shopify integration)
   session_dir = "Sessions/CLIENT_M/2025-11-10_1/"
   barcode_dir = session_dir / "packing/DHL_Orders/barcodes"
   ```

3. **Update file references:**
   ```python
   # Old
   state_file = session_dir / "packing_state.json"

   # New (for Shopify integration)
   state_file = session_dir / "packing/DHL_Orders/packing_state.json"
   ```

## New Workflow

### End-to-End Shopify Integration Workflow

1. **Shopify Tool: Analyze Orders**
   ```
   - Select client and date
   - Fetch orders from Shopify
   - Analyze and create session: Sessions/CLIENT_M/2025-11-10_1/
   - Generate analysis_data.json
   ```

2. **Shopify Tool: Create Packing Lists (Optional)**
   ```
   - Filter orders by courier
   - Generate packing_lists/DHL_Orders.json
   - Generate packing_lists/PostOne_Orders.json
   ```

3. **Packing Tool: Load Session**
   ```
   - Click "Load from Shopify Session"
   - Navigate to Sessions/CLIENT_M/2025-11-10_1/
   - Tool detects session_info.json and analysis_data.json
   ```

4. **Packing Tool: Select Packing List**
   ```
   - Choose which courier list to pack (DHL, PostOne, etc.)
   - Or load all orders from analysis_data.json
   ```

5. **Packing Tool: Pack Orders**
   ```
   - Barcodes generated in: packing/DHL_Orders/barcodes/
   - Progress saved in: packing/DHL_Orders/packing_state.json
   - Work as normal with barcode scanner
   ```

6. **Completion**
   ```
   - Reports saved in: packing/DHL_Orders/reports/
   - Session metadata updated
   - Ready for next packing list or session
   ```

## Directory Structure Changes

### Old Directory Structure
```
Project Root/
├── src/
├── Sessions/
│   └── CLIENT_M/
│       └── OrdersFulfillment_2025-11-10_1/
│           ├── packing_state.json
│           ├── barcodes/
│           └── report.xlsx
└── config.json
```

### New Directory Structure
```
Project Root/
├── src/
├── Sessions/
│   └── CLIENT_M/                    # Client directory
│       └── 2025-11-10_1/            # Unified session directory
│           ├── session_info.json    # Session metadata (both tools)
│           ├── analysis/            # Shopify Tool data
│           │   ├── analysis_data.json
│           │   └── raw_orders.json
│           ├── packing_lists/       # Shopify Tool generated lists
│           │   ├── DHL_Orders.json
│           │   └── PostOne_Orders.json
│           └── packing/             # Packing Tool work directories
│               ├── DHL_Orders/      # Per-list work directory
│               │   ├── barcodes/
│               │   ├── packing_state.json
│               │   └── reports/
│               └── PostOne_Orders/
│                   ├── barcodes/
│                   ├── packing_state.json
│                   └── reports/
└── config.json
```

## API Changes

### PackerLogic Class

#### New Methods

```python
def load_from_shopify_analysis(self, session_dir: Path) -> Tuple[int, str]:
    """
    Load orders from Shopify Tool analysis_data.json.

    Args:
        session_dir: Path to Shopify session directory

    Returns:
        Tuple of (order_count, analyzed_at_timestamp)

    Raises:
        ValueError: If analysis_data.json is invalid or missing required fields
        FileNotFoundError: If session directory or analysis file not found
    """
```

#### Modified Methods

```python
def __init__(self, client_id: str, profile_manager, barcode_dir: str):
    """
    barcode_dir can now point to nested location like:
    Sessions/CLIENT/DATE/packing/LIST_NAME/barcodes/
    """
```

### New Validation

```python
# Shopify data now requires these fields in each order:
required_order_fields = ['order_number', 'courier', 'items']

# Missing fields will raise ValueError:
# "Missing required columns in order data: ['courier']"
```

## Backward Compatibility

### What Still Works

✅ **All existing functionality is preserved:**
- Excel file loading via "Start Session"
- Column mapping for custom Excel formats
- Traditional session directories
- All barcode generation and printing
- Crash recovery
- Session history
- Worker management

✅ **Old sessions remain accessible:**
- Previous sessions created before v1.3.0 can still be opened
- Reports and barcodes from old sessions are readable
- No data conversion required

### What's New (Optional)

➕ **New features you can adopt:**
- Load from Shopify sessions
- Unified work directory structure
- Multiple concurrent packing lists
- Enhanced session metadata
- Better audit trail

### What Doesn't Work

❌ **No deprecated features** - Everything from v1.2.x still works

## Troubleshooting

### Issue: "Missing required columns" error when loading Shopify session

**Cause:** Shopify analysis_data.json is missing required fields (order_number or courier)

**Solution:**
1. Check that analysis_data.json contains all required fields
2. Re-run Shopify Tool analysis if data is incomplete
3. Verify courier field is not null or empty

**Example of valid order:**
```json
{
  "order_number": "ORDER-001",
  "courier": "DHL",
  "items": [...]
}
```

### Issue: Cannot find session_info.json

**Cause:** Selected directory is not a Shopify Tool session

**Solution:**
1. Ensure you're selecting the correct session directory
2. Check that Shopify Tool created the session properly
3. Look for `session_info.json` in the root of the session directory

### Issue: Packing state not saving to correct location

**Cause:** barcode_dir not set correctly for Shopify integration

**Solution:**
```python
# Correct barcode_dir for Shopify integration:
barcode_dir = session_dir / "packing" / "DHL_Orders" / "barcodes"

# Not:
barcode_dir = session_dir / "barcodes"  # Old style
```

### Issue: Multiple packing lists conflicting

**Cause:** Using same barcode_dir for different packing lists

**Solution:**
Each packing list needs its own directory:
```python
# DHL orders
barcode_dir_dhl = session_dir / "packing" / "DHL_Orders" / "barcodes"

# PostOne orders
barcode_dir_postone = session_dir / "packing" / "PostOne_Orders" / "barcodes"
```

### Issue: Old Excel workflow not working

**Cause:** This shouldn't happen - old workflow is fully supported

**Solution:**
1. Verify you're using "Start Session" (not "Load from Shopify Session")
2. Check that Excel file is in correct format
3. Review column mapping if prompted
4. Check logs for specific error messages

If problems persist, file an issue with:
- Packing Tool version
- Workflow type (Excel vs Shopify)
- Error messages from logs
- Steps to reproduce

## Getting Help

- **Documentation:** See README.md for full feature list
- **Issues:** File bug reports at GitHub Issues
- **Examples:** See `tests/test_shopify_full_workflow.py` for integration examples

## Summary

The Shopify integration enhances Packing Tool without breaking existing functionality. You can:
- Continue using Excel workflow exactly as before
- Gradually adopt Shopify integration when ready
- Mix both workflows as needed

The unified directory structure provides better organization and audit trails while maintaining full backward compatibility with existing sessions.
