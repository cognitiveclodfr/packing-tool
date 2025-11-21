# Priority 2 + Lock Issue Audit

**Date:** 2025-11-21
**Branch:** `audit/priority-2-and-lock-issue`
**Version:** v1.3.0-dev

---

## 🔴 CRITICAL: Lock Mechanism Not Working

### Root Cause

**Lock files (.session.lock) are NOT being created for Shopify packing sessions.**

The Shopify workflow (`open_shopify_session()`) **never calls `session_manager.start_session()`**, which is responsible for:
- Acquiring the session lock
- Creating `.session.lock` file
- Starting heartbeat timer
- Creating `session_info.json`

### Code Flow Analysis

#### Excel Workflow (✅ WORKS):
```
main.py:open_excel_packing_list()
└─> line 603: session_manager.start_session(file_path, restore_dir=restore_dir)
    └─> session_manager.py:start_session() (line 95)
        └─> line 242: lock_manager.acquire_lock(client_id, output_dir, worker_id, worker_name)
            └─> session_lock_manager.py:acquire_lock() (line 71)
                └─> lines 154-165: Creates .session.lock file atomically
        └─> line 297: _start_heartbeat() - starts QTimer for heartbeat updates
```

#### Shopify Workflow (❌ BROKEN):
```
main.py:open_shopify_session()
└─> line 1481: session_manager.get_packing_work_dir(session_path, packing_list_name)
    └─> Creates work directories (packing/{list_name}/)
    └─> ❌ NEVER calls session_manager.start_session()
    └─> ❌ NEVER acquires lock
    └─> ❌ NEVER starts heartbeat
```

### Missing Steps in Shopify Workflow

**File:** `src/main.py:open_shopify_session()`
**Line:** ~1481-1505

Currently:
```python
# Line 1481: Create work directory
work_dir = self.session_manager.get_packing_work_dir(
    session_path=str(session_path),
    packing_list_name=packing_list_name
)

# Line 1501: Create PackerLogic
self.logic = PackerLogic(...)

# ❌ MISSING: No lock acquisition!
```

### Fix Required

**Add lock acquisition to Shopify workflow after creating work_dir:**

```python
# After line 1497 (after work_dir creation):

# Acquire session lock for work directory
try:
    success, error_msg = self.lock_manager.acquire_lock(
        client_id=self.current_client_id,
        session_dir=work_dir,
        worker_id=self.current_worker_id,
        worker_name=self.current_worker_name
    )

    if not success:
        raise SessionLockedError(error_msg)

    # Start heartbeat timer
    self.session_manager._start_heartbeat_for_dir(work_dir)

    logger.info(f"Session lock acquired for {work_dir}")

except SessionLockedError as e:
    QMessageBox.warning(self, "Session Locked", str(e))
    return
```

**Alternative:** Refactor `session_manager.start_session()` to support Shopify workflow where work_dir is already created.

### Why This Bug Exists

The Shopify workflow was added in Phase 1.8+ and uses a different architecture:
- Excel workflow: SessionManager creates session directory → acquires lock
- Shopify workflow: Work directory created separately → **lock acquisition forgotten**

This is a **critical multi-PC data corruption risk** - multiple PCs can work on same packing list simultaneously!

---

## 🟠 Session Resume Data Overwrite

### Root Cause

**Initialization order bug in `PackerLogic.__init__`** causes restored metadata to be overwritten.

### Code Location

**File:** `src/packer_logic.py`
**Method:** `__init__` (lines 94-164)

**BUG:**
```python
# Line 152: Load session state (includes completed_orders_metadata)
self._load_session_state()
# ↓ Inside _load_session_state() at line 321:
#   self.completed_orders_metadata = completed_list  # ✅ Restored from state

# Line 157: Initialize to empty list (❌ OVERWRITES restored data!)
self.completed_orders_metadata = []
```

### Execution Flow

1. **Day 1:** Scan 50 orders
   - Orders are appended to `completed_orders_metadata` (line 552)
   - Saved to `packing_state.json` (Phase 2b format)

2. **Day 2:** Resume session
   - `__init__` called
   - Line 152: `_load_session_state()` loads 50 orders into `completed_orders_metadata`
   - Line 157: `self.completed_orders_metadata = []` **clears it**
   - Scan 50 more orders → only these 50 are in metadata

3. **End session:** Generate summary
   - Line 1771: `"orders": self.completed_orders_metadata`
   - Result: Only Day 2's 50 orders in session_summary.json

### Fix Approach

**Move initialization BEFORE loading state:**

