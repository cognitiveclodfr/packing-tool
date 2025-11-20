# PHASE 3 PREREQUISITES AUDIT REPORT

**Date:** 2025-11-20
**Phase:** Pre-Phase 3 (Session Browser Planning)
**Status:** Audit Complete
**Priority:** P0 CRITICAL
**Purpose:** Understand existing session management components and plan Session Browser implementation

---

## EXECUTIVE SUMMARY

This audit provides a comprehensive analysis of existing session management infrastructure to support the development of the **Session Browser** feature - the largest addition in v1.3.0. The Session Browser will replace the current Restore Session dialog and Session Monitor widget, while providing enhanced functionality for browsing active, completed, and available sessions.

**Key Findings:**
- ✅ Strong foundation exists: SessionHistoryManager, SessionManager, SessionLockManager
- ✅ Existing UI components can be reference implementations: SessionHistoryWidget, SessionMonitorWidget
- ✅ All data sources needed for Session Browser are accessible
- ✅ Clear integration points identified in main.py
- ⚠️ Restore Session dialog will be deprecated in favor of Session Browser
- ⚠️ Session Monitor widget will be deprecated in favor of Session Browser Active tab

---

## PART 1: EXISTING COMPONENTS ANALYSIS

### 1.1 SessionHistoryManager

**Location:** `src/session_history_manager.py` (Lines 1-666)
**Status:** ✅ Fully implemented and working

#### Purpose
Manages historical session data retrieval and analytics for completed packing sessions. Provides scanning, filtering, searching, and export capabilities for session history.

#### Key Methods

| Method | Line | Purpose |
|--------|------|---------|
| `__init__(profile_manager)` | 99-107 | Initialize with profile manager |
| `get_client_sessions(client_id, start_date, end_date, include_incomplete)` | 109-200 | Retrieve all sessions for a client with optional filters |
| `_parse_session_directory(client_id, session_dir)` | 202-270 | Parse session directory (supports Phase 1 Shopify & Legacy Excel) |
| `_parse_session_summary(client_id, session_dir, summary_file)` | 272-324 | Parse session_summary.json (v1.3.0 format) |
| `_parse_packing_state(client_id, session_dir, state_file)` | 326-414 | Parse packing_state.json for in-progress sessions |
| `get_client_analytics(client_id, start_date, end_date)` | 477-535 | Generate aggregated analytics for a client |
| `search_sessions(client_id, search_term, search_fields)` | 537-569 | Search sessions by various fields |
| `get_session_details(client_id, session_id)` | 571-635 | Get detailed information about a specific session |
| `export_sessions_to_dict(sessions)` | 637-665 | Export sessions to dictionary for pandas DataFrame |

#### Data Structure Returned

```python
SessionHistoryRecord:
    session_id: str                    # e.g., "2025-11-20_143045"
    client_id: str                     # e.g., "M"
    start_time: Optional[datetime]     # Session start timestamp
    end_time: Optional[datetime]       # Session end timestamp
    duration_seconds: Optional[float]  # Total duration
    total_orders: int                  # Total orders in session
    completed_orders: int              # Number completed
    in_progress_orders: int            # Number in progress
    total_items_packed: int            # Total items packed
    pc_name: Optional[str]             # Computer name
    packing_list_path: Optional[str]   # Original packing list path
    session_path: str                  # Full path to session directory
```

