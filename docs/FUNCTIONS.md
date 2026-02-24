# Packer's Assistant - Functions Catalog

**Version:** 1.3.2.0 (Pre-release)
**Last Updated:** 2026-02-24

Complete catalog of all classes, methods, and functions in the Packer's Assistant application.

## Table of Contents

- [Core Business Logic](#core-business-logic)
  - [packer_logic.py](#packer_logicpy)
  - [session_manager.py](#session_managerpy)
  - [profile_manager.py](#profile_managerpy)
  - [statistics_manager.py](#statistics_managerpy)
- [Data Management](#data-management)
  - [session_lock_manager.py](#session_lock_managerpy)
  - [session_history_manager.py](#session_history_managerpy)
- [Async / Background](#async--background)
  - [async_state_writer.py](#async_state_writerpy)
  - [session_browser/session_cache_manager.py](#session_browsersession_cache_managerpy)
- [UI Components](#ui-components)
  - [main.py](#mainpy)
  - [packer_mode_widget.py](#packer_mode_widgetpy)
  - [session_browser/](#session_browser)
- [UI Dialogs](#ui-dialogs)
  - [restore_session_dialog.py](#restore_session_dialogpy)
  - [sku_mapping_dialog.py](#sku_mapping_dialogpy)
  - [print_dialog.py](#print_dialogpy)
- [Data Models](#data-models)
  - [order_table_model.py](#order_table_modelpy)
  - [custom_filter_proxy_model.py](#custom_filter_proxy_modelpy)
- [Utilities](#utilities)
  - [logger.py](#loggerpy)
  - [exceptions.py](#exceptionspy)

---

## Core Business Logic

### packer_logic.py

**Description**: Core order loading, barcode scan processing, and packing state machine.

#### Class: `PackerLogic(QObject)`

Order processing and packing state management.

**Signals:**
- `item_packed(str, str, int, int)` - Emitted when item is packed
- `order_completed(str)` - Emitted when order is complete
- `error_occurred(str)` - Emitted when error occurs
- `session_data_loaded()` - Emitted when session data loaded

**Constructor:**
- `__init__(session_dir, profile_manager, parent=None)` - Initialize PackerLogic

**Public Methods:**
- `load_packing_list_json(packing_list_path) -> Tuple[int, str]` - Load packing list from Shopify JSON
- `load_from_shopify_analysis(analysis_path) -> Tuple[int, str]` - Load session from Shopify Tool analysis
- `start_order_packing(order_number) -> tuple[bool, str, list]` - Start packing an order
- `process_sku_scan(barcode_data) -> tuple[bool, str, int, int, bool]` - Process SKU scan
- `get_order_details(order_number) -> list[dict]` - Get order items
- `get_order_state(order_number) -> list[dict]` - Get packing state
- `is_order_complete(order_number) -> bool` - Check if order complete
- `get_summary_data() -> pd.DataFrame` - Get order summary
- `get_order_metadata(order_number) -> dict` - Get per-order metadata (courier, tags, etc.)
- `skip_order(order_number)` - Skip current order; preserves in_progress state
- `save_state()` - Synchronous state save (flush + write)
- `end_session_cleanup()` - Clean up session files
- `close()` - Flush AsyncStateWriter; must be called on teardown

**Private Methods:**
- `_normalize_order_number(order_number) -> str` - Normalize order numbers for barcode matching
- `_normalize_sku(sku) -> str` - Normalize SKU for comparison
- `_apply_sku_mapping(scanned_barcode) -> str` - Apply SKU mapping
- `_save_session_state()` - Synchronous save (used for checkpoints and session end)
- `_save_session_state_async()` - Non-blocking save via AsyncStateWriter (used on every scan)

---

### session_manager.py

**Description**: Session lifecycle management with multi-PC coordination.

#### Class: `SessionManager(QObject)`

Manages creation, tracking, and cleanup of packing sessions.

**Signals:**
- `session_started(str)` - Emitted when session starts
- `session_ended(str)` - Emitted when session ends
- `heartbeat_failed()` - Emitted when heartbeat fails

**Constructor:**
- `__init__(profile_manager, lock_manager, parent=None)` - Initialize SessionManager

**Public Methods:**
- `start_session(packing_list_path, restore_dir=None) -> str` - Start new session
- `end_session()` - End current session
- `get_session_info() -> dict` - Get session information
- `is_session_active() -> bool` - Check if session active
- `get_packing_work_dir(session_path, packing_list_name) -> Path` - **[NEW v1.2.0]** Get/create Phase 1 work directory

**Private Methods:**
- `_create_session_directory(client_id) -> tuple[Path, str]` - Create session directory
- `_save_session_info(packing_list_path)` - Save session metadata
- `_update_heartbeat()` - Update session heartbeat

---

### profile_manager.py

**Description**: Client profile and configuration management.

#### Class: `ProfileManager`

Manages client profiles on centralized file server.

**Constructor:**
- `__init__(file_server_root)` - Initialize with file server path

**Public Methods:**
- `create_client_profile(client_id, config=None) -> bool` - Create new client profile
- `get_client_config(client_id) -> dict` - Load client configuration
- `update_client_config(client_id, config) -> bool` - Update client configuration
- `load_sku_mapping(client_id) -> dict` - Load SKU mappings
- `save_sku_mapping(client_id, mapping) -> bool` - Save SKU mappings
- `list_clients() -> list[str]` - List all clients
- `get_incomplete_sessions(client_id) -> list[Path]` - Find incomplete sessions
- `get_clients_root() -> Path` - Get clients root directory
- `get_sessions_root() -> Path` - Get sessions root directory
- `get_stats_root() -> Path` - Get stats root directory
- `test_connectivity() -> bool` - Test file server connection

**Private Methods:**
- `_load_json_with_lock(file_path) -> dict` - Load JSON with file locking
- `_save_json_with_lock(file_path, data) -> bool` - Save JSON with file locking
- `_create_backup(file_path)` - Create backup of file
- `_cleanup_old_backups(backup_dir, max_backups=10)` - Remove old backups

---

### statistics_manager.py

**Description**: Centralized statistics tracking and analytics.

#### Class: `StatisticsManager`

Tracks global statistics across all clients and sessions.

**Constructor:**
- `__init__(profile_manager)` - Initialize with profile manager

**Public Methods:**
- `record_session_completion(client_id, session_id, completed_orders, total_items, duration_seconds, session_metadata=None) -> bool` - Record session
- `get_client_stats(client_id) -> dict` - Get client statistics
- `get_global_stats() -> dict` - Get global statistics
- `get_performance_metrics(client_id=None, days=30) -> dict` - Calculate performance metrics
- `track_unique_order(order_id) -> bool` - Track unique order
- `is_order_tracked(order_id) -> bool` - Check if order tracked
- `get_session_history(client_id=None, limit=100) -> list[dict]` - Get session history

**Private Methods:**
- `_load_stats() -> dict` - Load statistics from file
- `_save_stats() -> bool` - Save statistics to file
- `_initialize_stats_structure() -> dict` - Create default stats structure

---

## Data Management

### session_lock_manager.py

**Description**: File-based session locking for multi-PC safety.

#### Class: `SessionLockManager`

Provides locking mechanism with heartbeat for crash detection.

**Class Constants:**
- `LOCK_FILENAME = ".session.lock"`
- `HEARTBEAT_INTERVAL = 60` seconds
- `STALE_TIMEOUT = 120` seconds

**Constructor:**
- `__init__(profile_manager)` - Initialize lock manager

**Public Methods:**
- `acquire_lock(client_id, session_dir) -> tuple[bool, Optional[str]]` - Acquire session lock
- `release_lock(session_dir) -> bool` - Release session lock
- `is_locked(session_dir) -> tuple[bool, Optional[dict]]` - Check if session locked
- `update_heartbeat(session_dir) -> bool` - Update heartbeat timestamp
- `is_lock_stale(lock_info, stale_timeout=None) -> bool` - Check if lock is stale
- `force_release_lock(session_dir) -> bool` - Force release lock
- `get_lock_display_info(lock_info) -> str` - Format lock info for display
- `get_all_active_sessions() -> dict[str, list]` - Get all active sessions

**Private Methods:**
- `_get_username() -> str` - Get current Windows username
- `_get_stale_minutes(lock_info) -> int` - Calculate stale minutes
- `_format_active_lock_message(lock_info) -> str` - Format active lock message
- `_format_stale_lock_message(lock_info) -> str` - Format stale lock message

---

### session_history_manager.py

**Description**: Historical session data queries and analytics.

#### Dataclass: `SessionHistoryRecord`

Represents a historical session with metrics.

**Fields:**
- `session_id: str` - Session identifier
- `client_id: str` - Client identifier
- `start_time: Optional[datetime]` - Start timestamp
- `end_time: Optional[datetime]` - End timestamp
- `duration_seconds: Optional[float]` - Duration
- `total_orders: int` - Total orders
- `completed_orders: int` - Completed orders
- `in_progress_orders: int` - Incomplete orders
- `total_items_packed: int` - Items packed
- `pc_name: Optional[str]` - Computer name
- `packing_list_path: Optional[str]` - File path
- `session_path: str` - Session directory

**Methods:**
- `to_dict() -> dict` - Convert to dictionary

#### Dataclass: `ClientAnalytics`

Aggregated analytics for a client.

**Fields:**
- `client_id: str` - Client identifier
- `total_sessions: int` - Total sessions
- `total_orders_packed: int` - Total orders
- `average_orders_per_session: float` - Average orders
- `average_session_duration_minutes: float` - Average duration
- `total_items_packed: int` - Total items
- `last_session_date: Optional[datetime]` - Last session date

**Methods:**
- `to_dict() -> dict` - Convert to dictionary

#### Class: `SessionHistoryManager`

Manages historical session data and analytics.

**Constructor:**
- `__init__(profile_manager)` - Initialize history manager

**Public Methods:**
- `get_client_sessions(client_id, start_date=None, end_date=None, include_incomplete=True) -> list[SessionHistoryRecord]` - Get sessions
- `get_client_analytics(client_id, start_date=None, end_date=None) -> ClientAnalytics` - Generate analytics
- `search_sessions(client_id, search_term, search_fields=None) -> list[SessionHistoryRecord]` - Search sessions
- `get_session_details(client_id, session_id) -> Optional[dict]` - Get session details
- `export_sessions_to_dict(sessions) -> list[dict]` - Export to DataFrame format

**Private Methods:**
- `_parse_session_directory(client_id, session_dir) -> Optional[SessionHistoryRecord]` - Parse session
- `_parse_session_summary(client_id, session_dir, summary_file) -> Optional[SessionHistoryRecord]` - Parse summary
- `_load_session_info(session_dir) -> Optional[dict]` - Load session info
- `_parse_session_timestamp(session_id) -> Optional[datetime]` - Parse timestamp
- `_count_packed_items(in_progress, completed) -> int` - Count packed items

---

## Async / Background

### async_state_writer.py

**Description**: Write-behind queue for non-blocking `packing_state.json` persistence.

#### Class: `AsyncStateWriter`

Batches state write requests and executes them on a background thread.

**Constructor:**
- `__init__()` - Initialize writer; starts background thread

**Public Methods:**
- `schedule(path, data)` - Queue a write; previous pending write for same path is dropped
- `flush()` - Block until all queued writes have completed
- `close()` - Flush and shut down background thread; must be called on teardown

**Usage pattern:**
```python
# Hot path (every scan) — non-blocking:
logic._save_session_state_async()

# Checkpoint / session end — blocking:
logic._save_session_state_sync()
```

---

### session_browser/session_cache_manager.py

**Description**: Disk-based persistent cache for Session Browser scan results.

#### Class: `SessionCacheManager`

**Constructor:**
- `__init__(cache_path)` - Initialize with path to cache JSON file

**Public Methods:**
- `get_cached_data(client_id=None) -> Optional[dict]` - Retrieve cached data (None if stale or missing)
- `save_to_cache(client_id, data)` - Save scan results; updates timestamp
- `save_session_dir_mtimes(mtimes)` - Store directory mtime snapshot for incremental refresh
- `clear_cache()` - Delete all cached data

**Cache TTL:** 300 seconds (5 minutes)

---

## UI Components

### main.py

**Description**: Main application window and orchestrator.

#### Class: `MainWindow(QMainWindow)`

Central application coordinator.

**Constructor:**
- `__init__(profile_manager, lock_manager, stats_manager)` - Initialize main window

**Public Methods:**
- `start_session()` - Start new packing session
- `end_session()` - End current session
- `restore_session()` - Restore incomplete session
- `switch_to_dashboard()` - Switch to dashboard view
- `switch_to_history()` - Switch to history view
- `open_sku_mapping_dialog()` - Open SKU mapping editor
- `open_session_monitor()` - Open session monitor

**Private Methods:**
- `_init_ui()` - Initialize UI components
- `_setup_signals()` - Connect signals and slots
- `_load_stylesheet()` - Load QSS theme
- `_create_menu_view()` - Create main menu
- `_create_session_view()` - Create session view
- `_create_packer_mode_view()` - Create packer mode view
- `_on_scanner_input(barcode_data)` - Handle barcode scan
- `_on_item_packed(order_number, sku, packed_count, required_count)` - Handle item packed
- `_on_order_completed(order_number)` - Handle order completed
- `_on_error_occurred(error_message)` - Handle error
- `_flash_border(color, duration=500)` - Flash visual feedback
- `_play_sound(sound_type)` - Play audio feedback
- `_auto_clear_after_complete()` - Auto-clear after order complete
- `_generate_completion_report()` - Generate Excel report
- `_load_available_clients()` - Load client list
- `setup_order_table(summary_df)` - Setup order summary table

#### Function: `main()`

Application entry point.

**Description**: Initialize managers and start application.

**Returns**: `int` - Exit code

---

### packer_mode_widget.py

**Description**: Barcode scanning interface widget.

#### Class: `PackerModeWidget(QWidget)`

Interactive packer mode UI.

**Signals:**
- `barcode_scanned(str)` - Emitted when barcode scanned
- `exit_packing_mode()` - Emitted when exit button clicked
- `skip_order_requested()` - Emitted when Skip Order button clicked
- `force_complete_sku(str)` - Emitted when Force button clicked for a row

**Constructor:**
- `__init__(parent=None)` - Initialize widget

**Public Methods:**
- `display_order(items, order_state)` - Display order items in center table
- `display_order_metadata(metadata, courier)` - Populate left panel metadata frame
- `clear_order_info()` - Hide the metadata frame
- `update_item_row(row, packed_count, is_complete)` - Update item row status
- `update_session_progress(completed, total)` - Update session-wide progress bar
- `show_notification(text, color_name)` - Show notification banner
- `show_previous_order_items(items)` - Show dimmed previous-order items
- `clear_screen()` - Clear current order display
- `set_focus_to_scanner()` - Focus scanner input
- `update_raw_scan_display(text)` - Update raw scan text
- `add_order_to_history(order_number, item_count=0)` - Add order to history table

**Private Methods:**
- `_on_scan()` - Handle scan event
- `_on_manual_confirm(sku)` - Handle manual confirm

---

### session_browser/

**Description**: Session Browser package — three-tab session management UI.

**Location:** `src/session_browser/`

**Key classes:**

- `SessionBrowserWidget(QWidget)` — main container with `QTabWidget`; hosts the three tabs and the `RefreshWorker`
- `ActiveSessionsTab(QWidget)` — shows locked/in-progress sessions; resume and force-unlock actions
- `CompletedSessionsTab(QWidget)` — shows completed sessions via `SessionHistoryManager`; date/client filters, Excel export
- `AvailableSessionsTab(QWidget)` — scans for Shopify sessions with unstarted packing lists; Start Packing action
- `SessionDetailsDialog(QDialog)` — three-tab detail view (Overview, Orders tree, Metrics) for any session
- `RefreshWorker(QThread)` — background directory scanner; emits `refresh_progress(str)` and `refresh_complete(dict)`

---

## UI Dialogs

### restore_session_dialog.py

**Description**: Session restoration dialog with lock status.

#### Class: `RestoreSessionDialog(QDialog)`

Select and restore incomplete sessions.

**Constructor:**
- `__init__(client_id, profile_manager, lock_manager, parent=None)` - Initialize dialog

**Public Methods:**
- `get_selected_session() -> Optional[Path]` - Get selected session

**Private Methods:**
- `_init_ui()` - Initialize UI
- `_load_sessions()` - Load incomplete sessions
- `_on_selection_changed()` - Handle selection
- `_on_item_double_clicked(item)` - Handle double-click
- `_on_restore()` - Handle restore button

---

### sku_mapping_dialog.py

**Description**: SKU mapping editor dialog.

#### Class: `SKUMappingDialog(QDialog)`

Manage barcode-to-SKU mappings.

**Constructor:**
- `__init__(client_id, profile_manager, parent=None)` - Initialize dialog

**Public Methods:**
- `get_mappings() -> dict[str, str]` - Get current mappings

**Private Methods:**
- `_init_ui()` - Initialize UI
- `_populate_table()` - Populate table with mappings
- `_add_item()` - Add new mapping
- `_edit_item()` - Edit selected mapping
- `_delete_item()` - Delete selected mapping
- `_reload_from_server()` - Reload from file server
- `_save_and_close()` - Save and close dialog

---

### print_dialog.py

**Description**: Barcode label printing dialog.

#### Class: `PrintDialog(QDialog)`

Preview and print barcode labels.

**Constructor:**
- `__init__(orders_data, parent=None)` - Initialize dialog

**Public Methods:**
- `print_widget()` - Open print dialog and print

---

## Data Models

### order_table_model.py

**Description**: Qt table model for order summary.

#### Class: `OrderTableModel(QAbstractTableModel)`

DataFrame-backed Qt table model.

**Constructor:**
- `__init__(data, parent=None)` - Initialize with DataFrame

**Qt Model Methods:**
- `rowCount(parent=QModelIndex()) -> int` - Get row count
- `columnCount(parent=QModelIndex()) -> int` - Get column count
- `data(index, role=Qt.DisplayRole) -> Any` - Get cell data
- `headerData(section, orientation, role=Qt.DisplayRole) -> Optional[str]` - Get header
- `setData(index, value, role=Qt.EditRole) -> bool` - Set cell data
- `flags(index) -> Qt.ItemFlags` - Get item flags

**Custom Methods:**
- `get_column_index(column_name) -> int` - Get column index by name

---

### custom_filter_proxy_model.py

**Description**: Advanced multi-column filter model.

#### Class: `CustomFilterProxyModel(QSortFilterProxyModel)`

Filter by order, status, or SKU.

**Constructor:**
- `__init__(parent=None)` - Initialize proxy model

**Public Methods:**
- `set_processed_df(df)` - Set detailed DataFrame
- `setFilterFixedString(text)` - Set search term

**Qt Override Methods:**
- `filterAcceptsRow(source_row, source_parent) -> bool` - Filter logic

---

## Utilities

### logger.py

**Description**: Centralized logging configuration.

#### Class: `AppLogger`

Thread-safe logging with rotation.

**Class Methods:**
- `get_logger(name=None) -> logging.Logger` - Get configured logger

**Private Class Methods:**
- `_setup_logging()` - Configure logging system
- `_cleanup_old_logs()` - Remove old log files

#### Function: `get_logger(name=None) -> logging.Logger`

Convenience function for getting logger.

---

### exceptions.py

**Description**: Custom exception classes.

#### Class: `PackingToolError(Exception)`

Base exception for all application errors.

#### Class: `NetworkError(PackingToolError)`

File server connectivity errors.

#### Class: `SessionLockedError(PackingToolError)`

Session locked by another PC.

#### Class: `StaleLockError(SessionLockedError)`

Session has stale lock (crashed).

#### Class: `ProfileError(PackingToolError)`

Client profile operation errors.

#### Class: `ValidationError(PackingToolError)`

Input validation errors.

---

## Summary Statistics

### Module Count
- **Total Modules**: ~20 (including session_browser/ sub-package)
- **Core Logic**: 4 (packer_logic, session_manager, profile_manager, statistics_manager)
- **Data Management**: 2 (session_lock_manager, session_history_manager)
- **Async / Background**: 2 (async_state_writer, session_cache_manager)
- **UI Components**: 3 (main, packer_mode_widget, session_browser/)
- **UI Dialogs**: 3 (restore_session_dialog, sku_mapping_dialog, print_dialog)
- **Data Models**: 2 (order_table_model, custom_filter_proxy_model)
- **Utilities**: 2 (logger, exceptions)

### Class Count (approximate)
- **Core logic**: ~6
- **Session browser**: ~6 (SessionBrowserWidget + 4 tabs + SessionDetailsDialog)
- **Data models**: 2
- **Exception classes**: 6
- **Worker threads**: ~4 (SessionStartWorker, SessionEndWorker, RefreshWorker, SessionScanWorker)

### Method Count by Type

#### Public Methods
- **Total Public Methods**: ~160
- **PackerLogic**: 12
- **SessionManager**: 4
- **ProfileManager**: 10
- **StatisticsManager**: 7
- **SessionLockManager**: 8
- **SessionHistoryManager**: 6
- **MainWindow**: 8
- **Widgets**: ~50 (across all widgets)
- **Dialogs**: ~20 (across all dialogs)
- **Models**: ~15 (Qt model methods)

#### Private Methods
- **Total Private Methods**: ~60
- **Implementation helpers**: ~40
- **UI initialization**: ~20

#### Special Methods
- **Constructors (`__init__`)**: 27
- **Qt Overrides**: ~25
- **Signal Handlers**: ~30

### Lines of Code (Approximate)
- **packer_logic.py**: ~650 lines
- **session_manager.py**: ~300 lines
- **profile_manager.py**: ~400 lines
- **statistics_manager.py**: ~350 lines
- **session_lock_manager.py**: ~540 lines
- **session_history_manager.py**: ~590 lines
- **main.py**: ~1200 lines
- **Widgets**: ~800 lines total
- **Dialogs**: ~600 lines total
- **Models**: ~260 lines total
- **Utilities**: ~200 lines total
- **Total**: ~5900 lines

---

## Function Reference by Category

### File Operations
- `ProfileManager.load_sku_mapping()` - Load SKU mapping with locking
- `ProfileManager.save_sku_mapping()` - Save SKU mapping with locking
- `ProfileManager._load_json_with_lock()` - Thread-safe JSON read
- `ProfileManager._save_json_with_lock()` - Thread-safe JSON write
- `PackerLogic._save_session_state()` - Synchronous state save
- `PackerLogic._save_session_state_async()` - Async state save
- `AsyncStateWriter.schedule()` - Queue a write
- `AsyncStateWriter.flush()` - Flush pending writes
- `SessionCacheManager.save_to_cache()` - Persist session cache

### Session Management
- `SessionManager.start_session()` - Create new session
- `SessionManager.end_session()` - End session
- `SessionManager._create_session_directory()` - Create directory
- `SessionManager._update_heartbeat()` - Update heartbeat

### Lock Management
- `SessionLockManager.acquire_lock()` - Acquire lock
- `SessionLockManager.release_lock()` - Release lock
- `SessionLockManager.update_heartbeat()` - Update heartbeat
- `SessionLockManager.force_release_lock()` - Force release
- `SessionLockManager.is_lock_stale()` - Check staleness

### Statistics & Analytics
- `StatisticsManager.record_session_completion()` - Record session
- `StatisticsManager.get_client_stats()` - Client statistics
- `StatisticsManager.get_performance_metrics()` - Calculate metrics
- `SessionHistoryManager.get_client_analytics()` - Generate analytics

### UI Updates
- `MainWindow._on_scanner_input()` - Handle scan
- `MainWindow._on_item_packed()` - Update item UI
- `MainWindow._on_order_completed()` - Show completion
- `PackerModeWidget.update_item_row()` - Update table row
- `PackerModeWidget.show_notification()` - Show notification

### Data Queries
- `SessionHistoryManager.get_client_sessions()` - Query sessions
- `SessionHistoryManager.search_sessions()` - Search sessions
- `StatisticsManager.get_session_history()` - Get history
- `ProfileManager.get_incomplete_sessions()` - Find incomplete

### SKU Processing
- `PackerLogic.process_sku_scan()` - Process SKU scan
- `PackerLogic._normalize_sku()` - Normalize SKU
- `PackerLogic._apply_sku_mapping()` - Apply mapping

---

## Index by Function Name (Alphabetical)

### A
- `acquire_lock()` - SessionLockManager
- `add_order_to_history()` - PackerModeWidget

### C
- `clear_screen()` - PackerModeWidget
- `close()` - AsyncStateWriter, PackerLogic
- `columnCount()` - OrderTableModel
- `create_client_profile()` - ProfileManager

### D
- `data()` - OrderTableModel
- `display_order()` - PackerModeWidget

### E
- `end_session()` - SessionManager, MainWindow
- `end_session_cleanup()` - PackerLogic
- `export_sessions_to_dict()` - SessionHistoryManager

### F
- `filterAcceptsRow()` - CustomFilterProxyModel
- `flags()` - OrderTableModel
- `force_release_lock()` - SessionLockManager

### G
- `get_all_active_sessions()` - SessionLockManager
- `get_cached_data()` - SessionCacheManager
- `get_client_analytics()` - SessionHistoryManager
- `get_client_config()` - ProfileManager
- `get_client_sessions()` - SessionHistoryManager
- `get_client_stats()` - StatisticsManager
- `get_clients_root()` - ProfileManager
- `get_column_index()` - OrderTableModel
- `get_global_stats()` - StatisticsManager
- `get_incomplete_sessions()` - ProfileManager
- `get_lock_display_info()` - SessionLockManager
- `get_logger()` - AppLogger, logger module
- `get_mappings()` - SKUMappingDialog
- `get_order_details()` - PackerLogic
- `get_order_metadata()` - PackerLogic
- `get_order_state()` - PackerLogic
- `get_performance_metrics()` - StatisticsManager
- `get_selected_session()` - RestoreSessionDialog
- `get_session_details()` - SessionHistoryManager
- `get_session_history()` - StatisticsManager
- `get_session_info()` - SessionManager
- `get_sessions_root()` - ProfileManager
- `get_stats_root()` - ProfileManager
- `get_summary_data()` - PackerLogic

### H
- `headerData()` - OrderTableModel

### I
- `is_lock_stale()` - SessionLockManager
- `is_locked()` - SessionLockManager
- `is_order_complete()` - PackerLogic
- `is_order_tracked()` - StatisticsManager
- `is_session_active()` - SessionManager

### L
- `list_clients()` - ProfileManager
- `load_from_shopify_analysis()` - PackerLogic
- `load_packing_list_json()` - PackerLogic
- `load_sku_mapping()` - ProfileManager

### M
- `main()` - main module

### O
- `open_sku_mapping_dialog()` - MainWindow

### P
- `print_widget()` - PrintDialog
- `process_sku_scan()` - PackerLogic

### R
- `record_session_completion()` - StatisticsManager
- `release_lock()` - SessionLockManager
- `rowCount()` - OrderTableModel

### S
- `save_session_dir_mtimes()` - SessionCacheManager
- `save_to_cache()` - SessionCacheManager
- `save_sku_mapping()` - ProfileManager
- `save_state()` - PackerLogic
- `search_sessions()` - SessionHistoryManager
- `set_auto_refresh()` - SessionMonitorWidget
- `set_focus_to_scanner()` - PackerModeWidget
- `set_processed_df()` - CustomFilterProxyModel
- `set_subtitle()` - MetricCard
- `set_value()` - MetricCard
- `setData()` - OrderTableModel
- `setFilterFixedString()` - CustomFilterProxyModel
- `setup_order_table()` - MainWindow
- `show_notification()` - PackerModeWidget
- `start_order_packing()` - PackerLogic
- `start_session()` - SessionManager

### T
- `test_connectivity()` - ProfileManager
- `to_dict()` - SessionHistoryRecord, ClientAnalytics
- `track_unique_order()` - StatisticsManager

### U
- `update_client_config()` - ProfileManager
- `update_heartbeat()` - SessionLockManager
- `update_item_row()` - PackerModeWidget
- `update_raw_scan_display()` - PackerModeWidget

---

**Document Version**: 1.3.2.0 (Pre-release)
**Last Updated**: 2026-02-24
