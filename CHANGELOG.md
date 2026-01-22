# Changelog - Packer Tool

All notable changes to Packer Tool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.3.0.0] - 2026-01-22 - Major Cleanup & Performance Release

### 🎯 Summary

Major release focused on removing duplicate functionality, performance optimizations,
and complete Shopify Tool integration. Excel input workflow removed in favor of
unified Shopify-first approach.

### ⚠️ BREAKING CHANGES

#### Removed Features (Integrated with Shopify Tool)
- ❌ **Local barcode generation** - Now handled by Shopify Tool (Feature #5)
- ❌ **Excel input workflow** - All sessions created through Shopify Tool
- ❌ **Manual barcode mapping** - Replaced with automatic order number normalization

**Migration:** All new sessions must be created in Shopify Tool first. Packer Tool
now operates as a warehouse execution tool only.

### ✨ New Features

#### Session Browser (Phase 3.1) ✅
Complete session management interface with three tabs:

**Active Sessions Tab:**
- Real-time monitoring of in-progress packing sessions
- Lock status indicators
- Resume capability with state restoration

**Completed Sessions Tab:**
- Historical session tracking
- Excel export functionality
- Statistics and metrics

**Available Sessions Tab:**
- Browse Shopify Tool sessions ready for packing
- Multi-packing-list support per session
- Direct session opening

**Technical Implementation:**
- `SessionCacheManager` - 5-minute persistent cache for instant loading
- `RefreshWorker(QThread)` - Background session scanning (non-blocking UI)
- Auto-refresh with user toggle control
- Loading overlay with state management

#### Order Number Normalization ✅
- `_normalize_order_number()` - Robust order matching
- Removes special characters (#, !, spaces) for consistent comparison
- Matches Shopify Tool's barcode normalization logic
- 7 new unit tests for normalization scenarios

### 🚀 Performance Improvements

#### Session Browser Optimizations:
- **Persistent cache** - Session data cached on disk (5 min TTL)
- **Background scanning** - QThread workers prevent UI freezing
- **Instant loading** - First open uses cache, refresh in background
- **60-100 second scans** eliminated from UI thread

**Metrics:**
- Before: 60-100 second UI freezes every 30 seconds
- After: Instant UI response, background updates

#### State Save Optimizations:
- **Debounced saves** - Batch multiple state changes
- **Reduced I/O** - Fewer file operations during scanning
- **Timer-based batching** - QTimer for efficient save scheduling

### 🐛 Bug Fixes

#### Critical Fixes:
- Fixed Session Browser UI freezing during directory scans
- Fixed session resume AttributeError (missing order_state)
- Fixed dict/SessionHistoryRecord serialization issues
- Fixed state save race conditions in multi-PC environments

#### Shopify Integration Fixes:
- Fixed session detection for multi-packing-list sessions
- Fixed packing_state.json path detection (packing/{list}/packing_state.json)
- Fixed session summary location detection

### 📉 Code Cleanup

**Removed (Dead Code):**
- 1,073 lines of duplicate barcode generation code
- `process_data_and_generate_barcodes()` - 390 lines
- `generate_barcode()` method
- `barcode_to_order_number` mapping dictionary
- `mapping_dialog.py` - 99 lines
- `test_barcode_size.py` - 236 lines

**Removed Dependencies:**
- `python-barcode` (barcode generation moved to Shopify Tool)
- `reportlab` or `pypdf` (PDF generation moved to Shopify Tool)

**Simplified:**
- Excel workflow logic removed
- Column mapping dialog removed
- Manual SKU mapping simplified

### 🔧 Technical Changes

#### Session Structure (Shopify Integration):
```
Sessions/CLIENT_X/2025-11-19_1/
├── analysis/
│   └── analysis_data.json          ← From Shopify Tool
├── packing/
│   ├── DHL_Orders/
│   │   ├── packing_list.json       ← From Shopify Tool
│   │   ├── barcodes/               ← From Shopify Tool
│   │   ├── packing_state.json      ← Packer Tool (saves state)
│   │   └── session_summary.json    ← Packer Tool (completion)
│   └── PostOne_Orders/
│       └── ...
```

#### New Methods:
- `SessionCacheManager.get_cached_data()` - Retrieve cached sessions
- `SessionCacheManager.save_to_cache()` - Persist session data
- `RefreshWorker.run()` - Background session scanning
- `PackerLogic._normalize_order_number()` - Order matching

#### Modified Methods:
- `load_from_shopify_analysis()` - Now primary loading method
- `load_packing_list_json()` - Support for Shopify JSON format
- `start_order_packing()` - Uses normalization for matching
- `_save_session_state()` - Debounced saves

### 🧪 Testing

**Test Updates:**
- 4 Excel workflow tests marked as skipped (workflow removed)
- 7 new unit tests for order normalization
- Updated integration tests for Shopify workflow
- Fixed serialization tests

**Test Files:** 18 total
- All tests passing except intentionally skipped (Excel workflow)
- Test coverage maintained after cleanup

### 📦 Dependencies

**Current (Minimal):**
```
PySide6          # GUI framework
pandas           # Data processing
openpyxl         # Excel export only
pyinstaller      # Build tool
pytest           # Testing
pytest-qt        # Qt testing
```

**Removed:**
```
python-barcode   # Moved to Shopify Tool
reportlab/pypdf  # Moved to Shopify Tool
```

### 🔄 Migration Guide

#### For Warehouse Users:
1. **New Session Creation:**
   - Create all sessions in Shopify Tool (Feature #5)
   - Generate barcodes in Shopify Tool
   - Open session in Packer Tool for warehouse execution

2. **Existing Sessions:**
   - Old sessions remain accessible in Completed Sessions tab
   - New sessions must follow Shopify Tool workflow

3. **Scanning Workflow:**
   - Scan order barcodes generated by Shopify Tool
   - System automatically normalizes and matches orders
   - No manual mapping required

#### For Developers:
1. **Removed APIs:**
   - `process_data_and_generate_barcodes()` → REMOVED
   - `generate_barcode()` → REMOVED
   - `barcode_to_order_number` → REMOVED

2. **New APIs:**
   - `load_from_shopify_analysis()` - Load sessions
   - `_normalize_order_number()` - Match orders
   - `SessionCacheManager` - Cache management

3. **Testing:**
   - Excel workflow tests now skipped
   - Focus on Shopify integration tests

### 📊 Release Metrics

| Metric | Value |
|--------|-------|
| **Code Removed** | 1,073 lines |
| **Files Deleted** | 2 (mapping_dialog.py, test_barcode_size.py) |
| **Tests Added** | 7 (normalization) |
| **Tests Updated** | 18 files |
| **Commits** | 139 since v1.2.0 |
| **Performance Gain** | 60-100s → instant UI response |

### 🎯 Next Steps (Post-Release)

**Optional Improvements:**
- Add performance timing logs (module exists, integrate fully)
- Complete test coverage documentation
- User-facing release notes for warehouse staff

### 📞 Support

For issues or questions:
- GitHub Issues: https://github.com/cognitiveclodfr/packing-tool/issues
- Documentation: `docs/` directory
- Logs: `~/.packers_assistant/logs/`

---

## [1.3.1] - 2025-12-12

### 🚀 Performance Improvements - Session Browser

**Session Browser - Background Threading & Persistent Cache (CRITICAL)**
- **Problem**: Session Browser froze UI for 60-100 seconds during refresh, slow opening, no feedback
- **Solution**: Implemented QThread background worker + persistent JSON cache
- **Features Implemented**:
  - **SessionCacheManager** (`src/session_browser/session_cache_manager.py`):
    - Disk-based JSON cache at `.session_browser_cache.json`
    - 5-minute TTL with automatic staleness detection
    - Per-client caching with timestamps
    - Survives app restarts for instant subsequent openings
  - **RefreshWorker QThread** (in `session_browser_widget.py`):
    - Background scanning of all three tabs (Active, Completed, Available)
    - Progress signals for UI updates (`refresh_progress`, `refresh_complete`)
    - Abort capability for long-running scans
    - All file I/O moved to background thread
  - **Session Browser UI Enhancements**:
    - Loading overlay with progress indicator for first-time opening
    - Auto-refresh toggle checkbox (enable/disable 30s interval)
    - Manual "Refresh Now" button
    - Abort button for stopping scans
    - Status label showing current operation
  - **Tab Refactoring**:
    - Split `refresh()` into `_scan_sessions()` (background) + `populate_table()` (main thread)
    - Applied to all three tabs: ActiveSessionsTab, CompletedSessionsTab, AvailableSessionsTab
    - Thread-safe data flow: scan → cache → UI update

**Performance Impact**:
- ✅ **First opening (no cache)**: 10-15s with loading overlay (was 60-100s blocking)
- ✅ **Second+ openings (fresh cache)**: <1s instant display (was 60-100s)
- ✅ **Background refresh**: 3-5s without blocking UI (was 60-100s blocking)
- ✅ **UI freeze time**: **0 seconds** (was 60-100s)
- ✅ **Cache hit rate**: ~90% for typical usage patterns

**User Experience**:
- Clear loading indicators (no more "empty window" confusion)
- Instant Session Browser opening with cached data
- Can interact with UI during background refresh
- User control over auto-refresh behavior
- Cache survives app restarts

**Technical Notes**:
- Cache location: `{sessions_root}/.session_browser_cache.json`
- Cache TTL: 300 seconds (5 minutes)
- Thread-safe atomic cache writes
- Backward compatible with legacy `refresh()` calls

## [1.3.0] - In Progress

### 🎯 Major Release - Session Browser & UI/UX Enhancements

### 🐛 Critical Bug Fixes

**Issue #1: Session Resume AttributeError (CRITICAL)**
- **Problem**: Application crashed with `AttributeError: 'str' object has no attribute 'get'` when resuming incomplete sessions via "Load Shopify Session" dialog
- **Root Cause**: Missing validation in state loading - corrupted or malformed packing_state.json could have strings instead of dicts in item_state lists
- **Fixes Applied**:
  - `packer_logic.py`: Added comprehensive validation in `_load_session_state()` method
    - Validates `in_progress` structure is a dict
    - Validates each order_state is a list (not string)
    - Validates each item_state is a dict with required keys
    - Logs detailed warnings for any invalid data
    - Gracefully skips invalid entries instead of crashing
  - `main.py`: Added defensive type checks before calling `.get()` on item_state
    - Lines 553-571: Added validation in `_populate_order_tree()`
    - Lines 762-781: Added validation in `_update_statistics()`
- **Impact**: Users can now safely resume partial sessions without crashes, even if state files are corrupted
- **Testing**: Verified with various state file formats including corrupted data

**Issue #2: Active Sessions Missing Progress Display (HIGH)**
- **Problem**: Active Sessions tab showed "N/A" for progress - couldn't monitor warehouse activity
- **Root Cause**: `_get_progress()` method reading from old state format, not new v1.3.0 structure with progress metadata
- **Fixes Applied**:
  - `active_sessions_tab.py`: Completely rewrote `_get_progress()` method (lines 254-361)
    - Reads from new v1.3.0 format with `progress` metadata
    - Falls back to legacy formats for backward compatibility
    - Calculates progress percentage
    - Returns in_progress count for better visibility
  - Enhanced table display (lines 400-424):
    - Shows "5/10 (50%)" format with percentage
    - Color-coded progress indicators:
      - Green (≥75%): Almost done
      - Orange (25-74%): In progress
      - Gray (<25%): Just started
      - Light gray (0%): Not started
- **Impact**: Warehouse managers can now see real-time progress of all active sessions at a glance
- **Testing**: Verified with multiple active sessions showing different progress levels

**Issue #3: Unreliable Silent Printing (CRITICAL)**
- **Problem**: Silent printing with QPrinter/win32print was unreliable - wrong printer, no confirmation, no preview
- **Desired**: Windows Photo Viewer integration for reliable printing with full user control
- **Fixes Applied**:
  - `print_dialog.py`: Replaced silent printing with Windows Photo Viewer approach
    - Removed `_print_image_win32()` and `print_via_windows()` methods
    - Added `open_in_photo_viewer()` method (lines 200-303):
      - Opens selected barcodes in Windows default image viewer (Photos or Photo Viewer)
      - Users press Ctrl+P to print with full control
      - Can select any printer, adjust settings, preview before printing
    - Added `open_in_explorer()` method (lines 305-385):
      - Alternative approach for batch printing
      - Opens Explorer with folder, users select files and right-click → Print
    - Updated UI buttons and instructions (lines 130-186):
      - "Open in Photo Viewer" primary button
      - "Open in Explorer" secondary button
      - Clear workflow instructions for users
- **Advantages**:
  - ✅ Reliable - uses native Windows printing
  - ✅ User can preview before printing
  - ✅ Full control over printer selection (not just default)
  - ✅ Can adjust print settings per job
  - ✅ Familiar Windows interface
  - ✅ Works with Citizen CL-E300 and any Windows-compatible printer
- **Impact**: Warehouse workers have reliable, predictable printing with full control
- **Testing**: Verified with Citizen CL-E300 thermal printer - successful prints with proper alignment

### ✨ Added

**Performance Optimizations (v1.3.1):**
- **JSON Caching Infrastructure**: New `json_cache.py` module with LRU cache for JSON files
  - Automatic time-based expiration (60s TTL by default)
  - Size-based eviction (LRU policy, 100 files max)
  - Cache invalidation after writes to prevent stale data
  - Reduces repeated file reads from 10-50ms to <1ms (cache hit)
  - Applied to: `packer_logic.py`, `session_history_manager.py`, `session_browser/`
  - **Impact**: Session Browser scanning 100+ sessions: 5-10x faster

- **Vectorized DataFrame Operations**: Replaced slow `iterrows()` with optimized methods
  - **main.py line 540**: Items display - replaced `iterrows()` with `itertuples()` (5-10x faster)
  - **main.py line 737**: Courier stats - replaced `iterrows()` with `itertuples()` (5-10x faster)
  - **main.py line 780**: Completed orders SKU counting - replaced nested `iterrows()` with vectorized `groupby()` (10-25x faster)
  - **main.py line 789**: SKU table population - replaced `iterrows()` with `itertuples()` (5-10x faster)
  - **Impact**: Statistics tab refresh for 500+ orders: 10-15x faster

- **Optimized Hot Paths**:
  - `packer_logic._load_session_state()`: Uses JSON cache with automatic invalidation after writes
  - `session_history_manager`: All JSON loads now cached (session_info.json, packing_state.json)
  - `session_browser/available_sessions_tab.py`: Packing list metadata cached during scanning
  - `session_browser/session_details_dialog.py`: Session files cached for quick details view

**UI/UX Improvements:**
- **Expandable Order Table**: Replaced flat table with hierarchical tree widget
  - Orders display as expandable/collapsible tree nodes
  - Child items show SKU, product name, quantity, and scan status
  - Real-time status updates with visual icons (✅ Completed, ⏳ Pending)
  - Automatic expand for in-progress orders, collapse for completed
  - Bold formatting for order headers, normal for items
  - Search/filter functionality across orders and SKUs

- **Statistics Tab**: New comprehensive session analytics view
  - **Session Totals**: Total orders, completed orders, items, unique SKUs, progress percentage
  - **By Courier**: Breakdown showing order and item counts per courier
  - **SKU Summary Table**: Complete inventory view with scan status per SKU
  - Real-time updates during packing operations
  - Scroll area for comfortable viewing of large datasets

- **Modern UI Styling**:
  - Styled group boxes with borders and rounded corners
  - Consistent 11pt font sizing throughout application
  - 30px row heights for comfortable reading
  - Rounded buttons and input fields
  - Professional padding and spacing

- **Enhanced Menu Bar**:
  - Organized into File, Session, and Settings menus
  - Icons for visual clarity (📁, 📦, ⚙️)
  - Quick access to all major functions
  - Proper keyboard shortcuts

- **New Toolbar**:
  - Quick-access buttons for common operations
  - Session info label showing active session
  - End session button in toolbar
  - Visual feedback for session state

- **Improved Layout**:
  - Minimum window size of 1200x700 for optimal viewing
  - Responsive design with proper spacing
  - Tab-based interface for Packing and Statistics views
  - Professional appearance with consistent padding

**Session Browser (Phase 3.1):**
- New unified Session Browser widget replacing Restore Session dialog and Session Monitor
- **Active Sessions Tab**: View and manage in-progress sessions
  - Real-time lock status classification (Active/Stale/Paused)
  - Worker and PC tracking for each session
  - Progress bars showing X/Y orders completed
  - Resume session action
  - Force unlock action for stale sessions
  - View Details button for comprehensive session information
- **Completed Sessions Tab**: Browse session history with analytics
  - Date range and client filters
  - Search functionality across multiple fields
  - Export to Excel
  - Sortable columns for easy data analysis
  - View Details button for detailed session analysis

**Session Browser (Phase 3.2 - NEW):**
- **Available Sessions Tab**: Shows Shopify sessions ready to start
  - Scans for packing lists that haven't been started yet
  - Displays session info, courier, order/item counts
  - Start Packing button to begin new session directly from browser
  - Client filtering
  - Automatic detection of unstarted vs. started lists
- **Session Details Dialog**: Comprehensive 3-tab view for any session
  - **Overview Tab**: Session metadata, timing, progress summary
  - **Orders Tab**: Hierarchical tree view with Phase 2b timing data
    - Expandable orders showing all items
    - Per-order duration and timestamps
    - Per-item scan times and time-from-start metrics
    - Search/filter by order number
    - Expand/Collapse all functionality
  - **Metrics Tab**: Performance statistics
    - Average time per order/item
    - Fastest/slowest orders
    - Orders per hour and items per hour rates
  - Excel export for session details with item-level timing data
  - Graceful fallback for sessions without Phase 2b timing data

**Session Management Enhancements:**
- Session Browser integrates with SessionHistoryManager for completed sessions
- Session Browser uses SessionLockManager for active session detection
- Worker information displayed in session details
- Enhanced session status visualization with color-coded indicators
- Complete workflow: Browse Available → Start Packing → Active → Completed → Details

### 🔧 Changed
- Replaced "Restore Session" button with "Session Browser" button
- Deprecated old Restore Session dialog (kept for backward compatibility)
- Deprecated Session Monitor widget (functionality merged into Session Browser Active tab)

### 🚀 Improved
- Better user experience for finding and resuming sessions
- Unified interface for all session-related operations
- Enhanced visibility into active sessions across warehouse PCs

### 📚 Documentation
- Updated CHANGELOG.md with Phase 3.1 features
- Updated README.md with Session Browser overview
- Created Phase 3.1 Implementation Report

### 🔄 Technical Changes
- New `session_browser` package with modular tab architecture
- SessionBrowserWidget: Main container with QTabWidget
- ActiveSessionsTab: Scans for locked and paused sessions
- CompletedSessionsTab: Uses SessionHistoryManager for history display
- **AvailableSessionsTab** (Phase 3.2): Scans for Shopify packing_lists without work directories
- **SessionDetailsDialog** (Phase 3.2): Dialog with 3 sub-tabs for detailed session view
  - OverviewTab: Metadata and progress display
  - OrdersTab: QTreeWidget for hierarchical order/item view
  - MetricsTab: Performance statistics display
- Integration with main.py via signals/slots
- Excel export using pandas for detailed session data
- Graceful error handling for missing timing data

### 🧪 Testing
- Comprehensive unit tests for Phase 3.2 components
- Test coverage for Available Sessions scanning logic
- Test coverage for Session Details Dialog tabs
- Mock-based testing for UI components

### 🔧 Fixed

**Priority 2 - Lock, Resume, and Cleanup Fixes:**
- **CRITICAL: Lock Creation for Shopify Sessions**: Fixed missing lock files for Shopify workflow
  - Added lock acquisition in `open_shopify_session()` after work_dir creation
  - Added lock acquisition in `_handle_start_packing_from_browser()` for Session Browser integration
  - Implemented heartbeat timer (60s interval) to keep locks alive during active sessions
  - Lock properly released in `end_session()` with heartbeat timer cleanup
  - Handles both new sessions and resume scenarios with stale lock detection
  - Prevents concurrent access to same packing list across multiple PCs
  - **BUGFIX**: Fixed TypeError in lock acquisition (client_id argument, return tuple handling, Path objects)
- **Session Resume Metadata Restoration**: Fixed lost timing data on session resume
  - Restored `completed_orders_metadata` array when loading session state
  - Phase 2b timing data (order durations, item scan times) now preserved across resume
  - Removed duplicate restoration code for cleaner logic
  - Graceful fallback for old format sessions without timing data
- **UI Cleanup - Removed Deprecated Widgets**:
  - Deleted `dashboard_widget.py` (replaced by Session Browser)
  - Deleted `session_history_widget.py` (replaced by Session Browser Completed tab)
  - Deleted `session_monitor_widget.py` (replaced by Session Browser Active tab)
  - Removed all references and menu items for deprecated widgets
  - Cleaned up client loading code that referenced removed widgets
  - Removed stats display labels from main toolbar (Total Orders Packed, Total Sessions)
  - Removed `_update_dashboard()` method
- **Worker Display Enhancement**: Improved Completed Sessions tab worker column
  - Now shows "worker_id (worker_name)" format when available
  - Graceful fallback to PC name for old sessions without worker info
  - Better visibility of who completed each session
- **Session Browser Auto-Refresh**: Added automatic refresh every 30 seconds
  - Keeps session data up-to-date without manual refresh
  - Timer properly stopped on browser close
  - Improves multi-PC warehouse workflow visibility

**Session Browser Critical Issues:**
- **Active Sessions Filter**: Fixed completed lists appearing in Active tab
  - Added session_summary.json check to skip completed packing lists
  - Completed sessions now properly filtered out from Active tab
- **Completed Sessions Multiple Lists**: Fixed sessions with multiple packing lists showing only one record
  - Removed early return in `_parse_session_directory()` that stopped after first list
  - Sessions with 3 packing lists now correctly show 3 separate records
- **View Details Consistency**: Standardized data structure passed to SessionDetailsDialog
  - Active Sessions tab now provides complete session data including worker info and progress
  - Completed Sessions tab provides standardized format matching active sessions
  - SessionDetailsDialog handles both active and completed session data gracefully
  - Overview, Orders, and Metrics tabs now display consistently regardless of source
- **Test Fixes**:
  - Fixed dict access in test_session_browser_phase32.py (record is dict, not object)
  - Added timing metadata population in test_state_persistence.py for avg_time_per_order calculation
  - Removed mock_widgets fixture (DashboardWidget, SessionHistoryWidget no longer exist)
  - Updated test_tab_navigation to expect 1 tab instead of 3 (Dashboard/History removed)

**Priority 1 - Code Duplication & Crash Handler:**
- **Unified Session Start Method**: Eliminated massive code duplication in session management
  - Created `start_shopify_packing_session()` unified method for starting/resuming packing sessions
  - Refactored `_handle_resume_session_from_browser()` to use unified method (reduced from ~180 to ~72 lines)
  - Refactored `_handle_start_packing_from_browser()` to use unified method (reduced from ~183 to ~77 lines)
  - Refactored `open_shopify_session()` packing_list mode to use unified method (simplified significantly)
  - Created `_cleanup_failed_session_start()` helper to centralize error cleanup logic
  - All error paths now consistently release locks and clean up resources
  - Comprehensive exception handling with proper user feedback
  - Improved code maintainability and reduced risk of inconsistencies
- **Application Close Handler**: Added critical `closeEvent()` handler to MainWindow
  - Prevents lock leaks when application closes unexpectedly
  - Stops heartbeat timer before cleanup (prevents lock updates during shutdown)
  - Saves packing state on unexpected close (preserves work progress)
  - Releases all session locks immediately (no 2-minute stale lock timeout)
  - Handles X button, Alt+F4, SIGTERM, and system shutdown gracefully
  - All cleanup operations wrapped in try/except for robustness
  - Never blocks shutdown (always accepts close event)
  - Critical for multi-PC warehouse deployment reliability

**Dead Code Cleanup & Maintainability:**
- **Removed Unused Methods**: Deleted 160 lines of dead code from main.py
  - `_process_shopify_packing_data()` (101 lines): Functionality replaced by PackerLogic.load_packing_list_json()
  - `open_restore_session_dialog()` (59 lines): Functionality replaced by Session Browser Active/Completed tabs
  - Both methods were well-implemented but never called anywhere in codebase
  - Verified with comprehensive grep search - zero references found
- **Removed Unused Imports**: Cleaned up 33 files across src/ and tests/
  - Used autoflake to automatically detect and remove 44 lines of unused imports
  - Removed: RestoreSessionDialog, OrderTableModel, CustomFilterProxyModel, ProfileManagerError
  - Removed unused Qt imports, typing imports, and other orphaned dependencies
  - All files still compile and function correctly
- **StatsManager Documentation**: Added comprehensive documentation explaining minimal usage
  - Decision: KEEP StatsManager (recommended approach)
  - Called once per session by design - records completion statistics
  - Critical for integration with Shopify Tool (shared Stats/global_stats.json)
  - Provides historical analytics, audit trail, and worker performance metrics
  - Essential for warehouse operations tracking and reporting
- **Impact**: Improved code maintainability, reduced cognitive load, cleaner codebase
  - 204 total lines removed (160 dead code + 44 unused imports)
  - Better documentation prevents future confusion about "unused" components
  - All functionality preserved - zero breaking changes

---

## [1.2.0] - 2025-11-19

### 🎯 Major Release - Session Management & Print Fixes

This release focuses on fixing critical session detection issues and optimizing barcode printing for production use.

### ✨ Added

**Session Management:**
- Support for multiple packing lists per Shopify session
- Real-time session statistics tracking
- Improved session history parsing for Phase 1 architecture

**User Experience:**
- Client pre-selection in Shopify session dialog
- Streamlined workflow - no double client selection needed
- Enhanced error messages with actionable information

### 🔧 Fixed

**Critical Fixes:**
- Fixed session detection for Shopify sessions (Dashboard and History Browser now working)
- Fixed path mismatch between file generation and search in session_history_manager
- Session files now correctly found in packing/*/packing_state.json structure

**Print & Barcode:**
- Fixed barcode size for 68x38mm thermal labels
- Optimized for Citizen CL-E300 printer (203 DPI)
- Fixed 1:1 scale printing - barcodes now print at correct size
- Added DPI metadata to PNG files for proper printer handling

**Integration:**
- Fixed SessionHistoryManager to support both Phase 1 (Shopify) and Legacy (Excel) structures
- Backward compatibility maintained for Excel workflow

### 🚀 Improved

**Performance:**
- Optimized session scanning for large session directories
- Improved file search performance with Phase 1 structure

**Code Quality:**
- Enhanced error handling throughout application
- Comprehensive logging for debugging
- Reduced code complexity

### 📚 Documentation

**User Documentation:**
- Updated README with v1.2.0 features and version info
- Added printer specifications
- Updated system requirements
- Enhanced troubleshooting guide
- Created comprehensive RELEASE_NOTES_v1.2.0.md

**Technical Documentation:**
- Updated API.md with Phase 1 APIs (get_packing_work_dir, load_packing_list_json)
- Updated ARCHITECTURE.md with Phase 1 directory structure
- Updated FUNCTIONS.md with v1.2.0 method signatures
- Created REFERENCE_INDEX.md cross-reference guide
- All docs versioned to 1.2.0 with last updated dates

### 🔄 Technical Changes

**Architecture:**
- Unified session state management (Phase 1 complete)
- Proper integration with shared StatsManager
- Support for multiple work directories per session

**Dependencies:**
- All dependencies verified and up to date
- No breaking changes in dependencies

### 🐛 Known Issues

- Dashboard and History Browser show minimal UI (will be enhanced in v1.3.0)
- Some TODOs remain for future features

### ⚠️ Breaking Changes

**None** - Full backward compatibility maintained with v1.1.x

### 📦 Migration Notes

**From v1.1.x to v1.2.0:**
- No migration required
- Existing sessions fully compatible
- Excel workflow unchanged
- Shopify integration enhanced

---

## [1.1.0] - 2025-11-XX

### Added
- Initial Shopify Tool integration
- Phase 1 architecture implementation
- Session locking for multi-user support

### Fixed
- Various bug fixes and improvements

---

## [1.0.0] - 2025-XX-XX

### Added
- Initial release
- Excel-based packing workflow
- Barcode scanning and printing
- Crash recovery
- Session management