#### What It DOES
- ✅ Scans Sessions/{client}/ directories recursively
- ✅ Parses packing_state.json (in-progress sessions)
- ✅ Parses session_summary.json (completed sessions with Phase 2b metadata)
- ✅ Filters by client, date range, completion status
- ✅ Supports both Phase 1 (Shopify: packing/*/) and Legacy (Excel: barcodes/) structures
- ✅ Provides search functionality across session fields
- ✅ Generates client analytics (totals, averages, rates)
- ✅ Exports data to Excel/CSV format

#### What It DOESN'T Do (Gaps for Phase 3)
- ❌ Does NOT explicitly detect active sessions with locks (needs SessionLockManager)
- ❌ Does NOT find available Shopify sessions (sessions with packing_lists/ but no packing work dirs)
- ❌ Does NOT provide real-time monitoring of active sessions
- ❌ Does NOT integrate lock status into session records
- ❌ Does NOT scan for available packing lists within Shopify sessions

**Recommendation for Phase 3:**
- Keep SessionHistoryManager as-is for completed sessions
- Session Browser Completed tab will use `get_client_sessions()` directly
- Active tab will need NEW logic combining SessionLockManager + ProfileManager
- Available tab will need NEW scanning logic for packing_lists/

---

### 1.2 SessionManager

**Location:** `src/session_manager.py` (Lines 1-752)
**Status:** ✅ Fully implemented and working

#### Purpose
Manages the lifecycle of packing sessions: creation, lock acquisition, heartbeat mechanism, and session state tracking. Coordinates with SessionLockManager for multi-PC safety.

#### Key Methods Related to Session Discovery

| Method | Line | Purpose |
|--------|------|---------|
| `__init__(client_id, profile_manager, lock_manager, worker_id, worker_name)` | 64-93 | Initialize session manager for a client |
| `start_session(packing_list_path, restore_dir)` | 95-300 | Start new or restore existing session |
| `end_session()` | 302-331 | End session and cleanup |
| `load_packing_list(session_path, packing_list_name)` | 563-643 | Load packing list JSON from Shopify session |
| `get_packing_work_dir(session_path, packing_list_name)` | 645-705 | Get or create packing/{list_name}/ work directory |
| `get_session_info()` | 409-429 | Get session_info.json data |

#### Phase 1 Features (Already Implemented)

- ✅ `get_packing_work_dir()` - Creates `packing/{list_name}/` structure
- ✅ `load_packing_list()` - Loads JSON from `packing_lists/` directory
- ✅ Session lock acquisition with worker_id/worker_name
- ✅ Heartbeat mechanism (60-second updates)
- ✅ Stale lock detection (2-minute timeout)
- ✅ session_info.json creation/deletion (incomplete session marker)

#### Relevant for Session Browser?

**For Active Sessions Tab:**
- ✅ Can detect incomplete sessions via session_info.json presence
- ✅ Lock status available through SessionLockManager integration
- ✅ Worker info stored in lock file (worker_id, worker_name)

**For Available Sessions Tab:**
- ✅ Can load packing lists from packing_lists/ directory
- ✅ Can check if work directory exists via `get_packing_work_dir()`
- ⚠️ Need to scan for lists WITHOUT work dirs (new logic needed)

**For Restore Workflow:**
- ✅ start_session() supports restore_dir parameter
- ✅ Handles lock conflicts (SessionLockedError, StaleLockError)
- ✅ Integrated with RestoreSessionDialog workflow

---

### 1.3 SessionLockManager

**Location:** `src/session_lock_manager.py` (Lines 1-570)
**Status:** ✅ Fully implemented and working

#### Purpose
Manages file-based session locks to prevent concurrent access, with heartbeat mechanism for crash detection and stale lock recovery.

#### Key Methods

| Method | Line | Purpose |
|--------|------|---------|
| `__init__(profile_manager)` | 44-56 | Initialize with hostname, username, process_id |
| `acquire_lock(client_id, session_dir, worker_id, worker_name)` | 71-184 | Acquire lock on session |
| `release_lock(session_dir)` | 186-237 | Release lock (only if we own it) |
| `is_locked(session_dir)` | 239-282 | Check if session is locked, return lock info |
| `update_heartbeat(session_dir)` | 284-366 | Update heartbeat timestamp (every 60 sec) |
| `is_lock_stale(lock_info, stale_timeout)` | 368-398 | Check if lock is stale (>2 min no heartbeat) |
| `force_release_lock(session_dir)` | 400-449 | Force-release lock (for crash recovery) |
| `get_lock_display_info(lock_info)` | 451-480 | Format lock info for UI display |
| `get_all_active_sessions()` | 524-569 | Get all active sessions across all clients |

#### Lock File Structure (.session.lock)

```json
{
  "locked_by": "PC-NAME",           // Hostname
  "user_name": "john_doe",          // Windows username
  "lock_time": "2025-11-20T14:30:45+00:00",  // ISO timestamp
  "process_id": 12345,              // Process ID
  "app_version": "1.3.0",           // Application version
  "heartbeat": "2025-11-20T14:31:45+00:00",  // Updated every 60 sec
  "worker_id": "worker_001",        // Worker ID (Phase 1.3)
  "worker_name": "Dolphin"          // Worker display name (Phase 1.3)
}
```

#### Stale Lock Detection

**Mechanism:**
- Heartbeat updates every **60 seconds** (HEARTBEAT_INTERVAL)
- Lock is **stale** if no heartbeat for **120 seconds** (STALE_TIMEOUT)
- Stale lock indicates crashed/hung process
- Users can force-release stale locks

**How It Works:**
1. SessionManager starts heartbeat timer on session start
2. Timer calls `update_heartbeat()` every 60 seconds
3. Other PCs check heartbeat timestamp via `is_lock_stale()`
4. If >2 minutes since last heartbeat → lock is stale
5. User can choose to force-release and take over session

#### Relevant for Active Sessions Tab

**Perfect fit for Session Browser Active tab!**

✅ `get_all_active_sessions()` - Returns dict of {client_id: [session_info]} for all locked sessions
✅ Distinguishes active vs stale locks
✅ Provides lock info: user, PC, time, worker
✅ Can force-release stale locks from UI
✅ Supports multi-PC warehouse operations

**Data Returned by get_all_active_sessions():**

```python
{
    'M': [
        {
            'session_name': '2025-11-20_143045',
            'session_dir': Path(...),
            'lock_info': {
                'locked_by': 'PC-WAREHOUSE-01',
                'user_name': 'john_doe',
                'lock_time': '...',
                'heartbeat': '...',
                'worker_id': 'worker_001',
                'worker_name': 'Dolphin'
            }
        },
        ...
    ],
    'R': [...]
}
```

---

## PART 2: EXISTING UI COMPONENTS

### 2.1 SessionHistoryWidget (History Browser)

**Location:** `src/session_history_widget.py` (Lines 1-418)
**Status:** ✅ EXISTS - Fully functional

#### Purpose
Widget for viewing and searching historical session data with filters and export capabilities.

#### UI Structure

**Components:**
- Client filter dropdown (All Clients / specific client)
- Search box (session ID, PC name, file path)
- Date range filter (from/to date pickers)
- Include incomplete checkbox
- Refresh/Export buttons (Excel, CSV)
- Table with 10 columns: Session ID, Client, Start Time, Duration, Total Orders, Completed, In Progress, Items Packed, PC Name, Status

**Actions:**
- Filter by client, date range, completion status
- Search across multiple fields
- Double-click row → Show session details dialog
- Export filtered results to Excel/CSV

#### Data Source
- Uses `SessionHistoryManager.get_client_sessions()`
- Shows both completed and incomplete sessions
- Can filter to show only completed sessions

#### Features
- ✅ Client filter
- ✅ Date range filter
- ✅ Search functionality
- ✅ Completion status filter
- ✅ Excel/CSV export
- ✅ Session details dialog
- ✅ Auto-sorts by start time (newest first)

#### Relationship to Session Browser

**Decision:** ✅ **Keep as separate quick-access tool**

**Rationale:**
- Session History is a specialized read-only view for completed sessions
- Session Browser is broader (active + completed + available)
- Both serve different use cases:
  - History Browser: Quick analytics, export, historical review
  - Session Browser: Active session management, restore, start new work

**Phase 3 Actions:**
- Keep SessionHistoryWidget as-is
- Add "Session Browser" button next to History Browser in toolbar
- Both can coexist - different purposes

---

### 2.2 DashboardWidget

**Location:** `src/dashboard_widget.py` (Lines 1-392)
**Status:** ✅ EXISTS - Fully functional

#### Purpose
Dashboard widget displaying performance metrics and analytics with time period selection and auto-refresh.

#### UI Structure

**Metric Cards:**
1. **Overall Statistics** (3 cards)
   - Total Sessions
   - Total Orders
   - Total Items

2. **Averages** (3 cards)
   - Avg Orders/Session
   - Avg Items/Session
   - Avg Duration (minutes)

3. **Performance Metrics** (2 cards)
   - Orders/Hour (packing rate)
   - Items/Hour (item scan rate)

4. **Client-Specific Statistics** (3 cards, shown when client selected)
   - Client Sessions
   - Client Orders
   - Client Items

**Filters:**
- Time Period: Last 7/30/90 Days, All Time
- Client: All Clients / specific client
- Auto-refresh every 60 seconds

#### Data Source
- Uses `SessionHistoryManager` to calculate metrics from actual session data
- Method: `_calculate_performance_metrics(client_id, days)`
- Supports both Phase 1 (Shopify) and Legacy (Excel) structures

#### What Stats Are Displayed?

**Overall:**
- Total sessions count
- Total orders packed
- Total items scanned

**Averages:**
- Orders per session
- Items per session
- Session duration (minutes)

**Performance:**
- Orders per hour (rate calculation)
- Items per hour (rate calculation)

**Per-Client:**
- Same metrics filtered by selected client

#### Relevant for Session Browser?

**No direct overlap** - Dashboard shows aggregated statistics, Session Browser shows individual session management.

**Possible integration:**
- Session Browser could show summary stats at top (similar to dashboard cards)
- Dashboard remains separate for overall performance monitoring

---

### 2.3 SessionMonitorWidget

**Location:** `src/session_monitor_widget.py` (Lines 1-165)
**Status:** ✅ EXISTS - Fully functional

#### Purpose
Widget for monitoring active sessions across all clients in real-time.

#### UI Structure

**Table with 6 columns:**
1. Client
2. Session (name/ID)
3. User (username)
4. Computer (PC name)
5. Started (lock time)
6. Last Heartbeat (heartbeat timestamp)

**Features:**
- Auto-refresh every 30 seconds
- Refresh Now button
- Shows all active (locked, non-stale) sessions
- Formats timestamps for display

#### Data Source
- Uses `SessionLockManager.get_all_active_sessions()`
- Filters to show only active (non-stale) locks
- Displays lock info: user, PC, times

#### What It Shows

For each active session:
- ✅ Client ID
- ✅ Session name/ID
- ✅ Who is working (username)
- ✅ Which PC (computer name)
- ✅ When started (lock_time)
- ✅ Last heartbeat timestamp

#### To Be Replaced

**Decision:** ⚠️ **Session Monitor → Deprecated by Session Browser Active tab**

**Rationale:**
- Session Browser Active tab provides same functionality PLUS:
  - Progress information (X/Y orders)
  - Resume action
  - Force unlock action
  - View details
  - Better UI (cards instead of table)

**Phase 3 Actions:**
- Remove Session Monitor widget from main.py
- Redirect any Session Monitor calls to Session Browser (Active tab)
- Keep get_all_active_sessions() method (used by Session Browser)

---

### 2.4 RestoreSessionDialog (Restore Session Functionality)

**Location:** `src/restore_session_dialog.py` (Lines 1-240)
**Current UI:** Button in main.py toolbar (Line 253)

#### Purpose
Dialog for selecting and restoring incomplete sessions with lock status indicators.

#### How It Works Now

**UI Elements:**
- List of incomplete sessions for current client
- Lock status icons:
  - 🔒 = Active on another PC (cannot select)
  - ⚠️ = Stale lock (can force-release)
  - 📦 = Available (can restore)
- Refresh button
- Restore Selected button

**What It Shows:**
- Session name (directory name, e.g., "2025-11-20_143045")
- Lock status
- User and PC info (if locked)

**How User Selects:**
1. Click "Restore Session" button in toolbar
2. Dialog opens showing incomplete sessions
3. User selects available or stale session
4. For stale locks: confirmation dialog to force-release
5. Dialog returns selected session path
6. main.py calls `start_session(restore_dir=...)`

#### Data Source
- Uses `ProfileManager.get_incomplete_sessions(client_id)`
- Incomplete session = has `session_info.json` file
- Uses `SessionLockManager` to check lock status

#### To Be Replaced

**Decision:** ⚠️ **Restore Session Dialog → Deprecated by Session Browser**

**Rationale:**
- Session Browser provides superior functionality:
  - **Active tab** shows in-progress sessions with progress
  - **Available tab** shows Shopify sessions ready to start
  - Resume action directly from Session Browser
  - More context and information
  - Unified interface for all session operations

**Phase 3 Actions:**
- Remove "Restore Session" button from toolbar
- Add "Session Browser" button in its place
- Keep `start_session(restore_dir=...)` logic in main.py (called from Session Browser)

---

## PART 3: DATA SOURCES AVAILABLE

### 3.1 For ACTIVE SESSIONS Tab

**Data Needed:**
- List of in-progress sessions (with session_info.json)
- Lock status (who, when, where)
- Progress (X/Y orders)
- Time elapsed
- Worker info (worker_id, worker_name)
- Packing list name

**Available From:**

1. **session_info.json** (Lines 270-276 in session_manager.py)
   ```json
   {
     "client_id": "M",
     "packing_list_path": "\\\\server\\...\\DHL_Orders.json",
     "started_at": "2025-11-20T14:30:45",
     "pc_name": "PC-WAREHOUSE-01"
   }
   ```

2. **.session.lock** (if exists → session is active RIGHT NOW)
   ```json
   {
     "locked_by": "PC-WAREHOUSE-01",
     "user_name": "john_doe",
     "lock_time": "2025-11-20T14:30:45+00:00",
     "heartbeat": "2025-11-20T14:31:45+00:00",
     "worker_id": "worker_001",
     "worker_name": "Dolphin",
     "process_id": 12345,
     "app_version": "1.3.0"
   }
   ```

3. **packing_state.json** (for progress)
   ```json
   {
     "data": {
       "in_progress": { "ORDER-123": {...} },
       "completed_orders": ["ORDER-456", "ORDER-789"],
       "skipped_orders": []
     },
     "timestamp": "2025-11-20T14:35:12+00:00"
   }
   ```

**How to Find Active Sessions:**

```python
# Method 1: Use ProfileManager.get_incomplete_sessions()
incomplete_sessions = profile_manager.get_incomplete_sessions(client_id)
# Returns: List[Path] of sessions with session_info.json

# Method 2: For each incomplete session, check lock status
for session_dir in incomplete_sessions:
    is_locked, lock_info = lock_manager.is_locked(session_dir)
    if is_locked and not lock_manager.is_lock_stale(lock_info):
        # This is an ACTIVE session (locked RIGHT NOW)
        pass
    elif is_locked and lock_manager.is_lock_stale(lock_info):
        # This is a session with STALE lock (crashed)
        pass
    else:
        # This is an INCOMPLETE but UNLOCKED session (paused/restored later)
        pass

# Method 3: Read packing_state.json for progress
packing_state_path = session_dir / "packing" / "{list_name}" / "packing_state.json"
# OR (legacy)
packing_state_path = session_dir / "barcodes" / "packing_state.json"

# Calculate progress
completed = len(packing_state['data']['completed_orders'])
in_progress = len(packing_state['data']['in_progress'])
total = completed + in_progress
progress_text = f"{completed}/{total} orders"
```

**Existing Helper Method:**
- `SessionLockManager.get_all_active_sessions()` - Returns all locked sessions across all clients

---

### 3.2 For COMPLETED SESSIONS Tab

**Data Needed:**
- List of finished sessions
- Worker who completed
- Timing metrics (duration, rates)
- Order counts (total, completed)
- Full details (orders list from Phase 2b)

**Available From:**

**session_summary.json** (v1.3.0 format with Phase 2b enhancements)
```json
{
  "session_id": "2025-11-20_143045",
  "packing_list_name": "DHL_Orders",
  "started_at": "2025-11-20T14:30:45+00:00",
  "completed_at": "2025-11-20T15:45:30+00:00",
  "duration_seconds": 4485,
  "pc_name": "PC-WAREHOUSE-01",
  "worker_id": "worker_001",
  "worker_name": "Dolphin",
  "app_version": "1.3.0",

  "total_orders": 50,
  "completed_orders": 48,
  "skipped_orders": 2,
  "total_items": 234,

  "metrics": {
    "orders_per_hour": 38.4,
    "items_per_hour": 187.2,
    "avg_items_per_order": 4.88,
    "avg_order_duration_seconds": 93.4
  },

  "orders": [  // Phase 2b: Enhanced metadata
    {
      "order_number": "ORDER-123",
      "status": "completed",
      "started_at": "2025-11-20T14:31:00+00:00",
      "completed_at": "2025-11-20T14:32:30+00:00",
      "duration_seconds": 90,
      "items": [
        {
          "sku": "SKU-001",
          "name": "Product Name",
          "scanned_at": "2025-11-20T14:31:15+00:00",
          "scan_duration_seconds": 5
        }
      ]
    }
  ]
}
```

**How to Find Completed Sessions:**

```python
# Use SessionHistoryManager (already implemented)
sessions = history_manager.get_client_sessions(
    client_id="M",
    start_date=datetime.now() - timedelta(days=30),
    end_date=datetime.now(),
    include_incomplete=False  # Only completed
)

# Returns: List[SessionHistoryRecord] with all metrics
for session in sessions:
    print(f"Session: {session.session_id}")
    print(f"Orders: {session.completed_orders}/{session.total_orders}")
    print(f"Duration: {session.duration_seconds / 60:.1f} min")
    print(f"Worker: {session.pc_name}")

# For detailed view with orders list (Phase 2b)
details = history_manager.get_session_details(client_id, session_id)
# Returns: {
#   'record': SessionHistoryRecord dict,
#   'packing_state': packing_state.json contents,
#   'session_info': session_info.json contents
# }
```

**Existing Tool:**
- ✅ `SessionHistoryManager` - Complete implementation for scanning, filtering, searching completed sessions
- ✅ Supports Phase 1 (Shopify: packing/*/) and Legacy (Excel: barcodes/) structures
- ✅ Returns rich SessionHistoryRecord objects with all metrics

