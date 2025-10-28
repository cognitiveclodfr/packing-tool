# Phase 1.3: Session History & Analytics - Technical Specification

## Overview

Phase 1.3 adds comprehensive session history tracking and analytics capabilities to help users understand their packing performance, identify bottlenecks, and make data-driven decisions.

**Key Goals:**
- Track completed session metrics
- Provide searchable history
- Generate performance statistics
- Enable data export for external analysis
- Include comprehensive unit tests

---

## Architecture

### 1. Data Storage

#### Session Completion Metadata

When a session ends, save extended metadata to `session_completed.json`:

**Location:** `{session_dir}/session_completed.json`

**Structure:**
```json
{
  "session_id": "Session_2025-10-28_143045",
  "client_id": "M",
  "client_name": "Manufacturer",
  "started_at": "2025-10-28T14:30:45",
  "completed_at": "2025-10-28T16:45:23",
  "duration_seconds": 8078,
  "duration_formatted": "2h 14m 38s",
  "pc_name": "DESKTOP-PC1",
  "user_name": "Ivan Petrenko",
  "statistics": {
    "total_orders": 45,
    "completed_orders": 45,
    "total_items": 187,
    "unique_skus": 32,
    "avg_items_per_order": 4.16,
    "orders_per_hour": 20.0,
    "items_per_hour": 83.2
  },
  "top_skus": [
    {"sku": "SKU001", "name": "Product A", "quantity": 45},
    {"sku": "SKU002", "name": "Product B", "quantity": 38}
  ],
  "packing_list_path": "C:\\Users\\Ivan\\orders.xlsx",
  "errors_count": 0,
  "warnings_count": 2
}
```

#### Analytics Database

**Location:** `\\...\\WAREHOUSE\\2Packing-tool\\analytics\\analytics.db` (SQLite)

**Rationale:** SQLite for:
- Fast queries across all clients/sessions
- Aggregation without loading all JSON files
- Easy export to other formats
- No additional dependencies

**Schema:**

```sql
-- Sessions table
CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT UNIQUE NOT NULL,
    client_id TEXT NOT NULL,
    client_name TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    pc_name TEXT,
    user_name TEXT,
    total_orders INTEGER DEFAULT 0,
    completed_orders INTEGER DEFAULT 0,
    total_items INTEGER DEFAULT 0,
    unique_skus INTEGER DEFAULT 0,
    orders_per_hour REAL DEFAULT 0,
    items_per_hour REAL DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    warnings_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- SKU statistics per session
CREATE TABLE session_skus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

-- Indexes for fast queries
CREATE INDEX idx_sessions_client ON sessions(client_id);
CREATE INDEX idx_sessions_date ON sessions(completed_at);
CREATE INDEX idx_sessions_user ON sessions(user_name);
CREATE INDEX idx_skus_session ON session_skus(session_id);
CREATE INDEX idx_skus_sku ON session_skus(sku);
```

---

## Components

### 1. HistoryManager Class

**File:** `src/history_manager.py`

**Responsibilities:**
- Save session completion data
- Query session history
- Calculate statistics
- Export data

**Key Methods:**

```python
class HistoryManager:
    def __init__(self, profile_manager):
        """Initialize with ProfileManager for accessing sessions."""

    def record_completed_session(
        self,
        session_dir: Path,
        client_id: str,
        packing_state: Dict,
        start_time: datetime,
        end_time: datetime
    ) -> bool:
        """
        Record a completed session with full statistics.

        - Creates session_completed.json in session directory
        - Inserts record into analytics.db
        - Returns True if successful
        """

    def get_session_history(
        self,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        user_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Query session history with filters.

        Returns list of session dictionaries sorted by completed_at descending.
        """

    def search_sessions(
        self,
        query: str,
        search_fields: List[str] = ['client_id', 'user_name', 'pc_name']
    ) -> List[Dict]:
        """
        Full-text search across sessions.

        Searches in specified fields and returns matching sessions.
        """

    def get_client_statistics(
        self,
        client_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get aggregated statistics for a client.

        Returns:
        {
            'total_sessions': 156,
            'total_orders': 4520,
            'total_items': 18934,
            'avg_orders_per_session': 28.97,
            'avg_duration_minutes': 67.5,
            'top_users': [
                {'user_name': 'Ivan', 'sessions': 89},
                {'user_name': 'Maria', 'sessions': 67}
            ],
            'most_packed_skus': [
                {'sku': 'SKU001', 'total_quantity': 456},
                ...
            ]
        }
        """

    def get_overall_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict:
        """
        Get statistics across all clients.

        Returns aggregated data for dashboard.
        """

    def export_to_excel(
        self,
        output_path: str,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> bool:
        """
        Export session data to Excel with multiple sheets:
        - Sheet 1: Session summary
        - Sheet 2: Detailed SKU breakdown
        - Sheet 3: Statistics
        """

    def export_to_csv(
        self,
        output_path: str,
        client_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> bool:
        """
        Export session data to CSV.
        """
```

