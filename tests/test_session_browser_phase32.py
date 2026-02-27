"""
Unit tests for Session Browser Phase 3.2 components.

Tests for:
- Session Details Dialog
- Overview Tab
- Orders Tab
- Metrics Tab

Note: AvailableSessionsTab was removed in v2.0 (replaced by unified SessionsListWidget).
"""
import unittest
from unittest.mock import Mock
from pathlib import Path
import json
import tempfile
import shutil

# Add src to path
import sys
tests_dir = Path(__file__).parent
sys.path.insert(0, str(tests_dir.parent / 'src'))

from PySide6.QtWidgets import QApplication

# Import components to test
from session_browser.session_details_dialog import SessionDetailsDialog
from session_browser.overview_tab import OverviewTab
from session_browser.orders_tab import OrdersTab
from session_browser.metrics_tab import MetricsTab


class TestSessionDetailsDialog(unittest.TestCase):
    """Test cases for Session Details Dialog."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures."""
        # Mock session history manager
        self.mock_history_manager = Mock()

        # Create mock session record (as dict, not Mock object)
        self.mock_record = {
            'session_id': '2025-11-20_1',
            'client_id': 'M',
            'packing_list_path': '/path/to/DHL_Orders.json',
            'worker_id': 'W001',
            'worker_name': 'John Doe',
            'pc_name': 'PC-001',
            'start_time': None,
            'end_time': None,
            'duration_seconds': 1200,
            'total_orders': 10,
            'completed_orders': 10,
            'in_progress_orders': 0,
            'total_items_packed': 35
        }

        # Mock session details
        self.mock_details = {
            'record': self.mock_record,
            'session_summary': {
                'orders': [
                    {
                        'order_number': 'ORDER-001',
                        'started_at': '2025-11-20T10:00:00+02:00',
                        'completed_at': '2025-11-20T10:05:00+02:00',
                        'duration_seconds': 300,
                        'items_count': 3,
                        'items': [
                            {
                                'sku': 'PROD-001',
                                'quantity': 2,
                                'scanned_at': '2025-11-20T10:00:15+02:00',
                                'time_from_order_start_seconds': 15
                            }
                        ]
                    }
                ],
                'metrics': {
                    'avg_time_per_order': 288.0,
                    'avg_time_per_item': 77.8,
                    'fastest_order_seconds': 120,
                    'slowest_order_seconds': 450,
                    'orders_per_hour': 12.5,
                    'items_per_hour': 46.25
                }
            }
        }

        self.mock_history_manager.get_session_details.return_value = self.mock_details

    def test_init(self):
        """Test dialog initialization."""
        dialog = SessionDetailsDialog(
            session_data={
                'client_id': 'M',
                'session_id': '2025-11-20_1'
            },
            session_history_manager=self.mock_history_manager
        )

        self.assertIsNotNone(dialog.tab_widget)
        self.assertEqual(dialog.tab_widget.count(), 3)  # Overview, Orders, Metrics

    def test_load_session_details(self):
        """Test loading session details."""
        dialog = SessionDetailsDialog(
            session_data={
                'client_id': 'M',
                'session_id': '2025-11-20_1'
            },
            session_history_manager=self.mock_history_manager
        )

        self.assertIsNotNone(dialog.details)
        self.assertEqual(dialog.details['record']['session_id'], '2025-11-20_1')

    def test_get_orders_for_export(self):
        """Test getting orders for Excel export."""
        dialog = SessionDetailsDialog(
            session_data={
                'client_id': 'M',
                'session_id': '2025-11-20_1'
            },
            session_history_manager=self.mock_history_manager
        )

        orders = dialog._get_orders_for_export()

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['order_number'], 'ORDER-001')
        self.assertEqual(len(orders[0]['items']), 1)