---

### 3.3 For AVAILABLE SESSIONS Tab

**Data Needed:**
- Shopify sessions without packing work directories
- Available packing lists per session
- Order counts per list
- Session metadata (date, source)

**Available From:**

**Directory Structure to Scan:**
```
Sessions/CLIENT_M/2025-11-20_1/
├── session_info.json           # Session metadata
├── packing_lists/              # From Shopify Tool
│   ├── DHL_Orders.json         # Available if packing/DHL_Orders/ NOT exists
│   └── PostOne_Orders.json     # Available if packing/PostOne_Orders/ NOT exists
└── packing/                    # Created by Packing Tool (may not exist yet)
    └── DHL_Orders/             # If exists → NOT available
        ├── packing_state.json
        └── barcodes/
```

**Packing List JSON Structure:**
```json
{
  "session_id": "2025-11-20_1",
  "report_name": "DHL Orders",
  "created_at": "2025-11-20T10:15:30+00:00",
  "total_orders": 45,
  "total_items": 198,
  "filters_applied": {
    "shipping_method": "DHL"
  },
  "orders": [
    {
      "order_number": "ORDER-123",
      "customer_name": "John Doe",
      "items": [...]
    }
  ]
}
```

**How to Find Available Sessions:**

```python
# Scan for Shopify sessions with packing_lists/ directory
sessions_root = profile_manager.get_sessions_root() / f"CLIENT_{client_id}"

available_sessions = []

for session_dir in sessions_root.iterdir():
    if not session_dir.is_dir():
        continue

    # Check for packing_lists/ directory (Shopify session marker)
    packing_lists_dir = session_dir / "packing_lists"
    if not packing_lists_dir.exists():
        continue  # Not a Shopify session

    # Find available packing lists (not yet started)
    available_lists = []

    for list_file in packing_lists_dir.glob("*.json"):
        list_name = list_file.stem  # Remove .json extension

        # Check if work directory exists
        work_dir = session_dir / "packing" / list_name
        if not work_dir.exists():
            # This packing list is AVAILABLE (not started yet)

            # Load JSON to get order count
            with open(list_file, 'r') as f:
                list_data = json.load(f)

            available_lists.append({
                'list_name': list_name,
                'list_path': list_file,
                'total_orders': list_data.get('total_orders', 0),
                'total_items': list_data.get('total_items', 0),
                'created_at': list_data.get('created_at', '')
            })

    if available_lists:
        available_sessions.append({
            'session_id': session_dir.name,
            'session_path': session_dir,
            'available_lists': available_lists
        })

# Result: List of Shopify sessions with at least one available packing list
```

**New Logic Needed:**
- ⚠️ Scan for packing_lists/ directories
- ⚠️ For each JSON, check if packing/{name}/ exists
- ⚠️ Load JSON to get order counts
- ⚠️ Group by session for display

**Session Browser Available tab will implement this new scanning logic.**

---

### 3.4 Directory Structure Summary

#### Shopify Session (Phase 1) - ACTIVE

```
Sessions/CLIENT_M/2025-11-20_1/
├── session_info.json           ✅ Exists = incomplete/active session
├── .session.lock              ✅ Exists = session is locked RIGHT NOW
│   └── Contains: worker_id, worker_name, user, PC, heartbeat
│
├── packing_lists/             ✅ From Shopify Tool
│   ├── DHL_Orders.json        ✅ Source packing list data
│   └── PostOne_Orders.json
│
└── packing/                   ✅ Work directories (Packing Tool)
    └── DHL_Orders/            ✅ Work in progress
        ├── packing_state.json  ✅ Current progress
        ├── barcodes/           ✅ Generated barcodes
        │   └── ORDER-123.png
        └── reports/            (if completed)
```