### 2. Integration with SessionManager

**Update `SessionManager.end_session()`:**

```python
def end_session(self):
    """End session and record completion data."""
    if not self.session_active:
        return

    # Calculate session metrics
    end_time = datetime.now()
    start_time_str = self.get_session_info().get('started_at')
    start_time = datetime.fromisoformat(start_time_str) if start_time_str else end_time

    # Get packing state from PackerLogic
    packing_state = self.logic.get_packing_state() if self.logic else {}

    # Record completion
    from history_manager import HistoryManager
    history = HistoryManager(self.profile_manager)
    history.record_completed_session(
        session_dir=self.output_dir,
        client_id=self.client_id,
        packing_state=packing_state,
        start_time=start_time,
        end_time=end_time
    )

    # Continue with normal cleanup
    self._stop_heartbeat()
    self.lock_manager.release_lock(self.output_dir)
    self._cleanup_session_files()
    # ...
```

---

## UI Components

### 1. Session History Dialog

**File:** `src/session_history_dialog.py`

**Features:**
- Table view of completed sessions
- Filter by client, date range, user
- Search box for full-text search
- Sort by any column
- Double-click to view details
- Export button

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Session History                                        │
├─────────────────────────────────────────────────────────┤
│  Filter: [Client ▼] [From: date] [To: date] [Apply]    │
│  Search: [_____________________________] [🔍]           │
├─────────────────────────────────────────────────────────┤
│  Date       │ Client │ User    │ Orders │ Duration     │
│  2025-10-28 │ M      │ Ivan    │ 45     │ 2h 14m       │
│  2025-10-27 │ R      │ Maria   │ 32     │ 1h 45m       │
│  ...                                                     │
├─────────────────────────────────────────────────────────┤
│  [View Details] [Export...] [Close]      Page 1 of 5   │
└─────────────────────────────────────────────────────────┘
```

### 2. Session Detail Dialog

**File:** `src/session_detail_dialog.py`

**Shows for selected session:**
- All metadata (client, user, PC, times)
- Order statistics
- Top SKUs packed
- Duration breakdown
- Link to session directory

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  Session Details: Session_2025-10-28_143045         │
├─────────────────────────────────────────────────────┤
│  📅 Date: 28.10.2025 14:30 - 16:45 (2h 14m)        │
│  👤 User: Ivan Petrenko on DESKTOP-PC1             │
│  📦 Client: M - Manufacturer                         │
│                                                      │
│  📊 Statistics:                                      │
│    • Total orders: 45                               │
│    • Total items: 187                               │
│    • Unique SKUs: 32                                │
│    • Orders/hour: 20.0                              │
│    • Items/hour: 83.2                               │
│                                                      │
│  🏆 Top SKUs:                                        │
│    1. SKU001 - Product A: 45 items                  │
│    2. SKU002 - Product B: 38 items                  │
│    3. SKU003 - Product C: 27 items                  │
│                                                      │
│  📁 Location: \\...\SESSIONS\CLIENT_M\Session_...   │
│                                                      │
│  [Open Folder] [Export This Session] [Close]       │
└─────────────────────────────────────────────────────┘
```

### 3. Statistics Dashboard Widget

**File:** `src/statistics_dashboard_widget.py`

**Features:**
- Overall statistics display
- Per-client statistics
- Time-based charts (if matplotlib available)
- Performance metrics
- Top users, top SKUs

