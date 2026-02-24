# Packer's Assistant - System Architecture

**Version:** 1.3.2.0 (Pre-release)
**Last Updated:** 2026-02-24
**Architecture Phase:** Phase 3.2 — Session Browser, Packer Mode, Async State Writer

---

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Storage Architecture](#storage-architecture)
6. [Multi-PC Coordination](#multi-pc-coordination)
7. [Session Lifecycle](#session-lifecycle)
8. [Technology Stack](#technology-stack)

## Overview

Packer's Assistant is a desktop application designed for small to medium-sized warehouse
operations. It is the execution stage of a two-tool workflow: Shopify Tool creates sessions and
packing lists from Shopify orders, and Packer's Assistant executes the physical packing by:

- Loading packing lists from Shopify Tool sessions (JSON format)
- Tracking packing progress in real-time with per-scan persistence
- Supporting crash recovery via session state files
- Enabling multi-PC collaboration via centralized file server storage
- Managing multiple packing lists per session (one per courier or filter)

The application is built with Python 3.9+ and PySide6 (Qt6).

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Presentation Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │   Main UI    │  │ Packer Mode  │  │  Session Browser   │   │
│  │   (QWidget)  │  │   (QWidget)  │  │     (QWidget)      │   │
│  └──────────────┘  └──────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Business Logic Layer                        │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────┐  │
│  │ PackerLogic  │  │SessionManager │  │ StatisticsManager  │  │
│  │ (Packing)    │  │ (Lifecycle)   │  │   (Analytics)      │  │
│  └──────────────┘  └───────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Data Access Layer                          │
│  ┌──────────────────┐  ┌─────────────────┐  ┌──────────────┐  │
│  │  ProfileManager  │  │ SessionLockMgr  │  │HistoryManager│  │
│  │ (File Server I/O)│  │  (Locking)      │  │  (Queries)   │  │
│  └──────────────────┘  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Layer                               │
│              Centralized File Server (SMB/CIFS)                  │
│                                                                   │
│  ├─ CLIENTS/                 (Client profiles & configs)         │
│  ├─ SESSIONS/                (Session data & barcodes)           │
│  └─ STATS/                   (Global statistics)                 │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture Layers

#### 1. Presentation Layer
- **Purpose**: User interface and interaction
- **Components**:
  - `MainWindow`: Central orchestrator with tabbed interface
  - `PackerModeWidget`: Barcode scanning interface (3-column layout)
  - `SessionBrowserWidget`: Three-tab session management (Active/Completed/Available)
- **Technology**: PySide6 (Qt6) with QSS dark/light themes

#### 2. Business Logic Layer
- **Purpose**: Core application logic, independent of UI
- **Components**:
  - `PackerLogic`: Order loading, scan processing, packing state machine
  - `SessionManager`: Session lifecycle management
  - `AsyncStateWriter`: Write-behind queue for non-blocking state saves
  - `StatisticsManager`: Metrics tracking and aggregation (shared)
- **Communication**: Qt Signals/Slots pattern for UI updates

#### 3. Data Access Layer
- **Purpose**: Abstraction over file system operations
- **Components**:
  - `ProfileManager`: Centralized client profile management
  - `SessionLockManager`: File-based locking with heartbeat
  - `SessionHistoryManager`: Historical data queries
- **Features**: Caching, file locking, atomic writes

#### 4. Storage Layer
- **Purpose**: Persistent data storage on file server
- **Structure**: Organized by clients and sessions
- **Access**: SMB/CIFS network share (Windows-optimized)

## Core Components

### Main Application (`main.py`)

The application entry point and main window orchestrator.

**Key Responsibilities:**
- Initialize core managers (ProfileManager, SessionLockManager)
- Manage client selection and session workflow
- Coordinate between different views (Session, Dashboard, History)
- Handle barcode scanning events
- Manage audio feedback (success/error sounds)

**Architecture Pattern**: MVC (Model-View-Controller)
- View: Qt widgets for UI
- Controller: MainWindow event handlers
- Model: PackerLogic and SessionManager

### PackerLogic (`packer_logic.py`)

Core business logic for order processing and packing.

**Key Responsibilities:**
- Load packing lists from Shopify Tool sessions (JSON format)
- Track packing state (New → In Progress → Completed)
- Handle SKU mapping and barcode normalization
- Persist packing state for crash recovery via `AsyncStateWriter`
- Provide order metadata to the UI

**State Management:**
```python
{
    "in_progress": {
        "ORDER-123": [
            {"original_sku": "SKU-001", "required": 5, "packed": 3},
            {"original_sku": "SKU-002", "required": 2, "packed": 0}
        ]
    },
    "completed_orders": ["ORDER-456"],
    "skipped_orders": ["ORDER-789"]
}
```

### SessionManager (`session_manager.py`)

Manages session lifecycle with multi-PC coordination.

**Key Responsibilities:**
- Create timestamped session directories
- Acquire and maintain session locks
- Heartbeat mechanism for crash detection
- Session restoration after crashes
- Clean up on graceful session end

**Session Lifecycle:**
```
[Start] → Acquire Lock → Initialize State → [Active]
                                              ↓
[Crashed] ← Stale Lock Detected ← No Heartbeat for 2 min
    ↓
Force Release → Restore State → [Active]
    ↓
[End] → Save Report → Release Lock → Cleanup
```

### ProfileManager (`profile_manager.py`)

Centralized client profile and configuration management.

**Key Responsibilities:**
- Client profile CRUD operations
- SKU mapping storage with file locking
- Session directory organization
- Network connectivity testing
- Configuration caching (60-second TTL)

**Client Profile Structure:**
```
CLIENTS/CLIENT_M/
├── config.json              (Client configuration)
├── sku_mapping.json         (Barcode-to-SKU mappings)
└── backups/                 (Config backups, last 10)
```

### SessionLockManager (`session_lock_manager.py`)

File-based locking mechanism for multi-PC safety.

**Key Responsibilities:**
- Acquire exclusive locks on session directories
- Update heartbeat every 60 seconds
- Detect stale locks (> 2 minutes without heartbeat)
- Force-release stale locks for crash recovery
- Monitor all active sessions across clients

**Lock File Structure:**
```json
{
  "locked_by": "PC-WAREHOUSE-2",
  "user_name": "john.smith",
  "lock_time": "2025-11-03T14:30:00",
  "process_id": 12345,
  "app_version": "1.2.0",
  "heartbeat": "2025-11-03T14:32:00"
}
```

### StatisticsManager (`statistics_manager.py`)

Centralized statistics tracking and analytics.

**Key Responsibilities:**
- Track unique orders processed globally
- Record session completion metrics
- Calculate performance metrics (orders/hour, items/hour)
- Generate client-specific analytics
- Maintain session history for reporting

**Statistics Structure:**
```json
{
  "version": "1.1",
  "processed_order_ids": ["ORDER-1", "ORDER-2", ...],
  "completed_order_ids": ["ORDER-1", ...],
  "client_stats": {
    "M": {
      "total_sessions": 45,
      "total_orders": 1234,
      "total_items": 5678,
      "total_duration_seconds": 36000
    }
  },
  "session_history": [...]
}
```

## Data Flow

### 1. Session Start Flow

```
User selects session in Session Browser (Available Sessions tab)
    ↓
MainWindow._handle_start_packing_from_browser()
    ↓
SessionStartWorker (QThread)
    ├─→ SessionManager.get_packing_work_dir() — create work directory
    ├─→ SessionLockManager.acquire_lock()
    ├─→ PackerLogic.load_from_shopify_analysis() or load_packing_list_json()
    └─→ Start heartbeat timer (60s interval)
    ↓
MainWindow._on_session_started()
    └─→ Display orders in UI tree
```

### 2. Barcode Scanning Flow

```
Worker scans barcode
    ↓
PackerModeWidget.barcode_scanned signal
    ↓
MainWindow.on_scanner_input()
    ↓
Is order barcode?
├─ YES → PackerLogic.start_order_packing()
│        ├─→ Load order items
│        ├─→ Check if completed
│        └─→ Display in table
└─ NO  → PackerLogic.process_sku_scan()
         ├─→ Normalize SKU (remove spaces, lowercase)
         ├─→ Apply SKU mapping if configured
         ├─→ Find matching item in current order
         ├─→ Increment packed count
         ├─→ Check if order complete
         └─→ Save state to disk
         ↓
Update UI with result
    ├─ Success → Green flash, success sound
    ├─ Error → Red flash, error sound
    └─ Complete → Victory sound, auto-clear after 3s
```

### 3. Session End Flow

```
User clicks "End Session"
    ↓
MainWindow.end_session()
    ↓
SessionEndWorker (QThread)
    ├─→ AsyncStateWriter.flush() — write any pending state
    ├─→ StatisticsManager.record_session_completion()
    │   ├─→ Calculate duration
    │   ├─→ Count orders and items
    │   └─→ Update global stats
    ├─→ Save session_summary.json
    ├─→ PackerLogic.end_session_cleanup()
    └─→ SessionLockManager.release_lock()
        └─→ Stop heartbeat timer
```

## Storage Architecture

### Directory Structure

**Phase 1 (v1.2.0) - Dual Workflow Support:**
- **Shopify Workflow**: Sessions with `packing/` directory (multiple lists)
- **Excel Workflow**: Sessions with `barcodes/` directory (single list)

#### Phase 1 - Shopify Session Structure (v1.2.0)

```
\\FileServer\PackerAssistant\
│
├── CLIENTS/                         # Client profiles
│   ├── CLIENT_M/
│   │   ├── config.json             # Client configuration
│   │   ├── sku_mapping.json        # Barcode-to-SKU mappings
│   │   └── backups/                # Configuration backups
│   │
│   └── CLIENT_R/
│       └── ...
│
├── SESSIONS/                        # Session data
│   ├── CLIENT_M/
│   │   ├── 2025-11-19_1/           # Shopify session (Phase 1)
│   │   │   ├── session_info.json   # Session metadata
│   │   │   ├── .session.lock       # Lock file with heartbeat
│   │   │   │
│   │   │   ├── analysis/           # Created by Shopify Tool
│   │   │   │   └── analysis_data.json
│   │   │   │
│   │   │   ├── packing_lists/      # Created by Shopify Tool
│   │   │   │   ├── DHL_Orders.json
│   │   │   │   ├── PostOne_Orders.json
│   │   │   │   └── ...
│   │   │   │
│   │   │   └── packing/            # Created by Packing Tool (Phase 1)
│   │   │       ├── DHL_Orders/     # Work dir for DHL list
│   │   │       │   ├── packing_state.json
│   │   │       │   ├── session_summary.json
│   │   │       │   ├── barcodes/
│   │   │       │   │   ├── ORDER-123.png
│   │   │       │   │   └── ORDER-456.png
│   │   │       │   └── reports/
│   │   │       │       └── packing_report.xlsx
│   │   │       │
│   │   │       └── PostOne_Orders/ # Work dir for PostOne list
│   │   │           └── [same structure]
│   │   │
│   │   ├── 2025-11-19_2/           # Excel session (Legacy)
│   │   │   ├── session_info.json
│   │   │   ├── .session.lock
│   │   │   └── barcodes/           # Legacy structure
│   │   │       ├── ORDER-789.png
│   │   │       ├── packing_state.json
│   │   │       └── session_summary.json
│   │   │
│   │   └── ...
│   │
│   └── CLIENT_R/
│       └── ...
│
└── STATS/                           # Global statistics
    └── global_stats.json            # Centralized metrics (unified)
```

**Key design points:**
- Multiple packing lists per Shopify session, one work directory each (`packing/{list_name}/`)
- Unified statistics via `shared/stats_manager.py`
- Session detection reads `packing_lists/` and `packing/` directory structure

### File Formats

#### session_info.json
```json
{
  "client_id": "M",
  "packing_list_path": "C:\\Users\\...\\orders.xlsx",
  "started_at": "2025-11-03T14:30:45",
  "pc_name": "PC-WAREHOUSE-1"
}
```

#### packing_state.json
```json
{
  "version": "1.0",
  "timestamp": "2025-11-03T14:35:00",
  "client_id": "M",
  "data": {
    "in_progress": {
      "ORDER-123": {
        "SKU-001": {"required": 5, "packed": 3, "normalized_sku": "sku001"},
        "SKU-002": {"required": 2, "packed": 0, "normalized_sku": "sku002"}
      }
    },
    "completed_orders": ["ORDER-456", "ORDER-789"]
  }
}
```

#### session_summary.json
```json
{
  "version": "1.0",
  "session_id": "2025-11-03_14-30",
  "client_id": "M",
  "started_at": "2025-11-03T14:30:45",
  "completed_at": "2025-11-03T15:45:30",
  "duration_seconds": 4485,
  "packing_list_path": "C:\\Users\\...\\orders.xlsx",
  "completed_file_path": "\\\\FileServer\\...\\packing_list_completed.xlsx",
  "pc_name": "PC-WAREHOUSE-1",
  "user_name": "john.smith",
  "total_orders": 150,
  "completed_orders": 148,
  "in_progress_orders": 2,
  "total_items": 567,
  "items_packed": 560
}
```

## Multi-PC Coordination

### Locking Mechanism

The application uses file-based locking to coordinate multiple PCs accessing the same file server.

**Components:**
1. **Lock File**: `.session.lock` in session directory
2. **Heartbeat**: Updated every 60 seconds
3. **Stale Detection**: Lock considered stale after 2 minutes without heartbeat
4. **Force Release**: Manual override for crashed sessions

**Lock Acquisition Process:**
```
PC-1: Acquire lock
    ↓
Create .session.lock with:
- locked_by: PC-WAREHOUSE-1
- process_id: 12345
- heartbeat: current timestamp
    ↓
Start heartbeat timer (updates every 60s)
    ↓
[Working on session...]
    ↓
Heartbeat updates timestamp every 60s
    ↓
PC-2: Try to acquire same lock
    ↓
Read .session.lock
    ↓
Check heartbeat timestamp
    ├─→ < 2 min ago: ACTIVE LOCK
    │   └─→ Show "Session in use" dialog
    └─→ > 2 min ago: STALE LOCK
        └─→ Offer to force-release
```

**Heartbeat Update:**
```python
def _update_heartbeat(self):
    """Called by QTimer every 60 seconds"""
    lock_file = session_dir / ".session.lock"

    # Atomic update with file locking
    with file_lock(lock_file):
        data = load_json(lock_file)
        data['heartbeat'] = datetime.now().isoformat()
        save_json(lock_file, data)
```

### Crash Recovery

When the application crashes, the session can be restored:

1. **Session Discovery**: UI scans for directories with `session_info.json`
2. **Lock Check**: Verify if lock is stale (no heartbeat for 2+ minutes)
3. **User Decision**: Offer to force-release stale lock
4. **State Restoration**: Load `packing_state.json` and resume
5. **Lock Reacquisition**: Take over the session lock

**Restore Process:**
```
Application restart
    ↓
MainWindow.load_available_clients()
    ↓
For each client:
    ProfileManager.get_incomplete_sessions()
    └─→ Find sessions with session_info.json
    ↓
User selects session to restore
    ↓
Check lock status
    ├─→ Active: Cannot restore (in use)
    ├─→ Stale: Offer force-release
    └─→ None: Safe to restore
    ↓
Load packing_state.json
    ↓
Restore UI state
    └─→ Display progress for all orders
```

## Session Lifecycle

### State Transitions

```
[No Session]
    │
    ├─→ Start New Session
    │   └─→ [Initializing]
    │       ├─→ Create work directory
    │       ├─→ Acquire lock
    │       ├─→ Load packing list
    │       └─→ [Active]
    │
    └─→ Restore Session
        └─→ [Restoring]
            ├─→ Load state
            ├─→ Acquire lock
            └─→ [Active]

[Active]
    │
    ├─→ Normal flow
    │   ├─→ Scan orders
    │   ├─→ Update state
    │   └─→ Heartbeat updates
    │
    ├─→ End Session
    │   └─→ [Completing]
    │       ├─→ Generate report
    │       ├─→ Save summary
    │       ├─→ Release lock
    │       └─→ [No Session]
    │
    └─→ Crash
        └─→ [Crashed]
            ├─→ Lock becomes stale
            ├─→ State preserved on disk
            └─→ Ready for restoration
```

### Session Files Timeline

```
Session Start:
├─ Create directory: SESSIONS/CLIENT_M/2025-11-03_14-30/
├─ Create session_info.json
├─ Create .session.lock
└─ Start heartbeat timer

During Session:
├─ Create packing_state.json
├─ Update packing_state.json after each scan (via AsyncStateWriter)
└─ Update .session.lock heartbeat every 60s

Session End:
├─ Generate output/packing_list_completed.xlsx
├─ Create output/session_summary.json
├─ Delete packing_state.json (cleanup)
├─ Delete session_info.json (mark as complete)
└─ Delete .session.lock (release)

Files Remaining:
├─ barcodes/*.png (for reference)
├─ output/packing_list_completed.xlsx (final report)
└─ output/session_summary.json (for history)
```

## Server Structure and Profile System

### Centralized File Server Architecture

The Packing Tool uses a **centralized file server** approach for data storage, enabling multi-PC coordination and data sharing across the warehouse. All application data is stored on a network share configured in `config.ini`.

#### Server Directory Structure

```
\\FileServer\Warehouse\
├── Clients/                          # Client profile configurations
│   ├── CLIENT_M/
│   │   ├── packer_config.json       # Unified configuration + SKU mapping
│   │   ├── client_config.json       # Basic client info (compatibility)
│   │   └── backups/                 # Configuration backups (last 10)
│   │       ├── packer_config_20251103_143000.json
│   │       └── ...
│   └── CLIENT_R/
│       └── ...
│
├── Sessions/                         # Session data by client
│   ├── CLIENT_M/
│   │   ├── 2025-11-03_14-30/       # Timestamped session
│   │   │   ├── session_info.json   # Session metadata (removed on completion)
│   │   │   ├── .session.lock       # Lock file with heartbeat
│   │   │   ├── barcodes/           # Generated barcodes + state
│   │   │   │   ├── ORDER-123.png
│   │   │   │   └── packing_state.json
│   │   │   └── output/             # Completion report (created on end)
│   │   │       ├── packing_list_completed.xlsx
│   │   │       └── session_summary.json
│   │   └── ...
│   └── CLIENT_R/
│       └── ...
│
├── Stats/                            # Global statistics
│   └── stats.json                   # Centralized metrics across all clients
│
└── Logs/                             # Centralized logging (optional)
    └── ...
```

### Profile System

#### Client Profiles

Each client has a dedicated profile directory under `Clients/CLIENT_{ID}/` containing:

**1. packer_config.json** - Unified configuration file:
```json
{
  "client_id": "M",
  "client_name": "M Cosmetics",
  "created_at": "2025-11-03T14:30:00",
  "barcode_label": {
    "width_mm": 65,
    "height_mm": 35,
    "dpi": 203,
    "show_quantity": false,
    "show_client_name": false,
    "font_size": 10
  },
  "courier_deadlines": {
    "PostOne": "15:00",
    "Speedy": "16:00",
    "DHL": "17:00"
  },
  "required_columns": {
    "order_number": "Order_Number",
    "sku": "SKU",
    "product_name": "Product_Name",
    "quantity": "Quantity",
    "courier": "Courier"
  },
  "sku_mapping": {
    "barcode_12345": "SKU-001",
    "barcode_67890": "SKU-002"
  },
  "barcode_settings": {
    "auto_generate": true,
    "format": "CODE128"
  },
  "packing_rules": {},
  "last_updated": "2025-11-03T15:00:00",
  "updated_by": "PC-WAREHOUSE-1"
}
```

**Key Features:**
- **Unified Config**: Combines packer settings and SKU mappings in one file
- **File Locking**: Uses Windows `msvcrt.locking()` for concurrent access safety
- **Automatic Backups**: Last 10 versions kept in `backups/` directory
- **Cache Layer**: 60-second TTL cache in ProfileManager reduces file I/O
- **Merge Support**: SKU mappings are merged, not replaced, on save

#### Profile Manager Responsibilities

The `ProfileManager` class provides centralized profile management:

- **CRUD Operations**: Create, read, update client profiles
- **SKU Mapping**: Load/save SKU mappings with file locking
- **Session Organization**: Manage session directories per client
- **Network Testing**: Verify file server connectivity
- **Validation**: Ensure client IDs meet requirements
- **Caching**: Cache configs and SKU mappings (60s TTL)

### Integration Between Applications

The Packing Tool is designed to work in a unified ecosystem with the Shopify Tool:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Shopify Export Tool                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  • Exports packing lists from Shopify                    │   │
│  │  • Generates analysis_data.json (optional metadata)      │   │
│  │  │  - Order statistics                                   │   │
│  │  │  - Product information                                │   │
│  │  │  - Courier breakdown                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼ (Excel file)
                     packing_list_YYYYMMDD_HHMMSS.xlsx
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Packing Tool                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  1. User imports Excel packing list                      │   │
│  │  2. PackerLogic generates barcodes for orders            │   │
│  │  3. Worker scans order barcode → displays items          │   │
│  │  4. Worker scans SKU barcodes → tracks progress          │   │
│  │  5. Order complete → next order                          │   │
│  │  6. Session end → generates completion report            │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Session Output:                                         │   │
│  │  • packing_list_completed.xlsx                           │   │
│  │  • session_summary.json                                  │   │
│  │  • Updated global stats.json                             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Centralized File Server                       │
│  • Stores all client profiles                                   │
│  • Stores all session data                                      │
│  • Stores global statistics                                     │
│  • Enables multi-PC collaboration                               │
└─────────────────────────────────────────────────────────────────┘
```

**Integration Points:**

1. **Excel Format Compatibility**: Both tools use the same Excel column structure
2. **Client Profiles**: Shared client configuration on file server
3. **SKU Mappings**: Centralized barcode-to-SKU mappings
4. **Statistics**: Unified stats.json tracks performance across both tools
5. **Session History**: Complete audit trail of all packing sessions

**Data Flow:**

```
Shopify → Shopify Tool → Excel File → Packing Tool → Session Output → File Server
                                          ↓
                                   Worker Scans
                                          ↓
                                  Realtime Updates
                                          ↓
                                  Statistics Manager
```

## Session Browser Architecture (Phase 3.1)

### Overview

The Session Browser is a unified interface for managing all packing sessions. Introduced in Phase 3.1, it replaces the previous Restore Session dialog and Session Monitor widgets with a comprehensive three-tab interface.

### Components

#### SessionCacheManager
Persistent disk-based cache for session scan results.

**Location:** `src/session_browser/session_cache_manager.py`

**Features:**
- Disk-based storage: `{sessions_root}/.session_browser_cache.json`
- Cache TTL: 300 seconds (5 minutes)
- Per-client caching with timestamps
- Thread-safe operations

**Cache Structure:**
```json
{
  "version": "1.0",
  "last_updated": 1234567890.123,
  "clients": {
    "CLIENT_X": {
      "active": [...],
      "completed": [...],
      "available": [...],
      "timestamp": 1234567890.123
    }
  }
}
```

#### RefreshWorker (QThread)
Background session scanning worker.

**Location:** `src/session_browser/session_browser_widget.py`

**Responsibilities:**
- Scan session directories in background thread
- Prevent UI blocking during scans
- Signal completion to main thread
- Update cache with fresh data

**Workflow:**
1. User opens Session Browser
2. Load from cache (instant display)
3. Start RefreshWorker in background
4. Worker scans directories
5. Signal UI to update with fresh data
6. Save results to cache

### Performance Improvements

**Before Phase 3.1:**
- UI freezes: 60-100 seconds every 30 seconds
- Blocking directory scans
- No caching
- Poor user experience

**After Phase 3.1:**
- Instant UI response
- Background scanning
- 5-minute persistent cache
- Smooth user experience

**Metrics:**
- First open (no cache): 10-15s with loading overlay
- Second+ opens (fresh cache): <1s instant display
- Background refresh: 3-5s without blocking UI
- UI freeze time: 0 seconds (was 60-100s)

### Tab Architecture

**Active Sessions Tab:**
- Scans for locked sessions across warehouse PCs
- Displays lock status, worker info, progress
- Resume and force unlock capabilities

**Completed Sessions Tab:**
- Integrates with SessionHistoryManager
- Date range and client filters
- Excel export functionality
- Detailed session statistics

**Available Sessions Tab:**
- Scans for Shopify sessions ready to pack
- Shows sessions without packing work directories
- Direct session opening capability
- Multi-packing-list support

## Technology Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Language** | Python 3.9+ | Application logic |
| **GUI Framework** | PySide6 (Qt6) | Desktop UI |
| **Data Processing** | pandas | Data handling and Excel export |
| **Excel I/O** | openpyxl | Export completed sessions to .xlsx |
| **Build Tool** | PyInstaller | Standalone .exe compilation |
| **Testing** | pytest, pytest-qt | Unit and integration tests |

**Removed in v1.3.0.0:** `python-barcode`, `reportlab`/`pypdf` — moved to Shopify Tool.

### Key Libraries

#### PySide6 (Qt6)
- **Version**: 6.x
- **Usage**:
  - Main application window (`QMainWindow`)
  - Tabbed interface (`QTabWidget`)
  - Table views (`QTableView`, `QTableWidget`)
  - Dialogs (`QDialog`, `QMessageBox`)
  - Signals/Slots for event handling
  - QSS styling for dark theme

#### pandas
- **Version**: Latest stable
- **Usage**:
  - Read Excel files: `pd.read_excel()`
  - Data validation and transformation
  - Grouping orders: `df.groupby('Order_Number')`
  - Aggregations for summary table

#### python-barcode

Removed in v1.3.0.0. Barcode generation is now handled by Shopify Tool.

### Windows-Specific Features

#### File Locking (msvcrt)
```python
import msvcrt

# Acquire exclusive lock
msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)

# Perform file operations
...

# Release lock
msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
```

#### Network Paths
- SMB/CIFS shares: `\\FileServer\Share\Path`
- Drive mapping support
- Network connectivity testing
- Automatic reconnection handling

## Design Patterns

### 1. Model-View-Controller (MVC)
- **Model**: PackerLogic, SessionManager (business logic)
- **View**: Qt widgets (MainWindow, PackerModeWidget)
- **Controller**: Event handlers in MainWindow

### 2. Signal-Slot Pattern (Qt)
- Decoupled communication between components
- Example: `PackerLogic.item_packed` → `MainWindow._on_item_packed()`

### 3. Manager Pattern
- Encapsulate complex subsystems
- Examples: ProfileManager, SessionLockManager, StatisticsManager

### 4. Strategy Pattern
- SKU normalization: Different strategies for barcode matching
- Column mapping: Flexible mapping between Excel columns and app requirements

### 5. Observer Pattern
- UI updates when packing state changes
- Qt Signals/Slots implement this pattern

### 6. Singleton Pattern
- Logger: `AppLogger.get_logger()` ensures single logging configuration
- ProfileManager: Typically one instance per application

## Error Handling

### Exception Hierarchy

```
PackingToolError (base)
├── NetworkError (file server issues)
├── SessionLockedError (active lock)
│   └── StaleLockError (crashed session)
├── ProfileError (client profile issues)
└── ValidationError (input validation)
```

### Error Handling Strategy

1. **UI Layer**: Display user-friendly message boxes
2. **Business Logic**: Raise specific exceptions with context
3. **Data Access**: Log errors, use fallback values when safe
4. **Logging**: All errors logged with stack traces

## Performance Considerations

### Caching
- ProfileManager caches configs and SKU mappings (60s TTL)
- Reduces file server I/O

### Atomic Writes
- Temp file + move pattern for critical files
- Prevents corruption from partial writes

### Lazy Loading
- Statistics loaded on-demand

### File Locking Optimization
- Non-blocking locks with retries
- Short lock duration (< 1 second typically)
- Exponential backoff for contention

## Security Considerations

### File Server Access
- Relies on Windows file permissions
- No application-level authentication
- Assumption: Trusted warehouse environment

### Data Integrity
- Atomic writes prevent corruption
- Backup system for critical files
- Session state persistence for crash recovery

### Lock Safety
- Heartbeat mechanism prevents indefinite locks
- Stale lock detection with user confirmation
- Process ID verification prevents accidental overwrites

## Future Enhancements

### Potential Improvements
1. **Database Backend**: Replace file-based storage with SQLite/PostgreSQL
2. **Web Interface**: Browser-based UI for remote access
3. **REST API**: Expose functionality to other systems
4. **Real-time Sync**: WebSocket-based updates for multi-PC coordination
5. **Mobile App**: Scanning interface for smartphones
6. **Printer Integration**: Direct printing without dialog
7. **Advanced Analytics**: Machine learning for performance predictions
8. **Internationalization**: Multi-language support

---

**Document Version**: 1.3.2.0 (Pre-release)
**Last Updated**: 2026-02-24