#### Shopify Session (Phase 1) - COMPLETED

```
Sessions/CLIENT_M/2025-11-20_1/
├── session_info.json           ❌ Removed on graceful completion
├── .session.lock              ❌ Removed on session end
│
├── packing_lists/
│   └── DHL_Orders.json
│
└── packing/
    └── DHL_Orders/
        ├── session_summary.json ✅ Created on completion (Phase 2b format)
        ├── packing_state.json   ✅ Final state
        ├── barcodes/
        └── reports/
```

#### Shopify Session - AVAILABLE (Not Started)

```
Sessions/CLIENT_M/2025-11-20_1/
├── session_info.json           ✅ May or may not exist (depends on if other lists started)
│
├── packing_lists/             ✅ Shopify session marker
│   ├── DHL_Orders.json        ✅ Available to start
│   └── PostOne_Orders.json    ✅ Available to start
│
└── packing/                   ❌ Does NOT exist yet (or missing some lists)
    └── (empty or partial)
```

#### Excel Session (Legacy) - ACTIVE

```
Sessions/CLIENT_M/2025-11-20_2/
├── session_info.json           ✅ Incomplete marker
├── .session.lock              ✅ Active lock
└── barcodes/                  ✅ Legacy structure
    ├── packing_state.json      ✅ Progress
    └── ORDER-123.png           ✅ Barcodes
```

#### Excel Session (Legacy) - COMPLETED

```
Sessions/CLIENT_M/2025-11-20_2/
├── session_info.json           ❌ Removed
├── .session.lock              ❌ Removed
└── barcodes/
    ├── session_summary.json    ✅ Completion metadata
    ├── packing_state.json      ✅ Final state
    └── ORDER-123.png
```

---

### 3.5 Status Detection Logic

#### Active Session (In Progress RIGHT NOW)
```python
has_session_info = (session_dir / "session_info.json").exists()
has_lock = (session_dir / ".session.lock").exists()
is_locked, lock_info = lock_manager.is_locked(session_dir)
is_stale = lock_manager.is_lock_stale(lock_info) if is_locked else False

if has_session_info and is_locked and not is_stale:
    # ACTIVE SESSION (someone working on it right now)
    status = "active"
```

#### Paused Session (Incomplete but Not Locked)
```python
if has_session_info and not is_locked:
    # PAUSED SESSION (was working, but not locked anymore)
    # Can be resumed
    status = "paused"
```

#### Stale Session (Crashed)
```python
if has_session_info and is_locked and is_stale:
    # STALE SESSION (lock exists but no heartbeat - crashed)
    # Can force-release and resume
    status = "stale"
```

#### Completed Session
```python
has_summary = (work_dir / "session_summary.json").exists()
if has_summary and not has_session_info:
    # COMPLETED SESSION (finished and cleaned up)
    status = "completed"
```

#### Available Session (Not Started)
```python
has_packing_lists = (session_dir / "packing_lists").exists()
work_dir_exists = (session_dir / "packing" / list_name).exists()

if has_packing_lists and not work_dir_exists:
    # AVAILABLE SESSION (Shopify session, list not started yet)
    status = "available"
```

---

## PART 4: SESSION BROWSER COMPONENT ARCHITECTURE

### 4.1 Overview

**Main Widget:** `SessionBrowserWidget`
**Location:** `src/session_browser/session_browser_widget.py` (NEW FILE)

**Structure:**
```
SessionBrowserWidget (QWidget)
├── QTabWidget (3 tabs)
│   ├── ActiveSessionsTab       (In-progress sessions)
│   ├── CompletedSessionsTab    (Finished sessions)
│   └── AvailableSessionsTab    (Shopify sessions ready to start)
└── Status bar
```

**Dependencies:**
- `ProfileManager` - Client and session directory access
- `SessionManager` - Session utilities (load_packing_list, get_packing_work_dir)
- `SessionHistoryManager` - Completed session scanning
- `SessionLockManager` - Lock status and active session detection
- `WorkerManager` - Worker information (if needed)

---

### 4.2 Tab 1: ActiveSessionsTab

**File:** `src/session_browser/active_sessions_tab.py` (NEW)

#### Purpose
Show in-progress sessions (active + paused + stale) with ability to resume or force-unlock.

#### UI Layout

```
┌─────────────────────────────────────────┐
│  Client Filter: [All Clients ▼]   [Refresh] │
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐  │
│  │ 🟢 Session: 2025-11-20_143045    │  │
│  │ Client: M  |  List: DHL_Orders   │  │
│  │ Worker: Dolphin (worker_001)     │  │
│  │ PC: WAREHOUSE-01 | User: john    │  │
│  │ Progress: ████████░░ 35/50       │  │
│  │ Started: 14:30 | Elapsed: 1h 15m │  │
│  │ [Resume] [View Details]          │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ⚠️ Stale Lock - May have crashed      │
│  Session: 2025-11-19_091234            │
│  [Force Unlock & Resume] [Details]     │
│                                         │
│  📦 Paused (No lock)                   │
│  Session: 2025-11-18_160000            │
│  [Resume] [View Details]               │
└─────────────────────────────────────────┘
Status: 3 sessions (1 active, 1 stale, 1 paused)
```

#### Session Card Types

**1. Active Session Card (Green border)**
- 🟢 Icon
- Session ID
- Client ID
- Packing list name
- Lock info: Worker name, PC, User
- Progress bar (X/Y orders)
- Time info: Started at, Elapsed time
- Actions: **Resume**, **View Details**

**2. Stale Lock Session Card (Orange border)**
- ⚠️ Icon
- Session ID
- Lock info with "Stale" warning
- Last heartbeat time
- Actions: **Force Unlock & Resume**, **View Details**

**3. Paused Session Card (Blue border)**
- 📦 Icon
- Session ID
- "Not currently locked" indicator
- Last modified time
- Actions: **Resume**, **View Details**

#### Data Source Logic

```python
def load_active_sessions(self, client_id: Optional[str] = None):
    """Load active sessions for display."""

    # Get incomplete sessions (have session_info.json)
    if client_id:
        clients = [client_id]
    else:
        clients = profile_manager.list_clients()

    active_sessions = []

    for cid in clients:
        incomplete = profile_manager.get_incomplete_sessions(cid)

        for session_dir in incomplete:
            # Load session_info.json
            session_info = load_session_info(session_dir)

            # Check lock status
            is_locked, lock_info = lock_manager.is_locked(session_dir)
            is_stale = lock_manager.is_lock_stale(lock_info) if is_locked else False

            # Find packing_state.json for progress
            packing_state = find_packing_state(session_dir)

            # Calculate progress
            if packing_state:
                completed = len(packing_state['data']['completed_orders'])
                in_progress = len(packing_state['data']['in_progress'])
                total = completed + in_progress
            else:
                completed, total = 0, 0

            # Determine status
            if is_locked and not is_stale:
                status = "active"
                sort_priority = 0  # Show first
            elif is_locked and is_stale:
                status = "stale"
                sort_priority = 1  # Show second
            else:
                status = "paused"
                sort_priority = 2  # Show last

            active_sessions.append({
                'session_dir': session_dir,
                'session_id': session_dir.name,
                'client_id': cid,
                'status': status,
                'lock_info': lock_info,
                'session_info': session_info,
                'progress': (completed, total),
                'sort_priority': sort_priority
            })

    # Sort: active first, then stale, then paused
    active_sessions.sort(key=lambda s: (s['sort_priority'], s['session_id']), reverse=True)

    return active_sessions
```

#### Actions

**Resume Button:**
```python
def on_resume_clicked(self, session_data):
    """Emit signal to resume session."""
    self.resume_session_requested.emit({
        'session_path': str(session_data['session_dir']),
        'client_id': session_data['client_id'],
        'packing_list_path': session_data['session_info'].get('packing_list_path', '')
    })
```

**Force Unlock Button:**
```python
def on_force_unlock_clicked(self, session_data):
    """Force-release stale lock and resume."""
    reply = QMessageBox.question(...)

    if reply == Yes:
        success = lock_manager.force_release_lock(session_data['session_dir'])
        if success:
            # Now resume
            self.on_resume_clicked(session_data)
```

**View Details Button:**
```python
def on_view_details_clicked(self, session_data):
    """Open session details dialog."""
    dialog = SessionDetailsDialog(session_data, parent=self)
    dialog.exec()
```

