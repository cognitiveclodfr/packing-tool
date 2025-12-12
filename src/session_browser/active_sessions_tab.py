"""Active Sessions Tab - Shows in-progress sessions with lock status"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QMessageBox, QLabel
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor

from pathlib import Path
from datetime import datetime, timezone
import json

from logger import get_logger

logger = get_logger(__name__)


class ActiveSessionsTab(QWidget):
    """Tab showing active/stale/paused sessions"""

    # Signals
    resume_requested = Signal(dict)  # {session_path, client_id, packing_list_name, lock_info}

    def __init__(self, profile_manager, session_lock_manager, worker_manager, parent=None):
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_lock_manager = session_lock_manager
        self.worker_manager = worker_manager

        self.sessions = []  # List of session dicts

        self._init_ui()
        self.refresh()

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Top bar: Client filter + Refresh
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        # Populate with actual clients
        try:
            for client_id in self.profile_manager.list_clients():
                self.client_combo.addItem(f"CLIENT_{client_id}", client_id)
        except Exception as e:
            logger.warning(f"Failed to load clients: {e}")
        self.client_combo.currentIndexChanged.connect(self.refresh)
        top_bar.addWidget(self.client_combo)

        top_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        top_bar.addWidget(refresh_btn)

        layout.addLayout(top_bar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Session ID", "Client", "Packing List", "Status",
            "Worker", "PC", "Lock Age", "Orders Progress"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.resume_btn = QPushButton("Resume Session")
        self.resume_btn.clicked.connect(self._on_resume)
        btn_layout.addWidget(self.resume_btn)

        self.unlock_btn = QPushButton("Force Unlock")
        self.unlock_btn.clicked.connect(self._on_force_unlock)
        btn_layout.addWidget(self.unlock_btn)

        self.details_btn = QPushButton("View Details")
        self.details_btn.clicked.connect(self._on_view_details)
        btn_layout.addWidget(self.details_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _scan_sessions(self) -> list:
        """
        Scan active sessions and return data WITHOUT updating UI.

        This method is called in a background thread and must NOT touch UI.

        Returns:
            list: List of session records ready for display
        """
        logger.debug("Scanning active sessions (background thread)")

        sessions = []
        selected_client = self.client_combo.currentData()

        # Get Sessions base path
        try:
            sessions_base = self.profile_manager.get_sessions_root()
        except Exception as e:
            logger.error(f"Failed to get sessions root: {e}")
            return []

        if not sessions_base.exists():
            logger.warning(f"Sessions directory does not exist: {sessions_base}")
            return []

        # Scan each client folder
        for client_dir in sessions_base.iterdir():
            if not client_dir.is_dir():
                continue

            if not client_dir.name.startswith("CLIENT_"):
                continue

            client_id = client_dir.name.replace("CLIENT_", "")

            # Filter by selected client
            if selected_client and client_id != selected_client:
                continue

            # Scan session directories
            for session_dir in client_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                session_id = session_dir.name
                packing_dir = session_dir / "packing"

                if not packing_dir.exists():
                    continue

                # Scan each packing list work directory
                for work_dir in packing_dir.iterdir():
                    if not work_dir.is_dir():
                        continue

                    packing_list_name = work_dir.name

                    # Skip completed packing lists (those with session_summary.json)
                    summary_file = work_dir / "session_summary.json"
                    if summary_file.exists():
                        logger.debug(f"Skipping completed list: {packing_list_name}")
                        continue  # Skip completed packing lists

                    # Check for lock or session_info
                    # Note: Lock file is in work_dir (packing work directory)
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

        logger.debug(f"Found {len(sessions)} active sessions")
        return sessions

    def populate_table(self, session_data: list):
        """
        Populate table with session data on main UI thread.

        This method updates the UI and must be called on the main thread.

        Args:
            session_data: List of session records from _scan_sessions()
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

    def _classify_lock_status(self, lock_info: dict) -> str:
        """Classify lock as Active or Stale based on heartbeat."""
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
        """
        Get packing progress from packing_state.json.

        CRITICAL FIX: Updated to read from new state structure (v1.3.0) with
        progress metadata. Also handles legacy formats for backward compatibility.

        Returns:
            dict: Progress information with keys:
                - completed: Number of completed orders
                - total: Total number of orders
                - in_progress: Number of in-progress orders (optional)
                - progress_pct: Completion percentage (optional)
        """
        state_file = work_dir / "packing_state.json"

        if not state_file.exists():
            return {'completed': 0, 'total': 0, 'progress_pct': 0.0}

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # Try new format first (v1.3.0+)
            if 'progress' in state:
                # New format: direct progress metadata
                progress_data = state.get('progress', {})
                total = progress_data.get('total_orders', 0)
                completed = progress_data.get('completed_orders', 0)
                in_progress_count = len(state.get('in_progress', {}))

                # Calculate percentage
                progress_pct = (completed / total * 100) if total > 0 else 0.0

                return {
                    'completed': completed,
                    'total': total,
                    'in_progress': in_progress_count,
                    'progress_pct': progress_pct
                }

            # Try legacy format with 'data' wrapper
            elif 'data' in state:
                data = state.get('data', {})

                # Check if data has in_progress/completed structure
                if 'in_progress' in data or 'completed' in data:
                    in_progress_dict = data.get('in_progress', {})
                    completed_list = data.get('completed', [])

                    # Handle both list of strings and list of dicts
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

                # Older format with orders array
                else:
                    orders = data.get('orders', [])
                    completed = sum(1 for o in orders if o.get('status') == 'completed')

                    return {
                        'completed': completed,
                        'total': len(orders),
                        'progress_pct': (completed / len(orders) * 100) if len(orders) > 0 else 0.0
                    }

            # Direct format without 'data' wrapper
            else:
                in_progress_dict = state.get('in_progress', {})
                completed_list = state.get('completed', state.get('completed_orders', []))

                # Handle both list of strings and list of dicts
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

    def _populate_table(self):
        """Fill table with session data."""
        self.table.setRowCount(len(self.sessions))

        for row, session in enumerate(self.sessions):
            # Session ID
            self.table.setItem(row, 0, QTableWidgetItem(session['session_id']))

            # Client
            self.table.setItem(row, 1, QTableWidgetItem(f"CLIENT_{session['client_id']}"))

            # Packing List
            self.table.setItem(row, 2, QTableWidgetItem(session['packing_list_name']))

            # Status (with color)
            status_item = QTableWidgetItem(session['status'])
            if session['status'] == 'Active':
                status_item.setBackground(QColor(200, 255, 200))  # Light green
            elif session['status'] == 'Stale':
                status_item.setBackground(QColor(255, 200, 200))  # Light red
            else:  # Paused
                status_item.setBackground(QColor(255, 255, 200))  # Light yellow
            self.table.setItem(row, 3, status_item)

            # Worker
            worker_id = session['worker_id']
            worker_name = self._get_worker_name(worker_id)
            self.table.setItem(row, 4, QTableWidgetItem(worker_name))

            # PC
            self.table.setItem(row, 5, QTableWidgetItem(session['pc_name']))

            # Lock Age
            lock_age = session['lock_age_minutes']
            age_text = f"{int(lock_age)} min" if lock_age else "N/A"
            self.table.setItem(row, 6, QTableWidgetItem(age_text))

            # Progress (with percentage and color coding)
            progress = session['progress']
            completed = progress.get('completed', 0)
            total = progress.get('total', 0)
            progress_pct = progress.get('progress_pct', 0.0)

            # Format: "5/10 (50%)"
            if total > 0:
                progress_text = f"{completed}/{total} ({progress_pct:.0f}%)"
            else:
                progress_text = "N/A"

            progress_item = QTableWidgetItem(progress_text)

            # Color code based on progress percentage
            if progress_pct >= 75:
                progress_item.setForeground(QColor(0, 150, 0))  # Green - almost done
            elif progress_pct >= 25:
                progress_item.setForeground(QColor(200, 100, 0))  # Orange - in progress
            elif progress_pct > 0:
                progress_item.setForeground(QColor(100, 100, 100))  # Gray - just started
            else:
                progress_item.setForeground(QColor(150, 150, 150))  # Light gray - not started

            self.table.setItem(row, 7, progress_item)

    def _get_worker_name(self, worker_id: str) -> str:
        """Get worker display name from worker_id."""
        if not worker_id or worker_id == 'Unknown':
            return worker_id

        try:
            worker_info = self.worker_manager.get_worker(worker_id)

            if worker_info:
                return worker_info.get('name', worker_id)
        except Exception as e:
            logger.debug(f"Failed to get worker name: {e}")

        return worker_id

    def _on_resume(self):
        """Handle Resume button click."""
        selected = self.table.currentRow()

        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a session to resume.")
            return

        session = self.sessions[selected]

        # Check if locked by another PC
        if session['is_locked']:
            lock_info = session['lock_info']
            current_pc = self.session_lock_manager.hostname

            if lock_info.get('locked_by') != current_pc:
                QMessageBox.warning(
                    self,
                    "Session Locked",
                    f"This session is locked by {lock_info.get('locked_by')}.\n"
                    f"Worker: {self._get_worker_name(lock_info.get('worker_id', 'Unknown'))}\n\n"
                    f"Use 'Force Unlock' if the session is stale."
                )
                return

        # Emit signal to resume
        self.resume_requested.emit({
            'session_path': session['session_path'],
            'client_id': session['client_id'],
            'packing_list_name': session['packing_list_name'],
            'work_dir': session['work_dir'],
            'lock_info': session.get('lock_info'),
            'session_info': session.get('session_info')
        })

    def _on_force_unlock(self):
        """Handle Force Unlock button click."""
        selected = self.table.currentRow()

        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a session to unlock.")
            return

        session = self.sessions[selected]

        if not session['is_locked']:
            QMessageBox.information(self, "Not Locked", "This session is not locked.")
            return

        # Confirm
        reply = QMessageBox.question(
            self,
            "Force Unlock",
            f"Are you sure you want to force unlock this session?\n\n"
            f"Session: {session['session_id']}\n"
            f"Packing List: {session['packing_list_name']}\n"
            f"Locked by: {self._get_worker_name(session['worker_id'])} on {session['pc_name']}\n\n"
            f"This should only be done if the session is truly stale.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Force release lock
                work_dir = Path(session['work_dir'])
                success = self.session_lock_manager.force_release_lock(work_dir)

                if success:
                    QMessageBox.information(self, "Success", "Lock released successfully.")
                    logger.info(f"Lock successfully released for {work_dir}")
                    self.refresh()
                else:
                    QMessageBox.warning(
                        self,
                        "Failed",
                        f"Failed to release lock for session.\n\nThe lock file may not exist or cannot be deleted."
                    )
                    logger.warning(f"Failed to release lock for {work_dir}")

            except Exception as e:
                logger.error(f"Failed to release lock: {e}", exc_info=True)
                QMessageBox.critical(self, "Error", f"Failed to release lock:\n{str(e)}")

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
            # Get SessionBrowserWidget (find first parent that has session_history_manager)
            browser_widget = self.parent()
            while browser_widget and not hasattr(browser_widget, 'session_history_manager'):
                browser_widget = browser_widget.parent()

            if not browser_widget:
                raise AttributeError("Could not find SessionBrowserWidget parent")

            # Build standardized structure
            work_dir_path = Path(session['work_dir'])

            session_data = {
                'session_id': session['session_id'],
                'client_id': session['client_id'],
                'packing_list_name': session['packing_list_name'],
                'worker_id': session.get('worker_id'),
                'worker_name': self._get_worker_name(session.get('worker_id', 'Unknown')),
                'pc_name': session.get('pc_name'),
                'status': session['status'],
                'lock_age': session.get('lock_age_minutes'),
                'session_path': session['session_path'],
                'work_dir': session['work_dir'],
            }

            # Load additional data from session_info.json if needed
            session_info_file = work_dir_path.parent / 'session_info.json'
            if session_info_file.exists():
                with open(session_info_file, 'r') as f:
                    info = json.load(f)
                    session_data.update({
                        'started_at': info.get('started_at'),
                        'orders_total': info.get('orders_total', 0),
                        'items_total': info.get('items_total', 0),
                    })

            # Load progress from packing_state.json
            state_file = work_dir_path / 'packing_state.json'
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    data = state.get('data', {})
                    orders = data.get('orders', [])
                    completed_count = sum(1 for o in orders if o.get('status') == 'completed')
                    session_data['orders_completed'] = completed_count

            dialog = SessionDetailsDialog(
                session_data=session_data,
                session_history_manager=browser_widget.session_history_manager,
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
