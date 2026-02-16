"""Metrics Tab - Performance statistics and rates"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel,
    QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt


class MetricsTab(QWidget):
    """Tab showing session performance metrics"""

    def __init__(self, details: dict, parent=None):
        """
        Initialize Metrics Tab.

        Args:
            details: Dict with session details (must include session_summary.metrics)
            parent: Parent widget
        """
        super().__init__(parent)

        self.details = details
        self._init_ui()

    def _init_ui(self):
        """Initialize UI."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        scroll.setWidget(scroll_widget)
        outer_layout.addWidget(scroll)

        # Check if metrics available
        metrics = self._get_metrics()

        if not metrics:
            no_data_label = QLabel(
                "ℹ️ Metrics not available\n\n"
                "Timing metrics are not available for this session."
            )
            no_data_label.setObjectName("no_metrics_label")
            no_data_label.setStyleSheet("color: #888888; font-weight: bold;")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_data_label)
            layout.addStretch()
            return

        # Order Metrics Group
        order_group = QGroupBox("Order Metrics")
        order_form = QFormLayout()

        avg_order_time = metrics.get('avg_time_per_order', 0)
        order_form.addRow(
            "Average Time per Order:",
            QLabel(self._format_seconds(avg_order_time))
        )

        fastest = metrics.get('fastest_order_seconds', 0)
        order_form.addRow(
            "Fastest Order:",
            QLabel(self._format_seconds(fastest))
        )

        slowest = metrics.get('slowest_order_seconds', 0)
        order_form.addRow(
            "Slowest Order:",
            QLabel(self._format_seconds(slowest))
        )

        order_group.setLayout(order_form)
        layout.addWidget(order_group)

        # Item Metrics Group
        item_group = QGroupBox("Item Metrics")
        item_form = QFormLayout()

        avg_item_time = metrics.get('avg_time_per_item', 0)
        item_form.addRow(
            "Average Time per Item:",
            QLabel(self._format_seconds(avg_item_time))
        )

        item_group.setLayout(item_form)
        layout.addWidget(item_group)

        # Performance Rates Group
        rate_group = QGroupBox("Performance Rates")
        rate_form = QFormLayout()

        orders_per_hour = metrics.get('orders_per_hour', 0)
        rate_form.addRow(
            "Orders per Hour:",
            QLabel(f"{orders_per_hour:.1f}")
        )

        items_per_hour = metrics.get('items_per_hour', 0)
        rate_form.addRow(
            "Items per Hour:",
            QLabel(f"{items_per_hour:.1f}")
        )

        rate_group.setLayout(rate_form)
        layout.addWidget(rate_group)

        layout.addStretch()

    def _get_metrics(self) -> dict:
        """Get metrics from session data."""

        # Try session_summary first
        if 'session_summary' in self.details:
            return self.details['session_summary'].get('metrics', {})

        # No metrics available
        return {}

    def _format_seconds(self, seconds: float) -> str:
        """Format seconds as readable time."""
        if not seconds:
            return "N/A"

        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m ({seconds:.0f}s)"
        else:
            hours = seconds / 3600
            minutes = (seconds % 3600) / 60
            return f"{hours:.1f}h {minutes:.0f}m"
