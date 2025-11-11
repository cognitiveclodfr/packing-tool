import sys
import os
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QFileDialog, QStackedWidget,
    QTableView, QHBoxLayout, QMessageBox, QHeaderView, QLineEdit, QComboBox, QDialog, QFormLayout,
    QDialogButtonBox, QTabWidget
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QTimer, Qt, QSettings
from datetime import datetime
from openpyxl.styles import PatternFill
import pandas as pd

from logger import get_logger
from profile_manager import ProfileManager, ProfileManagerError, NetworkError, ValidationError
from session_lock_manager import SessionLockManager
from exceptions import SessionLockedError, StaleLockError
from restore_session_dialog import RestoreSessionDialog
from session_monitor_widget import SessionMonitorWidget
from session_selector import SessionSelectorDialog
from mapping_dialog import ColumnMappingDialog
from print_dialog import PrintDialog
from packer_mode_widget import PackerModeWidget
from packer_logic import PackerLogic, REQUIRED_COLUMNS
from session_manager import SessionManager
from order_table_model import OrderTableModel
from statistics_manager import StatisticsManager
from custom_filter_proxy_model import CustomFilterProxyModel
from sku_mapping_manager import SKUMappingManager
from sku_mapping_dialog import SKUMappingDialog
from dashboard_widget import DashboardWidget
from session_history_widget import SessionHistoryWidget

logger = get_logger(__name__)

def find_latest_session_dir(base_dir: str = ".") -> str | None:
    """
    Finds the most recent, valid, and incomplete session directory.

    A session is considered valid and incomplete if it is a directory matching
    the session name pattern and contains a `session_info.json` file.

    Args:
        base_dir (str): The directory to search for session folders.

    Returns:
        str | None: The path to the latest valid session directory, or None if
                    none is found.
    """
    session_pattern = "OrdersFulfillment_"
    session_dirs = []
    try:
        session_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith(session_pattern)]
    except FileNotFoundError:
        return None # No base directory yet

    valid_sessions = []
    for dirname in session_dirs:
        dirpath = os.path.join(base_dir, dirname)
        # A valid, incomplete session must have a session_info file.
        if os.path.exists(os.path.join(dirpath, "session_info.json")):
            valid_sessions.append(dirpath)

    if not valid_sessions:
        return None

    # Return the one that was most recently modified
    latest_session_dir = max(valid_sessions, key=os.path.getmtime)
    return latest_session_dir


