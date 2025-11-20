# Changelog

All notable changes to Packing Tool will be documented in this file.

## [1.3.0] - In Progress

### 🎯 Major Release - Session Browser (Phase 3.1)

### ✨ Added

**Session Browser (Phase 3.1):**
- New unified Session Browser widget replacing Restore Session dialog and Session Monitor
- **Active Sessions Tab**: View and manage in-progress sessions
  - Real-time lock status classification (Active/Stale/Paused)
  - Worker and PC tracking for each session
  - Progress bars showing X/Y orders completed
  - Resume session action
  - Force unlock action for stale sessions
- **Completed Sessions Tab**: Browse session history with analytics
  - Date range and client filters
  - Search functionality across multiple fields
  - Export to Excel (PDF export coming in Phase 3.2)
  - Sortable columns for easy data analysis

**Session Management Enhancements:**
- Session Browser integrates with SessionHistoryManager for completed sessions
- Session Browser uses SessionLockManager for active session detection
- Worker information displayed in session details
- Enhanced session status visualization with color-coded indicators

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
- Integration with main.py via signals/slots

### ⏭️ Coming Next (Phase 3.2)
- Available Sessions Tab (Shopify sessions ready to start)
- Session Details Dialog (comprehensive session view)
- PDF export for completed sessions

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