---

### 4.3 Tab 2: CompletedSessionsTab

**File:** `src/session_browser/completed_sessions_tab.py` (NEW)

#### Purpose
Browse finished sessions with search, filters, and detailed metrics view.

#### UI Layout

```
┌─────────────────────────────────────────┐
│  Client: [All ▼]  Date: [Last 30 Days ▼]│
│  Search: [____________] [Refresh]       │
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐  │
│  │ ✅ Session: 2025-11-20_143045    │  │
│  │ Client: M  |  Worker: Dolphin     │  │
│  │ Completed: Nov 20, 15:45         │  │
│  │ Duration: 1h 15m | Orders: 48/50 │  │
│  │ Rate: 38.4 orders/hr             │  │
│  │ [View Details] [Export]          │  │
│  └───────────────────────────────────┘  │
│                                         │
│  (More session cards...)                │
│                                         │
└─────────────────────────────────────────┘
Showing 15 completed sessions
```

#### Session Card (Completed)

- ✅ Icon (completed)
- Session ID
- Client ID
- Worker name (from session_summary.json)
- Completion time (completed_at)
- Duration (formatted: "1h 15m")
- Orders: completed/total
- Performance metrics:
  - Orders/hour
  - Items/hour
- Actions: **View Details**, **Export**

#### Data Source

**Direct use of SessionHistoryManager:**

```python
def load_completed_sessions(self, client_id=None, days=30):
    """Load completed sessions."""

    start_date = None
    end_date = None
    if days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

    if client_id:
        sessions = history_manager.get_client_sessions(
            client_id,
            start_date=start_date,
            end_date=end_date,
            include_incomplete=False  # Only completed
        )
    else:
        # Load all clients
        sessions = []
        for cid in profile_manager.list_clients():
            client_sessions = history_manager.get_client_sessions(
                cid,
                start_date=start_date,
                end_date=end_date,
                include_incomplete=False
            )
            sessions.extend(client_sessions)

        sessions.sort(key=lambda s: s.start_time or datetime.min, reverse=True)

    return sessions
```

#### Search and Filters

**Search:**
```python
def on_search_changed(self, text):
    """Filter sessions by search term."""
    if not text:
        self.display_sessions(self.all_sessions)
        return

    filtered = [
        s for s in self.all_sessions
        if text.lower() in s.session_id.lower() or
           (s.pc_name and text.lower() in s.pc_name.lower()) or
           (s.packing_list_path and text.lower() in s.packing_list_path.lower())
    ]

    self.display_sessions(filtered)
```

**Filters:**
- Client dropdown (All / specific client)
- Date range dropdown (Last 7/30/90 days, All time)
- Worker filter (optional: show only specific worker)

#### Actions

**View Details:**
```python
def on_view_details_clicked(self, session):
    """Open detailed session view with Phase 2b data."""
    details = history_manager.get_session_details(
        session.client_id,
        session.session_id
    )

    dialog = SessionDetailsDialog(details, parent=self)
    dialog.exec()
```

**Export:**
```python
def on_export_clicked(self, session):
    """Export single session to Excel/PDF."""
    # Export session_summary.json data
    # Include orders list (Phase 2b)
    # Generate Excel report
```

---

### 4.4 Tab 3: AvailableSessionsTab

**File:** `src/session_browser/available_sessions_tab.py` (NEW)

#### Purpose
Show Shopify sessions with packing lists that haven't been started yet, allowing workers to start new packing work.

#### UI Layout

```
┌─────────────────────────────────────────┐
│  Client: [All Clients ▼]   [Refresh]   │
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐  │
│  │ 📋 Shopify Session: 2025-11-20_1 │  │
│  │ Client: M                         │  │
│  │ Created: Nov 20, 10:15           │  │
│  │                                   │  │
│  │ Available Packing Lists:         │  │
│  │ • DHL Orders (45 orders, 198 items)│
│  │   [Start Packing]                │  │
│  │ • Post One (23 orders, 89 items) │  │
│  │   [Start Packing]                │  │
│  └───────────────────────────────────┘  │
│                                         │
│  (More Shopify sessions...)             │
│                                         │
└─────────────────────────────────────────┘
Found 2 Shopify sessions with 3 available lists
```

#### Session Card (Available)

- 📋 Icon (Shopify session)
- Session ID (Shopify session timestamp)
- Client ID
- Created timestamp (from session_info.json or directory)
- **List of available packing lists:**
  - List name (from JSON filename)
  - Order count (from JSON: total_orders)
  - Item count (from JSON: total_items)
  - **Start Packing** button for each list

#### Data Source Logic (NEW)

```python
def scan_available_sessions(self, client_id: Optional[str] = None):
    """Scan for Shopify sessions with available packing lists."""

    if client_id:
        clients = [client_id]
    else:
        clients = profile_manager.list_clients()

    available_sessions = []

    for cid in clients:
        sessions_root = profile_manager.get_sessions_root() / f"CLIENT_{cid}"

        if not sessions_root.exists():
            continue

        for session_dir in sessions_root.iterdir():
            if not session_dir.is_dir():
                continue

            # Check for packing_lists/ directory (Shopify marker)
            packing_lists_dir = session_dir / "packing_lists"
            if not packing_lists_dir.exists():
                continue  # Not a Shopify session

            # Find available packing lists
            available_lists = []

            for list_file in packing_lists_dir.glob("*.json"):
                list_name = list_file.stem

                # Check if work directory exists
                work_dir = session_dir / "packing" / list_name
                if work_dir.exists():
                    continue  # Already started, skip

                # Load packing list JSON
                try:
                    with open(list_file, 'r', encoding='utf-8') as f:
                        list_data = json.load(f)

                    available_lists.append({
                        'list_name': list_name,
                        'list_file': list_file,
                        'total_orders': list_data.get('total_orders', 0),
                        'total_items': list_data.get('total_items', 0),
                        'created_at': list_data.get('created_at', ''),
                        'report_name': list_data.get('report_name', list_name)
                    })
                except Exception as e:
                    logger.warning(f"Could not load {list_file}: {e}")
                    continue

            # Only include sessions with at least one available list
            if available_lists:
                # Load session info if exists
                session_info_file = session_dir / "session_info.json"
                session_info = {}
                if session_info_file.exists():
                    try:
                        with open(session_info_file, 'r') as f:
                            session_info = json.load(f)
                    except:
                        pass

                available_sessions.append({
                    'session_id': session_dir.name,
                    'session_dir': session_dir,
                    'client_id': cid,
                    'session_info': session_info,
                    'available_lists': available_lists,
                    'created_at': session_info.get('started_at', '')
                })

    # Sort by session_id (newest first)
    available_sessions.sort(key=lambda s: s['session_id'], reverse=True)

    return available_sessions
```

#### Actions

**Start Packing Button:**
```python
def on_start_packing_clicked(self, session_data, list_data):
    """Start packing for selected list."""

    # Emit signal with session path and list name
    self.start_packing_requested.emit({
        'session_path': str(session_data['session_dir']),
        'client_id': session_data['client_id'],
        'packing_list_name': list_data['list_name'],
        'packing_list_file': str(list_data['list_file'])
    })
```

**Signal in main.py:**
```python
def on_start_packing_from_browser(self, info):
    """Handle start packing request from Session Browser."""

    # Load packing list using SessionManager
    packing_data = self.session_manager.load_packing_list(
        session_path=info['session_path'],
        packing_list_name=info['packing_list_name']
    )

    # Get or create work directory
    work_dir = self.session_manager.get_packing_work_dir(
        session_path=info['session_path'],
        packing_list_name=info['packing_list_name']
    )

    # Start session (existing logic)
    self.start_shopify_packing_session(
        session_path=info['session_path'],
        packing_list_name=info['packing_list_name'],
        packing_data=packing_data
    )
```

---

### 4.5 SessionDetailsDialog

**File:** `src/session_browser/session_details_dialog.py` (NEW)

#### Purpose
Show comprehensive details for a selected session (active, completed, or paused).

#### UI Layout

