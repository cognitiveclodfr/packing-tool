"""
Session Monitor Widget - Displays active sessions across all clients.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView
)
from PySide6.QtCore import Qt, QTimer

from logger import get_logger

logger = get_logger(__name__)


class SessionMonitorWidget(QWidget):
    """
    Widget for monitoring active sessions across all clients.

    Shows a table with:
    - Client ID
    - Session name
    - User name
    - Computer name
    - Lock time
    - Last heartbeat
    """

    def __init__(self, lock_manager, parent=None):
        """
        Initialize the session monitor widget.

        Args:
            lock_manager: SessionLockManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.lock_manager = lock_manager
        self.auto_refresh_enabled = True

        self._init_ui()
        self._refresh()

        # Auto-refresh every 30 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh)
        self.refresh_timer.start(30000)  # 30 seconds

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        title_label = QLabel("Active Sessions Monitor")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.refresh_button = QPushButton("Refresh Now")
        self.refresh_button.clicked.connect(self._refresh)
        header_layout.addWidget(self.refresh_button)

        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Client", "Session", "User", "Computer", "Started", "Last Heartbeat"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        # Status label
        self.status_label = QLabel("Auto-refresh every 30 seconds")
        self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.status_label)

    def _refresh(self):
        """Refresh the active sessions list."""
        if not self.auto_refresh_enabled:
            return

        try:
            all_sessions = self.lock_manager.get_all_active_sessions()

            self.table.setRowCount(0)

            if not all_sessions:
                self.status_label.setText("No active sessions found. Auto-refresh every 30 seconds.")
                return

            row = 0
            for client_id, sessions in all_sessions.items():
                for session_info in sessions:
                    self.table.insertRow(row)

                    # Client
                    self.table.setItem(row, 0, QTableWidgetItem(client_id))

                    # Session
                    session_name = session_info['session_name']
                    self.table.setItem(row, 1, QTableWidgetItem(session_name))

                    # Lock info
                    lock_info = session_info.get('lock_info', {})
                    user_name = lock_info.get('user_name', 'Unknown')
                    pc_name = lock_info.get('locked_by', 'Unknown')
                    lock_time = lock_info.get('lock_time', 'Unknown')
                    heartbeat = lock_info.get('heartbeat', 'Unknown')

                    # Format times
                    try:
                        from shared.metadata_utils import parse_timestamp
                        if lock_time != 'Unknown':
                            lock_dt = parse_timestamp(lock_time)
                            if lock_dt:
                                lock_time = lock_dt.strftime('%H:%M:%S')
                        if heartbeat != 'Unknown':
                            hb_dt = parse_timestamp(heartbeat)
                            if hb_dt:
                                heartbeat = hb_dt.strftime('%H:%M:%S')
                    except:
                        pass

                    self.table.setItem(row, 2, QTableWidgetItem(user_name))
                    self.table.setItem(row, 3, QTableWidgetItem(pc_name))
                    self.table.setItem(row, 4, QTableWidgetItem(lock_time))
                    self.table.setItem(row, 5, QTableWidgetItem(heartbeat))

                    row += 1

            total_sessions = sum(len(sessions) for sessions in all_sessions.values())
            self.status_label.setText(
                f"Found {total_sessions} active session(s) across {len(all_sessions)} client(s). "
                f"Auto-refresh every 30 seconds."
            )

            logger.debug(f"Session monitor refreshed: {total_sessions} active sessions")

        except Exception as e:
            logger.error(f"Failed to refresh session monitor: {e}", exc_info=True)
            self.status_label.setText(f"Error refreshing: {e}")

    def set_auto_refresh(self, enabled: bool):
        """Enable or disable auto-refresh."""
        self.auto_refresh_enabled = enabled
        if enabled:
            self.refresh_timer.start(30000)
            self.status_label.setText("Auto-refresh enabled (30 seconds)")
        else:
            self.refresh_timer.stop()
            self.status_label.setText("Auto-refresh disabled")

    def closeEvent(self, event):
        """Stop refresh timer when widget is closed."""
        self.refresh_timer.stop()
        super().closeEvent(event)
