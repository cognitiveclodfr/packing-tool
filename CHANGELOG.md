# Changelog - Packer's Assistant

All notable changes to Packer's Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Fixed

- Resolved session completion crash when the last order in a session was also the active
  in-progress order ([#144](https://github.com/cognitiveclodfr/packing-tool/pull/144),
  commit [e29af2e](https://github.com/cognitiveclodfr/packing-tool/commit/e29af2e))
- Fixed skip-order detection so re-scanning a skipped order correctly removes it from
  the skipped list and resumes packing

---

## [1.3.2.0] - 2026-02-03

[Tag](https://github.com/cognitiveclodfr/packing-tool/releases/tag/1.3.2.0) |
[PR #143](https://github.com/cognitiveclodfr/packing-tool/pull/143) |
Commit [5f9369b](https://github.com/cognitiveclodfr/packing-tool/commit/5f9369b)

### Added

- `AsyncStateWriter` (`src/async_state_writer.py`) — write-behind queue for
  `packing_state.json`. State changes are batched and written on a background thread,
  eliminating file I/O from the scan hot path.
- `SessionStartWorker` and `SessionEndWorker` in `main.py` — session load and save now
  run in background threads with a `QProgressDialog`, keeping the UI responsive during
  long operations.
- Incremental Session Browser refresh: `save_session_dir_mtimes()` in
  `SessionCacheManager` records directory modification times; `RefreshWorker` uses mtime
  snapshots to skip unchanged directories on subsequent scans.
- `_save_session_state_async()` on `PackerLogic` — non-blocking state save used on every
  scan; `_save_session_state_sync()` / `_save_session_state()` used for checkpoints and
  session end.

### Changed

- `PackerLogic.close()` must be called on teardown to flush the async writer. Test
  fixtures that construct `PackerLogic` must `yield` and then call `logic.close()`.

---

## [1.3.1.3] - 2026-01-22

[Tag](https://github.com/cognitiveclodfr/packing-tool/releases/tag/1.3.1.3) |
[PR #141](https://github.com/cognitiveclodfr/packing-tool/pull/141) |
Commit [36f4f1e](https://github.com/cognitiveclodfr/packing-tool/commit/36f4f1e)

### Added

- Packer Mode layout redesigned to 3-column format: left info panel (order metadata,
  session progress, items summary), center items table, right controls panel.
- Order metadata panel: courier chip, shipping method, tags, system notes — populated
  from Shopify session data via `PackerLogic.get_order_metadata()`.
- Extras detection panel: when more units of a SKU are scanned than required, the panel
  appears with Keep/Remove controls for each extra item.
- Force-complete button per row — stays enabled after an item is fully packed to allow
  re-triggering if needed; Confirm button disables once complete.
- Session-wide progress bar showing completed vs total orders across the full session
  (not just the active order).
- `skip_order()` on `PackerLogic` — marks the current order as skipped, preserves its
  `in_progress` state, and clears the active order. Re-scanning a skipped order removes
  it from `skipped_orders` and resumes packing.
- `SKU_EXTRA` scan result emits a distinct orange notification ("ALREADY PACKED!")
  separate from `SKU_NOT_FOUND` ("INCORRECT ITEM!").
- History table in Packer Mode now shows Order Number and item count (2 columns).

### Changed

- `session_packing_state` now has 3 keys: `in_progress`, `completed_orders`,
  `skipped_orders`.
- Quantity > 1 rows highlighted with bold text and amber background (#ffc107 fg,
  #5a4a00 bg) for quick visual identification.
- `add_order_to_history()` signature updated to include `item_count` parameter.

---

## [1.3.1.2] - 2026-01-10

[Tag](https://github.com/cognitiveclodfr/packing-tool/releases/tag/1.3.1.2) |
Commit [48e9ab6](https://github.com/cognitiveclodfr/packing-tool/commit/48e9ab6)

### Fixed

- Confirm Manually button no longer steals keyboard focus from the barcode scanner input
  on mouse hover, preventing missed scans.

---

## [1.3.1.1] - 2026-01-08

[Tag](https://github.com/cognitiveclodfr/packing-tool/releases/tag/1.3.1.1) |
[PR #139](https://github.com/cognitiveclodfr/packing-tool/pull/139) |
Commit [f9fac61](https://github.com/cognitiveclodfr/packing-tool/commit/f9fac61)

### Fixed

- Dark and light QSS theme files are now bundled correctly in the PyInstaller executable.
  Previously, the exe could not find `styles_dark.qss` / `styles_light.qss` at runtime
  because the paths were resolved relative to the source tree rather than `sys._MEIPASS`.
- Theme path resolution updated to use a safe `MEIPASS` check with glob-based QSS
  discovery in the `.spec` file.

---

## [1.3.1.0] - 2025-12-20

[Tag](https://github.com/cognitiveclodfr/packing-tool/releases/tag/1.3.1.0) |
[PR #137](https://github.com/cognitiveclodfr/packing-tool/pull/137) |
Commit [21b0ce9](https://github.com/cognitiveclodfr/packing-tool/commit/21b0ce9)

### Fixed

- Hover state styles corrected — several buttons showed incorrect background on hover in
  dark theme.
- Menu bar colors updated for dark theme consistency.
- Fixed two application crashes triggered by edge-case UI interactions.
- Theme toggle now applies correctly without requiring a restart.
- Minor layout alignment issues in Packer Mode corrected.

---

## [1.3.0.0] - 2026-01-22

### Summary

Major release: Excel input workflow removed, barcode generation removed, and all session
creation delegated to Shopify Tool. Packer's Assistant now operates as a warehouse
execution tool only.

### Breaking Changes

- **Excel input workflow removed** — all sessions must be created in Shopify Tool.
- **Local barcode generation removed** — handled by Shopify Tool (Feature #5).
- **Manual barcode mapping removed** — replaced with automatic order number
  normalization (`PackerLogic._normalize_order_number()`).
- `barcode_to_order_number` attribute removed from `PackerLogic`.
- `start_order_packing()` now accepts `order_number` directly; barcode decoding is done
  by the caller.
- `src/sku_mapping_manager.py` deleted (was deprecated; SKU mappings managed via
  `ProfileManager`).

### Added

#### Session Browser (three-tab interface)

- **Active Sessions tab** — lists in-progress sessions with lock status, worker and PC
  info, and a Resume action.
- **Completed Sessions tab** — historical records with date/client filters, search,
  Excel export, and per-session details dialog.
- **Available Sessions tab** — scans for Shopify Tool sessions that have packing lists
  not yet started; provides a Start Packing action.

**Implementation:**

- `SessionCacheManager` (`src/session_browser/session_cache_manager.py`) — disk-based
  JSON cache (5-minute TTL) for Session Browser data. Survives app restarts.
- `RefreshWorker(QThread)` — background scanning of all three tabs; emits
  `refresh_progress` and `refresh_complete` signals.
- Auto-refresh toggle and manual Refresh button.

#### Order Number Normalization

- `PackerLogic._normalize_order_number()` strips special characters (#, !, spaces) for
  consistent barcode-to-order matching, aligned with Shopify Tool's format.

#### UI Overhaul

- Dark and light QSS themes (`styles_dark.qss`, `styles_light.qss`) replace the
  previous single stylesheet.
- Toolbar with quick-access buttons for session operations.
- Hierarchical order tree (expandable rows showing SKU / product / qty / status) in the
  main Packing tab.
- Statistics tab with per-courier breakdown and SKU summary table.

#### Session Details Dialog

Three-tab dialog reachable from Active and Completed Sessions tabs:

- **Overview** — metadata, timing, progress summary.
- **Orders** — QTreeWidget with per-order durations and per-item scan times.
- **Metrics** — orders/hour, items/hour, fastest/slowest order.

#### Session Locking Improvements

- Lock acquisition added to Shopify session open and Session Browser resume paths.
- Heartbeat timer (60-second interval) keeps locks alive during active sessions.
- Lock released in `end_session()` with heartbeat cleanup.
- `closeEvent()` handler on `MainWindow` releases locks and saves state on any close
  (X button, Alt+F4, system shutdown).

### Fixed

- Session resume `AttributeError` when `packing_state.json` had malformed entries
  (strings instead of dicts in item lists).
- Active Sessions tab showed "N/A" for progress — `_get_progress()` rewritten to read
  the current state format.
- Session Browser UI freeze during directory scans (moved to `RefreshWorker` thread).
- `session_summary.json` detection for multi-packing-list sessions.
- Serialization issues between `dict` and `SessionHistoryRecord` in Completed Sessions
  tab.
- Timezone handling in `SessionLockManager.is_lock_stale()` — timestamps now stored and
  compared as timezone-aware ISO strings.

### Removed

- `process_data_and_generate_barcodes()` — 390 lines of barcode generation code.
- `generate_barcode()` method.
- `barcode_to_order_number` mapping dictionary.
- `mapping_dialog.py` — column mapping dialog (99 lines).
- `test_barcode_size.py` (236 lines).
- `dashboard_widget.py`, `session_history_widget.py`, `session_monitor_widget.py` —
  replaced by Session Browser.
- Dependencies: `python-barcode`, `reportlab` / `pypdf` (moved to Shopify Tool).

### Performance

- JSON caching layer (`src/json_cache.py`) with LRU eviction (100-file cap, 60-second
  TTL) applied to `packer_logic.py`, `session_history_manager.py`, and session browser
  tabs.
- `iterrows()` calls in `main.py` replaced with `itertuples()` and vectorized
  `groupby()` operations for the statistics tab.

---

## [1.2.0] - 2025-11-19

### Added

- Support for multiple packing lists per Shopify session (one work directory per list
  under `packing/{list_name}/`).
- Real-time session statistics tracking.
- Client pre-selection in Shopify session dialog.
- Improved session history parsing for Phase 1 directory structure.

### Fixed

- Session detection for Shopify sessions — history browser and dashboard now find
  sessions correctly.
- Path mismatch in `SessionHistoryManager` between file generation path and search path.
- Barcode label size calibrated for 68 mm x 38 mm thermal labels at 203 DPI (Citizen
  CL-E300).
- `SessionHistoryManager` supports both Phase 1 (Shopify) and legacy (Excel) structures.

### Changed

- No breaking changes — full backward compatibility with v1.1.x.

---

## [1.1.0] - 2025-11-XX

### Added

- Initial Shopify Tool integration (Phase 1 session structure).
- Session locking for multi-PC support.

---

## [1.0.0] - 2025-XX-XX

### Added

- Initial release: Excel-based packing workflow, barcode scanning, crash recovery,
  session management.