```
┌─────────────────────────────────────────┐
│  Session Details: 2025-11-20_143045    │
├─────────────────────────────────────────┤
│  [Overview] [Metrics] [Orders] [Timeline]│
├─────────────────────────────────────────┤
│  ┌───────────────────────────────────┐  │
│  │ OVERVIEW TAB                      │  │
│  │                                   │  │
│  │ Session ID: 2025-11-20_143045    │  │
│  │ Client: M                         │  │
│  │ Packing List: DHL_Orders          │  │
│  │ Worker: Dolphin (worker_001)     │  │
│  │ PC: WAREHOUSE-01                  │  │
│  │                                   │  │
│  │ Started: Nov 20, 14:30:45        │  │
│  │ Completed: Nov 20, 15:45:30      │  │
│  │ Duration: 1h 14m 45s             │  │
│  │                                   │  │
│  │ Status: ✅ Completed             │  │
│  └───────────────────────────────────┘  │
│                                         │
│  [Export PDF] [Export Excel] [Close]   │
└─────────────────────────────────────────┘
```

#### Tabs

**1. Overview Tab**
- Session metadata (ID, client, worker, PC)
- Timing (started, completed, duration)
- Status (active/completed/paused/stale)
- Lock info (if active)
- Packing list name
- Session path

**2. Metrics Tab**
- Orders: completed/total/skipped
- Items: total items packed
- Performance:
  - Orders per hour
  - Items per hour
  - Avg items per order
  - Avg order duration
- Progress chart (if applicable)

**3. Orders Tab** (Phase 2b data)
- Expandable tree view of orders
- Each order shows:
  - Order number
  - Status (completed/skipped)
  - Duration
  - Items list (expandable)
    - SKU, Name, Scanned at, Duration

**4. Timeline Tab** (Optional Phase 3.5)
- Gantt-style chart showing order progression over time
- Visualize packing flow
- Identify bottlenecks

#### Data Source

For **completed sessions**, use `session_summary.json`:
```python
def load_session_details(client_id, session_id):
    """Load complete session details."""

    # Use SessionHistoryManager
    details = history_manager.get_session_details(client_id, session_id)

    if not details:
        return None

    # details contains:
    # - record: SessionHistoryRecord
    # - packing_state: packing_state.json data
    # - session_info: session_info.json data

    # For Phase 2b, also load session_summary.json directly
    # to get orders[] array

    return details
```

For **active/paused sessions**, combine multiple sources:
```python
def load_active_session_details(session_dir):
    """Load details for in-progress session."""

    # Load session_info.json
    session_info = load_json(session_dir / "session_info.json")

    # Load packing_state.json
    packing_state = find_and_load_packing_state(session_dir)

    # Check lock status
    is_locked, lock_info = lock_manager.is_locked(session_dir)

    # Calculate metrics from packing_state
    metrics = calculate_session_metrics(packing_state)

    return {
        'session_info': session_info,
        'packing_state': packing_state,
        'lock_info': lock_info,
        'metrics': metrics
    }
```

---

### 4.6 SessionBrowserWidget (Main Container)

**File:** `src/session_browser/session_browser_widget.py` (NEW)

```python
class SessionBrowserWidget(QWidget):
    """
    Main Session Browser widget with tabs.

    Signals:
        resume_session_requested(dict): Emitted when user wants to resume a session
        start_packing_requested(dict): Emitted when user wants to start new packing
    """

    resume_session_requested = Signal(dict)
    start_packing_requested = Signal(dict)

    def __init__(
        self,
        profile_manager,
        session_manager,
        history_manager,
        lock_manager,
        parent=None
    ):
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_manager = session_manager
        self.history_manager = history_manager
        self.lock_manager = lock_manager

        self._init_ui()

    def _init_ui(self):
        """Initialize UI with tab widget."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Session Browser")
        header_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(header_label)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Create tabs
        self.active_tab = ActiveSessionsTab(
            self.profile_manager,
            self.lock_manager,
            parent=self
        )
        self.active_tab.resume_session_requested.connect(
            self.resume_session_requested.emit
        )

        self.completed_tab = CompletedSessionsTab(
            self.history_manager,
            self.profile_manager,
            parent=self
        )

        self.available_tab = AvailableSessionsTab(
            self.profile_manager,
            self.session_manager,
            parent=self
        )
        self.available_tab.start_packing_requested.connect(
            self.start_packing_requested.emit
        )

        # Add tabs
        self.tab_widget.addTab(self.active_tab, "Active")
        self.tab_widget.addTab(self.completed_tab, "Completed")
        self.tab_widget.addTab(self.available_tab, "Available")

        layout.addWidget(self.tab_widget)

    def refresh_all_tabs(self):
        """Refresh all tabs."""
        self.active_tab.refresh()
        self.completed_tab.refresh()
        self.available_tab.refresh()

    def switch_to_active_tab(self):
        """Switch to active sessions tab."""
        self.tab_widget.setCurrentWidget(self.active_tab)

    def switch_to_available_tab(self):
        """Switch to available sessions tab."""
        self.tab_widget.setCurrentWidget(self.available_tab)
```

---

## PART 5: INTEGRATION PLAN

### 5.1 Main Window Integration (main.py)

#### Add Session Browser Button

**Location:** Toolbar (near Dashboard, History Browser buttons)

**Code Changes:**

```python
# In _init_ui() method, around line 250-260

# BEFORE (OLD):
self.restore_session_button = QPushButton("Restore Session")
self.restore_session_button.clicked.connect(self.open_restore_session_dialog)
control_layout.addWidget(self.restore_session_button)

# Add Session Monitor button
self.session_monitor_button = QPushButton("Session Monitor")
self.session_monitor_button.clicked.connect(self.open_session_monitor)
control_layout.addWidget(self.session_monitor_button)

# AFTER (NEW):
# Replace both buttons with single Session Browser button
self.session_browser_button = QPushButton("Session Browser")
self.session_browser_button.clicked.connect(self.open_session_browser)
control_layout.addWidget(self.session_browser_button)

# Keep History Browser as separate quick-access tool
self.history_button = QPushButton("History Browser")
self.history_button.clicked.connect(self.open_history_browser)
control_layout.addWidget(self.history_button)
```

#### Add Session Browser Method

```python
def open_session_browser(self):
    """Open Session Browser dialog."""
    from session_browser.session_browser_widget import SessionBrowserWidget

    # Create dialog
    dialog = QDialog(self)
    dialog.setWindowTitle("Session Browser")
    dialog.setMinimumSize(1000, 700)
    dialog.setModal(False)  # Non-modal - can keep open while working

    # Create Session Browser widget
    browser = SessionBrowserWidget(
        profile_manager=self.profile_manager,
        session_manager=self.session_manager,
        history_manager=SessionHistoryManager(self.profile_manager),
        lock_manager=self.lock_manager,
        parent=dialog
    )

    # Connect signals
    browser.resume_session_requested.connect(
        lambda info: self._handle_resume_session(dialog, info)
    )
    browser.start_packing_requested.connect(
        lambda info: self._handle_start_packing(dialog, info)
    )

    # Layout
    layout = QVBoxLayout(dialog)
    layout.addWidget(browser)

    # Show dialog
    dialog.exec()

def _handle_resume_session(self, dialog, info):
    """Handle resume session request from Session Browser."""

    # Close browser dialog
    dialog.accept()

    # Resume session using existing logic
    self.start_session(
        file_path=info.get('packing_list_path', ''),
        restore_dir=info['session_path']
    )

def _handle_start_packing(self, dialog, info):
    """Handle start packing request from Session Browser."""

    # Close browser dialog
    dialog.accept()

    # Start new packing session for Shopify list
    # (This may need adjustment based on your Shopify packing workflow)
    self.start_shopify_session(
        session_path=info['session_path'],
        packing_list_name=info['packing_list_name']
    )
```

---

### 5.2 Remove Old Components

#### Components to Remove/Deprecate

1. **RestoreSessionDialog** (src/restore_session_dialog.py)
   - ❌ Remove: `self.restore_session_button` from toolbar
   - ❌ Remove: `open_restore_session_dialog()` method
   - ✅ Keep file for reference until Phase 3 complete
   - ✅ Can be deleted after testing Session Browser

2. **SessionMonitorWidget** (src/session_monitor_widget.py)
   - ❌ Remove: `self.session_monitor_button` from toolbar (if exists)
   - ❌ Remove: `open_session_monitor()` method
   - ✅ Keep file for reference until Phase 3 complete
   - ✅ Can be deleted after testing Session Browser

3. **Auto-restore on startup** (main.py, line 1938)
   - ⚠️ Keep for now, but consider replacing with:
     - "Open Session Browser?" prompt on startup
     - Check if user has paused/stale sessions
     - Offer to open Session Browser Active tab

#### Code Removal Plan

```python
# BEFORE:
def open_restore_session_dialog(self):
    """Open dialog to select and restore an incomplete session."""
    # ... 50 lines of code ...

def open_session_monitor(self):
    """Open session monitor window."""
    # ... code ...

# AFTER:
# Remove these methods entirely
# Replace with open_session_browser() (see above)
```

