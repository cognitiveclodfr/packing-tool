"""
Dashboard Widget - Displays performance metrics and analytics.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QGroupBox, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from datetime import datetime

from logger import get_logger
from statistics_manager import StatisticsManager
from session_history_manager import SessionHistoryManager

logger = get_logger(__name__)


class MetricCard(QGroupBox):
    """
    A card widget displaying a single metric.

    Shows a label and value with styling.
    """

    def __init__(self, title, value="0", subtitle="", parent=None):
        """
        Initialize a metric card.

        Args:
            title: Metric title
            value: Metric value
            subtitle: Optional subtitle/description
            parent: Parent widget
        """
        super().__init__(parent)
        self.setTitle(title)

        layout = QVBoxLayout(self)

        # Value label
        self.value_label = QLabel(str(value))
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        self.value_label.setFont(font)
        layout.addWidget(self.value_label)

        # Subtitle label
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.subtitle_label.setStyleSheet("color: gray; font-size: 9pt;")
            layout.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None

    def set_value(self, value):
        """Update the displayed value."""
        self.value_label.setText(str(value))

    def set_subtitle(self, subtitle):
        """Update the subtitle."""
        if self.subtitle_label:
            self.subtitle_label.setText(subtitle)


class DashboardWidget(QWidget):
    """
    Dashboard widget displaying performance metrics and analytics.

    Features:
    - Overall statistics (total sessions, orders, items)
    - Per-client analytics
    - Performance metrics (orders/hour, items/hour)
    - Time period selection
    - Auto-refresh
    """

    def __init__(self, profile_manager, stats_manager, parent=None):
        """
        Initialize the dashboard widget.

        Args:
            profile_manager: ProfileManager instance
            stats_manager: StatisticsManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.profile_manager = profile_manager
        self.stats_manager = stats_manager
        self.history_manager = SessionHistoryManager(profile_manager)

        self._init_ui()
        self._refresh_metrics()

        # Auto-refresh every 60 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_metrics)
        self.refresh_timer.start(60000)  # 60 seconds

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("Performance Dashboard")
        title_label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # Period selector
        header_layout.addWidget(QLabel("Time Period:"))
        self.period_combo = QComboBox()
        self.period_combo.addItem("Last 7 Days", 7)
        self.period_combo.addItem("Last 30 Days", 30)
        self.period_combo.addItem("Last 90 Days", 90)
        self.period_combo.addItem("All Time", None)
        self.period_combo.setCurrentIndex(1)  # Default to 30 days
        self.period_combo.currentIndexChanged.connect(self._refresh_metrics)
        header_layout.addWidget(self.period_combo)

        # Refresh button
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh_metrics)
        header_layout.addWidget(self.refresh_button)

        layout.addLayout(header_layout)

        # Client selector
        client_layout = QHBoxLayout()
        client_layout.addWidget(QLabel("Client:"))
        self.client_combo = QComboBox()
        self.client_combo.addItem("All Clients", None)
        self.client_combo.currentIndexChanged.connect(self._refresh_metrics)
        client_layout.addWidget(self.client_combo)
        client_layout.addStretch()
        layout.addLayout(client_layout)

        # Overall metrics section
        overall_group = QGroupBox("Overall Statistics")
        overall_layout = QGridLayout(overall_group)

        self.total_sessions_card = MetricCard("Total Sessions", "0")
        overall_layout.addWidget(self.total_sessions_card, 0, 0)

        self.total_orders_card = MetricCard("Total Orders", "0")
        overall_layout.addWidget(self.total_orders_card, 0, 1)

        self.total_items_card = MetricCard("Total Items", "0")
        overall_layout.addWidget(self.total_items_card, 0, 2)

        layout.addWidget(overall_group)

        # Average metrics section
        average_group = QGroupBox("Averages")
        average_layout = QGridLayout(average_group)

        self.avg_orders_card = MetricCard("Avg Orders/Session", "0.0")
        average_layout.addWidget(self.avg_orders_card, 0, 0)

        self.avg_items_card = MetricCard("Avg Items/Session", "0.0")
        average_layout.addWidget(self.avg_items_card, 0, 1)

        self.avg_duration_card = MetricCard("Avg Duration", "0.0 min")
        average_layout.addWidget(self.avg_duration_card, 0, 2)

        layout.addWidget(average_group)

        # Performance metrics section
        performance_group = QGroupBox("Performance Metrics")
        performance_layout = QGridLayout(performance_group)

        self.orders_per_hour_card = MetricCard("Orders/Hour", "0.0", "Packing rate")
        performance_layout.addWidget(self.orders_per_hour_card, 0, 0)

        self.items_per_hour_card = MetricCard("Items/Hour", "0.0", "Item scan rate")
        performance_layout.addWidget(self.items_per_hour_card, 0, 1)

        layout.addWidget(performance_group)

        # Client-specific section (will show when a client is selected)
        self.client_specific_group = QGroupBox("Client Statistics")
        client_specific_layout = QGridLayout(self.client_specific_group)

        self.client_sessions_card = MetricCard("Client Sessions", "0")
        client_specific_layout.addWidget(self.client_sessions_card, 0, 0)

        self.client_orders_card = MetricCard("Client Orders", "0")
        client_specific_layout.addWidget(self.client_orders_card, 0, 1)

        self.client_items_card = MetricCard("Client Items", "0")
        client_specific_layout.addWidget(self.client_items_card, 0, 2)

        layout.addWidget(self.client_specific_group)
        self.client_specific_group.setVisible(False)

        # Status label
        self.status_label = QLabel("Last updated: Never")
        self.status_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(self.status_label)

        layout.addStretch()

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

    def _refresh_metrics(self):
        """Refresh all metrics based on current filters."""
        try:
            client_id = self.client_combo.currentData()
            days = self.period_combo.currentData()

            # Get performance metrics
            metrics = self.stats_manager.get_performance_metrics(
                client_id=client_id,
                days=days if days else 36500  # ~100 years for "all time"
            )

            # Update overall statistics
            self.total_sessions_card.set_value(metrics['total_sessions'])
            self.total_orders_card.set_value(metrics['total_orders'])
            self.total_items_card.set_value(metrics['total_items'])

            # Update averages
            self.avg_orders_card.set_value(metrics['average_orders_per_session'])
            self.avg_items_card.set_value(metrics['average_items_per_session'])
            self.avg_duration_card.set_value(f"{metrics['average_duration_minutes']:.1f} min")

            # Update performance metrics
            self.orders_per_hour_card.set_value(metrics['orders_per_hour'])
            self.items_per_hour_card.set_value(metrics['items_per_hour'])

            # Show/hide client-specific section
            if client_id:
                self.client_specific_group.setVisible(True)
                client_stats = self.stats_manager.get_client_stats(client_id)

                self.client_sessions_card.set_value(client_stats['total_sessions'])
                self.client_orders_card.set_value(client_stats['total_orders'])
                self.client_items_card.set_value(client_stats['total_items'])
            else:
                self.client_specific_group.setVisible(False)

            # Update status
            period_text = f"Last {days} days" if days else "All time"
            client_text = f"Client {client_id}" if client_id else "All clients"
            self.status_label.setText(
                f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
                f"{period_text} | {client_text}"
            )

            logger.info(f"Dashboard metrics refreshed for {client_text}, {period_text}")

        except Exception as e:
            logger.error(f"Error refreshing metrics: {e}")
            self.status_label.setText(f"Error: {e}")

    def refresh(self):
        """Public method to refresh metrics."""
        self._refresh_metrics()
