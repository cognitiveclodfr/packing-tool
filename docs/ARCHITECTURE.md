# Packer's Assistant - System Architecture

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

Packer's Assistant is a desktop application designed for small to medium-sized warehouse operations. It streamlines the order fulfillment process by:
- Processing Excel packing lists
- Generating scannable barcode labels for orders
- Tracking packing progress in real-time
- Supporting crash recovery with session persistence
- Enabling multi-PC collaboration via centralized file server storage

The application is built with Python 3.8+ and PySide6 (Qt6) for cross-platform desktop GUI support.

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Presentation Layer                          │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐   │
│  │   Main UI    │  │ Packer Mode  │  │  Dashboard/History │   │
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
  - `PackerModeWidget`: Barcode scanning interface
  - `DashboardWidget`: Performance metrics display
  - `SessionHistoryWidget`: Historical session browser
- **Technology**: PySide6 (Qt6) with custom QSS styling

#### 2. Business Logic Layer
- **Purpose**: Core application logic, independent of UI
- **Components**:
  - `PackerLogic`: Order processing and barcode generation
  - `SessionManager`: Session lifecycle management
  - `StatisticsManager`: Metrics tracking and aggregation
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
- Load and validate Excel packing lists
- Generate Code-128 barcodes for orders
- Track packing state (New → In Progress → Completed)
- Handle SKU mapping (barcode translations)
- Persist packing state for crash recovery

**State Management:**
```python
{
    "in_progress": {
        "ORDER-123": {
            "SKU-001": {"required": 5, "packed": 3},
            "SKU-002": {"required": 2, "packed": 0}
        }
    },
    "completed_orders": ["ORDER-456", "ORDER-789"]
}
```

**Barcode Generation Process:**
1. Read Excel file with pandas
2. Validate required columns (Order_Number, SKU, Product_Name, Quantity, Courier)
3. Group items by order
4. Generate Code-128 barcode images (203 DPI, 65x35mm labels)
5. Add order number and courier text to labels
6. Save as PNG files in session directory

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
User selects Excel file
    ↓
MainWindow.start_session()
    ↓
SessionManager.start_session()
    ├─→ Create session directory
    ├─→ Acquire session lock
    └─→ Start heartbeat timer
    ↓
PackerLogic.load_packing_list_from_file()
    ↓
[Column Mapping Dialog if needed]
    ↓
PackerLogic.process_data_and_generate_barcodes()
    ├─→ Validate columns
    ├─→ Group by Order_Number
    ├─→ Generate barcode images
    └─→ Save to session directory
    ↓
MainWindow.setup_order_table()
    └─→ Display orders in UI
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
Generate completion report Excel
    ├─→ Mark completed rows as green
    ├─→ Add Status and Completed At columns
    └─→ Save to session/output/ directory
    ↓
StatisticsManager.record_session_completion()
    ├─→ Calculate duration
    ├─→ Count orders and items
    └─→ Update global stats
    ↓
Save session_summary.json
    └─→ Store metrics for history
    ↓
PackerLogic.end_session_cleanup()
    └─→ Remove packing_state.json
    ↓
SessionManager.end_session()
    ├─→ Stop heartbeat timer
    ├─→ Release session lock
    └─→ Remove session_info.json
```

## Storage Architecture

### Directory Structure

```
\\FileServer\PackerAssistant\
│
├── CLIENTS/                         # Client profiles
│   ├── CLIENT_M/
│   │   ├── config.json             # Client configuration
│   │   ├── sku_mapping.json        # Barcode-to-SKU mappings
│   │   └── backups/                # Configuration backups
│   │       ├── config_20251103_143000.json
│   │       └── sku_mapping_20251103_143000.json
│   │
│   └── CLIENT_R/
│       └── ...
│
├── SESSIONS/                        # Session data
│   ├── CLIENT_M/
│   │   ├── 2025-11-03_14-30/       # Timestamped session
│   │   │   ├── session_info.json   # Session metadata (deleted on end)
│   │   │   ├── .session.lock       # Lock file with heartbeat
│   │   │   ├── barcodes/           # Generated barcodes
│   │   │   │   ├── ORDER-123.png
│   │   │   │   ├── ORDER-456.png
│   │   │   │   └── packing_state.json  # Progress tracking
│   │   │   └── output/             # Completion report (created on end)
│   │   │       ├── packing_list_completed.xlsx
│   │   │       └── session_summary.json
│   │   │
│   │   └── 2025-11-03_16-15/
│   │       └── ...
│   │
│   └── CLIENT_R/
│       └── ...
│
└── STATS/                           # Global statistics
    └── stats.json                   # Centralized metrics
```

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
    │       ├─→ Create directory
    │       ├─→ Acquire lock
    │       ├─→ Generate barcodes
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
├─ Generate barcodes/*.png files
├─ Create packing_state.json
├─ Update packing_state.json after each scan
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

## Technology Stack

### Core Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Language** | Python 3.8+ | Application logic |
| **GUI Framework** | PySide6 (Qt6) | Desktop UI |
| **Data Processing** | pandas | Excel file handling |
| **Excel I/O** | openpyxl | Reading/writing .xlsx files |
| **Barcode Generation** | python-barcode | Code-128 barcodes |
| **Image Processing** | Pillow (PIL) | Label generation |
| **Build Tool** | PyInstaller | Standalone .exe compilation |
| **Testing** | pytest, pytest-qt | Unit and integration tests |

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
- **Version**: Latest stable
- **Usage**:
  - Code-128 barcode generation
  - ImageWriter for PNG output
  - Custom DPI and dimensions (203 DPI, 65x35mm labels)

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
- Barcode images generated only when session starts
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

**Document Version**: 1.0
**Last Updated**: 2025-11-04
**Authors**: Development Team
**Status**: Production
