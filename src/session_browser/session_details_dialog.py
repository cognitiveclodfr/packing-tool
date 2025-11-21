"""Session Details Dialog - Detailed view of session with orders, items, metrics"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt

from .overview_tab import OverviewTab
from .orders_tab import OrdersTab
from .metrics_tab import MetricsTab

from pathlib import Path
import json
from logger import get_logger

logger = get_logger(__name__)


class SessionDetailsDialog(QDialog):
    """Dialog showing detailed session information"""

    def __init__(
        self,
        session_data: dict,
        session_history_manager,
        parent=None
    ):
        """
        Initialize Session Details Dialog.

        Args:
            session_data: Dict with session info
                For completed: {client_id, session_id, work_dir (optional)}
                For active: {client_id, session_id, work_dir, lock_info (optional)}
            session_history_manager: SessionHistoryManager instance
            parent: Parent widget
        """
        super().__init__(parent)

        self.session_data = session_data
        self.session_history_manager = session_history_manager
        self.details = None

        self._load_session_details()
        self._init_ui()

        self.setWindowTitle(f"Session Details: {session_data['session_id']}")
        self.resize(900, 700)

    def _load_session_details(self):
        """Load session details from files."""

        client_id = self.session_data['client_id']
        session_id = self.session_data['session_id']
        work_dir = self.session_data.get('work_dir')

        # If work_dir specified explicitly, use it directly
        if work_dir:
            work_dir_path = Path(work_dir)

            # Load packing_state.json for basic info
            state_file = work_dir_path / "packing_state.json"
            packing_state = {}
            if state_file.exists():
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        packing_state = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load packing_state.json: {e}")

            # Load session_summary.json for Phase 2b data
            summary_file = work_dir_path / "session_summary.json"
            session_summary = {}
            if summary_file.exists():
                try:
                    with open(summary_file, 'r', encoding='utf-8') as f:
                        session_summary = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load session_summary.json: {e}")

            # Load session_info.json for metadata
            info_file = work_dir_path / "session_info.json"
            session_info = {}
            if info_file.exists():
                try:
                    with open(info_file, 'r', encoding='utf-8') as f:
                        session_info = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load session_info.json: {e}")

            # Build record from available data
            # Prefer session_summary, fallback to packing_state
            if session_summary:
                record = {
                    'session_id': session_summary.get('session_id', session_id),
                    'client_id': session_summary.get('client_id', client_id),
                    'packing_list_path': session_summary.get('packing_list_path', ''),
                    'packing_list_name': session_summary.get('packing_list_name', ''),
                    'worker_id': session_summary.get('worker_id', ''),
                    'worker_name': session_summary.get('worker_name', ''),
                    'pc_name': session_summary.get('pc_name', ''),
                    'start_time': session_summary.get('started_at', ''),
                    'end_time': session_summary.get('completed_at', ''),
                    'duration_seconds': session_summary.get('duration_seconds', 0),
                    'total_orders': session_summary.get('total_orders', 0),
                    'completed_orders': session_summary.get('completed_orders', 0),
                    'in_progress_orders': 0,
                    'total_items_packed': session_summary.get('total_items', 0)
                }
            elif session_info:
                record = {
                    'session_id': session_info.get('session_id', session_id),
                    'client_id': session_info.get('client_id', client_id),
                    'packing_list_path': session_info.get('packing_list_path', ''),
                    'packing_list_name': session_info.get('packing_list_name', ''),
                    'worker_id': session_info.get('worker_id', ''),
                    'worker_name': session_info.get('worker_name', ''),
                    'pc_name': session_info.get('pc_name', ''),
                    'start_time': session_info.get('started_at', ''),
                    'end_time': None,
                    'duration_seconds': 0,
                    'total_orders': packing_state.get('total_orders', 0),
                    'completed_orders': len(packing_state.get('completed', [])),
                    'in_progress_orders': len(packing_state.get('in_progress', [])),
                    'total_items_packed': sum(o.get('items_count', 0) for o in packing_state.get('completed', []))
                }
            else:
                raise ValueError(f"No valid session data found in work_dir: {work_dir}")

            self.details = {
                'record': record,
                'packing_state': packing_state,
                'session_info': session_info,
                'session_summary': session_summary
            }

            logger.info(f"Loaded session details from work_dir: {work_dir}")
            return

        # If no work_dir, try to load using SessionHistoryManager
        self.details = self.session_history_manager.get_session_details(
            client_id=client_id,
            session_id=session_id
        )

        if not self.details:
            raise ValueError(f"Session not found: {session_id}")

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Overview tab
        self.overview_tab = OverviewTab(self.details, parent=self)
        self.tab_widget.addTab(self.overview_tab, "Overview")

        # Orders tab (Phase 2b data)
        self.orders_tab = OrdersTab(self.details, parent=self)
        self.tab_widget.addTab(self.orders_tab, "Orders")

        # Metrics tab
        self.metrics_tab = MetricsTab(self.details, parent=self)
        self.tab_widget.addTab(self.metrics_tab, "Metrics")

        layout.addWidget(self.tab_widget)

        # Bottom buttons
        btn_layout = QHBoxLayout()

        export_excel_btn = QPushButton("Export Excel")
        export_excel_btn.clicked.connect(self._export_excel)
        btn_layout.addWidget(export_excel_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _export_excel(self):
        """Export session details to Excel."""

        # Get orders data
        orders = self._get_orders_for_export()

        if not orders:
            QMessageBox.warning(
                self,
                "No Data",
                "No orders data available for export."
            )
            return

        # Ask for save location
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Session Details",
            f"session_{self.session_data['session_id']}.xlsx",
            "Excel Files (*.xlsx)"
        )

        if not filepath:
            return

        try:
            import pandas as pd

            # Convert orders to flat structure
            rows = []
            for order in orders:
                for item in order.get('items', []):
                    rows.append({
                        'Order Number': order['order_number'],
                        'Order Started': order.get('started_at', ''),
                        'Order Completed': order.get('completed_at', ''),
                        'Order Duration (s)': order.get('duration_seconds', 0),
                        'SKU': item['sku'],
                        'Quantity': item['quantity'],
                        'Scanned At': item.get('scanned_at', ''),
                        'Time from Start (s)': item.get('time_from_order_start_seconds', 0)
                    })

            df = pd.DataFrame(rows)

            # Write to Excel
            df.to_excel(filepath, index=False, sheet_name="Session Details")

            QMessageBox.information(
                self,
                "Success",
                f"Session details exported to:\n{filepath}"
            )

        except Exception as e:
            logger.error(f"Failed to export: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export session details:\n{str(e)}"
            )

    def _get_orders_for_export(self) -> list:
        """Get orders array for export."""

        # Try session_summary first (Phase 2b data)
        if 'session_summary' in self.details:
            orders = self.details['session_summary'].get('orders', [])
            if orders:
                return orders

        # Try packing_state
        if 'packing_state' in self.details:
            # Build from completed orders (less detailed)
            completed = self.details['packing_state'].get('completed', [])
            return completed

        return []
