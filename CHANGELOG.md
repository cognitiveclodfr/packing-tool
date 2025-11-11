# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Shopify Tool Integration**: Full integration with Shopify Tool for unified order workflow
  - Load orders directly from Shopify session `analysis_data.json`
  - Unified work directory structure: `Sessions/CLIENT/DATE/packing/LIST_NAME/`
  - Support for multiple concurrent packing lists (e.g., DHL, PostOne)
  - Session progress tracking in `session_info.json`
  - Clear audit trail from Shopify analysis to packing completion
- **Comprehensive Integration Tests**: New test suite (`tests/test_shopify_full_workflow.py`) for complete Shopify workflow
  - Tests for full workflow from session creation to packing completion
  - Tests for directory structure verification
  - Tests for multiple concurrent packing lists
  - Tests for state restoration and audit trail
- **Documentation**:
  - Added Shopify Integration section to README.md
  - Created Shopify Integration Migration Guide (`docs/SHOPIFY_INTEGRATION_MIGRATION.md`)
  - Detailed workflow examples and troubleshooting

### Changed
- **Stricter Validation**: Enhanced order data validation for Shopify integration
  - `order_number` and `courier` fields are now required
  - Removed default "Unknown" values for missing courier data
  - ValueError raised with descriptive message if required fields missing
- **Error Handling Improvements**:
  - Better TypeError and ValueError handling in session history manager
  - Fixed `session_summary` null timestamp handling
  - Improved worker activities timestamp sorting
- **UI Robustness**:
  - Fixed AttributeError in packer mode when table items are None
  - Added null-safety checks before accessing table widget items
  - Better error logging for UI update operations

### Fixed
- **Test Failures**:
  - Fixed `test_packer_mode_and_scan_simulation` - table item null check
  - Fixed `test_reload_in_progress_order_restores_ui_state` - table item access
  - Fixed `test_summary_with_null_started_at` - TypeError handling for null timestamps
  - Fixed `test_load_from_shopify_analysis_missing_required_columns` - proper validation error raising
  - Fixed `test_get_worker_activities_sorted_by_timestamp` - improved sorting with better default values
- **Bug Fixes**:
  - PackerModeWidget: Added null check before accessing `table.item(row, col).text()`
  - SessionHistoryManager: Catch TypeError in addition to ValueError for `fromisoformat()`
  - WorkerManager: Use '0' as default timestamp for sorting instead of empty string
  - PackerLogic: Validate required order fields before DataFrame creation

### Migration Notes
- **Backward Compatibility**: All existing Excel-based workflows continue to work unchanged
- **New Workflow Available**: Shopify integration is optional - adopt when ready
- **No Breaking Changes**: All v1.2.x sessions remain fully accessible
- **Directory Structure**: Shopify sessions use nested structure, but old structure still supported

### Developer Notes
- New API method: `PackerLogic.load_from_shopify_analysis(session_dir)`
- Required order fields: `order_number`, `courier` (strict validation)
- Barcode directory can now be nested: `Sessions/CLIENT/DATE/packing/LIST/barcodes/`
- See `docs/SHOPIFY_INTEGRATION_MIGRATION.md` for full migration guide

## [1.2.0] - Previous Release

### Features
- Multi-client support with ProfileManager
- Session locking and crash recovery
- Worker management and statistics tracking
- Barcode generation and printing
- Excel column mapping
- Dark theme UI

---

**For upgrade instructions and migration guide, see:** [`docs/SHOPIFY_INTEGRATION_MIGRATION.md`](docs/SHOPIFY_INTEGRATION_MIGRATION.md)
