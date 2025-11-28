"""
Session Browser Widget - Main Container

Provides tabbed interface for browsing active, completed, and available packing sessions.
Replaces old Restore Session dialog and Session Monitor.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget
)
from PySide6.QtCore import Signal, QTimer

from .active_sessions_tab import ActiveSessionsTab
from .completed_sessions_tab import CompletedSessionsTab
from .available_sessions_tab import AvailableSessionsTab
from performance_profiler import profile_function, log_timing


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

        # ✅ ADD: Auto-refresh timer (30 seconds)
        # Performance optimization: Only refresh when widget is visible
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._on_auto_refresh)
        # Timer will be started/stopped in showEvent/hideEvent
        from logger import get_logger
        self.logger = get_logger(__name__)
        self.logger.debug("Auto-refresh timer initialized (30s interval, starts when visible)")

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

    def _on_auto_refresh(self):
        """Auto-refresh handler called by timer."""
        self.logger.debug("Auto-refresh triggered")
        self.refresh_all()

    @profile_function
    def refresh_all(self):
        """Refresh all tabs."""
        self.active_tab.refresh()
        self.completed_tab.refresh()
        self.available_tab.refresh()

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

    def showEvent(self, event):
        """Start auto-refresh when widget becomes visible."""
        super().showEvent(event)
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.start(30000)  # 30 seconds
            self.logger.debug("Auto-refresh started (widget visible)")
            # Do immediate refresh when shown
            self.refresh_all()

    def hideEvent(self, event):
        """Stop auto-refresh when widget is hidden."""
        super().hideEvent(event)
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
            self.logger.debug("Auto-refresh stopped (widget hidden)")

    def closeEvent(self, event):
        """Stop refresh timer on close."""
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
            self.logger.debug("Auto-refresh stopped (widget closed)")
        event.accept()
