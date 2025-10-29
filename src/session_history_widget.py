"""
Session History Widget - Displays and searches historical session data.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QComboBox, QDateEdit, QCheckBox, QHeaderView,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QDate, Signal
from datetime import datetime, timedelta
import pandas as pd

from logger import get_logger
from session_history_manager import SessionHistoryManager

logger = get_logger(__name__)


class SessionHistoryWidget(QWidget):
    """
    Widget for viewing and searching historical session data.

    Features:
    - View completed sessions with detailed metrics
    - Search by session ID, PC name, or date range
    - Export filtered results to Excel/CSV
    - View session details
    """

    session_selected = Signal(str, str)  # client_id, session_id

    def __init__(self, profile_manager, parent=None):
        """
        Initialize the session history widget.

        Args:
            profile_manager: ProfileManager instance for accessing session data
            parent: Parent widget
        """
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.history_manager = SessionHistoryManager(profile_manager)
        self.current_sessions = []

        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Session History")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Search and Filter Section
        filter_layout = QVBoxLayout()

        # Client filter
        client_filter_layout = QHBoxLayout()
        client_filter_layout.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        self.client_combo.currentIndexChanged.connect(self._on_filter_changed)
        client_filter_layout.addWidget(self.client_combo)
        client_filter_layout.addStretch()
        filter_layout.addLayout(client_filter_layout)

        # Search box
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by session ID, PC name, or file path...")
        self.search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_box)
        filter_layout.addLayout(search_layout)

        # Date range filter
        date_layout = QHBoxLayout()
        self.date_filter_checkbox = QCheckBox("Filter by date range:")
        self.date_filter_checkbox.stateChanged.connect(self._on_filter_changed)
        date_layout.addWidget(self.date_filter_checkbox)

        date_layout.addWidget(QLabel("From:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(QDate.currentDate().addMonths(-1))
        self.start_date_edit.dateChanged.connect(self._on_filter_changed)
        date_layout.addWidget(self.start_date_edit)

        date_layout.addWidget(QLabel("To:"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.dateChanged.connect(self._on_filter_changed)
        date_layout.addWidget(self.end_date_edit)

        date_layout.addStretch()
        filter_layout.addLayout(date_layout)

        # Include incomplete sessions
        incomplete_layout = QHBoxLayout()
        self.include_incomplete_checkbox = QCheckBox("Include incomplete sessions")
        self.include_incomplete_checkbox.setChecked(True)
        self.include_incomplete_checkbox.stateChanged.connect(self._on_filter_changed)
        incomplete_layout.addWidget(self.include_incomplete_checkbox)
        incomplete_layout.addStretch()
        filter_layout.addLayout(incomplete_layout)

        layout.addLayout(filter_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_sessions)
        button_layout.addWidget(self.refresh_button)

        self.export_button = QPushButton("Export to Excel")
        self.export_button.clicked.connect(self._export_to_excel)
        button_layout.addWidget(self.export_button)

        self.export_csv_button = QPushButton("Export to CSV")
        self.export_csv_button.clicked.connect(self._export_to_csv)
        button_layout.addWidget(self.export_csv_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Sessions table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Session ID", "Client", "Start Time", "Duration (min)",
            "Total Orders", "Completed", "In Progress", "Items Packed",
            "PC Name", "Status"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

        # Status label
        self.status_label = QLabel("No sessions loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.status_label)

    def load_clients(self, client_ids):
        """
        Load available clients into the filter combo box.

        Args:
            client_ids: List of client IDs
        """
        self.client_combo.clear()
        self.client_combo.addItem("All Clients", None)
        for client_id in client_ids:
            self.client_combo.addItem(f"Client {client_id}", client_id)

    def _load_sessions(self):
        """Load sessions based on current filters."""
        try:
            client_id = self.client_combo.currentData()

            # Date range filter
            start_date = None
            end_date = None
            if self.date_filter_checkbox.isChecked():
                qdate_start = self.start_date_edit.date()
                qdate_end = self.end_date_edit.date()
                start_date = datetime(qdate_start.year(), qdate_start.month(), qdate_start.day())
                end_date = datetime(qdate_end.year(), qdate_end.month(), qdate_end.day(), 23, 59, 59)

            include_incomplete = self.include_incomplete_checkbox.isChecked()

            # Load sessions
            if client_id:
                sessions = self.history_manager.get_client_sessions(
                    client_id,
                    start_date=start_date,
                    end_date=end_date,
                    include_incomplete=include_incomplete
                )
            else:
                # Load all clients
                sessions = []
                try:
                    clients_root = self.profile_manager.get_clients_root()
                    if clients_root.exists():
                        for client_dir in clients_root.iterdir():
                            if client_dir.is_dir() and client_dir.name.startswith("CLIENT_"):
                                client_id_temp = client_dir.name.replace("CLIENT_", "")
                                client_sessions = self.history_manager.get_client_sessions(
                                    client_id_temp,
                                    start_date=start_date,
                                    end_date=end_date,
                                    include_incomplete=include_incomplete
                                )
                                sessions.extend(client_sessions)
                except Exception as e:
                    logger.error(f"Error loading all clients: {e}")

                # Sort by start time
                sessions.sort(key=lambda s: s.start_time or datetime.min, reverse=True)

            self.current_sessions = sessions
            self._display_sessions(sessions)

            logger.info(f"Loaded {len(sessions)} sessions")

        except Exception as e:
            logger.error(f"Error loading sessions: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load sessions: {e}")

    def _display_sessions(self, sessions):
        """
        Display sessions in the table.

        Args:
            sessions: List of SessionHistoryRecord objects
        """
        self.table.setRowCount(0)

        if not sessions:
            self.status_label.setText("No sessions found matching the criteria")
            return

        self.table.setRowCount(len(sessions))

        for row, session in enumerate(sessions):
            # Session ID
            self.table.setItem(row, 0, QTableWidgetItem(session.session_id))

            # Client
            self.table.setItem(row, 1, QTableWidgetItem(session.client_id))

            # Start time
            start_time_str = session.start_time.strftime('%Y-%m-%d %H:%M:%S') if session.start_time else ''
            self.table.setItem(row, 2, QTableWidgetItem(start_time_str))

            # Duration
            duration_str = f"{session.duration_seconds / 60:.1f}" if session.duration_seconds else ''
            self.table.setItem(row, 3, QTableWidgetItem(duration_str))

            # Total orders
            self.table.setItem(row, 4, QTableWidgetItem(str(session.total_orders)))

            # Completed
            self.table.setItem(row, 5, QTableWidgetItem(str(session.completed_orders)))

            # In progress
            self.table.setItem(row, 6, QTableWidgetItem(str(session.in_progress_orders)))

            # Items packed
            self.table.setItem(row, 7, QTableWidgetItem(str(session.total_items_packed)))

            # PC name
            self.table.setItem(row, 8, QTableWidgetItem(session.pc_name or ''))

            # Status
            status = "Completed" if session.in_progress_orders == 0 else "Incomplete"
            status_item = QTableWidgetItem(status)
            if status == "Completed":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            self.table.setItem(row, 9, status_item)

        self.status_label.setText(f"Showing {len(sessions)} session(s)")

    def _on_filter_changed(self):
        """Handle filter changes."""
        self._load_sessions()

    def _on_search_changed(self, text):
        """Handle search text changes."""
        if not text:
            self._display_sessions(self.current_sessions)
            return

        search_term = text.lower()
        filtered_sessions = [
            s for s in self.current_sessions
            if search_term in s.session_id.lower() or
               (s.pc_name and search_term in s.pc_name.lower()) or
               (s.packing_list_path and search_term in s.packing_list_path.lower())
        ]

        self._display_sessions(filtered_sessions)

    def _on_row_double_clicked(self, item):
        """Handle row double click to view session details."""
        row = item.row()
        session_id = self.table.item(row, 0).text()
        client_id = self.table.item(row, 1).text()

        # Find the session
        session = next((s for s in self.current_sessions if s.session_id == session_id), None)

        if session:
            self._show_session_details(session)

    def _show_session_details(self, session):
        """
        Show detailed information about a session.

        Args:
            session: SessionHistoryRecord object
        """
        details = self.history_manager.get_session_details(session.client_id, session.session_id)

        if not details:
            QMessageBox.warning(self, "Error", "Could not load session details")
            return

        # Format details
        info_lines = [
            f"Session ID: {session.session_id}",
            f"Client: {session.client_id}",
            f"PC Name: {session.pc_name or 'N/A'}",
            f"Start Time: {session.start_time.strftime('%Y-%m-%d %H:%M:%S') if session.start_time else 'N/A'}",
            f"End Time: {session.end_time.strftime('%Y-%m-%d %H:%M:%S') if session.end_time else 'N/A'}",
            f"Duration: {session.duration_seconds / 60:.1f} minutes" if session.duration_seconds else "Duration: N/A",
            f"",
            f"Total Orders: {session.total_orders}",
            f"Completed Orders: {session.completed_orders}",
            f"In Progress: {session.in_progress_orders}",
            f"Items Packed: {session.total_items_packed}",
            f"",
            f"Packing List: {session.packing_list_path or 'N/A'}",
            f"Session Path: {session.session_path}",
        ]

        QMessageBox.information(
            self,
            "Session Details",
            "\n".join(info_lines)
        )

    def _export_to_excel(self):
        """Export filtered sessions to Excel."""
        if not self.current_sessions:
            QMessageBox.warning(self, "No Data", "No sessions to export")
            return

        try:
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export to Excel",
                f"session_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "Excel Files (*.xlsx)"
            )

            if not file_path:
                return

            # Convert to DataFrame and export
            data = self.history_manager.export_sessions_to_dict(self.current_sessions)
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False)

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(self.current_sessions)} sessions to:\n{file_path}"
            )

            logger.info(f"Exported {len(self.current_sessions)} sessions to {file_path}")

        except Exception as e:
            logger.error(f"Error exporting to Excel: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")

    def _export_to_csv(self):
        """Export filtered sessions to CSV."""
        if not self.current_sessions:
            QMessageBox.warning(self, "No Data", "No sessions to export")
            return

        try:
            # Get save file path
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export to CSV",
                f"session_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "CSV Files (*.csv)"
            )

            if not file_path:
                return

            # Convert to DataFrame and export
            data = self.history_manager.export_sessions_to_dict(self.current_sessions)
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False, encoding='utf-8-sig')

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(self.current_sessions)} sessions to:\n{file_path}"
            )

            logger.info(f"Exported {len(self.current_sessions)} sessions to {file_path}")

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")

    def refresh(self):
        """Public method to refresh the session list."""
        self._load_sessions()