**Layout:**
```
┌─────────────────────────────────────────────────────┐
│  📊 Statistics Dashboard                             │
├─────────────────────────────────────────────────────┤
│  Period: [Last 7 days ▼] [From: date] [To: date]   │
│                                                      │
│  Overall Performance:                                │
│  ┌─────────────┬─────────────┬─────────────┐        │
│  │  Sessions   │   Orders    │    Items    │        │
│  │     156     │    4,520    │   18,934    │        │
│  └─────────────┴─────────────┴─────────────┘        │
│                                                      │
│  Avg Duration: 67.5 min | Avg Orders/Hour: 24.3    │
│                                                      │
│  By Client:                                          │
│  M: 89 sessions, 2,340 orders                       │
│  R: 67 sessions, 2,180 orders                       │
│                                                      │
│  Top Users:                                          │
│  1. Ivan Petrenko: 89 sessions                      │
│  2. Maria Ivanova: 67 sessions                      │
│                                                      │
│  [Refresh] [Export Report...] [Close]               │
└─────────────────────────────────────────────────────┘
```

### 4. Export Dialog

**File:** `src/export_dialog.py`

**Options:**
- Format: Excel (.xlsx) or CSV (.csv)
- Client filter
- Date range
- Include SKU details checkbox
- Output path selection

---

## Unit Tests

### Test Structure

```
tests/
├── __init__.py
├── test_profile_manager.py
├── test_session_lock_manager.py
├── test_history_manager.py
├── test_packer_logic.py
├── test_session_manager.py
└── fixtures/
    ├── test_sessions/
    └── test_config.ini
```

### 1. test_profile_manager.py

```python
import unittest
from pathlib import Path
import tempfile
import shutil
from profile_manager import ProfileManager

class TestProfileManager(unittest.TestCase):
    def setUp(self):
        """Create temporary directory for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.config_path = Path(self.test_dir) / "config.ini"
        # Create test config

    def tearDown(self):
        """Clean up test directory."""
        shutil.rmtree(self.test_dir)

    def test_create_client_profile(self):
        """Test creating a new client profile."""
        pm = ProfileManager(self.config_path)
        success = pm.create_client_profile("TEST", "Test Client")
        self.assertTrue(success)
        self.assertTrue(pm.client_exists("TEST"))

    def test_validate_client_id(self):
        """Test client ID validation."""
        is_valid, msg = ProfileManager.validate_client_id("M")
        self.assertTrue(is_valid)

        is_valid, msg = ProfileManager.validate_client_id("123")
        self.assertFalse(is_valid)

    def test_get_incomplete_sessions(self):
        """Test getting incomplete sessions."""
        pm = ProfileManager(self.config_path)
        pm.create_client_profile("TEST", "Test")
        # Create test session with session_info.json
        sessions = pm.get_incomplete_sessions("TEST")
        self.assertIsInstance(sessions, list)

    # ... more tests
```

### 2. test_session_lock_manager.py

```python
import unittest
from session_lock_manager import SessionLockManager
from pathlib import Path
import tempfile

class TestSessionLockManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.session_dir = self.test_dir / "test_session"
        self.session_dir.mkdir()

    def test_acquire_lock(self):
        """Test acquiring a lock on a session."""
        lock_mgr = SessionLockManager(None)  # Mock profile_manager
        success, error = lock_mgr.acquire_lock("TEST", self.session_dir)
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify lock file exists
        lock_file = self.session_dir / ".session.lock"
        self.assertTrue(lock_file.exists())

    def test_is_lock_stale(self):
        """Test stale lock detection."""
        lock_mgr = SessionLockManager(None)

        # Create old lock info
        old_lock = {
            'heartbeat': '2025-10-28T10:00:00',
            'locked_by': 'TEST-PC'
        }

        is_stale = lock_mgr.is_lock_stale(old_lock, stale_timeout=60)
        self.assertTrue(is_stale)

    # ... more tests
```

### 3. test_history_manager.py