```python
# BEFORE (lines 148-157):
self.sku_map = self._load_sku_mapping()
self._load_session_state()  # Line 152
# Phase 2b: Order-level timing tracking
self.current_order_start_time = None
self.current_order_items_scanned = []
self.completed_orders_metadata = []  # ❌ Line 157 - WRONG!

# AFTER (corrected order):
self.sku_map = self._load_sku_mapping()

# Phase 2b: Order-level timing tracking (initialize BEFORE loading)
self.current_order_start_time = None
self.current_order_items_scanned = []
self.completed_orders_metadata = []  # ✅ Initialize first

# Load session state (will overwrite if data exists)
self._load_session_state()  # ✅ Load last
```

### Impact

- Multi-day sessions lose historical data
- Session summaries incomplete
- Analytics/metrics wrong (avg time per order, etc.)
- Worker performance tracking broken

---

## 🟢 Dashboard/History/Monitor Removal

### Files to Remove

- [x] `src/dashboard_widget.py`
- [x] `src/session_history_widget.py`
- [x] `src/session_monitor_widget.py`

### Dependencies in main.py

**Imports (lines 27, 40-41):**
```python
# Line 27
from session_monitor_widget import SessionMonitorWidget

# Lines 40-41
from dashboard_widget import DashboardWidget
from session_history_widget import SessionHistoryWidget
```

**Instantiation (lines 306-307):**
```python
self.dashboard_widget = DashboardWidget(self.profile_manager, self.stats_manager)
self.history_widget = SessionHistoryWidget(self.profile_manager)
```

**Tab Integration (line 312):**
```python
self.tab_widget.addTab(self.dashboard_widget, "Dashboard")
# Note: history_widget is created but NEVER added to tabs (orphaned)
```

**Usage (lines 395, 462):**
```python
# Line 395: In load_client_profile()
self.dashboard_widget.refresh()

# Line 462: In load_clients()
self.dashboard_widget.load_clients(clients)
```

**SessionMonitorWidget (lines 1671-1677):**
```python
def show_session_monitor(self):
    """Show active sessions monitor dialog."""
    monitor_dialog = QDialog(self)
    monitor_dialog.setWindowTitle("Active Sessions Monitor")
    monitor_dialog.resize(800, 600)

    layout = QVBoxLayout(monitor_dialog)
    monitor_widget = SessionMonitorWidget(self.lock_manager)  # Line 1674
    layout.addWidget(monitor_widget)
    # ...
```

### Safe to Remove?

**✅ YES - Safe to remove completely**

**Reasoning:**
1. **dashboard_widget:** Replaced by Session Browser (Phase 3)
2. **history_widget:** Created but never used (orphaned instance)
3. **session_monitor_widget:** Replaced by Session Browser Active tab

**Replacement:**
- All functionality now in `session_browser/` (Phase 3.1-3.2)
  - Active Sessions tab → replaces SessionMonitorWidget
  - Completed Sessions tab → replaces SessionHistoryWidget
  - Available Sessions tab → new functionality

**Steps to Remove:**
1. Delete 3 widget files
2. Remove imports (lines 27, 40-41)
3. Remove instantiation (lines 306-307)
4. Remove tab.addTab() call (line 312)
5. Remove refresh() calls (lines 395, 462)
6. Remove show_session_monitor() method (lines 1668-1692)
7. Remove menu action/toolbar button that calls show_session_monitor()

---

## 🟢 Stats Display Removal

### Location in UI

**File:** `src/main.py`

**Stats Labels (lines 234, 237):**
```python
# Line 234
self.total_orders_label = QLabel("Total Unique Orders: 0")

# Line 237: Add labels to layout
for label in [self.total_orders_label, self.completed_label]:
    label.setFont(...)
    # ... styling
```

**Note:** `self.completed_label` is used but never defined in visible code - likely defined elsewhere or typo.

### Lines to Remove/Modify

**Stats Update Method (lines 403-416):**
```python
def _update_stats_display(self):
    """Update the statistics dashboard with the latest data."""
    # Phase 1.4: Use unified StatsManager API
    global_stats = self.stats_manager.get_global_stats()  # Line 405
    total_packed = global_stats.get('total_orders_packed', 0)

    # Get client-specific stats if client is selected
    if self.current_client_id:
        client_stats = self.stats_manager.get_client_stats(self.current_client_id)  # Line 410
        client_packed = client_stats.get('orders_packed', 0)
        self.total_orders_label.setText(f"Total Orders Packed: {total_packed}")  # Line 412
        self.completed_label.setText(f"Client {self.current_client_id} Orders: {client_packed}")  # Line 413
    else:
        self.total_orders_label.setText(f"Total Orders Packed: {total_packed}")  # Line 415
        self.completed_label.setText(f"Total Sessions: {global_stats.get('total_sessions', 0)}")  # Line 416
```

