# PHASE 3.2 AUDIT REPORT
**Comprehensive Review of Phase 3.1 + Data Structures for Phase 3.2**

Generated: 2025-11-20
Branch: `claude/audit-phase-3-01C4idvvfu978yaVKdN6Pv6h`

---

## EXECUTIVE SUMMARY

**Phase 3.1 Status:** ✅ **SUCCESSFULLY IMPLEMENTED**

- Session Browser widget with 2 tabs (Active, Completed) created and integrated
- 3 new files: `session_browser_widget.py`, `active_sessions_tab.py`, `completed_sessions_tab.py`
- Integrated into main.py with toolbar button and signal handling
- Old Restore Session dialog still present (not removed)
- **No dedicated tests created** (tests/test_session_browser* not found)
- Total code: ~2,992 lines in Phase 3.1 components

**Phase 3.2 Requirements:**
1. **Available Sessions Tab** - Show Shopify sessions with packing_lists/*.json but no work dirs
2. **Session Details Dialog** - Detailed view with orders tree, items, metrics tabs
3. Both require deep understanding of data structures documented below

---

## PART 1: PHASE 3.1 IMPLEMENTATION REVIEW

### 1.1 Files Created/Modified

**Created Files:**
```
src/session_browser/
├── __init__.py              (452 bytes)  - Package initialization
├── session_browser_widget.py (3.9 KB)    - Main container with tabs
├── active_sessions_tab.py    (16 KB)     - Active sessions with lock status
└── completed_sessions_tab.py (12 KB)     - Session history with filters
```

**Modified Files:**
- `src/main.py` - Added Session Browser integration:
  - Line 43: Import `SessionBrowserWidget`
  - Line 259-263: Added `session_browser_button` to toolbar
  - Line 1683-1713: Added `open_session_browser()` method
  - Line 1715-1764: Added `_handle_resume_session_from_browser()` handler

**NOT Created:**
- ❌ `tests/test_session_browser.py` - No tests exist for Session Browser

---

### 1.2 Code Structure Analysis

#### A. `session_browser_widget.py` (129 lines)

**Class:** `SessionBrowserWidget(QWidget)`

**Purpose:** Main container for tabbed session browsing interface

**Signals Defined:**
```python
resume_session_requested = Signal(dict)  # {session_path, client_id, packing_list_name}
session_selected = Signal(dict)          # Generic session selection
```

**Manager Dependencies (passed to __init__):**
- `profile_manager` - For client/session paths
- `session_manager` - For loading packing lists
- `session_lock_manager` - For lock operations
- `session_history_manager` - For completed sessions
- `worker_manager` - For worker display names

**Tab Initialization:**
```python
# Active tab
self.active_tab = ActiveSessionsTab(
    profile_manager=self.profile_manager,
    session_lock_manager=self.session_lock_manager,
    worker_manager=self.worker_manager,
    parent=self
)

# Completed tab
self.completed_tab = CompletedSessionsTab(
    profile_manager=self.profile_manager,
    session_history_manager=self.session_history_manager,
    parent=self
)

# Available tab - Phase 3.2 (commented out)
# self.available_tab = AvailableSessionsTab(...)
```

**Key Methods:**
- `_connect_signals()` - Wire up tab signals to handlers
- `_handle_resume_request(session_info: dict)` - Relay resume signal to main.py
- `refresh_all()` - Refresh all tabs
- `set_current_tab(tab_name: str)` - Switch tabs programmatically

---

#### B. `active_sessions_tab.py` (422 lines)

**Class:** `ActiveSessionsTab(QWidget)`

**Purpose:** Display in-progress sessions with lock status classification

**Signals:**
```python
resume_requested = Signal(dict)  # Emitted when user clicks Resume
```

**Data Scanning Logic:**

**Session Discovery Algorithm (lines 96-202):**
```python
def refresh(self):
    # 1. Get Sessions base path from ProfileManager
    sessions_base = self.profile_manager.get_sessions_root()

    # 2. Scan CLIENT_* directories
    for client_dir in sessions_base.iterdir():
        if not client_dir.name.startswith("CLIENT_"):
            continue

        client_id = client_dir.name.replace("CLIENT_", "")

        # 3. Scan session directories (e.g., 2025-11-20_1)
        for session_dir in client_dir.iterdir():
            session_id = session_dir.name
            packing_dir = session_dir / "packing"

            if not packing_dir.exists():
                continue

            # 4. Scan each packing list work directory
            for work_dir in packing_dir.iterdir():
                packing_list_name = work_dir.name

                # 5. Check lock status
                is_locked, lock_info = self.session_lock_manager.is_locked(session_dir)

                # 6. Classify: Active/Stale/Paused
                if is_locked and lock_info:
                    status = self._classify_lock_status(lock_info)  # Active or Stale
                elif (session_dir / "session_info.json").exists():
                    status = "Paused"

                # 7. Get progress from packing_state.json
                progress = self._get_progress(work_dir)

                # 8. Store session data
                self.sessions.append({...})
```

**Lock Status Classification (lines 204-225):**
```python
def _classify_lock_status(self, lock_info: dict) -> str:
    """Classify lock as Active or Stale based on heartbeat."""
    last_heartbeat = lock_info.get('heartbeat')

    if not last_heartbeat:
        return 'Stale'

    # Parse timestamp
    heartbeat_time = parse_timestamp(last_heartbeat)
    now = datetime.now(timezone.utc)

    age_minutes = (now - heartbeat_time).total_seconds() / 60

    # Active if heartbeat < 5 minutes old
    return 'Active' if age_minutes < 5 else 'Stale'
```

**Progress Extraction (lines 248-267):**
```python
def _get_progress(self, work_dir: Path) -> dict:
    """Get packing progress from packing_state.json."""
    state_file = work_dir / "packing_state.json"

    if not state_file.exists():
        return {'completed': 0, 'total': 0}

    with open(state_file, 'r') as f:
        state = json.load(f)

    data = state.get('data', {})
    orders = data.get('orders', [])
    completed = sum(1 for o in orders if o.get('status') == 'completed')

    return {'completed': completed, 'total': len(orders)}
```

**Table Columns:**
1. Session ID
2. Client
3. Packing List
4. Status (Active/Stale/Paused with color coding)
5. Worker (display name from WorkerManager)
6. PC
7. Lock Age (in minutes)
8. Orders Progress (completed/total)

**Action Buttons:**
- `Resume Session` - Emits `resume_requested` signal
- `Force Unlock` - Calls `session_lock_manager.force_release_lock()`
- `View Details` - TODO: Phase 3.2 (currently shows MessageBox)

**Lock Validation Logic (lines 326-360):**
```python
def _on_resume(self):
    """Handle Resume button click."""
    session = self.sessions[selected]

    # Check if locked by another PC
    if session['is_locked']:
        lock_info = session['lock_info']
        current_pc = self.session_lock_manager.hostname

        if lock_info.get('locked_by') != current_pc:
            QMessageBox.warning(
                self, "Session Locked",
                f"This session is locked by {lock_info.get('locked_by')}.\n"
                f"Use 'Force Unlock' if the session is stale."
            )
            return

    # Emit signal to main.py
    self.resume_requested.emit({
        'session_path': session['session_path'],
        'client_id': session['client_id'],
        'packing_list_name': session['packing_list_name'],
        'work_dir': session['work_dir'],
        'lock_info': session.get('lock_info'),
        'session_info': session.get('session_info')
    })
```

---

#### C. `completed_sessions_tab.py` (331 lines)

**Class:** `CompletedSessionsTab(QWidget)`

**Purpose:** Display historical completed sessions with filtering and export

**Signals:**
```python
session_selected = Signal(dict)  # Emitted when viewing session details
```

**SessionHistoryManager Integration:**

**Data Loading (lines 143-215):**
```python
def refresh(self):
    # Get filters
    selected_client = self.client_combo.currentData()
    date_from = datetime(qdate_from.year(), qdate_from.month(), qdate_from.day())
    date_to = datetime(qdate_to.year(), qdate_to.month(), qdate_to.day(), 23, 59, 59)
    search_term = self.search_input.text().strip()

    # Get sessions from SessionHistoryManager
    if selected_client:
        sessions = self.session_history_manager.get_client_sessions(
            client_id=selected_client,
            start_date=date_from,
            end_date=date_to,
            include_incomplete=False  # Only completed
        )
    else:
        # Get for all clients
        sessions = []
        for client_id in self.profile_manager.list_clients():
            client_sessions = self.session_history_manager.get_client_sessions(
                client_id=client_id,
                start_date=date_from,
                end_date=date_to,
                include_incomplete=False
            )
            sessions.extend(client_sessions)

    # Apply search filter
    if search_term:
        # Filter by search_field (Session ID, Client ID, Worker, Packing List)
        ...

    self.sessions = sessions
    self._populate_table()
```

**Filter Implementation:**
- **Client Filter:** ComboBox with "All Clients" + list from `profile_manager.list_clients()`
- **Date Range:** QDateEdit with calendar popup (default: last month to today)
- **Search:** QLineEdit with field selector (All Fields, Session ID, Client ID, Worker, Packing List)

**Table Structure (9 columns):**
1. Session ID
2. Client
3. Packing List (extracted from path)
4. Worker (pc_name for now)
5. Start Time (YYYY-MM-DD HH:MM)
6. Duration (Xh Ym format)
7. Orders (completed/total)
8. Items (total_items_packed)
9. Status (✅ Complete or ⚠️ Incomplete)

**Export Functionality:**

**Excel Export (lines 269-301):**
```python
def _export_excel(self):
    """Export sessions to Excel."""
    # Ask for save location
    filepath, _ = QFileDialog.getSaveFileName(
        self, "Export to Excel",
        "completed_sessions.xlsx",
        "Excel Files (*.xlsx)"
    )

    # Convert sessions to dict
    data = self.session_history_manager.export_sessions_to_dict(self.sessions)

    # Create DataFrame
    df = pd.DataFrame(data)

    # Write to Excel
    df.to_excel(filepath, index=False, sheet_name="Completed Sessions")

    QMessageBox.information(self, "Success", f"Exported {len(self.sessions)} sessions")
```

**PDF Export:** Placeholder (lines 303-306) - "Not Implemented" message

**View Details Button:** TODO Phase 3.2 - Currently shows basic MessageBox with summary

---

### 1.3 Integration with main.py

**Toolbar Button (lines 259-263):**
```python
self.session_browser_button = QPushButton("Session Browser")
self.session_browser_button.clicked.connect(self.open_session_browser)
self.session_browser_button.setStyleSheet("background-color: #2196F3; color: white;")
self.session_browser_button.setToolTip("Browse active, completed, and available sessions")
control_layout.addWidget(self.session_browser_button)
```

**Button State Management:**
- **Disabled during packing:** Line 1649 - `self.session_browser_button.setEnabled(False)`
- **Enabled when idle:** Line 957 - `self.session_browser_button.setEnabled(True)`

**Dialog Creation (lines 1683-1713):**
```python
def open_session_browser(self):
    """Open Session Browser dialog."""
    logger.info("Opening Session Browser")

    # Create dialog
    browser_dialog = QDialog(self)
    browser_dialog.setWindowTitle("Session Browser")
    browser_dialog.resize(1200, 700)
    browser_dialog.setModal(False)  # Non-modal - can keep open while working

    layout = QVBoxLayout(browser_dialog)

    # Create Session Browser widget
    browser = SessionBrowserWidget(
        profile_manager=self.profile_manager,
        session_manager=self.session_manager,
        session_lock_manager=self.lock_manager,
        session_history_manager=self.session_history_manager,
        worker_manager=self.worker_manager,
        parent=browser_dialog
    )

    # Connect signals
    browser.resume_session_requested.connect(
        lambda info: self._handle_resume_session_from_browser(browser_dialog, info)
    )

    layout.addWidget(browser)

    # Show dialog
    browser_dialog.exec()
```

**Resume Handler (lines 1715-1764):**
```python
def _handle_resume_session_from_browser(self, dialog, session_info: dict):
    """Handle resume request from Session Browser."""
    logger.info(f"Resuming session from browser: {session_info.get('session_id', 'Unknown')}")

    # Close browser dialog
    dialog.accept()

    # Extract info
    session_path = Path(session_info['session_path'])
    client_id = session_info['client_id']
    packing_list_name = session_info['packing_list_name']

    # Set current client if different
    if self.current_client_id != client_id:
        for i in range(self.client_combo.count()):
            if self.client_combo.itemData(i) == client_id:
                self.client_combo.setCurrentIndex(i)
                break

    # Create SessionManager for this client if not exists
    if not self.session_manager or self.session_manager.client_id != client_id:
        self.session_manager = SessionManager(
            client_id=client_id,
            profile_manager=self.profile_manager,
            lock_manager=self.lock_manager,
            worker_id=self.current_worker_id,
            worker_name=self.current_worker_name
        )

    # Load packing list
    packing_data = self.session_manager.load_packing_list(
        session_path=str(session_path),
        packing_list_name=packing_list_name
    )

    # Resume session (using existing method)
    self.start_shopify_packing_session(
        session_path=str(session_path),
        packing_list_name=packing_list_name,
        packing_data=packing_data,
        is_resume=True
    )
```

---

### 1.4 Old Restore Session Dialog Status

**Still Present:**
- ✅ `src/restore_session_dialog.py` - Still exists (not removed)
- ✅ Line 26 in main.py: `from restore_session_dialog import RestoreSessionDialog`
- ✅ Line 1335-1380: `open_restore_session_dialog()` method still present
- ✅ Line 2039-2095: `restore_session()` startup function still present

**Conclusion:** Old dialog NOT removed - Phase 3.1 adds Session Browser alongside existing Restore dialog

---

### 1.5 Testing Status

**Tests Created:** ❌ **NONE**

**Search Results:**
```bash
$ pytest tests/test_session_browser* -v
ERROR: file or directory not found: tests/test_session_browser*
```

**Existing Session-Related Tests:**
- `tests/test_session_history_manager.py` - Tests SessionHistoryManager
- `tests/test_session_summary.py` - Tests session summary generation
- `tests/test_session_lock_manager.py` - Tests lock mechanism
- `tests/test_session_manager.py` - Tests SessionManager
- `tests/test_session_selector.py` - Tests old session selector

**Recommendation:** Create `tests/test_session_browser.py` with tests for:
- Active tab lock classification
- Completed tab filtering
- Signal emissions
- UI state management

---

### 1.6 Issues Found

**✅ No Critical Issues**

**Minor TODOs:**
1. Line 410 in `active_sessions_tab.py` - "TODO: Open SessionDetailsDialog (Phase 3.2)"
2. Line 318 in `completed_sessions_tab.py` - "TODO: Open SessionDetailsDialog (Phase 3.2)"
3. Line 306 in `completed_sessions_tab.py` - PDF export not implemented

**Code Quality:** ✅ Good
- Proper error handling
- Logging present
- Type hints used
- Signal-based architecture

---

## PART 2: AVAILABLE SESSIONS TAB DATA

### 2.1 Shopify Session Structure

**Directory Layout:**
```
Sessions/
└── CLIENT_M/
    └── 2025-11-20_1/               # Shopify session
        ├── session_info.json       # Session metadata
        ├── .session.lock           # Lock file (if active)
        │
        ├── analysis/               # Created by Shopify Tool
        │   └── analysis_data.json
        │
        ├── packing_lists/          # Created by Shopify Tool
        │   ├── DHL_Orders.json     # ← Available for packing
        │   ├── PostOne_Orders.json # ← Available for packing
        │   └── ...
        │
        └── packing/                # Created by Packing Tool (Phase 1)
            ├── DHL_Orders/         # ← Work directory (started)
            │   ├── packing_state.json
            │   ├── session_summary.json
            │   ├── barcodes/
            │   └── reports/
            │
            └── PostOne_Orders/     # ← Work directory (started)
                └── ...
```

**Key Concept:**
- **Available Session:** Has `packing_lists/*.json` but NO corresponding `packing/{list_name}/` directory
- **Started Session:** Has both `packing_lists/{name}.json` AND `packing/{name}/` directory

---

### 2.2 packing_lists/*.json Format

**Source:** Shopify Tool output (documented in `docs/API.md`)

**Complete Structure:**
```json
{
  "list_name": "DHL_Orders",
  "created_at": "2025-11-19T10:00:00",
  "courier": "DHL",
  "total_orders": 25,
  "total_items": 87,
  "orders": [
    {
      "order_number": "ORDER-12345",
      "customer_name": "John Doe",
      "courier": "DHL",
      "address": "123 Main St, City",
      "phone": "+1234567890",
      "items": [
        {
          "sku": "PROD-001",
          "title": "Product Name",
          "quantity": 2,
          "barcode": "1234567890123"
        },
        {
          "sku": "PROD-002",
          "title": "Another Product",
          "quantity": 1,
          "barcode": "9876543210987"
        }
      ]
    },
    {
      "order_number": "ORDER-12346",
      "customer_name": "Jane Smith",
      "courier": "DHL",
      "items": [...]
    }
  ]
}
```

**Key Fields:**
- **list_name** (str) - Name of the packing list (e.g., "DHL_Orders")
- **created_at** (str) - ISO 8601 timestamp
- **courier** (str) - Courier name (DHL, PostOne, etc.)
- **total_orders** (int) - Number of orders in the list
- **total_items** (int) - Total items across all orders
- **orders** (list) - Array of order objects

**Order Object Fields:**
- **order_number** (str) - Unique order identifier
- **customer_name** (str) - Customer name
- **courier** (str) - Shipping method
- **address** (str) - Shipping address (optional)
- **phone** (str) - Phone number (optional)
- **items** (list) - Array of item objects

**Item Object Fields:**
- **sku** (str) - Product SKU
- **title** (str) - Product description
- **quantity** (int) - Number of items
- **barcode** (str) - Product barcode (optional)

---

### 2.3 SessionManager Methods

**Relevant Methods for Available Sessions Tab:**

#### `load_packing_list(session_path: str, packing_list_name: str) -> dict`

**Location:** `src/session_manager.py:563-643`

**Signature:**
```python
def load_packing_list(self, session_path: str, packing_list_name: str) -> dict:
    """
    Load packing list JSON from Shopify session.

    Args:
        session_path: Full path to Shopify session
                     (e.g., "\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-10_1")
        packing_list_name: Name of packing list (e.g., "DHL_Orders")
                          Can be with or without .json extension

    Returns:
        dict: Packing list data containing:
            - session_id: Session identifier
            - report_name: Name of the report
            - created_at: Timestamp of creation
            - total_orders: Number of orders in the list
            - total_items: Total number of items
            - filters_applied: Filters used to generate the list
            - orders: List of order dictionaries

    Raises:
        FileNotFoundError: If packing list doesn't exist
        json.JSONDecodeError: If JSON is malformed
        KeyError: If 'orders' key missing
    """
```

**Example Usage:**
```python
packing_data = session_manager.load_packing_list(
    session_path="\\\\server\\...\\Sessions\\CLIENT_M\\2025-11-20_1",
    packing_list_name="DHL_Orders"
)

# Returns:
{
    "list_name": "DHL_Orders",
    "created_at": "2025-11-20T10:00:00",
    "total_orders": 25,
    "total_items": 87,
    "orders": [...]
}
```

---

#### `get_packing_work_dir(session_path: str, packing_list_name: str) -> Path`

**Location:** `src/session_manager.py:645-696`

**Signature:**
```python
def get_packing_work_dir(self, session_path: str, packing_list_name: str) -> Path:
    """
    Get or create working directory for packing results.

    Creates a working directory structure for a specific packing list
    within the Shopify session. This directory will contain:
    - barcodes: Generated barcode images and packing state
    - reports: Completed packing reports

    Directory structure created:
        session_path/packing/{packing_list_name}/
            barcodes/
            reports/

    Args:
        session_path: Full path to Shopify session
        packing_list_name: Name of packing list (without extension)

    Returns:
        Path: Working directory path
             Example: Path("...\\2025-11-20_1\\packing\\DHL_Orders")
    """
```

**Key Behavior:**
- Creates directory if it doesn't exist
- Creates subdirectories: `barcodes/` and `reports/`
- Removes `.json` extension from packing_list_name if present

---

### 2.4 Scanning Logic for Available Sessions Tab

**Pseudocode:**
```python
def scan_available_sessions(self, client_id: str = None):
    """
    Find Shopify sessions with packing lists that haven't been started.

    Returns list of available packing lists across all sessions.
    """
    available_sessions = []

    # 1. Get Sessions base path
    sessions_base = self.profile_manager.get_sessions_root()

    # 2. Scan CLIENT_* directories
    for client_dir in sessions_base.iterdir():
        if not client_dir.name.startswith("CLIENT_"):
            continue

        client = client_dir.name.replace("CLIENT_", "")

        # Filter by client if specified
        if client_id and client != client_id:
            continue

        # 3. Scan session directories
        for session_dir in client_dir.iterdir():
            if not session_dir.is_dir():
                continue

            session_id = session_dir.name

            # 4. Check for packing_lists/ directory
            packing_lists_dir = session_dir / "packing_lists"
            if not packing_lists_dir.exists():
                continue

            # 5. Check for packing/ directory
            packing_dir = session_dir / "packing"

            # 6. Scan each .json file in packing_lists/
            for json_file in packing_lists_dir.glob("*.json"):
                list_name = json_file.stem  # Remove .json extension

                # 7. Check if work directory exists
                work_dir = packing_dir / list_name if packing_dir.exists() else None

                if not work_dir or not work_dir.exists():
                    # This packing list is AVAILABLE (not started)

                    # 8. Load packing list data
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            packing_data = json.load(f)

                        available_sessions.append({
                            'session_id': session_id,
                            'client_id': client,
                            'session_path': str(session_dir),
                            'packing_list_name': list_name,
                            'packing_list_path': str(json_file),
                            'courier': packing_data.get('courier', 'Unknown'),
                            'created_at': packing_data.get('created_at'),
                            'total_orders': packing_data.get('total_orders', 0),
                            'total_items': packing_data.get('total_items', 0),
                        })

                    except Exception as e:
                        logger.warning(f"Failed to load {json_file}: {e}")
                        continue

    return available_sessions
```

**Table Columns for Available Sessions Tab:**
1. Session ID (e.g., "2025-11-20_1")
2. Client (e.g., "CLIENT_M")
3. Packing List (e.g., "DHL_Orders")
4. Courier (e.g., "DHL", "PostOne")
5. Created At (timestamp)
6. Orders (total_orders count)
7. Items (total_items count)
8. Action: "Start Packing" button

---

## PART 3: SESSION DETAILS DIALOG DATA

### 3.1 session_summary.json Structure (Phase 2b)

**File Location:** `work_dir/session_summary.json`
**Format Version:** v1.3.0
**Generated by:** `PackerLogic.generate_session_summary()` (lines 1587-1780)

**Complete Structure:**
```json
{
  "version": "1.3.0",
  "session_id": "2025-11-20_1",
  "session_type": "shopify",
  "client_id": "M",
  "packing_list_name": "DHL_Orders",

  "worker_id": "worker_001",
  "worker_name": "Dolphin",
  "pc_name": "WAREHOUSE-PC-01",

  "started_at": "2025-11-20T10:00:00+02:00",
  "completed_at": "2025-11-20T14:00:00+02:00",
  "duration_seconds": 14400,

  "total_orders": 50,
  "completed_orders": 50,
  "total_items": 185,
  "unique_skus": 42,

  "metrics": {
    "avg_time_per_order": 288.0,
    "avg_time_per_item": 77.8,
    "fastest_order_seconds": 120,
    "slowest_order_seconds": 450,
    "orders_per_hour": 12.5,
    "items_per_hour": 46.25
  },

  "orders": [
    {
      "order_number": "ORDER-12345",
      "started_at": "2025-11-20T10:05:00+02:00",
      "completed_at": "2025-11-20T10:08:30+02:00",
      "duration_seconds": 210,
      "items_count": 3,
      "items": [
        {
          "sku": "PROD-001",
          "quantity": 2,
          "scanned_at": "2025-11-20T10:05:15+02:00",
          "time_from_order_start_seconds": 15
        },
        {
          "sku": "PROD-002",
          "quantity": 1,
          "scanned_at": "2025-11-20T10:06:30+02:00",
          "time_from_order_start_seconds": 90
        }
      ]
    },
    {
      "order_number": "ORDER-12346",
      "started_at": "2025-11-20T10:08:35+02:00",
      "completed_at": "2025-11-20T10:13:20+02:00",
      "duration_seconds": 285,
      "items_count": 5,
      "items": [...]
    }
  ]
}
```

**Key Fields - Metadata:**
- **version** (str) - Format version "1.3.0"
- **session_id** (str) - Session identifier
- **session_type** (str) - "shopify" or "excel"
- **client_id** (str) - Client identifier
- **packing_list_name** (str) - Name of packing list

**Key Fields - Worker Info:**
- **worker_id** (str) - Worker ID (e.g., "worker_001")
- **worker_name** (str) - Display name (e.g., "Dolphin")
- **pc_name** (str) - Computer name

**Key Fields - Timing:**
- **started_at** (str) - ISO 8601 timestamp with timezone
- **completed_at** (str) - ISO 8601 timestamp with timezone
- **duration_seconds** (int) - Total session duration

**Key Fields - Counts:**
- **total_orders** (int) - Total orders in session
- **completed_orders** (int) - Orders completed
- **total_items** (int) - Total items packed
- **unique_skus** (int) - Number of unique SKUs

**Key Fields - Metrics:**
- **avg_time_per_order** (float) - Average seconds per order
- **avg_time_per_item** (float) - Average seconds per item
- **fastest_order_seconds** (int) - Fastest order duration
- **slowest_order_seconds** (int) - Slowest order duration
- **orders_per_hour** (float) - Orders per hour rate
- **items_per_hour** (float) - Items per hour rate

**Key Fields - Orders Array:**
- **orders** (list) - Array of order timing objects (Phase 2b)

---

### 3.2 orders[] Array Format (Phase 2b)

**Order Object Structure:**
```json
{
  "order_number": "ORDER-12345",
  "started_at": "2025-11-20T10:05:00+02:00",
  "completed_at": "2025-11-20T10:08:30+02:00",
  "duration_seconds": 210,
  "items_count": 3,
  "items": [
    {
      "sku": "PROD-001",
      "quantity": 2,
      "scanned_at": "2025-11-20T10:05:15+02:00",
      "time_from_order_start_seconds": 15
    }
  ]
}
```

**Order Fields:**
- **order_number** (str) - Order identifier
- **started_at** (str) - When first item scanned (ISO 8601)
- **completed_at** (str) - When order completed (ISO 8601)
- **duration_seconds** (int) - Time from start to completion
- **items_count** (int) - Number of items in order
- **items** (list) - Array of scanned items

**Item Fields:**
- **sku** (str) - Product SKU
- **quantity** (int) - Number of items scanned
- **scanned_at** (str) - Timestamp when scanned
- **time_from_order_start_seconds** (int) - Seconds since order start

**Note:** According to Phase 2b audit (PHASE_2B_AUDIT_REPORT.md):
- ✅ **orders[] array is populated** with timing data for completed sessions
- ✅ Stored by PackerLogic in `self.completed_orders_metadata`
- ✅ Included in session_summary.json via line 1771:
  ```python
  "orders": self.completed_orders_metadata if hasattr(self, 'completed_orders_metadata') else []
  ```

---

### 3.3 packing_state.json Structure

**File Location:** `work_dir/packing_state.json`
**Generated by:** `PackerLogic._save_session_state()` (lines 347-460)

**Purpose:** Real-time progress tracking (saved after every scan)

**Complete Structure:**
```json
{
  "version": "1.3.0",

  "session_id": "2025-11-20_1",
  "client_id": "M",
  "packing_list_name": "DHL_Orders",
  "started_at": "2025-11-20T10:00:00+02:00",
  "last_updated": "2025-11-20T12:30:45+02:00",
  "status": "in_progress",
  "pc_name": "WAREHOUSE-PC-01",

  "progress": {
    "total_orders": 50,
    "completed_orders": 25,
    "in_progress_order": "ORDER-12350",
    "total_items": 185,
    "packed_items": 92
  },

  "in_progress": {
    "ORDER-12350": [
      {
        "sku": "PROD-001",
        "expected": 2,
        "packed": 1,
        "status": "partial"
      },
      {
        "sku": "PROD-002",
        "expected": 1,
        "packed": 0,
        "status": "pending"
      }
    ],
    "_timing": {
      "current_order_start_time": "2025-11-20T12:25:00+02:00",
      "items_scanned": [
        {
          "sku": "PROD-001",
          "quantity": 1,
          "scanned_at": "2025-11-20T12:26:15+02:00"
        }
      ]
    }
  },

  "completed": [
    {
      "order_number": "ORDER-12345",
      "completed_at": "2025-11-20T10:08:30+02:00",
      "items_count": 3,
      "duration_seconds": 210
    },
    {
      "order_number": "ORDER-12346",
      "completed_at": "2025-11-20T10:13:20+02:00",
      "items_count": 5,
      "duration_seconds": 285
    }
  ]
}
```

**Key Differences from session_summary.json:**
- **Real-time updates** - Saved after every scan
- **In-progress data** - Shows current order being packed
- **Partial completion** - Shows items partially scanned
- **Timing metadata** - Includes `_timing` object for current order

---

### 3.4 session_info.json Structure

**File Location:** `session_dir/session_info.json`
**Generated by:** `SessionManager.start_session()` (lines 271-285)

**Purpose:** Session metadata for crash recovery

**Structure:**
```json
{
  "client_id": "M",
  "packing_list_path": "\\\\server\\...\\packing_lists\\DHL_Orders.json",
  "started_at": "2025-11-20T10:00:00",
  "pc_name": "WAREHOUSE-PC-01",
  "packing_progress": {
    "DHL_Orders": {
      "started_at": "2025-11-20T10:00:00",
      "status": "in_progress",
      "updated_at": "2025-11-20T12:30:45"
    },
    "PostOne_Orders": {
      "started_at": "2025-11-20T14:00:00",
      "status": "completed",
      "updated_at": "2025-11-20T15:30:00"
    }
  }
}
```

**Key Fields:**
- **client_id** (str) - Client identifier
- **packing_list_path** (str) - Original Excel file path (for Excel workflow)
- **started_at** (str) - Session start timestamp
- **pc_name** (str) - Computer name from COMPUTERNAME env var
- **packing_progress** (dict) - Per-packing-list status tracking (Phase 1)

**Note:** This file is **deleted** on graceful session end. Its presence indicates an incomplete session.

---

### 3.5 SessionHistoryManager.get_session_details()

**Location:** `src/session_history_manager.py:571-640`

**Signature:**
```python
def get_session_details(
    self,
    client_id: str,
    session_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific session.

    Supports both Phase 1 (Shopify) and Legacy (Excel) structures.

    Args:
        client_id: Client identifier
        session_id: Session identifier

    Returns:
        Dictionary with detailed session information including packing state
        None if session not found
    """
```

**Implementation Logic:**
```python
def get_session_details(self, client_id, session_id):
    session_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}" / session_id

    if not session_dir.exists():
        return None

    # Find packing state file (supports both Phase 1 and Legacy structures)
    state_file = None

    # Try Phase 1 structure first (packing/{list_name}/packing_state.json)
    packing_dir = session_dir / "packing"
    if packing_dir.exists() and packing_dir.is_dir():
        for work_dir in packing_dir.iterdir():
            potential_state = work_dir / "packing_state.json"
            if potential_state.exists():
                state_file = potential_state
                break

    # Try Legacy structure (barcodes/packing_state.json)
    if not state_file:
        legacy_state = session_dir / "barcodes" / "packing_state.json"
        if legacy_state.exists():
            state_file = legacy_state

    if not state_file:
        return None

    # Load packing state
    with open(state_file, 'r', encoding='utf-8') as f:
        state_data = json.load(f)

    return state_data
```

**Returns:** Complete `packing_state.json` data (see section 3.3)

---

## PART 4: METRICS CALCULATION

### 4.1 Available Metrics in session_summary.json

**Pre-Calculated Metrics (in `metrics` object):**

✅ **Already Available:**
- `avg_time_per_order` (float) - Calculated from order-level timing data
- `avg_time_per_item` (float) - Calculated from item-level timing data
- `fastest_order_seconds` (int) - Min duration from orders[] array
- `slowest_order_seconds` (int) - Max duration from orders[] array
- `orders_per_hour` (float) - Calculated: completed_orders / (duration_seconds / 3600)
- `items_per_hour` (float) - Calculated: total_items / (duration_seconds / 3600)

**Top-Level Counts:**
- `total_orders` (int) - From packing list
- `completed_orders` (int) - From completed orders count
- `total_items` (int) - Sum of all item quantities
- `unique_skus` (int) - Count of unique SKUs

**Timing:**
- `started_at` (str) - Session start timestamp
- `completed_at` (str) - Session end timestamp
- `duration_seconds` (int) - Total session duration

---

### 4.2 Metrics to Calculate Manually

**For Session Details Dialog - Metrics Tab:**

Most metrics are **already calculated** in session_summary.json. Additional calculations:

**✅ From orders[] Array:**
```python
# Average items per order
total_items_in_orders = sum(order['items_count'] for order in orders)
avg_items_per_order = total_items_in_orders / len(orders)

# Order duration distribution
durations = [order['duration_seconds'] for order in orders]
median_order_time = statistics.median(durations)
std_dev_order_time = statistics.stdev(durations)

# Item scan time analysis
all_item_times = []
for order in orders:
    for item in order['items']:
        all_item_times.append(item['time_from_order_start_seconds'])

avg_item_scan_time = sum(all_item_times) / len(all_item_times)
median_item_scan_time = statistics.median(all_item_times)
```

**✅ From packing_state.json (for Active Sessions):**
```python
# Current progress percentage
progress_percent = (completed_orders / total_orders) * 100

# Items packed percentage
items_percent = (packed_items / total_items) * 100

# Estimated time remaining (based on current rate)
elapsed_seconds = (now - started_at).total_seconds()
orders_per_second = completed_orders / elapsed_seconds
remaining_orders = total_orders - completed_orders
estimated_remaining_seconds = remaining_orders / orders_per_second
```

---

### 4.3 PackerLogic Implementation

**Method:** `generate_session_summary()` (lines 1587-1780)

**Metrics Calculation Logic:**

**Phase 2b - With Timing Data:**
```python
if hasattr(self, 'completed_orders_metadata') and self.completed_orders_metadata:
    orders_with_timing = self.completed_orders_metadata

    # Extract durations
    durations = [
        order['duration_seconds']
        for order in orders_with_timing
        if order.get('duration_seconds')
    ]

    # Calculate order-level metrics
    if durations:
        avg_time_per_order = round(sum(durations) / len(durations), 1)
        fastest_order_seconds = min(durations)
        slowest_order_seconds = max(durations)

    # Calculate item-level metrics
    all_items = []
    for order in orders_with_timing:
        all_items.extend(order.get('items', []))

    if all_items:
        item_times = [
            item['time_from_order_start_seconds']
            for item in all_items
            if 'time_from_order_start_seconds' in item
        ]
        avg_time_per_item = round(sum(item_times) / len(item_times), 1)
```

**Fallback - Without Timing Data:**
```python
else:
    # Fallback for old sessions without timing
    avg_time_per_order = 0
    avg_time_per_item = 0
    fastest_order_seconds = 0
    slowest_order_seconds = 0
```

**Session-Level Performance:**
```python
if duration_seconds and duration_seconds > 0:
    hours = duration_seconds / 3600.0

    if completed_orders > 0:
        orders_per_hour = round(completed_orders / hours, 1)

    items_for_rate = total_items_from_metadata if total_items_from_metadata > 0 else total_items
    if items_for_rate > 0:
        items_per_hour = round(items_for_rate / hours, 1)
```

**Data Source:** `self.completed_orders_metadata` (populated during packing in Phase 2b)

---

## PART 5: UI PATTERNS

### 5.1 Existing Dialog Patterns

**Reference Implementation:** `SessionHistoryWidget` (lines 1-200+)

**Common Pattern:**
```python
class SessionHistoryWidget(QWidget):
    """Widget for viewing and searching historical session data."""

    # Signal for row selection
    session_selected = Signal(str, str)  # client_id, session_id

    def __init__(self, profile_manager, parent=None):
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.history_manager = SessionHistoryManager(profile_manager)
        self.current_sessions = []

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header with title
        header_layout = QHBoxLayout()
        title_label = QLabel("Session History")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Filters section
        filter_layout = QVBoxLayout()

        # Client filter
        client_filter_layout = QHBoxLayout()
        client_filter_layout.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        self.client_combo.currentIndexChanged.connect(self._on_filter_changed)
        client_filter_layout.addWidget(self.client_combo)

        # Search box
        search_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by session ID, PC name...")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_box)

        # Date range
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))

        # Table
        self.table = QTableWidget()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()
        self.details_btn = QPushButton("View Details")
        self.details_btn.clicked.connect(self._on_view_details)
        btn_layout.addWidget(self.details_btn)
```

**Key UI Components:**
- **QVBoxLayout** - Main vertical layout
- **QHBoxLayout** - Horizontal sections (filters, buttons)
- **QComboBox** - Dropdowns (client selection, search fields)
- **QDateEdit** - Date pickers with calendar popup
- **QLineEdit** - Text input (search)
- **QTableWidget** - Data display with sorting
- **QPushButton** - Actions

---

### 5.2 Table/Tree Structures

**For Session Details Dialog - Orders Tab:**

Use **QTreeWidget** for hierarchical display (orders with expandable items):

```python
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

class OrdersTab(QWidget):
    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Order #", "Duration", "Items Count", "Started", "Completed"
        ])
        self.tree.setAlternatingRowColors(True)
        layout.addWidget(self.tree)

    def populate_orders(self, orders: list):
        """Populate tree with orders and items."""
        self.tree.clear()

        for order in orders:
            # Top-level: Order
            order_item = QTreeWidgetItem(self.tree)
            order_item.setText(0, order['order_number'])
            order_item.setText(1, f"{order['duration_seconds']}s")
            order_item.setText(2, str(order['items_count']))
            order_item.setText(3, order['started_at'])
            order_item.setText(4, order['completed_at'])

            # Children: Items
            for item in order['items']:
                item_node = QTreeWidgetItem(order_item)
                item_node.setText(0, f"  → {item['sku']}")
                item_node.setText(1, f"+{item['time_from_order_start_seconds']}s")
                item_node.setText(2, f"×{item['quantity']}")
                item_node.setText(3, item['scanned_at'])

        self.tree.expandAll()
```

**Alternative - QTableView with Model:**
```python
from PySide6.QtCore import QAbstractTableModel, Qt

class OrdersTableModel(QAbstractTableModel):
    def __init__(self, orders):
        super().__init__()
        self.orders = orders

    def rowCount(self, parent=None):
        return len(self.orders)

    def columnCount(self, parent=None):
        return 5  # Order #, Duration, Items, Started, Completed

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            order = self.orders[index.row()]
            col = index.column()

            if col == 0:
                return order['order_number']
            elif col == 1:
                return f"{order['duration_seconds']}s"
            # ...
```

---

### 5.3 Export Patterns

**Excel Export Implementation (from `completed_sessions_tab.py`):**

```python
def _export_excel(self):
    """Export sessions to Excel."""
    if not self.sessions:
        QMessageBox.warning(self, "No Data", "No sessions to export.")
        return

    # Ask for save location
    filepath, _ = QFileDialog.getSaveFileName(
        self,
        "Export to Excel",
        "completed_sessions.xlsx",
        "Excel Files (*.xlsx)"
    )

    if not filepath:
        return

    try:
        # Convert to dict
        data = self.session_history_manager.export_sessions_to_dict(self.sessions)

        # Create DataFrame
        df = pd.DataFrame(data)

        # Write to Excel
        df.to_excel(filepath, index=False, sheet_name="Completed Sessions")

        QMessageBox.information(
            self, "Success",
            f"Exported {len(self.sessions)} sessions to:\n{filepath}"
        )
        logger.info(f"Exported {len(self.sessions)} sessions to Excel: {filepath}")

    except Exception as e:
        logger.error(f"Failed to export to Excel: {e}", exc_info=True)
        QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")
```

**Helper Method in SessionHistoryManager:**
```python
def export_sessions_to_dict(self, sessions: List[SessionHistoryRecord]) -> List[Dict]:
    """Convert SessionHistoryRecord objects to dict for export."""
    return [session.to_dict() for session in sessions]
```

---

### 5.4 Dialog Window Pattern

**From main.py `open_session_browser()`:**

```python
def open_dialog_example(self):
    """Open a custom dialog."""
    # Create dialog
    dialog = QDialog(self)
    dialog.setWindowTitle("Dialog Title")
    dialog.resize(1200, 700)  # Width, Height
    dialog.setModal(False)  # Non-modal: can keep open while working
    # dialog.setModal(True)  # Modal: blocks interaction with main window

    # Layout
    layout = QVBoxLayout(dialog)

    # Add widgets
    widget = CustomWidget(
        manager1=self.manager1,
        manager2=self.manager2,
        parent=dialog
    )
    layout.addWidget(widget)

    # Optional: Add bottom buttons
    button_layout = QHBoxLayout()
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    button_layout.addStretch()
    button_layout.addWidget(close_btn)
    layout.addLayout(button_layout)

    # Show dialog
    dialog.exec()  # Modal
    # dialog.show()  # Non-modal
```

---

## PART 6: RECOMMENDATIONS

### 6.1 Implementation Strategy for Phase 3.2

**Recommended Order:**

#### **Step 1: Available Sessions Tab (2-3 hours)**
1. Create `src/session_browser/available_sessions_tab.py`
2. Implement scanning logic (section 2.4)
3. Add table with columns: Session ID, Client, Packing List, Courier, Created, Orders, Items
4. Add "Start Packing" button
5. Integrate into `session_browser_widget.py`
6. Test with real Shopify sessions

#### **Step 2: Session Details Dialog Structure (1 hour)**
1. Create `src/session_browser/session_details_dialog.py`
2. Implement QDialog with QTabWidget
3. Create placeholder tabs:
   - Overview Tab (summary info)
   - Orders Tab (QTreeWidget)
   - Metrics Tab (labels with metrics)
4. Add close button

#### **Step 3: Overview Tab (1 hour)**
1. Display session metadata (session_id, client, worker, pc_name)
2. Display timing (started_at, completed_at, duration)
3. Display counts (total_orders, completed_orders, total_items)
4. Use QFormLayout for clean label-value pairs

#### **Step 4: Orders Tab (2-3 hours)**
1. Implement QTreeWidget for orders hierarchy
2. Load orders from session_summary.json
3. Display order-level info (order_number, duration, items_count, timestamps)
4. Display item-level info (sku, quantity, scanned_at, time_from_start)
5. Add expand/collapse all buttons
6. Add search/filter by order number

#### **Step 5: Metrics Tab (1-2 hours)**
1. Display pre-calculated metrics from session_summary.json
2. Format metrics nicely (orders/hour, items/hour, avg times)
3. Add distribution charts (optional, using matplotlib)
4. Show fastest/slowest orders

#### **Step 6: Integration (1 hour)**
1. Connect "View Details" buttons in Active and Completed tabs
2. Load data based on session type (active vs completed)
3. Handle missing data gracefully
4. Test with various session states

#### **Step 7: Testing (2 hours)**
1. Create `tests/test_session_browser.py`
2. Test Available Sessions scanning
3. Test Session Details loading
4. Test edge cases (missing files, invalid JSON)

**Total Estimated Time:** 10-15 hours

---

### 6.2 Potential Issues

**⚠️ Issue 1: Missing orders[] Array in Old Sessions**
- **Problem:** Sessions created before Phase 2b have empty `orders` array
- **Solution:** Check if `orders` is empty, show warning: "Detailed timing data not available for this session"
- **Fallback:** Display summary metrics only (total counts, duration)

**⚠️ Issue 2: Active Sessions Without session_summary.json**
- **Problem:** In-progress sessions only have `packing_state.json`
- **Solution:** Use `packing_state.json` data structure (section 3.3)
- **Display:** Show progress metrics, in-progress order, completed orders list

**⚠️ Issue 3: Multiple Packing Lists per Session**
- **Problem:** Shopify sessions can have multiple work directories
- **Solution:** Session Details dialog should accept `work_dir` parameter
- **UI:** In Available Sessions tab, show each packing list as separate row

**⚠️ Issue 4: Large sessions (100+ orders)**
- **Problem:** QTreeWidget with 100+ orders might be slow
- **Solution:** Use lazy loading or pagination
- **Alternative:** Use QTableView with custom model for better performance

**⚠️ Issue 5: Date/Time Parsing**
- **Problem:** Mixed timezone-aware and naive datetimes
- **Solution:** Use `shared.metadata_utils.parse_timestamp()` consistently
- **Validation:** Check if timestamp is valid before displaying

---

### 6.3 Code Reuse Opportunities

**✅ Reuse from Existing Code:**

1. **Client Combo Population:**
   ```python
   # From active_sessions_tab.py lines 47-54
   self.client_combo = QComboBox()
   self.client_combo.addItem("All Clients", None)
   for client_id in self.profile_manager.list_clients():
       self.client_combo.addItem(f"CLIENT_{client_id}", client_id)
   ```

2. **Date Range Filters:**
   ```python
   # From completed_sessions_tab.py lines 56-66
   self.date_from = QDateEdit()
   self.date_from.setCalendarPopup(True)
   self.date_from.setDate(QDate.currentDate().addMonths(-1))
   ```

3. **Table Setup Pattern:**
   ```python
   # From active_sessions_tab.py lines 66-75
   self.table = QTableWidget()
   self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
   self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
   self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
   ```

4. **Worker Name Lookup:**
   ```python
   # From active_sessions_tab.py lines 311-324
   def _get_worker_name(self, worker_id: str) -> str:
       if not worker_id or worker_id == 'Unknown':
           return worker_id

       try:
           worker_info = self.worker_manager.get_worker(worker_id)
           if worker_info:
               return worker_info.get('name', worker_id)
       except Exception as e:
           logger.debug(f"Failed to get worker name: {e}")

       return worker_id
   ```

5. **Excel Export Pattern:**
   ```python
   # From completed_sessions_tab.py lines 269-301
   # Already documented in section 5.3
   ```

---

## APPENDIX: CODE EXAMPLES

### A. Available Sessions Tab - Complete Implementation Skeleton

```python
"""Available Sessions Tab - Shows Shopify sessions ready to start packing"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QMessageBox, QLabel
)
from PySide6.QtCore import Signal

from pathlib import Path
import json
from logger import get_logger

logger = get_logger(__name__)


class AvailableSessionsTab(QWidget):
    """Tab showing available packing lists that haven't been started"""

    # Signals
    start_packing_requested = Signal(dict)  # {session_path, client_id, packing_list_name}

    def __init__(self, profile_manager, session_manager, parent=None):
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_manager = session_manager
        self.available_lists = []

        self._init_ui()
        self.refresh()

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Top bar: Client filter + Refresh
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        try:
            for client_id in self.profile_manager.list_clients():
                self.client_combo.addItem(f"CLIENT_{client_id}", client_id)
        except Exception as e:
            logger.warning(f"Failed to load clients: {e}")
        self.client_combo.currentIndexChanged.connect(self.refresh)
        top_bar.addWidget(self.client_combo)

        top_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(refresh_btn)

        layout.addLayout(top_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Session ID", "Client", "Packing List", "Courier",
            "Created", "Orders", "Items"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Packing")
        self.start_btn.clicked.connect(self._on_start_packing)
        btn_layout.addWidget(self.start_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def refresh(self):
        """Scan for available packing lists."""
        self.available_lists = []
        self.table.setRowCount(0)

        selected_client = self.client_combo.currentData()

        try:
            sessions_base = self.profile_manager.get_sessions_root()
        except Exception as e:
            logger.error(f"Failed to get sessions root: {e}")
            return

        if not sessions_base.exists():
            logger.warning(f"Sessions directory does not exist: {sessions_base}")
            return

        # Scan each client folder
        for client_dir in sessions_base.iterdir():
            if not client_dir.is_dir() or not client_dir.name.startswith("CLIENT_"):
                continue

            client_id = client_dir.name.replace("CLIENT_", "")

            if selected_client and client_id != selected_client:
                continue

            # Scan session directories
            for session_dir in client_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                session_id = session_dir.name
                packing_lists_dir = session_dir / "packing_lists"

                if not packing_lists_dir.exists():
                    continue

                packing_dir = session_dir / "packing"

                # Scan each .json file in packing_lists/
                for json_file in packing_lists_dir.glob("*.json"):
                    list_name = json_file.stem

                    # Check if work directory exists
                    work_dir = packing_dir / list_name if packing_dir.exists() else None

                    if not work_dir or not work_dir.exists():
                        # This packing list is AVAILABLE
                        try:
                            with open(json_file, 'r', encoding='utf-8') as f:
                                packing_data = json.load(f)

                            self.available_lists.append({
                                'session_id': session_id,
                                'client_id': client_id,
                                'session_path': str(session_dir),
                                'packing_list_name': list_name,
                                'packing_list_path': str(json_file),
                                'courier': packing_data.get('courier', 'Unknown'),
                                'created_at': packing_data.get('created_at', 'Unknown'),
                                'total_orders': packing_data.get('total_orders', 0),
                                'total_items': packing_data.get('total_items', 0),
                            })

                        except Exception as e:
                            logger.warning(f"Failed to load {json_file}: {e}")
                            continue

        # Populate table
        self._populate_table()

    def _populate_table(self):
        """Fill table with available packing lists."""
        self.table.setRowCount(len(self.available_lists))

        for row, item in enumerate(self.available_lists):
            self.table.setItem(row, 0, QTableWidgetItem(item['session_id']))
            self.table.setItem(row, 1, QTableWidgetItem(f"CLIENT_{item['client_id']}"))
            self.table.setItem(row, 2, QTableWidgetItem(item['packing_list_name']))
            self.table.setItem(row, 3, QTableWidgetItem(item['courier']))
            self.table.setItem(row, 4, QTableWidgetItem(item['created_at']))
            self.table.setItem(row, 5, QTableWidgetItem(str(item['total_orders'])))
            self.table.setItem(row, 6, QTableWidgetItem(str(item['total_items'])))

    def _on_start_packing(self):
        """Handle Start Packing button click."""
        selected = self.table.currentRow()

        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a packing list to start.")
            return

        item = self.available_lists[selected]

        # Emit signal to main.py
        self.start_packing_requested.emit({
            'session_path': item['session_path'],
            'client_id': item['client_id'],
            'packing_list_name': item['packing_list_name'],
            'packing_list_path': item['packing_list_path']
        })
```

---

### B. Session Details Dialog - Skeleton

```python
"""Session Details Dialog - Shows detailed information about a session"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem,
    QFormLayout, QWidget
)
from PySide6.QtCore import Qt

from pathlib import Path
import json
from logger import get_logger

logger = get_logger(__name__)


class SessionDetailsDialog(QDialog):
    """Dialog showing detailed session information with tabs"""

    def __init__(self, session_data: dict, parent=None):
        """
        Initialize dialog.

        Args:
            session_data: Dict with session info:
                - session_path: Path to session directory
                - client_id: Client identifier
                - session_id: Session identifier
                - work_dir: Path to work directory (optional)
                - is_active: True if session is in progress
        """
        super().__init__(parent)

        self.session_data = session_data
        self.summary_data = None
        self.state_data = None

        self.setWindowTitle(f"Session Details - {session_data.get('session_id', 'Unknown')}")
        self.resize(1000, 700)

        self._load_data()
        self._init_ui()

    def _load_data(self):
        """Load session_summary.json or packing_state.json"""
        work_dir = Path(self.session_data.get('work_dir', ''))

        if not work_dir.exists():
            logger.warning(f"Work directory does not exist: {work_dir}")
            return

        # Try loading session_summary.json (completed sessions)
        summary_file = work_dir / "session_summary.json"
        if summary_file.exists():
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    self.summary_data = json.load(f)
                logger.info(f"Loaded session summary: {summary_file}")
            except Exception as e:
                logger.error(f"Failed to load session summary: {e}")

        # Try loading packing_state.json (active sessions)
        state_file = work_dir / "packing_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    self.state_data = json.load(f)
                logger.info(f"Loaded packing state: {state_file}")
            except Exception as e:
                logger.error(f"Failed to load packing state: {e}")

    def _init_ui(self):
        """Initialize UI with tabs."""
        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()

        # Overview tab
        overview_tab = self._create_overview_tab()
        tabs.addTab(overview_tab, "Overview")

        # Orders tab
        orders_tab = self._create_orders_tab()
        tabs.addTab(orders_tab, "Orders")

        # Metrics tab
        metrics_tab = self._create_metrics_tab()
        tabs.addTab(metrics_tab, "Metrics")

        layout.addWidget(tabs)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _create_overview_tab(self) -> QWidget:
        """Create overview tab with summary info."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Get data source (summary or state)
        data = self.summary_data or self.state_data or {}

        # Session metadata
        layout.addRow("Session ID:", QLabel(data.get('session_id', 'Unknown')))
        layout.addRow("Client:", QLabel(data.get('client_id', 'Unknown')))
        layout.addRow("Packing List:", QLabel(data.get('packing_list_name', 'Unknown')))

        # Worker info
        worker_name = data.get('worker_name', 'Unknown')
        pc_name = data.get('pc_name', 'Unknown')
        layout.addRow("Worker:", QLabel(f"{worker_name} (PC: {pc_name})"))

        # Timing
        started_at = data.get('started_at', 'Unknown')
        completed_at = data.get('completed_at', 'In Progress')
        duration = data.get('duration_seconds', 0)

        layout.addRow("Started:", QLabel(started_at))
        layout.addRow("Completed:", QLabel(completed_at))
        layout.addRow("Duration:", QLabel(f"{duration // 3600}h {(duration % 3600) // 60}m"))

        # Counts
        total_orders = data.get('total_orders', 0)
        completed_orders = data.get('completed_orders', 0)
        total_items = data.get('total_items', 0)

        layout.addRow("Orders:", QLabel(f"{completed_orders}/{total_orders}"))
        layout.addRow("Items:", QLabel(str(total_items)))

        return widget

    def _create_orders_tab(self) -> QWidget:
        """Create orders tab with tree view."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Tree widget
        tree = QTreeWidget()
        tree.setHeaderLabels([
            "Order #", "Duration", "Items", "Started", "Completed"
        ])
        tree.setAlternatingRowColors(True)

        # Populate from summary_data
        if self.summary_data and 'orders' in self.summary_data:
            orders = self.summary_data['orders']

            for order in orders:
                order_item = QTreeWidgetItem(tree)
                order_item.setText(0, order.get('order_number', 'Unknown'))
                order_item.setText(1, f"{order.get('duration_seconds', 0)}s")
                order_item.setText(2, str(order.get('items_count', 0)))
                order_item.setText(3, order.get('started_at', 'N/A'))
                order_item.setText(4, order.get('completed_at', 'N/A'))

                # Add items as children
                for item in order.get('items', []):
                    item_node = QTreeWidgetItem(order_item)
                    item_node.setText(0, f"  → {item.get('sku', 'Unknown')}")
                    item_node.setText(1, f"+{item.get('time_from_order_start_seconds', 0)}s")
                    item_node.setText(2, f"×{item.get('quantity', 0)}")
                    item_node.setText(3, item.get('scanned_at', 'N/A'))

            tree.expandAll()
        else:
            # No detailed orders data
            label = QLabel("Detailed order timing data not available for this session.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        layout.addWidget(tree)

        return widget

    def _create_metrics_tab(self) -> QWidget:
        """Create metrics tab with performance stats."""
        widget = QWidget()
        layout = QFormLayout(widget)

        # Get metrics from summary
        if self.summary_data and 'metrics' in self.summary_data:
            metrics = self.summary_data['metrics']

            layout.addRow("Orders per Hour:", QLabel(f"{metrics.get('orders_per_hour', 0):.1f}"))
            layout.addRow("Items per Hour:", QLabel(f"{metrics.get('items_per_hour', 0):.1f}"))
            layout.addRow("Avg Time per Order:", QLabel(f"{metrics.get('avg_time_per_order', 0):.1f}s"))
            layout.addRow("Avg Time per Item:", QLabel(f"{metrics.get('avg_time_per_item', 0):.1f}s"))
            layout.addRow("Fastest Order:", QLabel(f"{metrics.get('fastest_order_seconds', 0)}s"))
            layout.addRow("Slowest Order:", QLabel(f"{metrics.get('slowest_order_seconds', 0)}s"))
        else:
            label = QLabel("Metrics not available for this session.")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)

        return widget
```

---

## END OF AUDIT REPORT

**Next Steps:**
1. Review this audit report
2. Implement Available Sessions Tab using section 2.4 logic
3. Implement Session Details Dialog using section 3 data structures
4. Create tests in `tests/test_session_browser.py`
5. Remove old Restore Session Dialog (if desired)

**Questions?** Review specific sections for implementation details.