```python
import unittest
from history_manager import HistoryManager
from datetime import datetime
import tempfile

class TestHistoryManager(unittest.TestCase):
    def test_record_completed_session(self):
        """Test recording a completed session."""
        history = HistoryManager(None)  # Mock

        packing_state = {
            'ORD001': {'SKU001': {'packed': 5, 'required': 5}}
        }

        success = history.record_completed_session(
            session_dir=Path("test"),
            client_id="TEST",
            packing_state=packing_state,
            start_time=datetime.now(),
            end_time=datetime.now()
        )

        self.assertTrue(success)

    def test_get_client_statistics(self):
        """Test getting statistics for a client."""
        history = HistoryManager(None)
        stats = history.get_client_statistics("TEST")

        self.assertIn('total_sessions', stats)
        self.assertIn('total_orders', stats)
        self.assertIsInstance(stats['total_sessions'], int)

    # ... more tests
```

### 4. test_packer_logic.py

```python
import unittest
from packer_logic import PackerLogic

class TestPackerLogic(unittest.TestCase):
    def test_sku_mapping(self):
        """Test SKU mapping functionality."""
        logic = PackerLogic("TEST", None, "test_dir")

        # Test setting and getting SKU map
        test_map = {"SKU001": "MAPPED001"}
        logic.set_sku_map(test_map)

        mapped = logic.get_mapped_sku("SKU001")
        self.assertEqual(mapped, "MAPPED001")

    def test_scan_barcode(self):
        """Test barcode scanning logic."""
        # Mock packing list data
        logic = PackerLogic("TEST", None, "test_dir")
        # ... setup test data

        result = logic.scan_barcode("SKU001")
        self.assertIsNotNone(result)

    # ... more tests
```

---

## Testing Strategy

### Unit Tests Coverage

**Target: 80%+ coverage**

Run tests:
```bash
python -m pytest tests/ -v --cov=src --cov-report=html
```

### Manual Testing Checklist

- [ ] Record completed session
- [ ] View session history
- [ ] Filter by client
- [ ] Filter by date range
- [ ] Search sessions
- [ ] View session details
- [ ] Export to Excel
- [ ] Export to CSV
- [ ] Statistics dashboard loads
- [ ] Statistics calculations correct
- [ ] Performance with 100+ sessions

---

## Performance Considerations

### Database Indexing

- Indexes on frequently queried columns (client_id, completed_at, user_name)
- Consider VACUUM after large deletions

### Caching

- Cache statistics calculations (5 minute TTL)
- Cache recent history queries

### Lazy Loading

- Paginate history table (100 records per page)
- Load SKU details only when viewing session details

---

## Migration from Phase 1.2

### Backfill Historical Data

Create a migration script to process existing completed sessions:

```python
def migrate_existing_sessions():
    """
    Scan all session directories for completed sessions
    (those without session_info.json) and backfill analytics.db.
    """
    history = HistoryManager(profile_manager)

    for client in profile_manager.list_clients():
        sessions_dir = profile_manager.sessions_dir / f"CLIENT_{client}"
        for session_dir in sessions_dir.iterdir():
            if not (session_dir / "session_info.json").exists():
                # Session is completed
                # Try to extract data from packing_state.json
                # Record in database
                pass
```

---

## Dependencies

Add to `requirements.txt`:
```
openpyxl>=3.1.0  # Already have
pandas>=2.0.0     # Already have
pytest>=7.0.0     # NEW - for unit tests
pytest-cov>=4.0.0 # NEW - for coverage reports
```

---

## Implementation Order

1. **Database schema** - Create analytics.db with tables
2. **HistoryManager** - Core analytics logic
3. **SessionManager integration** - Record on session end
4. **Unit tests** - Write tests for existing and new code
5. **UI components** - History dialog, details, dashboard
6. **Export functionality** - Excel/CSV export
7. **Migration script** - Backfill existing data
8. **Documentation** - User guide and testing guide

---

## Estimated Development Time

- HistoryManager: 2-3 hours
- UI Components: 2-3 hours
- Unit Tests: 2-3 hours
- Integration & Testing: 1-2 hours
- Documentation: 1 hour

**Total: 8-12 hours**

---

## Success Criteria

✅ All completed sessions are recorded in database
✅ Session history is searchable and filterable
✅ Statistics are accurate and performant
✅ Export generates valid Excel/CSV files
✅ Unit test coverage > 80%
✅ Manual test checklist passed
✅ Documentation complete

---

**Version:** 1.3.0
**Phase:** Analytics & History
**Status:** Specification Complete - Ready for Implementation