**Stats Recording (lines 879-898):**
```python
# Record to unified stats (always, even if start_time is None)
self.stats_manager.record_packing(  # Line 879
    client_id=self.current_client_id,
    session_id=session_id,
    # ... parameters
)
```

### What to Keep vs Remove

**❌ Remove:**
- `self.total_orders_label` and `self.completed_label` widgets
- `_update_stats_display()` method
- Calls to `_update_stats_display()`

**✅ Keep:**
- `self.stats_manager` instance (used by DashboardWidget which we're removing, but might be used elsewhere)
- `stats_manager.record_packing()` calls (for historical data, analytics)

**🤔 Decision Needed:**
- If stats are ONLY used for UI display → remove stats_manager completely
- If stats are used for reporting/exports → keep stats_manager, remove UI only

### Impact

- Cleaner UI (no redundant stats labels)
- Session Browser has all stats display needs
- Historical stats still recorded for analytics

---

## 🟢 Worker Column in Completed Sessions

### Data Available?

**✅ YES** - Worker data IS saved in `session_summary.json`

**Source:** `src/packer_logic.py:generate_session_summary()` (lines 1745-1747)
```python
# Ownership
"worker_id": worker_id,
"worker_name": worker_name if worker_name else "Unknown",
"pc_name": self.worker_pc,
```

### Current Implementation

**File:** `src/session_browser/completed_sessions_tab.py`

**Already Has Worker Column (lines 123-124):**
```python
self.table.setHorizontalHeaderLabels([
    "Session ID", "Client", "Packing List", "Worker",  # ← Column exists!
    "Start Time", "Duration", "Orders", "Items", "Status"
])
```

**Currently Displays (lines 236-238):**
```python
# Worker (PC name for now)
worker_display = session.pc_name if session.pc_name else "Unknown"
self.table.setItem(row, 3, QTableWidgetItem(worker_display))
```

### Problem

**SessionHistoryRecord doesn't load worker fields!**

**File:** `src/session_history_manager.py`
**Class:** `SessionHistoryRecord` (lines 19-49)

**Current fields:**
```python
@dataclass
class SessionHistoryRecord:
    session_id: str
    client_id: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    total_orders: int
    completed_orders: int
    in_progress_orders: int
    total_items_packed: int
    pc_name: Optional[str]  # ✅ Has this
    packing_list_path: Optional[str]
    session_path: str

    # ❌ MISSING:
    # worker_id: Optional[str]
    # worker_name: Optional[str]
```

### Implementation Required

**1. Add fields to SessionHistoryRecord:**

```python
@dataclass
class SessionHistoryRecord:
    # ... existing fields ...
    pc_name: Optional[str]
    worker_id: Optional[str]  # ← ADD
    worker_name: Optional[str]  # ← ADD
    packing_list_path: Optional[str]
    session_path: str
```

**2. Load fields in SessionHistoryManager:**

Find where `SessionHistoryRecord` instances are created (likely in `_scan_session_directory()` or similar) and add:

```python
# When loading from session_summary.json:
worker_id = summary_data.get('worker_id')
worker_name = summary_data.get('worker_name')

record = SessionHistoryRecord(
    # ... existing params ...
    pc_name=summary_data.get('pc_name'),
    worker_id=worker_id,  # ← ADD
    worker_name=worker_name,  # ← ADD
    # ... remaining params ...
)
```

**3. Update display in completed_sessions_tab.py:**

```python
# Line 236-238: Change from pc_name to worker_id + worker_name
if session.worker_id and session.worker_name:
    worker_display = f"{session.worker_id} ({session.worker_name})"
elif session.worker_id:
    worker_display = session.worker_id
elif session.worker_name:
    worker_display = session.worker_name
else:
    worker_display = session.pc_name if session.pc_name else "Unknown"

self.table.setItem(row, 3, QTableWidgetItem(worker_display))
```

**Display format examples:**
- `"001 (John Doe)"` - ideal
- `"001"` - if name missing
- `"John Doe"` - if ID missing
- `"PC-WAREHOUSE-01"` - fallback to pc_name
- `"Unknown"` - no data

---

## 🟢 Auto-Refresh for Session Browser

### Current State

**Manual refresh only:**
- `SessionBrowserWidget.refresh_all()` method exists (line 129)
- Called manually via Refresh buttons in each tab
- No automatic updates

### Recommendation

**Option B: Polling Timer** ✅ **RECOMMENDED**

**Reasoning:**
- Simple to implement
- Reliable (no network/filesystem quirks)
- Low overhead (refresh every 30-60 seconds)
- Works consistently across network shares
- Easy to pause/resume/configure

### Implementation

**File:** `src/session_browser/session_browser_widget.py`

```python
from PySide6.QtCore import QTimer

class SessionBrowserWidget(QWidget):
    def __init__(self, ...):
        super().__init__(parent)
        # ... existing code ...

        self._init_ui()
        self._connect_signals()

        # Auto-refresh timer (Phase 3.3)
        self.auto_refresh_enabled = True
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self.refresh_timer.start(30000)  # 30 seconds

    def _auto_refresh(self):
        """Auto-refresh all tabs if enabled."""
        if self.auto_refresh_enabled:
            self.refresh_all()

    def pause_auto_refresh(self):
        """Pause auto-refresh (e.g., while user is viewing details)."""
        self.auto_refresh_enabled = False

    def resume_auto_refresh(self):
        """Resume auto-refresh."""
        self.auto_refresh_enabled = True
```

**Improvements:**
- Add checkbox in UI: "Auto-refresh (30s)"
- Add setting to configure interval (15s, 30s, 60s, disabled)
- Pause refresh while user has details dialog open
- Show "Last refreshed: X seconds ago" label

### Alternative: QFileSystemWatcher (NOT Recommended)

**Issues with network shares:**
- SMB/CIFS may not generate filesystem events
- Windows network redirector caching
- Unreliable for detecting changes on remote servers
- Tested in real warehouse environments - frequent misses

### Alternative: Signal-based (NOT Sufficient)

**Limitation:**
- Only works for local app actions (complete session, start session)
- Doesn't detect changes from other PCs
- User needs multi-PC awareness (main use case)

---

## 📊 PRIORITY ORDER

### Critical (Immediate Fix Required)

1. **🔴 Fix lock mechanism** - CRITICAL SECURITY/DATA INTEGRITY
   - File: `src/main.py:open_shopify_session()`
   - Impact: Multi-PC data corruption risk
   - Effort: 1-2 hours (testing required)

2. **🟠 Fix session resume overwrite** - DATA LOSS
   - File: `src/packer_logic.py:__init__`
   - Impact: Multi-day sessions lose data
   - Effort: 15 minutes (simple reorder)

### High Priority (User Experience)

3. **🟢 Remove Dashboard/History/Monitor** - Code cleanup
   - Files: 3 widget files + main.py integration
   - Impact: Reduced confusion, cleaner codebase
   - Effort: 1 hour (straightforward deletion)

4. **🟢 Remove stats display** - UI cleanup
   - File: `src/main.py` (labels and update method)
   - Impact: Cleaner UI
   - Effort: 30 minutes

### Medium Priority (Enhancement)

5. **🟢 Add worker column** - Analytics improvement
   - Files: session_history_manager.py, completed_sessions_tab.py
   - Impact: Better worker tracking
   - Effort: 1 hour (add fields, load data, update display)

6. **🟢 Auto-refresh** - User convenience
   - File: `src/session_browser/session_browser_widget.py`
   - Impact: Real-time updates
   - Effort: 30 minutes (QTimer implementation)

---

## 📝 Testing Checklist

### Lock Mechanism Fix
- [ ] Create Shopify session with packing list
- [ ] Verify `.session.lock` created in `packing/{list_name}/`
- [ ] Check lock file contains worker_id, worker_name
- [ ] Verify heartbeat updates every 60s
- [ ] Test multi-PC: PC-2 tries to open same packing list → shows lock warning
- [ ] Test crash recovery: Kill app → PC-2 sees stale lock after 2 minutes

### Session Resume Fix
- [ ] Day 1: Scan 25 orders → end session
- [ ] Day 2: Resume → scan 25 more orders → end session
- [ ] Check `session_summary.json` has all 50 orders in "orders" array
- [ ] Verify metrics: avg_time_per_order includes all 50 orders

### Widget Removal
- [ ] App launches without errors
- [ ] No broken imports
- [ ] Session Browser tab works (replaces old widgets)

### Worker Column
- [ ] Complete session with worker selected
- [ ] Session Browser → Completed tab → verify Worker column shows "001 (John Doe)"
- [ ] Test legacy sessions without worker_id → shows "Unknown"

### Auto-Refresh
- [ ] Session Browser open → PC-2 completes session → refreshes within 30s
- [ ] Verify no performance impact (network traffic acceptable)

---

## 🎯 Next Steps

1. **Implement critical fixes first** (lock mechanism + session resume)
2. **Test thoroughly** with multi-PC setup
3. **Create PR** with fixes
4. **Schedule cleanup tasks** (widget removal, stats removal)
5. **Enhancement PR** for worker column + auto-refresh

---

**End of Audit**
