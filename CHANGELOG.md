# Changelog

All notable changes to Packing Tool will be documented in this file.

## [1.3.0] - In Progress

### 🎯 Major Release - Session Browser & UI/UX Enhancements

### ✨ Added

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
  - Applied Fusion style for consistent cross-platform appearance
  - Custom light color palette with professional blue highlights
  - Styled group boxes with borders and rounded corners
  - Consistent 11pt font sizing throughout application
  - 30px row heights for comfortable reading
  - Rounded buttons and input fields

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
