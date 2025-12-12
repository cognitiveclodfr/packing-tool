"""Completed Sessions Tab - Shows session history with analytics"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QLineEdit, QLabel, QDateEdit, QMessageBox, QFileDialog
)
from PySide6.QtCore import Signal, QDate

from datetime import datetime
from pathlib import Path
import pandas as pd

from logger import get_logger

logger = get_logger(__name__)


class CompletedSessionsTab(QWidget):
    """Tab showing completed session history"""

    # Signals
    session_selected = Signal(dict)  # {session data}

    def __init__(self, profile_manager, session_history_manager, parent=None):
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_history_manager = session_history_manager

        self.sessions = []  # SessionHistoryRecord objects

        self._init_ui()
        # NOTE: Do NOT call refresh() here - it will be called by SessionBrowserWidget
        # after setting up the background worker and cache system

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Filters section
        filters = QVBoxLayout()

        # Row 1: Client + Date range
        row1 = QHBoxLayout()

        row1.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        try:
            for client_id in self.profile_manager.list_clients():
                self.client_combo.addItem(f"CLIENT_{client_id}", client_id)
        except Exception as e:
            logger.warning(f"Failed to load clients: {e}")
        row1.addWidget(self.client_combo)

        row1.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))  # Last month
        row1.addWidget(self.date_from)

        row1.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        row1.addWidget(self.date_to)

        row1.addStretch()

        filters.addLayout(row1)

        # Row 2: Search
        row2 = QHBoxLayout()

        row2.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search term...")
        self.search_input.returnPressed.connect(self.refresh)
        row2.addWidget(self.search_input)

        row2.addWidget(QLabel("in"))
        self.search_field = QComboBox()
        self.search_field.addItems([
            "All Fields",
            "Session ID",
            "Client ID",
            "Worker",
            "Packing List"
        ])
        row2.addWidget(self.search_field)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.refresh)
        row2.addWidget(search_btn)

        filters.addLayout(row2)

        # Row 3: Action buttons
        row3 = QHBoxLayout()

        export_excel_btn = QPushButton("Export Excel")
        export_excel_btn.clicked.connect(self._export_excel)
        row3.addWidget(export_excel_btn)

        export_pdf_btn = QPushButton("Export PDF")
        export_pdf_btn.clicked.connect(self._export_pdf)
        row3.addWidget(export_pdf_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        row3.addWidget(refresh_btn)

        row3.addStretch()

        filters.addLayout(row3)

        layout.addLayout(filters)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Session ID", "Client", "Packing List", "Worker",
            "Start Time", "Duration", "Orders", "Items", "Status"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        self.details_btn = QPushButton("View Details")
        self.details_btn.clicked.connect(self._on_view_details)
        btn_layout.addWidget(self.details_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _scan_sessions(self) -> list:
        """
        Scan completed sessions and return data WITHOUT updating UI.

        This method is called in a background thread and must NOT touch UI.

        Returns:
            list: List of SessionHistoryRecord objects
        """
        logger.debug("Scanning completed sessions (background thread)")

        # Get filters
        selected_client = self.client_combo.currentData()

        # Convert QDate to datetime (same as session_history_widget.py)
        qdate_from = self.date_from.date()
        qdate_to = self.date_to.date()
        date_from = datetime(qdate_from.year(), qdate_from.month(), qdate_from.day())
        date_to = datetime(qdate_to.year(), qdate_to.month(), qdate_to.day(), 23, 59, 59)

        search_term = self.search_input.text().strip()

        # Get sessions from SessionHistoryManager
        try:
            if selected_client:
                sessions = self.session_history_manager.get_client_sessions(
                    client_id=selected_client,
                    start_date=date_from,
                    end_date=date_to,
                    include_incomplete=False  # Only completed
                )
            else:
                # Get for all clients
                sessions = []
                for client_id in self.profile_manager.list_clients():
                    client_sessions = self.session_history_manager.get_client_sessions(
                        client_id=client_id,
                        start_date=date_from,
                        end_date=date_to,
                        include_incomplete=False
                    )
                    sessions.extend(client_sessions)

            # Apply search filter
            if search_term:
                search_field_map = {
                    "Session ID": ["session_id"],
                    "Client ID": ["client_id"],
                    "Worker": ["pc_name"],
                    "Packing List": ["packing_list_path"]
                }

                field_name = self.search_field.currentText()

                if field_name == "All Fields":
                    search_fields = ["session_id", "client_id", "pc_name", "packing_list_path"]
                else:
                    search_fields = search_field_map.get(field_name, [])

                # Filter sessions manually
                filtered_sessions = []
                for s in sessions:
                    for field in search_fields:
                        value = getattr(s, field, None)
                        if value and search_term.lower() in str(value).lower():
                            filtered_sessions.append(s)
                            break

                sessions = filtered_sessions

            logger.debug(f"Found {len(sessions)} completed sessions")
            return sessions

        except Exception as e:
            logger.error(f"Failed to load sessions: {e}", exc_info=True)
            return []

    def populate_table(self, session_data: list):
        """
        Populate table with session data on main UI thread.

        This method updates the UI and must be called on the main thread.

        Args:
            session_data: List of SessionHistoryRecord objects from _scan_sessions()
        """
        logger.debug(f"Populating table with {len(session_data)} sessions")

        self.sessions = session_data
        self._populate_table()

        logger.debug("Table populated successfully")

    def refresh(self):
        """
        Legacy synchronous refresh (for backward compatibility).

        This method is still used when refresh is called directly,
        but background worker now calls _scan_sessions() + populate_table().
        """
        data = self._scan_sessions()
        self.populate_table(data)

    def _populate_table(self):
        """Fill table with session data."""
        self.table.setSortingEnabled(False)  # Disable while populating
        self.table.setRowCount(len(self.sessions))

        for row, session in enumerate(self.sessions):
            # Session ID
            self.table.setItem(row, 0, QTableWidgetItem(session.session_id))

            # Client
            self.table.setItem(row, 1, QTableWidgetItem(f"CLIENT_{session.client_id}"))

            # Packing List (extract filename)
            if session.packing_list_path:
                list_name = Path(session.packing_list_path).stem
            else:
                list_name = "Unknown"
            self.table.setItem(row, 2, QTableWidgetItem(list_name))

            # Worker (enhanced to show worker_id and worker_name if available)
            worker_id = getattr(session, 'worker_id', None)
            worker_name = getattr(session, 'worker_name', None)

            if worker_id and worker_name:
                worker_display = f"{worker_id} ({worker_name})"
            elif worker_id:
                worker_display = worker_id
            elif worker_name:
                worker_display = worker_name
            else:
                # Fallback to PC name for old sessions without worker info
                worker_display = session.pc_name if session.pc_name else "Unknown"

            self.table.setItem(row, 3, QTableWidgetItem(worker_display))

            # Start Time
            start_time_str = session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "N/A"
            self.table.setItem(row, 4, QTableWidgetItem(start_time_str))

            # Duration
            if session.duration_seconds:
                hours = int(session.duration_seconds // 3600)
                minutes = int((session.duration_seconds % 3600) // 60)
                duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            else:
                duration_str = "N/A"
            self.table.setItem(row, 5, QTableWidgetItem(duration_str))

            # Orders
            orders_str = f"{session.completed_orders}/{session.total_orders}"
            self.table.setItem(row, 6, QTableWidgetItem(orders_str))

            # Items
            self.table.setItem(row, 7, QTableWidgetItem(str(session.total_items_packed)))

            # Status
            if session.completed_orders == session.total_orders and session.total_orders > 0:
                status = "✅ Complete"
            else:
                status = "⚠️ Incomplete"
            self.table.setItem(row, 8, QTableWidgetItem(status))

        self.table.setSortingEnabled(True)  # Re-enable sorting

    def _export_excel(self):
        """Export sessions to Excel."""
        if not self.sessions:
            QMessageBox.warning(self, "No Data", "No sessions to export.")
            return

        # Ask for save location
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export to Excel",
            "completed_sessions.xlsx",
            "Excel Files (*.xlsx)"
        )

        if not filepath:
            return

        try:
            # Convert to dict
            data = self.session_history_manager.export_sessions_to_dict(self.sessions)

            # Create DataFrame
            df = pd.DataFrame(data)

            # Write to Excel
            df.to_excel(filepath, index=False, sheet_name="Completed Sessions")

            QMessageBox.information(self, "Success", f"Exported {len(self.sessions)} sessions to:\n{filepath}")
            logger.info(f"Exported {len(self.sessions)} sessions to Excel: {filepath}")

        except Exception as e:
            logger.error(f"Failed to export to Excel: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to export:\n{str(e)}")

    def _export_pdf(self):
        """Export sessions to PDF."""
        # TODO: Implement PDF export (Phase 3.2 or later)
        QMessageBox.information(self, "Not Implemented", "PDF export will be added in Phase 3.2")

    def _on_view_details(self):
        """Handle View Details button click."""
        selected = self.table.currentRow()

        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a session.")
            return

        session = self.sessions[selected]

        # Import dialog
        from .session_details_dialog import SessionDetailsDialog

        # Create dialog
        try:
            # Standardize structure (session is a SessionHistoryRecord)
            packing_list_name = 'Unknown'
            if session.packing_list_path:
                packing_list_name = Path(session.packing_list_path).stem

            # Construct work_dir for completed sessions (Phase 1 structure)
            work_dir = None
            if session.session_path and session.packing_list_path:
                # Try to find the work directory
                potential_work_dir = Path(session.session_path) / "packing" / session.packing_list_path
                if potential_work_dir.exists():
                    work_dir = str(potential_work_dir)

            session_data = {
                'session_id': session.session_id,
                'client_id': session.client_id,
                'packing_list_name': packing_list_name,
                'worker_id': None,  # Not stored in v1.3.0 summary
                'worker_name': None,  # Not stored in v1.3.0 summary
                'pc_name': session.pc_name,
                'started_at': session.start_time.isoformat() if session.start_time else None,
                'ended_at': session.end_time.isoformat() if session.end_time else None,
                'duration_seconds': session.duration_seconds,
                'orders_completed': session.completed_orders,
                'orders_total': session.total_orders,
                'items_packed': session.total_items_packed,
                'session_path': session.session_path,
                'status': 'Completed',
                'work_dir': work_dir,  # Found work directory for loading session files
            }

            dialog = SessionDetailsDialog(
                session_data=session_data,
                session_history_manager=self.session_history_manager,
                parent=self
            )

            dialog.exec()

        except Exception as e:
            logger.error(f"Failed to open session details: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load session details:\n{str(e)}"
            )
