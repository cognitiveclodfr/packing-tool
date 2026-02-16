"""Orders Tab - Hierarchical view of orders and items with timing data"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLabel, QLineEdit
)
from PySide6.QtCore import Qt

from datetime import datetime
from logger import get_logger

logger = get_logger(__name__)


class OrdersTab(QWidget):
    """Tab showing orders tree with items and timing"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Orders Tab.

        Args:
            details: Dict with session details (must include session_summary for Phase 2b data)
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self.all_orders = []
        self.filtered_orders = []

        self._load_orders()
        self._init_ui()
        self._populate_tree()

    def _load_orders(self):
        """Load orders from session data."""

        # Try session_summary first (Phase 2b data with full timing)
        if 'session_summary' in self.details:
            self.all_orders = self.details['session_summary'].get('orders', [])
            logger.debug(f"Loaded {len(self.all_orders)} orders from session_summary")
            return

        # Fallback: Try packing_state (less detailed)
        if 'packing_state' in self.details:
            completed = self.details['packing_state'].get('completed', [])

            # Convert to orders format (minimal data)
            self.all_orders = [
                {
                    'order_number': order.get('order_number', 'Unknown'),
                    'completed_at': order.get('completed_at', ''),
                    'items_count': order.get('items_count', 0),
                    'duration_seconds': order.get('duration_seconds', 0),
                    'items': []  # No item-level data
                }
                for order in completed
            ]

    def _init_ui(self):
        """Initialize UI."""
        layout = QVBoxLayout(self)

        # Top bar: Search + Actions
        top_bar = QHBoxLayout()

        top_bar.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by order number...")
        self.search_input.textChanged.connect(self._on_search)
        top_bar.addWidget(self.search_input)

        expand_btn = QPushButton("Expand All")
        expand_btn.clicked.connect(lambda: self.tree.expandAll())
        top_bar.addWidget(expand_btn)

        collapse_btn = QPushButton("Collapse All")
        collapse_btn.clicked.connect(lambda: self.tree.collapseAll())
        top_bar.addWidget(collapse_btn)

        layout.addLayout(top_bar)

        # Info label
        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([
            "Order / Item",
            "Duration",
            "Count",
            "Started / Scanned",
            "Completed"
        ])
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 200)
        layout.addWidget(self.tree)

    def _populate_tree(self):
        """Populate tree with orders."""
        self.tree.clear()

        # Apply filter
        search_term = self.search_input.text().strip().lower()

        if search_term:
            self.filtered_orders = [
                o for o in self.all_orders
                if search_term in o.get('order_number', '').lower()
            ]
        else:
            self.filtered_orders = self.all_orders

        # Update info label
        if not self.all_orders:
            self.info_label.setText("ℹ️ No order data available for this session.")
            self.info_label.setStyleSheet("color: #888888; font-weight: bold;")
            return
        else:
            self.info_label.setText(f"Showing {len(self.filtered_orders)} of {len(self.all_orders)} orders")
            self.info_label.setStyleSheet("")

        # Add orders to tree
        for order in self.filtered_orders:
            # Top level: Order
            order_item = QTreeWidgetItem(self.tree)
            order_item.setText(0, order.get('order_number', 'Unknown'))

            # Duration
            duration = order.get('duration_seconds', 0)
            if duration:
                order_item.setText(1, f"{duration}s ({duration/60:.1f}m)")
            else:
                order_item.setText(1, "N/A")

            # Items count
            items_count = order.get('items_count', len(order.get('items', [])))
            order_item.setText(2, f"{items_count} items")

            # Started
            started = self._format_timestamp(order.get('started_at', ''))
            order_item.setText(3, started)

            # Completed
            completed = self._format_timestamp(order.get('completed_at', ''))
            order_item.setText(4, completed)

            # Make order bold
            font = order_item.font(0)
            font.setBold(True)
            for col in range(5):
                order_item.setFont(col, font)

            # Children: Items
            items = order.get('items', [])
            if items:
                for item in items:
                    item_node = QTreeWidgetItem(order_item)

                    # SKU
                    sku = item.get('sku', 'Unknown')
                    item_node.setText(0, f"  → {sku}")

                    # Time from order start
                    time_from_start = item.get('time_from_order_start_seconds', 0)
                    if time_from_start:
                        item_node.setText(1, f"+{time_from_start}s")

                    # Quantity
                    qty = item.get('quantity', 1)
                    item_node.setText(2, f"×{qty}")

                    # Scanned at
                    scanned = self._format_timestamp(item.get('scanned_at', ''))
                    item_node.setText(3, scanned)
            else:
                # No item-level data
                no_data_node = QTreeWidgetItem(order_item)
                no_data_node.setText(0, "  (Item details not available)")
                no_data_node.setForeground(0, Qt.GlobalColor.gray)

        # Auto-expand if few orders
        if len(self.filtered_orders) <= 10:
            self.tree.expandAll()

    def _on_search(self):
        """Handle search text change."""
        self._populate_tree()

    def _format_timestamp(self, ts: str) -> str:
        """Format ISO timestamp for display."""
        if not ts:
            return "N/A"

        try:
            # Handle both ISO formats with and without timezone
            ts_clean = ts.replace('Z', '+00:00')
            dt = datetime.fromisoformat(ts_clean)
            return dt.strftime("%H:%M:%S")
        except Exception:
            return ts
