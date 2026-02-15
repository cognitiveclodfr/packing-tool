"""
Session Browser Widget - Main Container

Provides tabbed interface for browsing active, completed, and available packing sessions.
Replaces old Restore Session dialog and Session Monitor.

Features (v1.3.1):
- Background threading for non-blocking session scans
- Persistent session cache for instant opening
- Loading overlay for initial scan
- Auto-refresh with user control
- Manual refresh with progress indication
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QCheckBox, QLabel, QFrame
)
from PySide6.QtCore import Signal, QTimer, QThread, Qt

from pathlib import Path
import time

from logger import get_logger
from .active_sessions_tab import ActiveSessionsTab
from .completed_sessions_tab import CompletedSessionsTab
from .available_sessions_tab import AvailableSessionsTab
from .session_cache_manager import SessionCacheManager

logger = get_logger(__name__)


class RefreshWorker(QThread):
    """
    Background worker thread for scanning sessions without blocking UI.

    This thread scans all three tabs (Active, Completed, Available) and emits
    results back to the main thread for UI updates. All file I/O happens here.

    After successful scan, results are saved to persistent cache for fast
    Session Browser opening on next launch.

    Signals:
        refresh_started: Emitted when scan begins
        refresh_progress: Emitted with progress updates (current_tab, total_tabs)
        refresh_complete: Emitted with scan results for all tabs
        refresh_failed: Emitted if scan fails with error message
    """

    # Signals to communicate with main thread
    refresh_started = Signal()
    refresh_progress = Signal(str, int, int)  # (tab_name, current, total)
    refresh_complete = Signal(list, list, list)  # (active, completed, available)
    refresh_failed = Signal(str)  # error_message

    def __init__(self, active_tab, completed_tab, available_tab, cache_manager: SessionCacheManager):
        """
        Initialize refresh worker.

        Args:
            active_tab: ActiveSessionsTab instance
            completed_tab: CompletedSessionsTab instance
            available_tab: AvailableSessionsTab instance
            cache_manager: SessionCacheManager for persistent caching
        """
        super().__init__()
        self.active_tab = active_tab
        self.completed_tab = completed_tab
        self.available_tab = available_tab
        self.cache_manager = cache_manager
        self._abort = False

    def abort(self):
        """Request worker to abort current operation."""
        self._abort = True

    def run(self):
        """
        Execute background scan of all sessions.

        This method runs in a background thread. All file I/O happens here.
        Results are emitted via signals to update UI on main thread.
        After successful scan, results are saved to persistent cache.
        """
        try:
            logger.info("Background refresh started")
            start_time = time.time()
            self.refresh_started.emit()

            # Scan Active Sessions (Tab 1/3)
            if self._abort:
                logger.info("Refresh aborted before active scan")
                return

            self.refresh_progress.emit("Active Sessions", 1, 3)
            active_start = time.time()
            active_data = self.active_tab._scan_sessions()
            active_time = time.time() - active_start
            logger.info(f"Active sessions scan completed in {active_time:.2f}s")

            # Scan Completed Sessions (Tab 2/3)
            if self._abort:
                logger.info("Refresh aborted before completed scan")
                return

            self.refresh_progress.emit("Completed Sessions", 2, 3)
            completed_start = time.time()
            completed_data = self.completed_tab._scan_sessions()
            completed_time = time.time() - completed_start
            logger.info(f"Completed sessions scan completed in {completed_time:.2f}s")

            # Scan Available Sessions (Tab 3/3)
            if self._abort:
                logger.info("Refresh aborted before available scan")
                return

            self.refresh_progress.emit("Available Sessions", 3, 3)
            available_start = time.time()
            available_data = self.available_tab._scan_sessions()
            available_time = time.time() - available_start
            logger.info(f"Available sessions scan completed in {available_time:.2f}s")

            # Save to persistent cache
            if not self._abort:
                cache_start = time.time()
                self.cache_manager.save_cached_data(
                    active_data,
                    completed_data,
                    available_data
                )
                cache_time = time.time() - cache_start
                logger.info(f"Cache saved in {cache_time:.2f}s")

                # Emit results
                total_time = time.time() - start_time
                logger.info(
                    f"PERFORMANCE: Background refresh completed in {total_time:.2f}s "
                    f"(active: {active_time:.2f}s, completed: {completed_time:.2f}s, "
                    f"available: {available_time:.2f}s, cache: {cache_time:.2f}s)"
                )
                self.refresh_complete.emit(active_data, completed_data, available_data)
            else:
                logger.info("Refresh aborted after scans completed")

        except Exception as e:
            logger.error(f"Background refresh failed: {e}", exc_info=True)
            self.refresh_failed.emit(str(e))


class SessionBrowserWidget(QWidget):
    """
    Main Session Browser widget with 3 tabs:
    - Active Sessions (in-progress, locked)
    - Completed Sessions (history with analytics)
    - Available Sessions (Shopify sessions ready to start) [Phase 3.2]

    Features (v1.3.1):
    - Instant opening with cached data (if available)
    - Background refresh updates cache without blocking UI
    - Auto-refresh with configurable interval (default: 30s)
    - Manual refresh button
    - Enable/disable auto-refresh checkbox
    - Loading overlay for initial scan
    - Progress indicator during background scan
    - Abort button for long-running scans
    """

    # Signals
    resume_session_requested = Signal(dict)  # {session_path, client_id, packing_list_name}
    start_packing_requested = Signal(dict)  # {session_path, client_id, packing_list_name, list_file}
    session_selected = Signal(dict)  # Generic session selection

    def __init__(
        self,
        profile_manager,
        session_manager,
        session_lock_manager,
        session_history_manager,
        worker_manager,
        parent=None
    ):
        """
        Initialize Session Browser.

        Args:
            profile_manager: ProfileManager instance
            session_manager: SessionManager instance
            session_lock_manager: SessionLockManager instance
            session_history_manager: SessionHistoryManager instance
            worker_manager: WorkerManager instance
            parent: Parent widget
        """
        super().__init__(parent)

        # Store managers
        self.profile_manager = profile_manager
        self.session_manager = session_manager
        self.session_lock_manager = session_lock_manager
        self.session_history_manager = session_history_manager
        self.worker_manager = worker_manager

        # Initialize cache manager (use app cache dir, not Sessions dir)
        import os
        cache_dir = Path(os.path.expanduser("~")) / ".packers_assistant" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_manager = SessionCacheManager(cache_dir)

        # Background worker state
        self.refresh_worker = None

        # Load auto-refresh preference and last refresh time from settings
        from PySide6.QtCore import QSettings
        self.settings = QSettings("PackingTool", "SessionBrowser")

        # Load auto-refresh enabled state (default: True on first run)
        self._auto_refresh_enabled = self.settings.value("auto_refresh_enabled", True, type=bool)
        logger.info(f"Loaded auto-refresh preference: {self._auto_refresh_enabled} (type: {type(self._auto_refresh_enabled)})")

        self._initial_load_complete = False
        self._auto_refresh_interval_ms = 600000  # 10 minutes

        self._init_ui()
        self._connect_signals()

        # Load cached data immediately (if available)
        self._load_cached_data_on_init()

        # Setup auto-refresh timer (10 minutes)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_auto_refresh_triggered)

        # Start timer based on saved preference and calculate time until next refresh
        self._setup_auto_refresh_timer()

        logger.info(f"SessionBrowserWidget initialized with cache support (auto-refresh: {self._auto_refresh_enabled})")

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # === TOP CONTROLS ===
        controls_layout = QHBoxLayout()

        # Manual refresh button
        self.refresh_button = QPushButton("🔄 Refresh Now")
        self.refresh_button.clicked.connect(self.refresh_all)
        controls_layout.addWidget(self.refresh_button)

        # Auto-refresh checkbox
        self.auto_refresh_checkbox = QCheckBox("Auto-refresh (10min)")
        self.auto_refresh_checkbox.setChecked(self._auto_refresh_enabled)  # Restore saved state
        self.auto_refresh_checkbox.stateChanged.connect(self._on_auto_refresh_toggled)
        controls_layout.addWidget(self.auto_refresh_checkbox)

        # Status label (shows "Refreshing..." during scan)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        controls_layout.addWidget(self.status_label)

        controls_layout.addStretch()

        # Abort button (only visible during refresh)
        self.abort_button = QPushButton("Abort")
        self.abort_button.clicked.connect(self._abort_refresh)
        self.abort_button.setVisible(False)
        controls_layout.addWidget(self.abort_button)

        layout.addLayout(controls_layout)

        # === TABS ===
        self.tab_widget = QTabWidget()

        # Create tabs
        self.active_tab = ActiveSessionsTab(
            profile_manager=self.profile_manager,
            session_lock_manager=self.session_lock_manager,
            worker_manager=self.worker_manager,
            parent=self
        )

        self.completed_tab = CompletedSessionsTab(
            profile_manager=self.profile_manager,
            session_history_manager=self.session_history_manager,
            parent=self
        )

        self.available_tab = AvailableSessionsTab(
            profile_manager=self.profile_manager,
            session_manager=self.session_manager,
            parent=self
        )

        # Add tabs
        self.tab_widget.addTab(self.active_tab, "Active Sessions")
        self.tab_widget.addTab(self.completed_tab, "Completed Sessions")
        self.tab_widget.addTab(self.available_tab, "Available Sessions")

        layout.addWidget(self.tab_widget)

        # Note: Loading overlay removed - status label provides sufficient feedback
        # without blocking user interaction

    def _connect_signals(self):
        """Connect internal signals."""
        # Active tab signals
        self.active_tab.resume_requested.connect(self._handle_resume_request)
        self.active_tab.refresh_requested.connect(self.refresh_all)

        # Completed tab signals
        self.completed_tab.session_selected.connect(self.session_selected.emit)
        self.completed_tab.refresh_requested.connect(self.refresh_all)

        # Available tab signals
        self.available_tab.start_packing_requested.connect(self._handle_start_packing_request)
        self.available_tab.refresh_requested.connect(self.refresh_all)

    def _handle_resume_request(self, session_info: dict):
        """
        Handle resume request from Active tab.

        Args:
            session_info: Dict with session_path, client_id, packing_list_name, lock_info
        """
        # Emit signal to main.py
        self.resume_session_requested.emit(session_info)

    def _handle_start_packing_request(self, packing_info: dict):
        """
        Handle start packing request from Available tab.

        Args:
            packing_info: Dict with session_path, client_id, packing_list_name, list_file
        """
        # Emit signal to main.py
        self.start_packing_requested.emit(packing_info)

    def _load_cached_data_on_init(self):
        """
        Load cached data immediately on widget initialization.

        Strategy:
        - If cache exists and fresh: Show immediately + schedule background refresh
        - If cache exists and stale: Show immediately + start background refresh NOW
        - If no cache: Show loading overlay + start background refresh NOW
        """
        logger.info("Loading cached data on initialization")

        # Try to get cached data
        cached = self.cache_manager.get_cached_data()

        if cached and not cached['is_stale']:
            # Cache HIT - Fresh data available
            logger.info("Fresh cache found, loading immediately")
            self._populate_from_cache(cached)
            self.status_label.setText("✅ Loaded from cache (fresh)")

            # Schedule background refresh for later
            QTimer.singleShot(5000, self.refresh_all)  # Refresh after 5 seconds

        elif cached and cached['is_stale']:
            # Cache HIT but STALE - Show stale data + refresh now
            logger.info("Stale cache found, showing stale data and refreshing")
            self._populate_from_cache(cached)
            self.status_label.setText("⚠️ Loading from stale cache, refreshing in background...")

            # Start background refresh immediately
            QTimer.singleShot(100, self.refresh_all)

        else:
            # Cache MISS - Show empty tables + scan in background
            logger.info("No cache found, starting background scan")
            self.status_label.setText("⏳ Loading sessions in background...")

            # Start background refresh immediately
            QTimer.singleShot(100, self.refresh_all)

    def _populate_from_cache(self, cached_data: dict):
        """Populate UI tables from cached data."""
        logger.info("Populating UI from cached data")

        self.active_tab.populate_table(cached_data['active'])
        self.completed_tab.populate_table(cached_data['completed'])
        self.available_tab.populate_table(cached_data['available'])

        self._initial_load_complete = True

    def _setup_auto_refresh_timer(self):
        """
        Setup auto-refresh timer based on saved preference and last refresh time.

        This makes the timer "persistent" across Session Browser open/close cycles.
        If enough time has passed since last refresh, triggers immediate refresh.
        Otherwise, schedules next refresh for remaining time.
        """
        if not self._auto_refresh_enabled:
            logger.info("Auto-refresh is disabled, not starting timer")
            return

        # Get last refresh timestamp (Unix timestamp in seconds)
        last_refresh = self.settings.value("last_refresh_time", 0, type=float)
        current_time = time.time()

        if last_refresh == 0:
            # First time - start timer normally
            logger.info(f"First Session Browser open, starting auto-refresh timer ({self._auto_refresh_interval_ms}ms)")
            self.refresh_timer.start(self._auto_refresh_interval_ms)
        else:
            # Calculate time since last refresh
            time_since_refresh_ms = (current_time - last_refresh) * 1000
            time_until_next_refresh_ms = self._auto_refresh_interval_ms - time_since_refresh_ms

            if time_until_next_refresh_ms <= 0:
                # Overdue - refresh immediately (but not on initial load, cache will trigger it)
                logger.info(f"Auto-refresh is overdue ({time_since_refresh_ms:.0f}ms since last), will refresh with cache load")
                # Start timer for next cycle
                self.refresh_timer.start(self._auto_refresh_interval_ms)
            else:
                # Schedule next refresh for remaining time
                logger.info(
                    f"Auto-refresh timer: {time_until_next_refresh_ms:.0f}ms until next refresh "
                    f"({time_since_refresh_ms:.0f}ms since last)"
                )
                self.refresh_timer.start(int(time_until_next_refresh_ms))

    # Note: Loading overlay methods removed - using status label only for better UX

    def _on_auto_refresh_toggled(self, state):
        """Handle auto-refresh checkbox toggle."""
        was_enabled = self._auto_refresh_enabled
        self._auto_refresh_enabled = (state == Qt.Checked)

        logger.info(f"Auto-refresh toggled: {was_enabled} -> {self._auto_refresh_enabled}")

        # Save preference to settings
        self.settings.setValue("auto_refresh_enabled", self._auto_refresh_enabled)

        if self._auto_refresh_enabled:
            logger.info("Auto-refresh enabled (10 minutes)")
            # Setup timer with persistent state
            self._setup_auto_refresh_timer()
            self.status_label.setText("Auto-refresh: ON (10min)")
            # Clear status after 2 seconds
            QTimer.singleShot(2000, lambda: self.status_label.setText(""))
        else:
            logger.info("Auto-refresh disabled")
            self.refresh_timer.stop()
            self.status_label.setText("Auto-refresh: OFF")

    def _on_auto_refresh_triggered(self):
        """Called by timer - only refresh if enabled."""
        if self._auto_refresh_enabled:
            logger.debug("Auto-refresh triggered")
            self.refresh_all()
            # Timer will be restarted with full interval after refresh completes
        else:
            logger.debug("Auto-refresh triggered but disabled, skipping")

    def refresh_all(self):
        """
        Refresh all tabs using background worker.

        This is the main refresh entry point. It starts a background thread
        to scan sessions without blocking the UI.

        If initial load is not complete, loading overlay is shown.
        """
        # Check if refresh already in progress
        if self.refresh_worker and self.refresh_worker.isRunning():
            logger.warning("Refresh already in progress, skipping")
            return

        logger.info("Starting background refresh")

        # Disable refresh button during scan
        self.refresh_button.setEnabled(False)
        self.status_label.setText("🔄 Refreshing in background...")
        self.abort_button.setVisible(True)

        # Note: No loading overlay - users can browse existing data while refresh happens

        # Create and start background worker
        self.refresh_worker = RefreshWorker(
            self.active_tab,
            self.completed_tab,
            self.available_tab,
            self.cache_manager  # Pass cache manager
        )

        # Connect signals
        self.refresh_worker.refresh_started.connect(self._on_refresh_started)
        self.refresh_worker.refresh_progress.connect(self._on_refresh_progress)
        self.refresh_worker.refresh_complete.connect(self._on_refresh_complete)
        self.refresh_worker.refresh_failed.connect(self._on_refresh_failed)
        self.refresh_worker.finished.connect(self._on_worker_finished)

        # Start background scan
        self.refresh_worker.start()

    def _abort_refresh(self):
        """Abort current refresh operation."""
        if self.refresh_worker and self.refresh_worker.isRunning():
            logger.info("Aborting refresh")
            self.status_label.setText("Aborting...")
            self.refresh_worker.abort()

    def _on_refresh_started(self):
        """Called when background refresh starts."""
        logger.debug("Refresh started signal received")

    def _on_refresh_progress(self, tab_name: str, current: int, total: int):
        """Update progress indicator."""
        progress_text = f"🔄 Refreshing: {tab_name} ({current}/{total})"
        self.status_label.setText(progress_text)

        logger.debug(f"Refresh progress: {tab_name} ({current}/{total})")

    def _on_refresh_complete(self, active_data, completed_data, available_data):
        """
        Handle successful refresh completion.

        This is called on the main UI thread with scan results.
        Updates all three tabs with the new data.
        Cache is already saved by RefreshWorker.
        """
        logger.info("Refresh completed, updating UI")

        try:
            # Update all tabs (fast, no I/O)
            self.active_tab.populate_table(active_data)
            self.completed_tab.populate_table(completed_data)
            self.available_tab.populate_table(available_data)

            self._initial_load_complete = True
            self.status_label.setText("✅ Refresh complete")
            logger.info("UI updated successfully")

            # Save last refresh timestamp (for persistent timer)
            current_time = time.time()
            self.settings.setValue("last_refresh_time", current_time)
            logger.debug(f"Saved last refresh time: {current_time}")

            # Restart auto-refresh timer with full interval if enabled
            if self._auto_refresh_enabled:
                self.refresh_timer.stop()
                self.refresh_timer.start(self._auto_refresh_interval_ms)
                logger.debug(f"Auto-refresh timer restarted for next cycle ({self._auto_refresh_interval_ms}ms)")

            # Clear status after 3 seconds
            QTimer.singleShot(3000, lambda: self.status_label.setText(""))

        except Exception as e:
            logger.error(f"Failed to update UI after refresh: {e}", exc_info=True)
            self.status_label.setText(f"❌ Update failed: {e}")

    def _on_refresh_failed(self, error_message: str):
        """Handle refresh failure."""
        logger.error(f"Refresh failed: {error_message}")

        self.status_label.setText(f"❌ Refresh failed: {error_message}")

    def _on_worker_finished(self):
        """Called when worker thread finishes (success or failure)."""
        logger.debug("Worker thread finished")

        # Re-enable controls
        self.refresh_button.setEnabled(True)
        self.abort_button.setVisible(False)

        # Clean up worker
        if self.refresh_worker:
            self.refresh_worker.deleteLater()
            self.refresh_worker = None

    def set_current_tab(self, tab_name: str):
        """
        Switch to specific tab.

        Args:
            tab_name: "active", "completed", or "available"
        """
        tab_map = {
            "active": 0,
            "completed": 1,
            "available": 2
        }

        if tab_name in tab_map:
            self.tab_widget.setCurrentIndex(tab_map[tab_name])

    def closeEvent(self, event):
        """Handle widget close - stop timer and abort any running refresh."""
        logger.info("SessionBrowserWidget closing")

        # Stop auto-refresh timer
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()

        # Abort any running refresh and wait for it to finish
        if self.refresh_worker and self.refresh_worker.isRunning():
            logger.info("Aborting refresh before close")
            self.refresh_worker.abort()

            # Wait up to 15 seconds for network scans to abort
            if not self.refresh_worker.wait(15000):
                logger.warning("Refresh worker did not finish in time, forcing termination")
                self.refresh_worker.terminate()
                self.refresh_worker.wait(2000)  # Wait for termination

        event.accept()
