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

    def __init__(self, profile_manager, parent=None):
        """
        Initialize SessionSelectorDialog.

        Args:
            profile_manager: ProfileManager instance for accessing sessions
            parent: Parent widget
        """
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.selected_session_path = None
        self.selected_session_data = None

        self.setWindowTitle("Select Shopify Session to Pack")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        self._init_ui()
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
        # SESSION INFO
        # ====================================================================
        info_group = QGroupBox("Session Details")
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
        client_id = self.client_combo.currentData()

        if not client_id:
            return

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

    def _on_session_selected(self):
        """Handle session selection change."""
        selected_items = self.sessions_list.selectedItems()

        if not selected_items:
            self.info_label.setText("Select a session to see details")
            self.load_button.setEnabled(False)
            return

        item = selected_items[0]
        session = item.data(Qt.UserRole)

        if not session or not isinstance(session, dict):
            return

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
        else:
            info_text += "<b>Type:</b> Regular session (no Shopify data)"
            self.load_button.setEnabled(False)

        self.info_label.setText(info_text)

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