---

### 5.3 Signal/Slot Connections

#### Signals from Session Browser to Main Window

```python
# SessionBrowserWidget signals:

resume_session_requested = Signal(dict)
# Emitted when user clicks Resume on active/paused session
# Payload: {
#     'session_path': str,
#     'client_id': str,
#     'packing_list_path': str
# }

start_packing_requested = Signal(dict)
# Emitted when user clicks Start Packing on available list
# Payload: {
#     'session_path': str,
#     'client_id': str,
#     'packing_list_name': str,
#     'packing_list_file': str
# }
```

#### Connection in main.py

```python
def open_session_browser(self):
    # ... create browser ...

    # Connect signals
    browser.resume_session_requested.connect(
        lambda info: self._handle_resume_session(dialog, info)
    )

    browser.start_packing_requested.connect(
        lambda info: self._handle_start_packing(dialog, info)
    )
```

#### Handlers

```python
def _handle_resume_session(self, dialog, info):
    """Handle resume session request."""
    dialog.accept()  # Close browser

    # Use existing session restoration logic
    try:
        self.start_session(
            file_path=info.get('packing_list_path', ''),
            restore_dir=info['session_path']
        )
    except SessionLockedError as e:
        # Session is locked - show error
        QMessageBox.warning(self, "Session Locked", str(e))
    except StaleLockError as e:
        # Stale lock - offer force-release (existing handler)
        self._handle_stale_lock_error(e, info.get('packing_list_path'), info['session_path'])

def _handle_start_packing(self, dialog, info):
    """Handle start new packing request."""
    dialog.accept()  # Close browser

    try:
        # Load packing list data
        packing_data = self.session_manager.load_packing_list(
            session_path=info['session_path'],
            packing_list_name=info['packing_list_name']
        )

        # Start packing session
        self.start_shopify_packing(
            session_path=info['session_path'],
            packing_list_name=info['packing_list_name'],
            packing_data=packing_data
        )
    except FileNotFoundError as e:
        QMessageBox.critical(self, "Error", f"Packing list not found:\n{e}")
    except Exception as e:
        QMessageBox.critical(self, "Error", f"Failed to start packing:\n{e}")
```

---

### 5.4 Session Browser Workflow Examples

#### Workflow 1: Resume Active Session

```
1. User clicks "Session Browser" button
2. Session Browser opens, showing Active tab
3. User sees: "🟢 Session 2025-11-20_143045 - Dolphin - 35/50 orders"
4. User clicks "Resume" button
5. Signal emitted: resume_session_requested({'session_path': '...', ...})
6. main.py receives signal → calls start_session(restore_dir='...')
7. SessionManager checks lock status
8. Session loads → User continues packing
9. Session Browser dialog closes
```

#### Workflow 2: Force-Release Stale Lock

```
1. User opens Session Browser → Active tab
2. Sees: "⚠️ Stale lock - john on PC-01 (no heartbeat for 5 min)"
3. Clicks "Force Unlock & Resume"
4. Confirmation dialog: "Force-release lock from crashed PC?"
5. User clicks "Yes"
6. SessionLockManager.force_release_lock() called
7. Lock removed
8. Signal emitted: resume_session_requested(...)
9. Session resumes normally
```

#### Workflow 3: Start New Packing from Available List

```
1. User opens Session Browser → Available tab
2. Sees: "📋 Shopify Session 2025-11-20_1"
   - DHL Orders (45 orders, 198 items) [Start Packing]
   - Post One (23 orders, 89 items) [Start Packing]
3. User clicks "Start Packing" on DHL Orders
4. Signal emitted: start_packing_requested({'session_path': '...', 'packing_list_name': 'DHL_Orders', ...})
5. main.py receives signal:
   - Loads DHL_Orders.json
   - Creates packing/DHL_Orders/ work directory
   - Starts session
6. User begins packing orders from DHL list
```

#### Workflow 4: View Completed Session Details

```
1. User opens Session Browser → Completed tab
2. Searches for session: "2025-11-19"
3. Finds yesterday's session
4. Clicks "View Details"
5. SessionDetailsDialog opens
6. User views:
   - Overview: worker, timing, metrics
   - Orders tab: expandable list of all 50 orders (Phase 2b data)
   - Item-by-item timeline
7. Clicks "Export Excel"
8. Session data exported to Excel file
```

---

## PART 6: IMPLEMENTATION ROADMAP

### Implementation Steps (Detailed)

#### Step 1: Core Infrastructure (2-3 hours)

**Goal:** Create basic Session Browser structure with empty tabs

**Tasks:**
1. Create directory: `src/session_browser/`
2. Create `__init__.py` in session_browser/
3. Create `session_browser_widget.py`:
   - Main container widget
   - QTabWidget with 3 empty tabs
   - Signal definitions
4. Create placeholder files:
   - `active_sessions_tab.py` (empty QWidget)
   - `completed_sessions_tab.py` (empty QWidget)
   - `available_sessions_tab.py` (empty QWidget)
5. Integrate into main.py:
   - Add "Session Browser" button
   - Add `open_session_browser()` method
   - Basic dialog opening/closing

**Testing:**
- ✅ Button appears in toolbar
- ✅ Clicking button opens dialog
- ✅ Dialog shows 3 tabs (empty)
- ✅ Dialog can be closed

**Deliverable:** Empty Session Browser opens

---

#### Step 2: Active Sessions Tab (3-4 hours)

**Goal:** Implement Active tab with lock status, progress, and resume action

**Tasks:**
1. Implement `active_sessions_tab.py`:
   - Create UI layout (scrollable area)
   - Implement `load_active_sessions()` method:
     - Use ProfileManager.get_incomplete_sessions()
     - Check lock status via SessionLockManager
     - Distinguish active/stale/paused
   - Create session card widgets:
     - `ActiveSessionCard` - for locked sessions
     - `StaleSessionCard` - for stale locks
     - `PausedSessionCard` - for unlocked
2. Implement progress calculation:
   - Find and load packing_state.json
   - Calculate X/Y orders
   - Show progress bar
3. Implement actions:
   - Resume button → emit signal
   - Force Unlock button → confirm, force-release, emit signal
   - View Details button → placeholder (implement later)
4. Connect signals to main.py:
   - `resume_session_requested` → `_handle_resume_session()`
5. Add refresh functionality

**Testing:**
- ✅ Active tab loads all incomplete sessions
- ✅ Lock status correctly displayed (active/stale/paused)
- ✅ Progress bars show correct X/Y
- ✅ Resume button works (starts session)
- ✅ Force unlock works for stale locks
- ✅ Refresh updates list

**Deliverable:** Can see and resume active sessions

---

#### Step 3: Completed Sessions Tab (3-4 hours)

**Goal:** Implement Completed tab with search, filters, and metrics

**Tasks:**
1. Implement `completed_sessions_tab.py`:
   - Create UI layout:
     - Client filter dropdown
     - Date range dropdown (7/30/90 days, All)
     - Search box
     - Scrollable card area
   - Implement `load_completed_sessions()`:
     - Use SessionHistoryManager.get_client_sessions()
     - Filter: include_incomplete=False
     - Apply date range filter
   - Create `CompletedSessionCard`:
     - Session ID, client, worker
     - Completion time, duration
     - Orders count, metrics
     - Actions: View Details, Export
2. Implement search functionality:
   - Filter by session ID, PC name, list path
3. Implement filters:
   - Client dropdown
   - Date range dropdown
4. Implement actions:
   - View Details → SessionDetailsDialog (placeholder for now)
   - Export → Single session export (Excel/PDF)
5. Add refresh button

**Testing:**
- ✅ Completed tab loads all completed sessions
- ✅ Search filters correctly
- ✅ Date range filter works
- ✅ Client filter works
- ✅ Session cards show correct metrics
- ✅ Refresh updates list

**Deliverable:** Can browse completed sessions with search/filters

---

#### Step 4: Available Sessions Tab (2-3 hours)

**Goal:** Implement Available tab to show Shopify sessions with unstarted packing lists

**Tasks:**
1. Implement `available_sessions_tab.py`:
   - Create UI layout:
     - Client filter
     - Scrollable card area
   - Implement `scan_available_sessions()` (NEW LOGIC):
     - Scan Sessions/CLIENT_*/
     - Find sessions with packing_lists/ directory
     - For each session:
       - List JSON files in packing_lists/
       - Check if packing/{name}/ exists
       - If NOT exists → available
     - Load JSON to get order counts
   - Create `AvailableSessionCard`:
     - Session ID, client
     - List of available packing lists
     - For each list:
       - Name, order count, item count
       - Start Packing button
