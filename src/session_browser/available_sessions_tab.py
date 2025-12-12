"""Available Sessions Tab - Shows Shopify sessions ready to start

Displays sessions that have packing_lists/*.json but no work directories yet.
These are Shopify-generated packing lists that haven't been started in the Packing Tool.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QMessageBox, QLabel
)
from PySide6.QtCore import Signal

from datetime import datetime
import json

from logger import get_logger
from json_cache import get_cached_json

logger = get_logger(__name__)


class AvailableSessionsTab(QWidget):
    """Tab showing available packing lists that haven't been started"""

    # Signal
    start_packing_requested = Signal(dict)  # {session_path, client_id, packing_list_name, list_file}

    def __init__(self, profile_manager, session_manager, parent=None):
        """
        Initialize Available Sessions Tab.

        Args:
            profile_manager: ProfileManager instance
            session_manager: SessionManager instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_manager = session_manager
        self.available_lists = []

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
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Session ID", "Client", "Packing List", "Courier",
            "Created", "Orders", "Items"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Packing")
        self.start_btn.clicked.connect(self._on_start_packing)
        btn_layout.addWidget(self.start_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    def _scan_sessions(self) -> list:
        """
        Scan for Shopify sessions with unstarted packing lists.

        This method is called in a background thread and must NOT touch UI.

        Returns:
            List of dicts with available packing list info
        """
        logger.debug("Scanning available sessions (background thread)")

        available_lists = []
        selected_client = self.client_combo.currentData()

        # Get Sessions base path
        try:
            sessions_base = self.profile_manager.get_sessions_root()
        except Exception as e:
            logger.error(f"Failed to get sessions root: {e}")
            return []

        if not sessions_base.exists():
            logger.info(f"Sessions directory not found: {sessions_base}")
            return []

        # Scan each client
        for client_dir in sessions_base.iterdir():
            if not client_dir.is_dir():
                continue

            client_id = client_dir.name.replace("CLIENT_", "")

            # Filter by selected client
            if selected_client and client_id != selected_client:
                continue

            # Scan each session
            for session_dir in client_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                session_id = session_dir.name
                packing_lists_dir = session_dir / "packing_lists"

                # Must have packing_lists/ directory (Shopify marker)
                if not packing_lists_dir.exists():
                    continue

                # Check each packing list
                for list_file in packing_lists_dir.glob("*.json"):
                    list_name = list_file.stem

                    # Check if work directory exists
                    work_dir = session_dir / "packing" / list_name

                    if work_dir.exists():
                        # Already started, skip
                        continue

                    # Load packing list data
                    try:
                        # OPTIMIZED: Use JSON cache for packing list metadata
                        # When scanning multiple sessions, this reduces repeated disk reads
                        list_data = get_cached_json(list_file, default={})

                        if not list_data:
                            logger.warning(f"Empty or invalid packing list: {list_file}")
                            continue

                        available_lists.append({
                            'session_id': session_id,
                            'client_id': client_id,
                            'session_path': str(session_dir),
                            'list_name': list_name,
                            'list_file': str(list_file),
                            'courier': list_data.get('courier', 'Unknown'),
                            'created_at': list_data.get('created_at', ''),
                            'total_orders': list_data.get('total_orders', 0),
                            'total_items': list_data.get('total_items', 0)
                        })

                    except Exception as e:
                        logger.warning(f"Failed to load {list_file}: {e}")
                        continue

        # Sort by session_id (newest first)
        available_lists.sort(key=lambda x: x['session_id'], reverse=True)

        logger.debug(f"Found {len(available_lists)} available sessions")
        return available_lists

    def populate_table(self, session_data: list):
        """
        Populate table with session data on main UI thread.

        This method updates the UI and must be called on the main thread.

        Args:
            session_data: List of available session records from _scan_sessions()
        """
        logger.debug(f"Populating table with {len(session_data)} available sessions")

        self.available_lists = session_data
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
        """Fill table with available lists."""
        self.table.setRowCount(len(self.available_lists))

        for row, item in enumerate(self.available_lists):
            # Session ID
            self.table.setItem(row, 0, QTableWidgetItem(item['session_id']))

            # Client
            self.table.setItem(row, 1, QTableWidgetItem(f"CLIENT_{item['client_id']}"))

            # Packing List
            self.table.setItem(row, 2, QTableWidgetItem(item['list_name']))

            # Courier
            self.table.setItem(row, 3, QTableWidgetItem(item['courier']))

            # Created
            created = item['created_at']
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    created = dt.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            self.table.setItem(row, 4, QTableWidgetItem(created))

            # Orders
            self.table.setItem(row, 5, QTableWidgetItem(str(item['total_orders'])))

            # Items
            self.table.setItem(row, 6, QTableWidgetItem(str(item['total_items'])))

    def _on_start_packing(self):
        """Handle Start Packing button click."""
        selected = self.table.currentRow()

        if selected < 0:
            QMessageBox.warning(self, "No Selection", "Please select a packing list to start.")
            return

        item = self.available_lists[selected]

        # Confirm
        reply = QMessageBox.question(
            self,
            "Start Packing",
            f"Start packing for:\n\n"
            f"Session: {item['session_id']}\n"
            f"Client: CLIENT_{item['client_id']}\n"
            f"Packing List: {item['list_name']}\n"
            f"Orders: {item['total_orders']}\n"
            f"Items: {item['total_items']}\n\n"
            f"This will create a new work directory and start the packing session.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal
            self.start_packing_requested.emit({
                'session_path': item['session_path'],
                'client_id': item['client_id'],
                'packing_list_name': item['list_name'],
                'list_file': item['list_file']
            })
