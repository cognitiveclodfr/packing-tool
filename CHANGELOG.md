# Changelog

All notable changes to Packing Tool will be documented in this file.

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
