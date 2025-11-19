"""
Session Selector Widget - Choose Shopify sessions to pack.

This module provides a UI widget for selecting Shopify Tool sessions
to load into Packing Tool. It displays available sessions with metadata
such as order count and allows filtering by date.

Integration with Shopify Tool (Phase 1.3.2):
- Scans Sessions/CLIENT_{ID}/ directories
- Looks for sessions with analysis/analysis_data.json
- Displays session info (date, orders count)
- Returns selected session path for loading
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QListWidget, QListWidgetItem, QPushButton, QDateEdit,
    QCheckBox, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, QDate

from logger import get_logger

logger = get_logger(__name__)


class SessionSelectorDialog(QDialog):
    """
    Dialog for selecting a Shopify session to load for packing.

    Displays:
    - Client selector dropdown
    - List of available Shopify sessions
    - Session metadata (date, orders count)
    - Date range filter

    Returns:
    - Selected session path (Path object)
    - Session metadata dictionary
    """

    def __init__(self, profile_manager, pre_selected_client=None, parent=None):
        """
        Initialize SessionSelectorDialog.

        Args:
            profile_manager: ProfileManager instance for accessing sessions
            pre_selected_client: Optional pre-selected client ID
                                If provided, client selector will be hidden
                                and sessions filtered to this client only
            parent: Parent widget
        """
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.pre_selected_client = pre_selected_client
        self.selected_session_path = None
        self.selected_session_data = None
        self.selected_packing_list_path = None  # NEW: Selected packing list JSON path

        self.setWindowTitle("Select Shopify Session to Pack")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)  # Increased height for packing lists section

        self._init_ui()

        # If client pre-selected, apply pre-selection immediately
        if self.pre_selected_client:
            self._apply_pre_selection()
        else:
            self._load_clients()

        logger.info("SessionSelectorDialog initialized")

    def _init_ui(self):
        """Initialize user interface components."""
        layout = QVBoxLayout(self)

        # ====================================================================
        # CLIENT SELECTION
        # ====================================================================
        client_group = QGroupBox("Select Client")
        client_layout = QHBoxLayout(client_group)

        client_label = QLabel("Client:")
        client_layout.addWidget(client_label)

        self.client_combo = QComboBox()
        self.client_combo.setMinimumWidth(200)
        self.client_combo.currentIndexChanged.connect(self._on_client_changed)
        client_layout.addWidget(self.client_combo)

        client_layout.addStretch()
        layout.addWidget(client_group)

        # ====================================================================
        # FILTER OPTIONS
        # ====================================================================
        filter_group = QGroupBox("Filter Sessions")
        filter_layout = QHBoxLayout(filter_group)

        # Date range filter
        self.use_date_filter_checkbox = QCheckBox("Filter by date range:")
        self.use_date_filter_checkbox.stateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.use_date_filter_checkbox)

        filter_layout.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.dateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.date_from)

        filter_layout.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.date_to)

        # Show only sessions with Shopify data
        self.shopify_only_checkbox = QCheckBox("Shopify sessions only")
        self.shopify_only_checkbox.setChecked(True)
        self.shopify_only_checkbox.stateChanged.connect(self._refresh_sessions)
        filter_layout.addWidget(self.shopify_only_checkbox)

        filter_layout.addStretch()
        layout.addWidget(filter_group)

        # ====================================================================
        # SESSIONS LIST
        # ====================================================================
        sessions_group = QGroupBox("Available Sessions")
        sessions_layout = QVBoxLayout(sessions_group)

        self.sessions_list = QListWidget()
        self.sessions_list.itemDoubleClicked.connect(self._on_session_double_clicked)
        sessions_layout.addWidget(self.sessions_list)

        layout.addWidget(sessions_group)

        # ====================================================================
        # PACKING LISTS (NEW)
        # ====================================================================
        packing_lists_group = QGroupBox("Packing Lists (Optional)")
        packing_lists_layout = QVBoxLayout(packing_lists_group)

        packing_info = QLabel("Select a specific packing list to load only those orders, or load the entire session")
        packing_info.setWordWrap(True)
        packing_info.setStyleSheet("color: gray; font-style: italic;")
        packing_lists_layout.addWidget(packing_info)

        self.packing_lists_widget = QListWidget()
        self.packing_lists_widget.itemSelectionChanged.connect(self._on_packing_list_selected)
        self.packing_lists_widget.itemDoubleClicked.connect(self._on_packing_list_double_clicked)
        packing_lists_layout.addWidget(self.packing_lists_widget)

        layout.addWidget(packing_lists_group)

        # ====================================================================
        # SESSION INFO
        # ====================================================================
        info_group = QGroupBox("Selection Details")
        info_layout = QVBoxLayout(info_group)

        self.info_label = QLabel("Select a session to see details")
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)

        layout.addWidget(info_group)

        # ====================================================================
        # BUTTONS
        # ====================================================================
        button_layout = QHBoxLayout()

        self.load_button = QPushButton("Load Session")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self._on_load_clicked)
        button_layout.addWidget(self.load_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect selection change
        self.sessions_list.itemSelectionChanged.connect(self._on_session_selected)

    def _load_clients(self):
        """Load available clients from ProfileManager."""
        logger.info("Loading available clients")

        self.client_combo.blockSignals(True)
        self.client_combo.clear()

        try:
            clients = self.profile_manager.get_available_clients()

            if not clients:
                logger.warning("No clients found")
                self.client_combo.addItem("(No clients available)", None)
                self.client_combo.setEnabled(False)
                return

            self.client_combo.setEnabled(True)

            for client_id in clients:
                config = self.profile_manager.load_client_config(client_id)
                if config:
                    display_name = f"{config.get('client_name', client_id)} ({client_id})"
                else:
                    display_name = client_id

                self.client_combo.addItem(display_name, client_id)

            logger.info(f"Loaded {len(clients)} clients")

        except Exception as e:
            logger.error(f"Error loading clients: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load clients:\n\n{e}")

        finally:
            self.client_combo.blockSignals(False)

        # Trigger loading sessions for first client
        if self.client_combo.count() > 0 and self.client_combo.currentData():
            self._on_client_changed(0)

    def _apply_pre_selection(self):
        """
        Apply pre-selected client filter and hide client selector.

        Called when dialog is opened with a pre-selected client from main menu.
        Hides the client ComboBox and shows static label instead.
        """
        logger.info(f"Applying pre-selection for client: {self.pre_selected_client}")

        # Hide client selector ComboBox
        if hasattr(self, 'client_combo'):
            self.client_combo.setVisible(False)
            self.client_combo.setEnabled(False)

        # Create and show static label instead
        if not hasattr(self, 'client_label'):
            # Get client display name
            try:
                config = self.profile_manager.load_client_config(self.pre_selected_client)
                if config:
                    display_name = f"{config.get('client_name', self.pre_selected_client)} ({self.pre_selected_client})"
                else:
                    display_name = self.pre_selected_client
            except:
                display_name = self.pre_selected_client

            self.client_label = QLabel(f"Client: {display_name}")
            self.client_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #2E7D32;")

            # Insert into client group layout (before combo)
            client_group = self.client_combo.parent()
            if client_group:
                layout = client_group.layout()
                if layout:
                    # Insert at position 1 (after "Client:" label)
                    layout.insertWidget(1, self.client_label)

        self.client_label.setVisible(True)

        # Update window title
        self.setWindowTitle(f"Select Shopify Session - {self.pre_selected_client}")

        # Load sessions immediately for this client
        self._refresh_sessions_for_client(self.pre_selected_client)

        logger.info(f"Pre-selection applied successfully for client {self.pre_selected_client}")

    def _refresh_sessions_for_client(self, client_id: str):
        """
        Refresh sessions list for a specific client.

        Args:
            client_id: Client identifier to load sessions for
        """
        logger.info(f"Refreshing sessions for client {client_id}")

        self.sessions_list.clear()
        self.info_label.setText("Select a session to see details")
        self.load_button.setEnabled(False)

        try:
            # Get all sessions for client
            sessions = self._scan_shopify_sessions(client_id)

            # Apply filters
            if self.use_date_filter_checkbox.isChecked():
                sessions = self._filter_by_date(sessions)

            if self.shopify_only_checkbox.isChecked():
                sessions = [s for s in sessions if s.get('has_shopify_data', False)]

            logger.info(f"Found {len(sessions)} sessions after filtering")

            # Populate list
            for session in sessions:
                item = QListWidgetItem()

                # Format display text
                session_name = session['name']
                orders_count = session.get('orders_count', 0)
                has_shopify = session.get('has_shopify_data', False)

                display_text = f"{session_name}"
                if has_shopify:
                    display_text += f" - {orders_count} orders (Shopify)"
                else:
                    display_text += " - No Shopify data"

                item.setText(display_text)
                item.setData(Qt.UserRole, session)

                # Color code by type
                if has_shopify:
                    item.setForeground(Qt.darkGreen)
                else:
                    item.setForeground(Qt.gray)

                self.sessions_list.addItem(item)

            if len(sessions) == 0:
                info_item = QListWidgetItem("No sessions found for this client")
                info_item.setForeground(Qt.gray)
                self.sessions_list.addItem(info_item)

        except Exception as e:
            logger.error(f"Error refreshing sessions: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load sessions:\n\n{e}")

    def _on_client_changed(self, index: int):
        """Handle client selection change."""
        client_id = self.client_combo.currentData()

        if not client_id:
            logger.debug("No valid client selected")
            return

        logger.info(f"Client changed to: {client_id}")
        self._refresh_sessions()

    def _refresh_sessions(self):
        """Refresh sessions list for current client with filters."""
        # Use pre-selected client if available, otherwise get from combo
        if self.pre_selected_client:
            client_id = self.pre_selected_client
        else:
            client_id = self.client_combo.currentData()

        if not client_id:
            return

        # Use the unified refresh method
        self._refresh_sessions_for_client(client_id)

    def _scan_shopify_sessions(self, client_id: str) -> List[Dict]:
        """
        Scan for Shopify sessions in Sessions/CLIENT_{ID}/ directory.

        A Shopify session is identified by:
        - Has analysis/analysis_data.json file
        - Created by Shopify Tool

        Args:
            client_id: Client identifier

        Returns:
            List of session dictionaries with metadata
        """
        sessions_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}"

        if not sessions_dir.exists():
            logger.debug(f"No sessions directory for client {client_id}")
            return []

        sessions = []

        try:
            for session_dir in sessions_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                session_info = {
                    'name': session_dir.name,
                    'path': session_dir,
                    'modified': datetime.fromtimestamp(session_dir.stat().st_mtime),
                    'has_shopify_data': False,
                    'orders_count': 0
                }

                # Check for Shopify data
                analysis_data_path = session_dir / "analysis" / "analysis_data.json"

                if analysis_data_path.exists():
                    try:
                        with open(analysis_data_path, 'r', encoding='utf-8') as f:
                            analysis_data = json.load(f)

                        session_info['has_shopify_data'] = True
                        session_info['orders_count'] = analysis_data.get('total_orders', 0)
                        session_info['analysis_data'] = analysis_data

                        logger.debug(f"Found Shopify session: {session_dir.name} ({session_info['orders_count']} orders)")

                    except Exception as e:
                        logger.warning(f"Error reading analysis_data.json for {session_dir.name}: {e}")

                sessions.append(session_info)

            # Sort by modification time (newest first)
            sessions.sort(key=lambda x: x['modified'], reverse=True)

            return sessions

        except Exception as e:
            logger.error(f"Error scanning sessions: {e}", exc_info=True)
            return []

    def _filter_by_date(self, sessions: List[Dict]) -> List[Dict]:
        """
        Filter sessions by date range.

        Args:
            sessions: List of session dictionaries

        Returns:
            Filtered list of sessions
        """
        from_date = self.date_from.date().toPython()
        to_date = self.date_to.date().toPython()

        filtered = []
        for session in sessions:
            session_date = session['modified'].date()
            if from_date <= session_date <= to_date:
                filtered.append(session)

        return filtered

    def _scan_packing_lists(self, session_path: Path) -> List[Dict]:
        """
        Scan for packing list JSON files in session/packing_lists/ directory.

        Args:
            session_path: Path to session directory

        Returns:
            List of packing list dictionaries with metadata
        """
        packing_lists_dir = session_path / "packing_lists"

        if not packing_lists_dir.exists():
            logger.debug(f"No packing_lists directory in {session_path.name}")
            return []

        packing_lists = []

        try:
            for json_file in packing_lists_dir.glob("*.json"):
                if not json_file.is_file():
                    continue

                packing_list_info = {
                    'name': json_file.stem,
                    'filename': json_file.name,
                    'path': json_file,
                    'modified': datetime.fromtimestamp(json_file.stat().st_mtime),
                    'orders_count': 0,
                    'courier': None
                }

                # Try to read metadata from JSON
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    packing_list_info['orders_count'] = data.get('total_orders', len(data.get('orders', [])))
                    packing_list_info['courier'] = data.get('courier')
                    packing_list_info['list_name'] = data.get('list_name', json_file.stem)

                    logger.debug(f"Found packing list: {json_file.name} ({packing_list_info['orders_count']} orders)")

                except Exception as e:
                    logger.warning(f"Error reading packing list {json_file.name}: {e}")

                packing_lists.append(packing_list_info)

            # Sort by name
            packing_lists.sort(key=lambda x: x['name'])

            return packing_lists

        except Exception as e:
            logger.error(f"Error scanning packing lists: {e}", exc_info=True)
            return []

    def _on_session_selected(self):
        """Handle session selection change."""
        selected_items = self.sessions_list.selectedItems()

        if not selected_items:
            self.info_label.setText("Select a session to see details")
            self.load_button.setEnabled(False)
            self.packing_lists_widget.clear()
            self.selected_packing_list_path = None
            return

        item = selected_items[0]
        session = item.data(Qt.UserRole)

        if not session or not isinstance(session, dict):
            return

        # Clear previous packing list selection
        self.selected_packing_list_path = None

        # Update info label
        info_text = f"<b>Session:</b> {session['name']}<br>"
        info_text += f"<b>Modified:</b> {session['modified'].strftime('%Y-%m-%d %H:%M')}<br>"

        if session.get('has_shopify_data'):
            info_text += f"<b>Orders:</b> {session.get('orders_count', 0)}<br>"
            info_text += f"<b>Type:</b> Shopify Session<br>"

            # Show path to analysis data
            analysis_path = session['path'] / "analysis" / "analysis_data.json"
            info_text += f"<b>Data:</b> {analysis_path.name}"

            self.load_button.setEnabled(True)

            # Scan for packing lists
            packing_lists = self._scan_packing_lists(session['path'])
            self.packing_lists_widget.clear()

            if packing_lists:
                info_text += f"<br><b>Packing Lists:</b> {len(packing_lists)} available"

                for pl in packing_lists:
                    list_item = QListWidgetItem()

                    display_text = f"{pl['list_name']}"
                    if pl['courier']:
                        display_text += f" ({pl['courier']})"
                    display_text += f" - {pl['orders_count']} orders"

                    list_item.setText(display_text)
                    list_item.setData(Qt.UserRole, pl)
                    list_item.setForeground(Qt.darkBlue)

                    self.packing_lists_widget.addItem(list_item)

                logger.info(f"Loaded {len(packing_lists)} packing lists for session {session['name']}")
            else:
                no_lists_item = QListWidgetItem("No packing lists available (load entire session)")
                no_lists_item.setForeground(Qt.gray)
                self.packing_lists_widget.addItem(no_lists_item)

        else:
            info_text += "<b>Type:</b> Regular session (no Shopify data)"
            self.load_button.setEnabled(False)
            self.packing_lists_widget.clear()

        self.info_label.setText(info_text)

    def _on_packing_list_selected(self):
        """Handle packing list selection change."""
        selected_items = self.packing_lists_widget.selectedItems()

        if not selected_items:
            # No packing list selected, will load entire session
            self.selected_packing_list_path = None
            return

        item = selected_items[0]
        packing_list = item.data(Qt.UserRole)

        if not packing_list or not isinstance(packing_list, dict):
            self.selected_packing_list_path = None
            return

        # Store selected packing list path
        self.selected_packing_list_path = packing_list['path']

        # Update info label to show selected packing list
        session_items = self.sessions_list.selectedItems()
        if session_items:
            session = session_items[0].data(Qt.UserRole)
            if session:
                info_text = f"<b>Session:</b> {session['name']}<br>"
                info_text += f"<b>Modified:</b> {session['modified'].strftime('%Y-%m-%d %H:%M')}<br>"
                info_text += f"<hr><b>Selected Packing List:</b> {packing_list['list_name']}<br>"
                info_text += f"<b>Orders:</b> {packing_list['orders_count']}<br>"
                if packing_list['courier']:
                    info_text += f"<b>Courier:</b> {packing_list['courier']}<br>"
                info_text += f"<b>File:</b> {packing_list['filename']}"

                self.info_label.setText(info_text)

        logger.info(f"Selected packing list: {packing_list['list_name']}")

    def _on_packing_list_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on packing list (same as clicking Load)."""
        packing_list = item.data(Qt.UserRole)

        if packing_list and isinstance(packing_list, dict):
            self._on_load_clicked()

    def _on_session_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on session (same as clicking Load)."""
        session = item.data(Qt.UserRole)

        if session and isinstance(session, dict) and session.get('has_shopify_data'):
            self._on_load_clicked()

    def _on_load_clicked(self):
        """Handle Load button click."""
        selected_items = self.sessions_list.selectedItems()

        if not selected_items:
            return

        item = selected_items[0]
        session = item.data(Qt.UserRole)

        if not session or not isinstance(session, dict):
            return

        if not session.get('has_shopify_data'):
            QMessageBox.warning(
                self,
                "Invalid Session",
                "Selected session does not have Shopify data.\n"
                "Please select a session created by Shopify Tool."
            )
            return

        logger.info(f"Loading Shopify session: {session['name']}")

        self.selected_session_path = session['path']
        self.selected_session_data = session.get('analysis_data')

        # Packing list path is already set by _on_packing_list_selected or None
        if self.selected_packing_list_path:
            logger.info(f"Will load packing list: {self.selected_packing_list_path.name}")
        else:
            logger.info("Will load entire session (no specific packing list selected)")

        self.accept()

    def get_selected_session(self) -> Optional[Path]:
        """
        Get selected session path.

        Returns:
            Path to selected session directory, or None if cancelled
        """
        return self.selected_session_path

    def get_session_data(self) -> Optional[Dict]:
        """
        Get selected session's analysis data.

        Returns:
            Analysis data dictionary, or None if not available
        """
        return self.selected_session_data

    def get_selected_packing_list(self) -> Optional[Path]:
        """
        Get selected packing list path.

        Returns:
            Path to selected packing list JSON file, or None if no specific list selected
        """
        return self.selected_packing_list_path