class TestOverviewTab(unittest.TestCase):
    """Test cases for Overview Tab."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures."""
        # Create mock session record
        self.mock_record = {
            'session_id': '2025-11-20_1',
            'client_id': 'M',
            'packing_list_path': '/path/to/DHL_Orders.json',
            'worker_id': 'W001',
            'worker_name': 'John Doe',
            'pc_name': 'PC-001',
            'start_time': None,
            'end_time': None,
            'duration_seconds': 1200,
            'total_orders': 10,
            'completed_orders': 10,
            'in_progress_orders': 0,
            'total_items_packed': 35
        }

        self.mock_details = {'record': self.mock_record}

    def test_init(self):
        """Test tab initialization."""
        tab = OverviewTab(self.mock_details)

        self.assertIsNotNone(tab)

    def test_format_duration(self):
        """Test duration formatting."""
        tab = OverviewTab(self.mock_details)

        # Test seconds
        self.assertEqual(tab._format_duration(45), "45s")

        # Test minutes
        self.assertEqual(tab._format_duration(125), "2m 5s")

        # Test hours
        self.assertEqual(tab._format_duration(7325), "2h 2m 5s")


class TestOrdersTab(unittest.TestCase):
    """Test cases for Orders Tab."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures."""
        self.mock_details = {
            'session_summary': {
                'orders': [
                    {
                        'order_number': 'ORDER-001',
                        'started_at': '2025-11-20T10:00:00+02:00',
                        'completed_at': '2025-11-20T10:05:00+02:00',
                        'duration_seconds': 300,
                        'items_count': 2,
                        'items': [
                            {
                                'sku': 'PROD-001',
                                'quantity': 2,
                                'scanned_at': '2025-11-20T10:00:15+02:00',
                                'time_from_order_start_seconds': 15
                            },
                            {
                                'sku': 'PROD-002',
                                'quantity': 1,
                                'scanned_at': '2025-11-20T10:01:30+02:00',
                                'time_from_order_start_seconds': 90
                            }
                        ]
                    }
                ]
            }
        }

    def test_init(self):
        """Test tab initialization."""
        tab = OrdersTab(self.mock_details)

        self.assertIsNotNone(tab.tree)
        self.assertEqual(len(tab.all_orders), 1)

    def test_load_orders_from_summary(self):
        """Test loading orders from session_summary."""
        tab = OrdersTab(self.mock_details)

        self.assertEqual(len(tab.all_orders), 1)
        self.assertEqual(tab.all_orders[0]['order_number'], 'ORDER-001')
        self.assertEqual(len(tab.all_orders[0]['items']), 2)

    def test_load_orders_no_data(self):
        """Test loading orders when no data available."""
        tab = OrdersTab({})

        self.assertEqual(len(tab.all_orders), 0)


class TestMetricsTab(unittest.TestCase):
    """Test cases for Metrics Tab."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures."""
        self.mock_details = {
            'session_summary': {
                'metrics': {
                    'avg_time_per_order': 288.0,
                    'avg_time_per_item': 77.8,
                    'fastest_order_seconds': 120,
                    'slowest_order_seconds': 450,
                    'orders_per_hour': 12.5,
                    'items_per_hour': 46.25
                }
            }
        }

    def test_init(self):
        """Test tab initialization."""
        tab = MetricsTab(self.mock_details)

        self.assertIsNotNone(tab)

    def test_get_metrics(self):
        """Test getting metrics from session data."""
        tab = MetricsTab(self.mock_details)

        metrics = tab._get_metrics()

        self.assertEqual(metrics['avg_time_per_order'], 288.0)
        self.assertEqual(metrics['orders_per_hour'], 12.5)

    def test_no_metrics_available(self):
        """Test handling when no metrics available."""
        tab = MetricsTab({})

        metrics = tab._get_metrics()

        self.assertEqual(metrics, {})

    def test_format_seconds(self):
        """Test seconds formatting."""
        tab = MetricsTab(self.mock_details)

        # Test seconds
        self.assertEqual(tab._format_seconds(45.5), "45.5s")

        # Test minutes
        self.assertEqual(tab._format_seconds(125), "2.1m (125s)")

        # Test hours
        self.assertEqual(tab._format_seconds(7325), "2.0h 2m")


if __name__ == '__main__':
    unittest.main()