2. Implement actions:
   - Start Packing button → emit signal
3. Connect signals to main.py:
   - `start_packing_requested` → `_handle_start_packing()`
4. Implement refresh

**Testing:**
- ✅ Available tab scans for Shopify sessions
- ✅ Shows only sessions with unstarted lists
- ✅ Displays order/item counts correctly
- ✅ Start Packing button works
- ✅ Creates work directory and starts session
- ✅ Refresh updates list

**Deliverable:** Can start new packing from Shopify sessions

---

#### Step 5: Session Details Dialog (3-4 hours)

**Goal:** Create detailed view showing all session information

**Tasks:**
1. Create `session_details_dialog.py`:
   - Dialog with QTabWidget (4 tabs)
   - Tab 1: Overview
     - Session metadata (ID, client, worker, PC)
     - Timing (started, completed, duration)
     - Status, lock info
   - Tab 2: Metrics
     - Orders: total/completed/skipped
     - Items: total
     - Performance rates (orders/hr, items/hr)
     - Averages
   - Tab 3: Orders (Phase 2b)
     - Tree widget showing orders list
     - Expandable items within each order
     - Show SKU, name, timestamps, durations
   - Tab 4: Timeline (Optional - Phase 3.5)
     - Visual timeline/chart of order progression
     - Can be placeholder for now
2. Implement data loading:
   - For completed sessions:
     - Use SessionHistoryManager.get_session_details()
     - Load session_summary.json for Phase 2b data
   - For active/paused sessions:
     - Load session_info.json
     - Load packing_state.json
     - Load lock_info
3. Implement export actions:
   - Export to PDF
   - Export to Excel
4. Connect from tabs:
   - Active tab: View Details → open dialog
   - Completed tab: View Details → open dialog

**Testing:**
- ✅ Dialog opens from both Active and Completed tabs
- ✅ Overview shows correct metadata
- ✅ Metrics calculated correctly
- ✅ Orders tab shows Phase 2b data (if available)
- ✅ Export works (Excel/PDF)

**Deliverable:** Detailed view of any session

---

#### Step 6: Integration & Testing (2-3 hours)

**Goal:** Finalize integration, remove old components, test all workflows

**Tasks:**
1. Remove old components from main.py:
   - Remove `self.restore_session_button`
   - Remove `open_restore_session_dialog()` method
   - Remove `self.session_monitor_button` (if exists)
   - Remove `open_session_monitor()` method
2. Update toolbar layout:
   - Position Session Browser button prominently
   - Keep History Browser as separate tool
3. Test all workflows:
   - Resume active session
   - Force-unlock stale session
   - Start packing from available list
   - View completed session details
   - Search and filter completed sessions
   - Export session data
4. Test edge cases:
   - No incomplete sessions
   - No completed sessions
   - No available sessions
   - Lock conflicts
   - Stale lock confirmation
   - Network errors (file server unavailable)
5. Code cleanup:
   - Remove unused imports
   - Add docstrings
   - Code review
6. Documentation:
   - Update user manual (if exists)
   - Add comments explaining new workflows

**Testing Checklist:**
- ✅ All 3 tabs load without errors
- ✅ Active tab shows correct lock status
- ✅ Resume workflow works end-to-end
- ✅ Force unlock works for stale locks
- ✅ Completed tab search/filters work
- ✅ Available tab shows only unstarted lists
- ✅ Start Packing creates work dir and starts session
- ✅ Session Details dialog shows correct info
- ✅ Export works (Excel/PDF)
- ✅ Refresh buttons work on all tabs
- ✅ Client filters work on all tabs
- ✅ No crashes or exceptions
- ✅ Old Restore Session dialog removed
- ✅ Old Session Monitor removed

**Deliverable:** Session Browser fully integrated and tested

---

### Time Estimates Summary

| Step | Description | Estimated Time |
|------|-------------|----------------|
| 1 | Core Infrastructure | 2-3 hours |
| 2 | Active Sessions Tab | 3-4 hours |
| 3 | Completed Sessions Tab | 3-4 hours |
| 4 | Available Sessions Tab | 2-3 hours |
| 5 | Session Details Dialog | 3-4 hours |
| 6 | Integration & Testing | 2-3 hours |
| **Total** | | **15-21 hours** |

**Realistic Estimate:** 2-3 days of focused development

**Buffer for unknowns:** +5 hours

**Total with buffer:** 20-26 hours (3-4 days)

---

### Dependencies and Order

**Must complete in order:**
1. Step 1 (Core) → Required for all other steps
2. Steps 2, 3, 4 (Tabs) → Can be done in parallel or any order
3. Step 5 (Details Dialog) → Depends on Step 3 (uses SessionHistoryManager data)
4. Step 6 (Integration) → Final step after all features complete

**Parallel work possible:**
- Active, Completed, and Available tabs can be developed simultaneously
- Details Dialog can be started after Completed tab is functional

---

## PART 7: NEXT STEPS

### Immediate Actions (Phase 3 Preparation)

1. **Review This Audit** ✅
   - Verify all information is accurate
   - Clarify any unclear sections
   - Confirm architectural decisions

2. **Create Phase 3 Implementation Prompt**
   - Based on this audit
   - Step-by-step instructions
   - Include code templates

3. **Set Up Development Environment**
   - Ensure all dependencies installed
   - Test existing components work
   - Prepare test data (sessions with various states)

4. **Backup Current Code**
   - Commit current v1.3.0 state to git
   - Create Phase 3 branch: `feature/session-browser`
   - Tag current state: `v1.3.0-pre-phase-3`

5. **Create Test Sessions**
   - Active session (locked, with progress)
   - Stale session (old lock, no heartbeat)
   - Paused session (session_info.json, no lock)
   - Completed session (session_summary.json)
   - Available Shopify session (packing_lists/ but no packing/)

### Phase 3 Execution Plan

**Week 1:**
- Day 1: Core infrastructure + Active Sessions Tab (Steps 1-2)
- Day 2: Completed Sessions Tab (Step 3)
- Day 3: Available Sessions Tab (Step 4)

**Week 2:**
- Day 1: Session Details Dialog (Step 5)
- Day 2-3: Integration, testing, bug fixes (Step 6)

**Milestone:** Session Browser v1.0 Complete

### Post-Phase 3 (Future Enhancements)

**Phase 3.5: Advanced Features (Optional)**
- Timeline visualization in Details Dialog
- Batch operations (export multiple sessions)
- Session comparison (compare 2 sessions side-by-side)
- Advanced analytics (trends, worker performance)
- Session archiving (move old sessions to archive/)

**Phase 4: Mobile/Web View (Future)**
- Read-only Session Browser accessible from mobile/web
- Monitor active sessions from any device
- View session history remotely

---

## CONCLUSION

### Audit Summary

This comprehensive audit has analyzed all existing session management infrastructure and defined a complete architecture for the **Session Browser** feature in v1.3.0.

**Key Achievements:**
- ✅ **Existing Components Documented:** SessionHistoryManager, SessionManager, SessionLockManager all fully analyzed
- ✅ **UI Components Reviewed:** SessionHistoryWidget, DashboardWidget, SessionMonitorWidget, RestoreSessionDialog
- ✅ **Data Sources Mapped:** Clear understanding of how to access active, completed, and available session data
- ✅ **Architecture Defined:** Complete component structure for all 3 tabs + details dialog
- ✅ **Integration Points Identified:** Signals, slots, and workflow in main.py
- ✅ **Implementation Roadmap Created:** 6 steps with time estimates (15-21 hours)

**Readiness for Phase 3:** ✅ **READY**

All prerequisites are in place. The foundation is solid, the architecture is clear, and the implementation path is well-defined. Phase 3 can begin immediately.

**Estimated Completion Time:** 3-4 days of focused development

**Risk Assessment:** **LOW**
- All required components exist and are working
- Data sources are accessible and well-structured
- Similar UI patterns exist (SessionHistoryWidget, SessionMonitorWidget) as reference
- Integration points are clear and straightforward

**Recommendation:** Proceed with Phase 3 implementation following this audit as the blueprint.

---

**Status:** ✅ **AUDIT COMPLETE - READY FOR PHASE 3**

**Next:** Create detailed Phase 3 implementation prompt and begin development.

---

**Document Version:** 1.0
**Date:** 2025-11-20
**Author:** Phase 3 Prerequisites Audit
**Approved for:** Session Browser Implementation (Phase 3)
