"""
Session Browser Widget - Main Container

Provides tabbed interface for browsing active, completed, and available packing sessions.
Replaces old Restore Session dialog and Session Monitor.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QMessageBox
)
from PySide6.QtCore import Signal, QTimer, QThread

from pathlib import Path
import json

from logger import get_logger

from .active_sessions_tab import ActiveSessionsTab
from .completed_sessions_tab import CompletedSessionsTab
from .available_sessions_tab import AvailableSessionsTab

logger = get_logger(__name__)


class SessionScannerThread(QThread):
    """
    Background thread for scanning sessions without blocking UI.

    Scans both active and completed sessions, then emits results
    to main thread for UI update.
    """

    # Signals to emit results to main thread
    scan_complete = Signal(dict)  # Emits {'active': [...], 'completed': [...]}
    scan_error = Signal(str)      # Emits error message

    def __init__(self, profile_manager, session_lock_manager, session_history_manager):
        super().__init__()
        self.profile_manager = profile_manager
        self.session_lock_manager = session_lock_manager
        self.session_history_manager = session_history_manager
        self._abort = False

    def abort(self):
        """Signal thread to abort scanning."""
        self._abort = True

    def run(self):
        """Run session scan in background."""
        try:
            logger.debug("Background session scan started")

            if self._abort:
                return

            # Scan active sessions (fast operation ~300-700ms)
            active_sessions = self._scan_active_sessions()

            if self._abort:
                return

            # Scan completed sessions (slow operation ~1500-2200ms)
            completed_sessions = self._scan_completed_sessions()

            if self._abort:
                return

            # Emit results to main thread
            self.scan_complete.emit({
                'active': active_sessions,
                'completed': completed_sessions
            })

            logger.debug("Background session scan completed successfully")

        except Exception as e:
            logger.error(f"Error in background session scan: {e}", exc_info=True)
            self.scan_error.emit(str(e))

    def _scan_active_sessions(self):
        """
        Scan for active sessions (locked or in-progress).

        Returns:
            list: List of active session dicts
        """
        sessions = []

        try:
            # Get Sessions base path
            sessions_base = self.profile_manager.get_sessions_root()

            if not sessions_base.exists():
                logger.warning(f"Sessions directory does not exist: {sessions_base}")
                return sessions

            # Scan each client folder
            for client_dir in sessions_base.iterdir():
                if self._abort:
                    break

                if not client_dir.is_dir():
                    continue

                if not client_dir.name.startswith("CLIENT_"):
                    continue

                client_id = client_dir.name.replace("CLIENT_", "")

                # Scan session directories
                for session_dir in client_dir.iterdir():
                    if self._abort:
                        break

                    if not session_dir.is_dir():
                        continue

                    session_id = session_dir.name
                    packing_dir = session_dir / "packing"

                    if not packing_dir.exists():
                        continue

                    # Scan each packing list work directory
                    for work_dir in packing_dir.iterdir():
                        if self._abort:
                            break

                        if not work_dir.is_dir():
                            continue

                        packing_list_name = work_dir.name

                        # Skip completed packing lists (those with session_summary.json)
                        summary_file = work_dir / "session_summary.json"
                        if summary_file.exists():
                            continue

                        # Check for lock or session_info
                        is_locked, lock_info = self.session_lock_manager.is_locked(work_dir)
                        session_info_file = session_dir / "session_info.json"

                        session_data = None

                        if is_locked and lock_info:
                            # Active or stale lock
                            status = self._classify_lock_status(lock_info)

                            session_data = {
                                'session_id': session_id,
                                'client_id': client_id,
                                'packing_list_name': packing_list_name,
                                'session_path': str(session_dir),
                                'work_dir': str(work_dir),
                                'status': status,
                                'worker_id': lock_info.get('worker_id', 'Unknown'),
                                'pc_name': lock_info.get('locked_by', 'Unknown'),
                                'lock_age_minutes': self._calculate_lock_age(lock_info),
                                'lock_info': lock_info,
                                'is_locked': True
                            }

                        elif session_info_file.exists():
                            # Paused session (no lock)
                            try:
                                with open(session_info_file, 'r', encoding='utf-8') as f:
                                    session_info = json.load(f)

                                session_data = {
                                    'session_id': session_id,
                                    'client_id': client_id,
                                    'packing_list_name': packing_list_name,
                                    'session_path': str(session_dir),
                                    'work_dir': str(work_dir),
                                    'status': 'Paused',
                                    'worker_id': session_info.get('worker_id', 'Unknown'),
                                    'pc_name': session_info.get('pc_name', 'Unknown'),
                                    'lock_age_minutes': None,
                                    'session_info': session_info,
                                    'is_locked': False
                                }
                            except Exception as e:
                                logger.warning(f"Failed to load session_info.json: {e}")
                                continue

                        if session_data:
                            # Get progress from packing_state.json
                            progress = self._get_progress(work_dir)
                            session_data['progress'] = progress

                            sessions.append(session_data)

        except Exception as e:
            logger.error(f"Error scanning active sessions: {e}", exc_info=True)

        return sessions

    def _scan_completed_sessions(self):
        """
        Scan for completed sessions.

        Returns:
            list: List of completed session records
        """
        completed = []

        try:
            # Get all client profiles
            clients = self.profile_manager.get_all_profiles()

            for client_id in clients.keys():
                if self._abort:
                    break

                # Use SessionHistoryManager to get completed sessions
                # Get all sessions without date filtering for full scan
                sessions = self.session_history_manager.get_client_sessions(
                    client_id=client_id,
                    include_incomplete=False
                )
                completed.extend(sessions)

        except Exception as e:
            logger.error(f"Error scanning completed sessions: {e}", exc_info=True)

        return completed

    def _classify_lock_status(self, lock_info: dict) -> str:
        """Classify lock as Active or Stale based on heartbeat."""
        from datetime import datetime, timezone

        last_heartbeat = lock_info.get('heartbeat')

        if not last_heartbeat:
            return 'Stale'

        try:
            from shared.metadata_utils import parse_timestamp
            heartbeat_time = parse_timestamp(last_heartbeat)
            if not heartbeat_time:
                return 'Stale'

            now = datetime.now(timezone.utc)
            age_minutes = (now - heartbeat_time).total_seconds() / 60

            return 'Active' if age_minutes < 5 else 'Stale'

        except Exception as e:
            logger.warning(f"Failed to classify lock status: {e}")
            return 'Stale'

    def _calculate_lock_age(self, lock_info: dict) -> float:
        """Calculate lock age in minutes."""
        from datetime import datetime, timezone

        lock_time = lock_info.get('lock_time')

        if not lock_time:
            return 0.0

        try:
            from shared.metadata_utils import parse_timestamp
            lock_dt = parse_timestamp(lock_time)
            if not lock_dt:
                return 0.0

            now = datetime.now(timezone.utc)
            return (now - lock_dt).total_seconds() / 60

        except Exception as e:
            logger.warning(f"Failed to calculate lock age: {e}")
            return 0.0

    def _get_progress(self, work_dir: Path) -> dict:
        """Load progress information from packing_state.json."""
        state_file = work_dir / "packing_state.json"

        if not state_file.exists():
            return {'completed': 0, 'total': 0, 'progress_pct': 0.0}

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Try new format first (v1.3.0+)
            if 'progress' in state:
                progress_data = state.get('progress', {})
                total = progress_data.get('total_orders', 0)
                completed = progress_data.get('completed_orders', 0)
                in_progress_count = len(state.get('in_progress', {}))

                progress_pct = (completed / total * 100) if total > 0 else 0.0

                return {
                    'completed': completed,
                    'total': total,
                    'in_progress': in_progress_count,
                    'progress_pct': progress_pct
                }

            # Try legacy formats
            elif 'data' in state:
                data = state.get('data', {})

                if 'in_progress' in data or 'completed' in data:
                    in_progress_dict = data.get('in_progress', {})
                    completed_list = data.get('completed', [])

                    if completed_list and isinstance(completed_list[0], dict):
                        completed_count = len(completed_list)
                    else:
                        completed_count = len(completed_list) if isinstance(completed_list, list) else 0

                    in_progress_count = len(in_progress_dict)
                    total = completed_count + in_progress_count

                    progress_pct = (completed_count / total * 100) if total > 0 else 0.0

                    return {
                        'completed': completed_count,
                        'total': total,
                        'in_progress': in_progress_count,
                        'progress_pct': progress_pct
                    }

            # Direct format without 'data' wrapper
            else:
                in_progress_dict = state.get('in_progress', {})
                completed_list = state.get('completed', state.get('completed_orders', []))

                if completed_list and isinstance(completed_list, list) and len(completed_list) > 0:
                    if isinstance(completed_list[0], dict):
                        completed_count = len(completed_list)
                    else:
                        completed_count = len(completed_list)
                else:
                    completed_count = 0

                in_progress_count = len(in_progress_dict)
                total = completed_count + in_progress_count

                progress_pct = (completed_count / total * 100) if total > 0 else 0.0

                return {
                    'completed': completed_count,
                    'total': total,
                    'in_progress': in_progress_count,
                    'progress_pct': progress_pct
                }

        except Exception as e:
            logger.error(f"Failed to get progress from {state_file}: {e}", exc_info=True)
            return {'completed': 0, 'total': 0, 'progress_pct': 0.0}


class SessionBrowserWidget(QWidget):
    """
    Main Session Browser widget with 3 tabs:
    - Active Sessions (in-progress, locked)
    - Completed Sessions (history with analytics)
    - Available Sessions (Shopify sessions ready to start) [Phase 3.2]
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

        self._init_ui()
        self._connect_signals()

        # Create scanner thread (but don't start yet)
        self.scanner_thread = SessionScannerThread(
            profile_manager,
            session_lock_manager,
            session_history_manager
        )
        self.scanner_thread.scan_complete.connect(self._on_scan_complete)
        self.scanner_thread.scan_error.connect(self._on_scan_error)

        # Auto-refresh timer (30 seconds)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._start_background_scan)
        self.refresh_timer.start(30000)  # 30 seconds
        logger.debug("Auto-refresh enabled (30s interval) with background scanning")

    def _init_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
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

    def _connect_signals(self):
        """Connect internal signals."""
        # Active tab signals
        self.active_tab.resume_requested.connect(self._handle_resume_request)

        # Completed tab signals
        self.completed_tab.session_selected.connect(self.session_selected.emit)

        # Available tab signals
        self.available_tab.start_packing_requested.connect(self._handle_start_packing_request)

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

    def refresh_all(self):
        """
        Refresh all tabs.

        Now triggers background scan instead of blocking UI.
        """
        self._start_background_scan()

    def _start_background_scan(self):
        """Start background scan if not already running."""
        if self.scanner_thread.isRunning():
            logger.warning("Background scan already in progress, skipping...")
            return

        logger.debug("Starting background session scan...")
        self.scanner_thread.start()

    def _on_scan_complete(self, results: dict):
        """
        Handle scan results from background thread.

        This runs on main thread and updates UI quickly with pre-scanned data.
        """
        try:
            active_sessions = results.get('active', [])
            completed_sessions = results.get('completed', [])

            logger.info(f"Background scan complete: {len(active_sessions)} active, {len(completed_sessions)} completed")

            # Update tabs with results (fast - just UI update)
            if hasattr(self, 'active_tab'):
                self.active_tab.update_from_scan_results(active_sessions)

            if hasattr(self, 'completed_tab'):
                self.completed_tab.update_from_scan_results(completed_sessions)

        except Exception as e:
            logger.error(f"Error updating UI with scan results: {e}", exc_info=True)

    def _on_scan_error(self, error_msg: str):
        """Handle scan error from background thread."""
        logger.error(f"Background scan error: {error_msg}")
        QMessageBox.warning(
            self,
            "Scan Error",
            f"Error scanning sessions:\n{error_msg}"
        )

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
        """Stop background thread and refresh timer on close."""
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()

        if hasattr(self, 'scanner_thread') and self.scanner_thread.isRunning():
            logger.debug("Aborting background scan thread...")
            self.scanner_thread.abort()
            self.scanner_thread.wait(1000)  # Wait up to 1 second

        event.accept()