class MainWindow(QMainWindow):
    """
    The main application window, acting as the central orchestrator.

    This class initializes the UI, manages application state, and connects UI
    events to the backend logic. It handles the overall workflow, including
    session management, data loading, and switching between different views.

    Attributes:
        session_manager (SessionManager): Manages the lifecycle of packing sessions.
        logic (PackerLogic | None): The core business logic for the current session.
        stats_manager (StatisticsManager): Manages persistent application statistics.
        session_widget (QWidget): The main widget for the session view.
        packer_mode_widget (PackerModeWidget): The widget for the packer mode view.
        stacked_widget (QStackedWidget): Manages switching between views.
        orders_table (QTableView): The table displaying the list of orders.
        table_model (OrderTableModel): The model for the orders table.
        proxy_model (CustomFilterProxyModel): The proxy model for filtering the table.
    """
    def __init__(self):
        """Initialize the MainWindow, sets up UI, and loads initial state."""
        super().__init__()
        self.setWindowTitle("Packer's Assistant")
        self.resize(1024, 768)

        logger.info("Initializing MainWindow")

        # Initialize ProfileManager (may raise NetworkError)
        try:
            self.profile_manager = ProfileManager()
            logger.info("ProfileManager initialized successfully")
        except NetworkError as e:
            logger.error(f"Failed to initialize ProfileManager: {e}")
            QMessageBox.critical(
                self,
                "Network Error",
                f"Cannot connect to file server:\n\n{e}\n\n"
                f"Please check your network connection and try again."
            )
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error initializing ProfileManager: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to initialize application:\n\n{e}")
            sys.exit(1)

        # Initialize SessionLockManager
        self.lock_manager = SessionLockManager(self.profile_manager)
        logger.info("SessionLockManager initialized successfully")

        # Current client state
        self.current_client_id = None
        self.session_manager = None  # Will be instantiated per client
        self.logic = None  # Will be instantiated per session

        # Shopify session state (new workflow)
        self.current_session_path = None  # Path to current Shopify session
        self.current_packing_list = None  # Name of selected packing list
        self.current_work_dir = None      # Work directory for packing results
        self.packing_data = None          # Loaded packing list data

        # Phase 1.3: StatisticsManager with centralized storage on file server
        self.stats_manager = StatisticsManager(profile_manager=self.profile_manager)

        # Legacy SKU manager (kept for backward compatibility, but not used in new workflow)
        self.sku_manager = SKUMappingManager()

        # Settings for remembering last client
        self.settings = QSettings("PackingTool", "ClientSelection")

        self._init_ui()

        self._update_dashboard()

        # Load available clients and restore last selected
        self.load_available_clients()

        logger.info("MainWindow initialized successfully")

    def _init_ui(self):
        """Initialize all user interface components and layouts."""
        self.session_widget = QWidget()
        main_layout = QVBoxLayout(self.session_widget)

        # ====================================================================
        # CLIENT SELECTION (NEW)
        # ====================================================================
        client_selection_widget = QWidget()
        client_selection_widget.setObjectName("ClientSelection")
        client_selection_layout = QHBoxLayout(client_selection_widget)
        main_layout.addWidget(client_selection_widget)

        client_label = QLabel("Client:")
        client_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        client_selection_layout.addWidget(client_label)

        self.client_combo = QComboBox()
        self.client_combo.setMinimumWidth(250)
        self.client_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.client_combo.currentIndexChanged.connect(self.on_client_changed)
        client_selection_layout.addWidget(self.client_combo)

        self.new_client_button = QPushButton("+ New Client")
        self.new_client_button.clicked.connect(self.create_new_client)
        client_selection_layout.addWidget(self.new_client_button)

        client_selection_layout.addStretch()

        # Dashboard
        dashboard_widget = QWidget()
        dashboard_widget.setObjectName("Dashboard")
        dashboard_layout = QHBoxLayout(dashboard_widget)
        main_layout.addWidget(dashboard_widget)

        self.total_orders_label = QLabel("Total Unique Orders: 0")
        self.completed_label = QLabel("Total Completed: 0")

        for label in [self.total_orders_label, self.completed_label]:
            label.setAlignment(Qt.AlignCenter)
            font = label.font()
            font.setPointSize(14)
            font.setBold(True)
            label.setFont(font)
            dashboard_layout.addWidget(label)

        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        main_layout.addWidget(control_panel)

        self.start_session_button = QPushButton("Start Session")
        self.start_session_button.clicked.connect(self.start_session)
        control_layout.addWidget(self.start_session_button)

        self.load_shopify_button = QPushButton("Open Shopify Session")
        self.load_shopify_button.clicked.connect(self.open_shopify_session)
        self.load_shopify_button.setStyleSheet("background-color: #4CAF50; color: white;")
        self.load_shopify_button.setToolTip("Open Shopify session and select packing list to work on")
        control_layout.addWidget(self.load_shopify_button)

        self.restore_session_button = QPushButton("Restore Session")
        self.restore_session_button.clicked.connect(self.open_restore_session_dialog)
        control_layout.addWidget(self.restore_session_button)

        self.end_session_button = QPushButton("End Session")
        self.end_session_button.setEnabled(False)
        self.end_session_button.clicked.connect(self.end_session)
        control_layout.addWidget(self.end_session_button)

        control_layout.addStretch()

        self.print_button = QPushButton("Print Barcodes")
        self.print_button.setEnabled(False)
        self.print_button.clicked.connect(self.open_print_dialog)
        control_layout.addWidget(self.print_button)

        self.packer_mode_button = QPushButton("Switch to Packer Mode")
        self.packer_mode_button.setEnabled(False)
        self.packer_mode_button.clicked.connect(self.switch_to_packer_mode)
        control_layout.addWidget(self.packer_mode_button)

        self.sku_mapping_button = QPushButton("SKU Mapping")
        self.sku_mapping_button.clicked.connect(self.open_sku_mapping_dialog)
        control_layout.addWidget(self.sku_mapping_button)

        self.session_monitor_button = QPushButton("Session Monitor")
        self.session_monitor_button.clicked.connect(self.open_session_monitor)
        control_layout.addWidget(self.session_monitor_button)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Order Number, SKU, or Status...")
        main_layout.addWidget(self.search_input)

        self.orders_table = QTableView()
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        main_layout.addWidget(self.orders_table)

        self.status_label = QLabel("Start a new session to load a packing list.")
        main_layout.addWidget(self.status_label)

        self.packer_mode_widget = PackerModeWidget()
        self.packer_mode_widget.barcode_scanned.connect(self.on_scanner_input)
        self.packer_mode_widget.exit_packing_mode.connect(self.switch_to_session_view)

        # Phase 1.3: Dashboard and History widgets
        self.dashboard_widget = DashboardWidget(self.profile_manager, self.stats_manager)
        self.history_widget = SessionHistoryWidget(self.profile_manager)

        # Create tab widget for main views
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.session_widget, "Session")
        self.tab_widget.addTab(self.dashboard_widget, "Dashboard")
        self.tab_widget.addTab(self.history_widget, "History")

        # Stacked widget to switch between tabbed view and packer mode
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.tab_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.setCentralWidget(self.stacked_widget)

        # Create menu bar
        self._init_menu_bar()

    def _init_menu_bar(self):
        """Initialize the menu bar with actions."""
        menubar = self.menuBar()

        # View menu
        view_menu = menubar.addMenu("&View")

        session_action = QAction("&Session", self)
        session_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        view_menu.addAction(session_action)

        dashboard_action = QAction("&Dashboard", self)
        dashboard_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        view_menu.addAction(dashboard_action)

        history_action = QAction("&History", self)
        history_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(2))
        view_menu.addAction(history_action)

        view_menu.addSeparator()

        refresh_action = QAction("&Refresh All", self)
        refresh_action.triggered.connect(self._refresh_all_views)
        view_menu.addAction(refresh_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        sku_mapping_action = QAction("SKU &Mapping", self)
        sku_mapping_action.triggered.connect(self.open_sku_mapping_dialog)
        tools_menu.addAction(sku_mapping_action)

        session_monitor_action = QAction("Session &Monitor", self)
        session_monitor_action.triggered.connect(self.open_session_monitor)
        tools_menu.addAction(session_monitor_action)

    def _refresh_all_views(self):
        """Refresh all dashboard and history views."""
        try:
            self.dashboard_widget.refresh()
            self.history_widget.refresh()
            QMessageBox.information(self, "Refresh Complete", "All views have been refreshed")
        except Exception as e:
            logger.error(f"Error refreshing views: {e}")
            QMessageBox.warning(self, "Refresh Error", f"Failed to refresh views: {e}")

    def _update_dashboard(self):
        """Update the statistics dashboard with the latest data."""
        stats = self.stats_manager.get_display_stats()
        self.total_orders_label.setText(f"Total Unique Orders: {stats['Total Unique Orders']}")
        self.completed_label.setText(f"Total Completed: {stats['Total Completed']}")

    # ========================================================================
    # CLIENT MANAGEMENT (NEW)
    # ========================================================================

    def load_available_clients(self):
        """Load available client profiles and populate dropdown."""
        logger.info("Loading available clients")

        self.client_combo.blockSignals(True)  # Prevent triggering on_client_changed during load
        self.client_combo.clear()

        try:
            clients = self.profile_manager.get_available_clients()

            if not clients:
                logger.warning("No clients found")
                self.client_combo.addItem("(No clients available)", None)
                self.client_combo.setEnabled(False)
                self.status_label.setText("No clients found. Click '+ New Client' to create one.")
                return

            self.client_combo.setEnabled(True)

            for client_id in clients:
                config = self.profile_manager.load_client_config(client_id)
                if config:
                    display_name = f"{config.get('client_name', client_id)} ({client_id})"
                else:
                    display_name = client_id

                self.client_combo.addItem(display_name, client_id)
                logger.debug(f"Added client: {client_id}")

            # Restore last selected client
            last_client = self.settings.value("last_client")
            if last_client:
                index = self.client_combo.findData(last_client)
                if index >= 0:
                    self.client_combo.setCurrentIndex(index)
                    logger.info(f"Restored last selected client: {last_client}")

            logger.info(f"Loaded {len(clients)} clients")

            # Phase 1.3: Load clients into dashboard and history widgets
            self.dashboard_widget.load_clients(clients)
            self.history_widget.load_clients(clients)

        except Exception as e:
            logger.error(f"Error loading clients: {e}", exc_info=True)
            QMessageBox.warning(self, "Error", f"Failed to load clients:\n\n{e}")

        finally:
            self.client_combo.blockSignals(False)

        # Trigger selection if there's a valid item
        if self.client_combo.currentData():
            self.on_client_changed(self.client_combo.currentIndex())

    def on_client_changed(self, index: int):
        """
        Handle client selection change.

        Args:
            index: Index of selected item in combo box
        """
        client_id = self.client_combo.currentData()

        if not client_id:
            logger.debug("No valid client selected")
            self.current_client_id = None
            self.status_label.setText("Please select or create a client.")
            return

        logger.info(f"Client changed to: {client_id}")

        self.current_client_id = client_id

        # Save as last selected client
        self.settings.setValue("last_client", client_id)

        # Update status
        client_name = self.client_combo.currentText()
        self.status_label.setText(f"Selected client: {client_name}\nReady to start a session.")

        logger.debug(f"Current client set to: {client_id}")

    def create_new_client(self):
        """Open dialog to create a new client profile."""
        logger.info("Opening new client dialog")

        dialog = NewClientDialog(self.profile_manager, self)

        if dialog.exec() == QDialog.Accepted:
            client_id = dialog.client_id
            logger.info(f"New client created: {client_id}")

            # Reload clients and select the new one
            self.load_available_clients()

            # Select newly created client
            index = self.client_combo.findData(client_id)
            if index >= 0:
                self.client_combo.setCurrentIndex(index)

            QMessageBox.information(
                self,
                "Client Created",
                f"Client '{dialog.client_name}' (ID: {client_id}) created successfully!"
            )

    def flash_border(self, color: str, duration_ms: int = 500):
        """
        Flashes the border of the packer mode table's frame.

        This provides visual feedback for scan results (e.g., green for success,
        red for error).

        Args:
            color (str): The color of the border (e.g., "green", "red").
            duration_ms (int): The duration of the flash in milliseconds.
        """
        self.packer_mode_widget.table_frame.setStyleSheet(f"QFrame#TableFrame {{ border: 2px solid {color}; }}")
        QTimer.singleShot(duration_ms, lambda: self.packer_mode_widget.table_frame.setStyleSheet(""))


    def start_session(self, file_path: str = None, restore_dir: str = None):
        """
        Start a new packing session for the currently selected client.

        This can be triggered by the user selecting a file or by the application
        restoring a previous, incomplete session.

        Args:
            file_path: Optional path to the packing list Excel file. If None, a file dialog is shown
            restore_dir: Optional directory of the session to restore
        """
        logger.info("Starting new session")

        # Check if client is selected
        if not self.current_client_id:
            logger.warning("Attempted to start session without selecting client")
            self.client_combo.setStyleSheet("border: 2px solid red;")
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client before starting a session!"
            )
            QTimer.singleShot(2000, lambda: self.client_combo.setStyleSheet(""))
            return

        # Check if session already active
        if self.session_manager and self.session_manager.is_active():
            logger.warning("Attempted to start session while one is already active")
            self.status_label.setText("A session is already active. Please end it first.")
            return

        # Clear existing table
        self.orders_table.setModel(None)

        # File selection dialog if no path provided
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Packing List",
                "",
                "Excel Files (*.xlsx)"
            )
            if not file_path:
                logger.info("Session start cancelled by user")
                self.status_label.setText("Session start cancelled.")
                return

        logger.info(f"Starting session for client {self.current_client_id} with file: {file_path}")

        try:
            # Create SessionManager for this client
            self.session_manager = SessionManager(
                client_id=self.current_client_id,
                profile_manager=self.profile_manager,
                lock_manager=self.lock_manager
            )

            # Start session
            session_id = self.session_manager.start_session(file_path, restore_dir=restore_dir)
            logger.info(f"Session started: {session_id}")

            # Get barcode directory
            barcodes_dir = self.session_manager.get_barcodes_dir()

            # Create PackerLogic instance
            self.logic = PackerLogic(
                client_id=self.current_client_id,
                profile_manager=self.profile_manager,
                barcode_dir=barcodes_dir
            )

            # Connect signals
            self.logic.item_packed.connect(self._on_item_packed)

            # Load and process file
            self.load_and_process_file(file_path)

        except StaleLockError as e:
            # Session has a stale lock - offer to force-release it
            logger.warning(f"Session has stale lock: {e}")
            self._handle_stale_lock_error(e, file_path, restore_dir)
            self.session_manager = None
            self.logic = None

        except SessionLockedError as e:
            # Session is actively locked by another process
            logger.warning(f"Session is locked: {e}")
            self._handle_session_locked_error(e)
            self.session_manager = None
            self.logic = None

        except Exception as e:
            logger.error(f"Failed to start session: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to start session:\n\n{e}")
            if self.session_manager:
                self.session_manager.end_session()
            self.session_manager = None
            self.logic = None

    def open_sku_mapping_dialog(self):
        """
        Open SKU mapping dialog for current client.

        Phase 1.3: Uses ProfileManager for centralized storage on file server.
        All changes are synchronized across all PCs with file locking.
        """
        if not self.current_client_id:
            logger.warning("Attempted to open SKU mapping without selecting client")
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client first!"
            )
            return

        logger.info(f"Opening SKU mapping dialog for client {self.current_client_id}")

        # Phase 1.3: Use ProfileManager directly for centralized storage
        dialog = SKUMappingDialog(self.current_client_id, self.profile_manager, self)

        if dialog.exec():  # User clicked "Save & Close"
            # Mappings are already saved by the dialog
            logger.info("SKU mapping dialog closed with save")

            # If a session is active, reload the SKU map into logic instance
            if self.logic:
                try:
                    new_map = self.profile_manager.load_sku_mapping(self.current_client_id)
                    self.logic.set_sku_map(new_map)
                    self.status_label.setText("SKU mapping updated and synchronized across all PCs.")
                    logger.info("SKU mapping reloaded into active session")
                except Exception as e:
                    logger.error(f"Failed to reload SKU mapping into session: {e}")
                    QMessageBox.warning(
                        self,
                        "Reload Warning",
                        f"Mappings saved successfully but failed to reload into current session:\n\n{e}\n\n"
                        f"Please restart the session to use new mappings."
                    )

    def end_session(self):
        """
        Ends the current session gracefully.

        This involves saving a final report, cleaning up session files, and
        resetting the UI to its initial state.

        For Shopify sessions (unified work directory):
        - Report saved to: current_work_dir/reports/packing_completed.xlsx

        For Excel sessions (legacy):
        - Report saved to: session_dir/[original_filename]_completed.xlsx
        """
        # Check if any session is active (Excel or Shopify)
        is_excel_session = self.session_manager and self.session_manager.is_active()
        is_shopify_session = hasattr(self, 'current_work_dir') and self.current_work_dir

        if not (is_excel_session or is_shopify_session):
            logger.warning("end_session called but no active session found")
            return

        try:
            # Determine output path based on session type
            if hasattr(self, 'current_work_dir') and self.current_work_dir:
                # Shopify session - save to unified work directory
                from pathlib import Path
                report_dir = Path(self.current_work_dir) / "reports"
                report_dir.mkdir(exist_ok=True, parents=True)
                new_filename = "packing_completed.xlsx"
                output_path = str(report_dir / new_filename)
                logger.info(f"Saving Shopify session report to: {output_path}")
            else:
                # Excel session - save to session directory (legacy behavior)
                output_dir = self.session_manager.get_output_dir()
                original_filename = os.path.basename(self.session_manager.packing_list_path)
                new_filename = f"{os.path.splitext(original_filename)[0]}_completed.xlsx"
                output_path = os.path.join(output_dir, new_filename)
                logger.info(f"Saving Excel session report to: {output_path}")

            status_map = self.order_summary_df.set_index('Order_Number')['Status'].to_dict()
            completed_at_map = self.order_summary_df.set_index('Order_Number')['Completed At'].to_dict()

            final_df = self.logic.packing_list_df.copy()
            final_df['Status'] = final_df['Order_Number'].map(status_map).fillna('New')
            final_df['Completed At'] = final_df['Order_Number'].map(completed_at_map).fillna('')

            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Sheet1')
                workbook = writer.book
                worksheet = writer.sheets['Sheet1']
                green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                status_col_idx = final_df.columns.get_loc('Status') + 1

                for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, max_row=worksheet.max_row)):
                    status_cell = worksheet.cell(row=row_idx + 2, column=status_col_idx)
                    if status_cell.value == 'Completed':
                        for cell in row:
                            cell.fill = green_fill

            self.status_label.setText(f"Session ended. Report saved to {output_path}")

            # Phase 1.3: Record session completion metrics and save session summary
            # ALWAYS save session summary, even if errors occur
            try:
                session_info = self.session_manager.get_session_info()

                # Get timestamps
                start_time = None
                if session_info and 'started_at' in session_info:
                    try:
                        start_time = datetime.fromisoformat(session_info['started_at'])
                    except (ValueError, TypeError):
                        logger.warning("Could not parse started_at from session_info")

                end_time = datetime.now()

                # Count completed orders and items
                completed_orders_list = self.logic.session_packing_state.get('completed_orders', [])
                completed_orders = len(completed_orders_list)

                in_progress_orders_dict = self.logic.session_packing_state.get('in_progress', {})
                in_progress_orders = len(in_progress_orders_dict)

                # Calculate items_packed correctly:
                # CRITICAL: Use pd.to_numeric() to avoid string concatenation
                # 1. For completed orders: all items are packed
                # 2. For in-progress orders: sum 'packed' values
                items_packed = 0

                try:
                    # Items from completed orders (all items packed)
                    if self.logic.processed_df is not None and completed_orders_list:
                        completed_items = pd.to_numeric(
                            self.logic.processed_df[
                                self.logic.processed_df['Order_Number'].isin(completed_orders_list)
                            ]['Quantity'],
                            errors='coerce'
                        ).sum()
                        items_packed += int(completed_items)
                        logger.debug(f"Completed orders items: {int(completed_items)}")

                    # Items from in-progress orders (partial packing)
                    in_progress_items = 0
                    for order_data in in_progress_orders_dict.values():
                        for sku_data in order_data.values():
                            if isinstance(sku_data, dict):
                                in_progress_items += sku_data.get('packed', 0)

                    items_packed += in_progress_items
                    logger.debug(f"In-progress items: {in_progress_items}")
                    logger.info(f"Total items_packed: {items_packed} (completed: {int(completed_items) if completed_orders_list else 0}, in-progress: {in_progress_items})")

                except Exception as e:
                    logger.error(f"Error calculating items_packed: {e}", exc_info=True)
                    items_packed = 0

                # Count total orders and items from processed_df
                try:
                    total_orders = len(self.logic.processed_df['Order_Number'].unique()) if self.logic.processed_df is not None else 0
                    # CRITICAL: Use pd.to_numeric() to avoid string concatenation
                    total_items = int(pd.to_numeric(self.logic.processed_df['Quantity'], errors='coerce').sum()) if self.logic.processed_df is not None else 0
                except Exception as e:
                    logger.error(f"Error calculating totals: {e}", exc_info=True)
                    total_orders = 0
                    total_items = 0

                # Get session identifier and packing list path based on session type
                if is_shopify_session:
                    # Shopify session - use current_packing_list as identifier
                    session_id = f"{self.current_session_path}_{self.current_packing_list}" if hasattr(self, 'current_session_path') else "shopify_session"
                    packing_list_path = self.current_packing_list if hasattr(self, 'current_packing_list') else "Unknown"
                    summary_output_dir = self.current_work_dir
                else:
                    # Excel session - use session_manager data
                    session_id = self.session_manager.session_id
                    packing_list_path = self.session_manager.packing_list_path
                    summary_output_dir = output_dir

                # Record session completion in statistics
                try:
                    if start_time:  # Only record if we have start_time
                        self.stats_manager.record_session_completion(
                            client_id=self.current_client_id,
                            session_id=session_id,
                            start_time=start_time,
                            end_time=end_time,
                            orders_completed=completed_orders,
                            items_packed=items_packed
                        )
                        logger.info(f"Recorded session completion: {completed_orders} orders, {items_packed} items")
                except Exception as e:
                    logger.error(f"Error recording session metrics to stats: {e}", exc_info=True)

                # Phase 1.3: ALWAYS save session summary for History
                try:
                    summary_path = os.path.join(summary_output_dir, "session_summary.json")
                    session_summary = {
                        "version": "1.0",
                        "session_id": session_id,
                        "session_type": "shopify" if is_shopify_session else "excel",
                        "client_id": self.current_client_id,
                        "started_at": start_time.isoformat() if start_time else None,
                        "completed_at": end_time.isoformat(),
                        "duration_seconds": int((end_time - start_time).total_seconds()) if start_time else None,
                        "packing_list_path": packing_list_path,
                        "completed_file_path": output_path,
                        "pc_name": session_info.get('pc_name') if session_info else os.environ.get('COMPUTERNAME', 'Unknown'),
                        "user_name": os.environ.get('USERNAME', 'Unknown'),
                        "total_orders": total_orders,
                        "completed_orders": completed_orders,
                        "in_progress_orders": in_progress_orders,
                        "total_items": total_items,
                        "items_packed": items_packed
                    }

                    with open(summary_path, 'w', encoding='utf-8') as f:
                        json.dump(session_summary, f, indent=2, ensure_ascii=False)

                    logger.info(f"Saved session summary: {completed_orders}/{total_orders} orders, {items_packed}/{total_items} items to {summary_path}")

                    # Update session metadata with completion status
                    if hasattr(self, 'current_session_path') and hasattr(self, 'current_packing_list'):
                        if self.current_session_path and self.current_packing_list:
                            self.session_manager.update_session_metadata(
                                self.current_session_path,
                                self.current_packing_list,
                                'completed'
                            )

                except Exception as e:
                    logger.error(f"CRITICAL: Error saving session summary: {e}", exc_info=True)
                    # Try to save minimal summary
                    try:
                        minimal_summary = {
                            "version": "1.0",
                            "session_id": session_id,
                            "session_type": "shopify" if is_shopify_session else "excel",
                            "client_id": self.current_client_id,
                            "completed_at": datetime.now().isoformat(),
                            "error": str(e)
                        }
                        with open(os.path.join(summary_output_dir, "session_summary.json"), 'w') as f:
                            json.dump(minimal_summary, f, indent=2)
                        logger.warning("Saved minimal session summary due to errors")
                    except Exception as e2:
                        logger.error(f"Could not save even minimal summary: {e2}")

            except Exception as e:
                logger.error(f"CRITICAL: Exception in session completion block: {e}", exc_info=True)

        except Exception as e:
            self.status_label.setText(f"Could not save the report. Error: {e}")
            logger.error(f"Error during end_session: {e}")

        # Cleanup PackerLogic state
        if self.logic:
            self.logic.end_session_cleanup()
            self.logic = None

        # End Excel session if active
        if self.session_manager and self.session_manager.is_active():
            self.session_manager.end_session()

        # Clear Shopify session variables
        if hasattr(self, 'current_work_dir'):
            self.current_work_dir = None
        if hasattr(self, 'current_session_path'):
            self.current_session_path = None
        if hasattr(self, 'current_packing_list'):
            self.current_packing_list = None
        if hasattr(self, 'packing_data'):
            self.packing_data = None

        self.start_session_button.setEnabled(True)
        self.load_shopify_button.setEnabled(True)
        self.restore_session_button.setEnabled(True)
        self.end_session_button.setEnabled(False)
        self.print_button.setEnabled(False)
        self.packer_mode_button.setEnabled(False)
        self.orders_table.setModel(None)
        self.status_label.setText("Session ended. Start a new session to begin.")

        logger.info("Session ended and all variables cleared")

    def load_and_process_file(self, file_path: str):
        """
        Loads, processes, and displays the data from a packing list file.

        This method coordinates the PackerLogic to parse the file, handle column
        mapping if necessary, generate barcodes, and then sets up the main
        orders table.

        Args:
            file_path (str): The path to the Excel file to load.
        """
        try:
            df = self.logic.load_packing_list_from_file(file_path)

            file_columns = list(df.columns)
            mapping = None
            if not all(col in file_columns for col in REQUIRED_COLUMNS):
                dialog = ColumnMappingDialog(REQUIRED_COLUMNS, file_columns, self)
                if not dialog.exec():
                    self.status_label.setText("File loading cancelled.")
                    self.end_session()
                    return
                mapping = dialog.get_mapping()

            session_id = self.session_manager.session_id
            self.status_label.setText(f"Session '{session_id}' started. Processing file...")
            order_count = self.logic.process_data_and_generate_barcodes(mapping)

            self.setup_order_table()

            order_ids = self.order_summary_df['Order_Number'].tolist()
            self.stats_manager.record_new_orders(order_ids)
            self._update_dashboard()

            self.status_label.setText(f"Successfully processed {order_count} orders for session '{session_id}'.")
            self.start_session_button.setEnabled(False)
            self.end_session_button.setEnabled(True)
            self.print_button.setEnabled(True)
            self.packer_mode_button.setEnabled(True)
        except Exception as e:
            self.status_label.setText(f"An unexpected error occurred: {e}")
            self.end_session()

    def setup_order_table(self):
        """
        Generates an aggregated summary and sets up the main orders table.

        This method transforms the detailed, item-level DataFrame from
        PackerLogic into a summarized, per-order view. It then initializes
        the table model and the proxy model for filtering.
        """
        df = self.logic.processed_df
        extra_cols = [col for col in df.columns if col not in REQUIRED_COLUMNS]

        agg_dict = {
            'SKU': 'nunique',
            'Quantity': lambda x: pd.to_numeric(x, errors='coerce').sum()
        }
        for col in extra_cols:
            agg_dict[col] = 'first'

        order_summary = df.groupby('Order_Number').agg(agg_dict).reset_index()
        order_summary.rename(columns={'SKU': 'Total_SKUs', 'Quantity': 'Total_Quantity'}, inplace=True)

        final_cols = ['Order_Number'] + extra_cols + ['Total_SKUs', 'Total_Quantity']
        order_summary = order_summary[final_cols]

        order_summary['Packing Progress'] = "0 / " + order_summary['Total_Quantity'].astype(int).astype(str)
        order_summary['Status'] = 'New'
        order_summary['Completed At'] = ''

        completed_orders = self.logic.session_packing_state.get('completed_orders', [])
        in_progress_orders = self.logic.session_packing_state.get('in_progress', {})

        for index, row in order_summary.iterrows():
            order_number = row['Order_Number']
            total_required = order_summary.at[index, 'Total_Quantity']

            if order_number in completed_orders:
                order_summary.at[index, 'Status'] = 'Completed'
                order_summary.at[index, 'Packing Progress'] = f"{int(total_required)} / {int(total_required)}"
            elif order_number in in_progress_orders:
                order_state = in_progress_orders[order_number]
                total_packed = sum(s['packed'] for s in order_state.values())
                order_summary.at[index, 'Packing Progress'] = f"{total_packed} / {int(total_required)}"
                if total_packed > 0:
                    order_summary.at[index, 'Status'] = 'In Progress'

        self.order_summary_df = order_summary
        self.table_model = OrderTableModel(self.order_summary_df)
        self.proxy_model = CustomFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.set_processed_df(self.logic.processed_df)
        self.orders_table.setModel(self.proxy_model)
        self.search_input.textChanged.connect(self.proxy_model.setFilterFixedString)
        self.orders_table.resizeColumnsToContents()

    def switch_to_packer_mode(self):
        """Switches the view to the Packer Mode widget."""
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_session_view(self):
        """Switches the view back to the main session widget (tabbed interface)."""
        self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        # Phase 1.3: Return to tabbed widget (Session tab will be active)
        self.stacked_widget.setCurrentWidget(self.tab_widget)
        # Ensure Session tab is active
        self.tab_widget.setCurrentIndex(0)

    def open_print_dialog(self):
        """Opens the dialog for printing order barcodes."""
        if not self.logic.orders_data:
            self.status_label.setText("No data to print.")
            return
        dialog = PrintDialog(self.logic.orders_data, self)
        dialog.exec()

    def on_scanner_input(self, text: str):
        """
        Handles input from the barcode scanner in Packer Mode.

        This is the central callback for all barcode scans. It determines if
        the scan is for an order or a product SKU and routes the logic accordingly.

        Args:
            text (str): The decoded text from the barcode scanner.
        """
        self.packer_mode_widget.update_raw_scan_display(text)
        self.packer_mode_widget.show_notification("", "black")

        if self.logic.current_order_number is None:
            order_number_from_scan = self.logic.barcode_to_order_number.get(text)
            if not order_number_from_scan:
                self.packer_mode_widget.show_notification("ORDER NOT FOUND", "red")
                self.flash_border("red")
                return

            if order_number_from_scan in self.logic.session_packing_state.get('completed_orders', []):
                self.packer_mode_widget.show_notification(f"ORDER {order_number_from_scan} ALREADY COMPLETED", "orange")
                self.flash_border("orange")
                return

            items, status = self.logic.start_order_packing(text)
            if status == "ORDER_LOADED":
                self.packer_mode_widget.add_order_to_history(order_number_from_scan)
                self.packer_mode_widget.display_order(items, self.logic.current_order_state)
                self.update_order_status(order_number_from_scan, "In Progress")
            else:
                self.packer_mode_widget.show_notification("ORDER NOT FOUND", "red")
                self.flash_border("red")
        else:
            result, status = self.logic.process_sku_scan(text)
            if status == "SKU_OK":
                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.flash_border("green")
            elif status == "SKU_NOT_FOUND":
                self.packer_mode_widget.show_notification("INCORRECT ITEM!", "red")
                self.flash_border("red")
            elif status == "ORDER_COMPLETE":
                current_order_num = self.logic.current_order_number
                self.stats_manager.record_order_completion(current_order_num)
                self._update_dashboard()

                self.packer_mode_widget.update_item_row(result["row"], result["packed"], result["is_complete"])
                self.packer_mode_widget.show_notification(f"ORDER {current_order_num} COMPLETE!", "green")
                self.flash_border("green")
                self.update_order_status(current_order_num, "Completed")
                self.packer_mode_widget.scanner_input.setEnabled(False)
                self.logic.clear_current_order()
                QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)

    def _process_shopify_packing_data(self, packing_data: dict) -> int:
        """
        Process Shopify packing list data and generate barcodes.

        This method converts the JSON packing list format from Shopify Tool
        into the DataFrame format expected by PackerLogic, then generates barcodes.

        Args:
            packing_data: Dictionary containing orders data with structure:
                {
                    'orders': [
                        {
                            'order_number': str,
                            'items': [{'sku': str, 'quantity': int, 'product_name': str}],
                            'courier': str,
                            ...other fields...
                        }
                    ],
                    'total_orders': int,
                    'total_items': int,
                    ...
                }

        Returns:
            int: Number of orders processed

        Raises:
            ValueError: If packing data is invalid or missing required fields
            RuntimeError: If barcode generation fails
        """
        import pandas as pd

        logger.info("Converting Shopify packing data to DataFrame")

        # Extract orders list
        orders_list = packing_data.get('orders', [])
        if not orders_list:
            error_msg = "No orders found in packing data"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Convert to DataFrame (packing list format)
        # Each order may have multiple items, need to flatten
        rows = []

        for order in orders_list:
            order_number = order.get('order_number', 'UNKNOWN')
            courier = order.get('courier', 'Unknown')
            items = order.get('items', [])

            for item in items:
                row = {
                    'Order_Number': order_number,
                    'SKU': item.get('sku', ''),
                    'Product_Name': item.get('product_name', ''),
                    'Quantity': str(item.get('quantity', 1)),  # Convert to string for consistency
                    'Courier': courier
                }

                # Add any extra fields from order
                for key, value in order.items():
                    if key not in ['order_number', 'courier', 'items']:
                        # Capitalize key to match packing list style
                        formatted_key = key.replace('_', ' ').title().replace(' ', '_')
                        row[formatted_key] = str(value)

                rows.append(row)

        # Create DataFrame
        df = pd.DataFrame(rows)

        if df.empty:
            logger.warning("No order items to process")
            return 0

        # Validate required columns
        from packer_logic import REQUIRED_COLUMNS
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in packing data: {missing_cols}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Store as packing_list_df and processed_df in logic
        self.logic.packing_list_df = df
        self.logic.processed_df = df.copy()

        logger.info(f"Converted {len(df)} items from {len(orders_list)} orders to DataFrame")

        # Generate barcodes
        try:
            order_count = self.logic.process_data_and_generate_barcodes(column_mapping=None)
            logger.info(f"Successfully generated barcodes for {order_count} orders")
            logger.info(f"Barcodes saved to: {self.logic.barcode_dir}")

            return order_count

        except Exception as e:
            error_msg = f"Error generating barcodes from Shopify data: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)

    def _on_item_packed(self, order_number: str, packed_count: int, required_count: int):
        """
        Slot to handle real-time progress updates from the logic layer.

        This method is connected to the `item_packed` signal from PackerLogic.
        It updates the 'Packing Progress' cell in the main orders table.

        Args:
            order_number (str): The order number that was updated.
            packed_count (int): The new total of items packed for the order.
            required_count (int): The total items required for the order.
        """
        try:
            row_index = self.order_summary_df.index[self.order_summary_df['Order_Number'] == order_number][0]
            progress_col_index = self.order_summary_df.columns.get_loc('Packing Progress')

            new_progress = f"{packed_count} / {required_count}"
            self.order_summary_df.iloc[row_index, progress_col_index] = new_progress

            self.table_model.dataChanged.emit(
                self.table_model.index(row_index, progress_col_index),
                self.table_model.index(row_index, progress_col_index)
            )
        except (IndexError, KeyError):
            pass

    def update_order_status(self, order_number: str, status: str):
        """
        Updates the status and related fields of an order in the main table.

        Args:
            order_number (str): The order number to update.
            status (str): The new status ('In Progress' or 'Completed').
        """
        try:
            row_index = self.order_summary_df.index[self.order_summary_df['Order_Number'] == order_number][0]

            status_col_index = self.order_summary_df.columns.get_loc('Status')
            self.order_summary_df.iloc[row_index, status_col_index] = status

            progress_col_index = self.order_summary_df.columns.get_loc('Packing Progress')
            if status == 'Completed':
                total_quantity = self.order_summary_df.iloc[row_index]['Total_Quantity']
                self.order_summary_df.iloc[row_index, progress_col_index] = f"{int(total_quantity)} / {int(total_quantity)}"
                completed_col_index = self.order_summary_df.columns.get_loc('Completed At')
                self.order_summary_df.iloc[row_index, completed_col_index] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif status == 'In Progress':
                if order_number in self.logic.session_packing_state:
                    order_state = self.logic.session_packing_state[order_number]
                    total_packed = sum(s['packed'] for s in order_state.values())
                    total_required = sum(s['required'] for s in order_state.values())
                    self.order_summary_df.iloc[row_index, progress_col_index] = f"{total_packed} / {total_required}"

            self.table_model.dataChanged.emit(
                self.table_model.index(row_index, 0),
                self.table_model.index(row_index, self.table_model.columnCount() - 1)
            )
        except (IndexError, KeyError):
            logger.warning(f"Could not update status for order number {order_number}. Not found in summary table.")

    def open_restore_session_dialog(self):
        """Open dialog to select and restore an incomplete session."""
        if not self.current_client_id:
            logger.warning("Attempted to restore session without selecting client")
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client first!"
            )
            return

        # Check if session already active
        if self.session_manager and self.session_manager.is_active():
            logger.warning("Attempted to restore session while one is already active")
            QMessageBox.warning(
                self,
                "Session Active",
                "A session is already active. Please end it first."
            )
            return

        logger.info(f"Opening restore session dialog for client {self.current_client_id}")

        dialog = RestoreSessionDialog(
            self.current_client_id,
            self.profile_manager,
            self.lock_manager,
            self
        )

        if dialog.exec() == QDialog.Accepted:
            selected_session = dialog.get_selected_session()
            if selected_session:
                logger.info(f"User selected session to restore: {selected_session}")

                # Get session info to find packing list path
                session_info_path = selected_session / "session_info.json"
                try:
                    import json
                    with open(session_info_path, 'r', encoding='utf-8') as f:
                        session_info = json.load(f)

                    packing_list_path = session_info.get('packing_list_path')
                    if packing_list_path:
                        # Start session with restore_dir
                        self.start_session(file_path=packing_list_path, restore_dir=str(selected_session))
                    else:
                        QMessageBox.warning(
                            self,
                            "Error",
                            "Session info does not contain packing list path."
                        )
                except Exception as e:
                    logger.error(f"Error reading session info: {e}", exc_info=True)
                    QMessageBox.critical(
                        self,
                        "Error",
                        f"Failed to read session information:\n\n{e}"
                    )

    def open_shopify_session(self):
        """
        Open Shopify session and select packing list to work on.

        Phase 1.8 Enhanced workflow:
        1. Use SessionSelectorDialog to browse Shopify sessions
        2. Automatically scan packing_lists/ folder
        3. User can select specific packing list or load entire session
        4. Create work directory: packing/{list_name}/ for selected lists
        """
        logger.info("Opening Shopify session selector")

        # Check if client is selected
        if not self.current_client_id:
            logger.warning("Attempted to open Shopify session without selecting client")
            self.client_combo.setStyleSheet("border: 2px solid red;")
            QMessageBox.warning(
                self,
                "No Client Selected",
                "Please select a client before opening a Shopify session!"
            )
            QTimer.singleShot(2000, lambda: self.client_combo.setStyleSheet(""))
            return

        # Check if session already active
        if self.session_manager and self.session_manager.is_active():
            logger.warning("Attempted to open Shopify session while one is already active")
            QMessageBox.warning(
                self,
                "Session Active",
                "A session is already active. Please end it first."
            )
            return

        # Step 1: Use SessionSelectorDialog to select session and packing list
        selector_dialog = SessionSelectorDialog(self.profile_manager, self)

        if not selector_dialog.exec():
            logger.info("Shopify session selection cancelled")
            return

        session_path = selector_dialog.get_selected_session()
        packing_list_path = selector_dialog.get_selected_packing_list()

        if not session_path:
            logger.warning("No session selected")
            return

        logger.info(f"Selected Shopify session: {session_path}")

        # Step 2: Determine loading mode
        if packing_list_path:
            # User selected a specific packing list
            selected_name = packing_list_path.stem
            logger.info(f"Selected packing list: {selected_name}")
            load_mode = "packing_list"
        else:
            # User wants to load entire session (analysis_data.json)
            logger.info("Loading entire session (analysis_data.json)")
            selected_name = "full_session"
            load_mode = "full_session"

        # Step 3: Create work directory structure
        try:
            # Create SessionManager for this client (not initialized yet)
            if not self.session_manager:
                self.session_manager = SessionManager(
                    client_id=self.current_client_id,
                    profile_manager=self.profile_manager,
                    lock_manager=self.lock_manager
                )

            # Create work directory: packing/{list_name}/ for specific lists
            if load_mode == "packing_list":
                work_dir = session_path / "packing" / selected_name
            else:
                # For full session, use legacy structure
                work_dir = session_path / "packing_full_session"

            work_dir.mkdir(parents=True, exist_ok=True)

            # Create barcodes subdirectory
            barcodes_dir = work_dir / "barcodes"
            barcodes_dir.mkdir(parents=True, exist_ok=True)

            # Store current session info
            self.current_session_path = str(session_path)
            self.current_packing_list = selected_name
            self.current_work_dir = str(work_dir)

            logger.info(f"Work directory created: {work_dir}")
            logger.info(f"Barcodes directory: {barcodes_dir}")

            # Step 4: Create PackerLogic instance
            self.logic = PackerLogic(
                client_id=self.current_client_id,
                profile_manager=self.profile_manager,
                barcode_dir=str(barcodes_dir)
            )

            # Connect signals
            self.logic.item_packed.connect(self._on_item_packed)

            # Step 5: Load data based on mode
            if load_mode == "packing_list":
                # Load specific packing list JSON
                logger.info(f"Loading packing list from: {packing_list_path}")
                order_count, list_name = self.logic.load_packing_list_json(packing_list_path)

                logger.info(f"Loaded packing list '{list_name}': {order_count} orders")
            else:
                # Load entire session (analysis_data.json)
                logger.info(f"Loading full session from: {session_path}")
                order_count, analyzed_at = self.logic.load_from_shopify_analysis(session_path)

                logger.info(f"Loaded full session: {order_count} orders (analyzed at {analyzed_at})")

            # Update session metadata with packing progress
            if hasattr(self.session_manager, 'update_session_metadata'):
                try:
                    self.session_manager.update_session_metadata(
                        self.current_session_path,
                        self.current_packing_list,
                        'in_progress'
                    )
                except Exception as e:
                    logger.warning(f"Could not update session metadata: {e}")

            # Setup order table
            self.setup_order_table()

            # Update UI with loaded data
            self.status_label.setText(
                f"Loaded: {session_path.name} / {selected_name}\n"
                f"Orders: {order_count}\n"
                f"Barcodes generated successfully"
            )

            # Enable packing UI
            self.enable_packing_mode()

            QMessageBox.information(
                self,
                "Session Loaded",
                f"Session: {session_path.name}\n"
                f"{'Packing List' if load_mode == 'packing_list' else 'Mode'}: {selected_name}\n"
                f"Orders: {order_count}\n\n"
                f"Work directory:\n{work_dir}"
            )

        except FileNotFoundError as e:
            logger.error(f"Packing list file not found: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "File Not Found",
                f"Packing list file not found:\n{str(e)}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in packing list: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Invalid Data",
                f"Packing list contains invalid JSON:\n{str(e)}"
            )
        except KeyError as e:
            logger.error(f"Missing required key in packing list: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Invalid Format",
                f"Packing list is missing required data:\n{str(e)}"
            )
        except ValueError as e:
            logger.error(f"Invalid packing data: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Invalid Data",
                f"Packing data validation failed:\n{str(e)}"
            )
            # Cleanup on failure
            if self.logic:
                self.logic = None
        except RuntimeError as e:
            logger.error(f"Barcode generation failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Generation Failed",
                f"Failed to generate barcodes:\n{str(e)}"
            )
            # Cleanup on failure
            if self.logic:
                self.logic = None
        except Exception as e:
            logger.error(f"Failed to load packing list: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load packing list:\n{str(e)}"
            )

            # Cleanup on failure
            if self.session_manager:
                self.session_manager = None
            self.logic = None

    def enable_packing_mode(self):
        """
        Enable packing UI after session data is loaded.

        This method:
        - Disables session start buttons
        - Enables packing operation buttons
        - Updates status message
        - Prepares UI for packing operations
        """
        logger.info("Enabling packing mode UI")

        # Disable session start buttons
        self.start_session_button.setEnabled(False)
        self.load_shopify_button.setEnabled(False)
        self.restore_session_button.setEnabled(False)

        # Enable packing operation buttons
        self.end_session_button.setEnabled(True)
        self.print_button.setEnabled(True)
        self.packer_mode_button.setEnabled(True)

        # Update status
        self.status_label.setText(
            f"Ready to pack: {self.current_packing_list}\n"
            f"Orders: {self.packing_data.get('total_orders', 0)}"
        )

        logger.info("Packing mode UI enabled successfully")

    def open_session_monitor(self):
        """Open the session monitor window."""
        logger.info("Opening session monitor")

        monitor_dialog = QDialog(self)
        monitor_dialog.setWindowTitle("Active Sessions Monitor")
        monitor_dialog.setMinimumSize(800, 400)

        layout = QVBoxLayout(monitor_dialog)

        monitor_widget = SessionMonitorWidget(self.lock_manager)
        layout.addWidget(monitor_widget)

        close_button = QPushButton("Close")
        close_button.clicked.connect(monitor_dialog.close)
        layout.addWidget(close_button)

        monitor_dialog.exec()

    def _handle_session_locked_error(self, error: SessionLockedError):
        """
        Handle when a session is actively locked by another process.

        Shows a dialog informing the user that the session is currently in use.

        Args:
            error: SessionLockedError with lock information
        """
        lock_info = error.lock_info
        if not lock_info:
            QMessageBox.warning(
                self,
                "Session Locked",
                "This session is currently locked by another process.\n\n"
                "Please wait or choose a different session."
            )
            return

        locked_by = lock_info.get('locked_by', 'Unknown PC')
        user_name = lock_info.get('user_name', 'Unknown user')
        lock_time = lock_info.get('lock_time', 'Unknown time')

        # Format time nicely
        try:
            from datetime import datetime
            lock_dt = datetime.fromisoformat(lock_time)
            lock_time_formatted = lock_dt.strftime('%d.%m.%Y %H:%M')
        except:
            lock_time_formatted = lock_time

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Session Already in Use")
        msg.setText("This session is currently active on another computer.")
        msg.setInformativeText(
            f"<b>User:</b> {user_name}<br>"
            f"<b>Computer:</b> {locked_by}<br>"
            f"<b>Started:</b> {lock_time_formatted}<br><br>"
            "Please wait for the user to finish, or choose another session."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()

    def _handle_stale_lock_error(self, error: StaleLockError, file_path: str, restore_dir: str):
        """
        Handle when a session has a stale lock (possible crash).

        Shows a dialog allowing the user to force-release the lock and open the session.

        Args:
            error: StaleLockError with lock information
            file_path: Path to the packing list file
            restore_dir: Directory of the session to restore
        """
        lock_info = error.lock_info
        if not lock_info:
            QMessageBox.warning(self, "Stale Lock", "Session has an invalid lock file.")
            return

        locked_by = lock_info.get('locked_by', 'Unknown PC')
        user_name = lock_info.get('user_name', 'Unknown user')
        heartbeat = lock_info.get('heartbeat', 'Unknown')
        stale_minutes = error.stale_minutes

        # Format time nicely
        try:
            from datetime import datetime
            heartbeat_dt = datetime.fromisoformat(heartbeat)
            heartbeat_formatted = heartbeat_dt.strftime('%d.%m.%Y %H:%M')
        except:
            heartbeat_formatted = heartbeat

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Stale Session Lock Detected")
        msg.setText("This session has a stale lock - the application may have crashed.")
        msg.setInformativeText(
            f"<b>Original user:</b> {user_name}<br>"
            f"<b>Computer:</b> {locked_by}<br>"
            f"<b>Last heartbeat:</b> {heartbeat_formatted}<br>"
            f"<b>No response for:</b> {stale_minutes} minutes<br><br>"
            "The application may have crashed on that PC.<br><br>"
            "<b>Do you want to force-release the lock and open this session?</b>"
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.Yes)

        reply = msg.exec()

        if reply == QMessageBox.Yes:
            # Force release the lock
            logger.info(f"User chose to force-release stale lock for session {restore_dir}")
            try:
                success = self.lock_manager.force_release_lock(Path(restore_dir))
                if success:
                    logger.info("Stale lock force-released successfully")
                    # Retry opening the session
                    QTimer.singleShot(100, lambda: self.start_session(file_path=file_path, restore_dir=restore_dir))
                else:
                    logger.error("Failed to force-release lock")
                    QMessageBox.critical(
                        self,
                        "Error",
                        "Failed to release the lock. Please try again or contact support."
                    )
            except Exception as e:
                logger.error(f"Error force-releasing lock: {e}", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to release lock:\n\n{e}"
                )
        else:
            logger.info("User cancelled force-release of stale lock")
            self.status_label.setText("Session opening cancelled.")


# ==============================================================================
# NEW CLIENT DIALOG
# ==============================================================================

class NewClientDialog(QDialog):
    """Dialog for creating a new client profile."""

    def __init__(self, profile_manager: ProfileManager, parent=None):
        """
        Initialize the new client dialog.

        Args:
            profile_manager: ProfileManager instance for validation and creation
            parent: Parent widget
        """
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.client_id = None
        self.client_name = None

        self.setWindowTitle("Create New Client Profile")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        # Instructions
        instructions = QLabel(
            "Create a new client profile. The client ID should be short (1-10 characters) "
            "and will be used to organize sessions and settings."
        )
        instructions.setWordWrap(True)
        layout.addRow(instructions)

        # Client ID input
        self.client_id_input = QLineEdit()
        self.client_id_input.setPlaceholderText("e.g., M, R, CLIENT_A")
        self.client_id_input.setMaxLength(10)
        self.client_id_input.textChanged.connect(self.on_id_changed)
        layout.addRow("Client ID (short):", self.client_id_input)

        # Validation label
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("color: red;")
        self.validation_label.setWordWrap(True)
        layout.addRow("", self.validation_label)

        # Client name input
        self.client_name_input = QLineEdit()
        self.client_name_input.setPlaceholderText("e.g., M Cosmetics, R Fashion")
        layout.addRow("Client Full Name:", self.client_name_input)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok_button = button_box.button(QDialogButtonBox.Ok)
        self.ok_button.setEnabled(False)
        button_box.accepted.connect(self.accept_dialog)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def on_id_changed(self, text: str):
        """
        Validate client ID as user types.

        Args:
            text: Current text in client ID input
        """
        if not text:
            self.validation_label.setText("")
            self.ok_button.setEnabled(False)
            return

        # Convert to uppercase
        text_upper = text.upper()
        if text != text_upper:
            # Update to uppercase
            self.client_id_input.blockSignals(True)
            cursor_pos = self.client_id_input.cursorPosition()
            self.client_id_input.setText(text_upper)
            self.client_id_input.setCursorPosition(cursor_pos)
            self.client_id_input.blockSignals(False)
            text = text_upper

        # Validate
        is_valid, error_msg = self.profile_manager.validate_client_id(text)

        if not is_valid:
            self.validation_label.setText(f"⚠ {error_msg}")
            self.validation_label.setStyleSheet("color: red;")
            self.ok_button.setEnabled(False)
            return

        # Check if already exists
        if self.profile_manager.client_exists(text):
            self.validation_label.setText(f"⚠ Client '{text}' already exists!")
            self.validation_label.setStyleSheet("color: red;")
            self.ok_button.setEnabled(False)
            return

        # Valid
        self.validation_label.setText("✓ Valid client ID")
        self.validation_label.setStyleSheet("color: green;")
        self.ok_button.setEnabled(bool(self.client_name_input.text().strip()))

    def accept_dialog(self):
        """Handle OK button click."""
        client_id = self.client_id_input.text().strip().upper()
        client_name = self.client_name_input.text().strip()

        if not client_name:
            QMessageBox.warning(self, "Invalid Input", "Please enter a client name.")
            return

        logger.info(f"Creating new client: {client_id} - {client_name}")

        try:
            success = self.profile_manager.create_client_profile(client_id, client_name)

            if success:
                self.client_id = client_id
                self.client_name = client_name
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Client '{client_id}' already exists!"
                )

        except ValidationError as e:
            logger.error(f"Validation error creating client: {e}")
            QMessageBox.warning(self, "Validation Error", str(e))

        except Exception as e:
            logger.error(f"Error creating client: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to create client profile:\n\n{e}"
            )


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def restore_session(window: MainWindow):
    """
    Checks for and offers to restore an incomplete session on startup.

    Args:
        window (MainWindow): The main application window instance.
    """
    latest_dir = find_latest_session_dir()
    if not latest_dir:
        return

    session_info_path = os.path.join(latest_dir, "session_info.json")
    state_path = os.path.join(latest_dir, "packing_state.json")

    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText("An incomplete session was found.")
    msg_box.setInformativeText(f"Would you like to restore session '{os.path.basename(latest_dir)}'?")
    msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg_box.setDefaultButton(QMessageBox.Yes)
    reply = msg_box.exec()

    if reply == QMessageBox.Yes:
        try:
            with open(session_info_path, 'r') as f:
                session_info = json.load(f)
            packing_list_path = session_info.get('packing_list_path')
            if packing_list_path and os.path.exists(packing_list_path):
                window.start_session(file_path=packing_list_path, restore_dir=latest_dir)
            else:
                QMessageBox.critical(window, "Error", "Could not restore session. The original packing list file was not found.")
        except Exception as e:
            QMessageBox.critical(window, "Error", f"An error occurred during session restoration: {e}")
    else:
        try:
            if os.path.exists(session_info_path):
                os.rename(session_info_path, session_info_path + ".ignored")
            if os.path.exists(state_path):
                os.rename(state_path, state_path + ".ignored")
        except OSError as e:
            QMessageBox.warning(window, "Cleanup Warning", f"Could not ignore all session files: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Load and apply stylesheet
    try:
        with open("src/styles.qss", "r") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("Warning: stylesheet 'src/styles.qss' not found.")

    window = MainWindow()

    # Check for abandoned sessions before showing the main window
    restore_session(window)

    window.show()
    sys.exit(app.exec())
