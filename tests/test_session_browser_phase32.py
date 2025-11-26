"""
Unit tests for Session Browser Phase 3.2 components.

Tests for:
- Available Sessions Tab
- Session Details Dialog
- Overview Tab
- Orders Tab
- Metrics Tab
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
from session_browser.available_sessions_tab import AvailableSessionsTab
from session_browser.session_details_dialog import SessionDetailsDialog
from session_browser.overview_tab import OverviewTab
from session_browser.orders_tab import OrdersTab
from session_browser.metrics_tab import MetricsTab


class TestAvailableSessionsTab(unittest.TestCase):
    """Test cases for Available Sessions Tab."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for tests."""
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.sessions_base = self.temp_dir / "Sessions"
        self.sessions_base.mkdir(parents=True)

        # Mock managers
        self.mock_profile_manager = Mock()
        self.mock_profile_manager.get_sessions_root.return_value = self.sessions_base
        self.mock_profile_manager.list_clients.return_value = ['M', 'K']

        self.mock_session_manager = Mock()

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_packing_list(self, client_id, session_id, list_name, total_orders=10, total_items=35):
        """Helper to create a test packing list."""
        # sessions_base already points to Sessions/ directory
        session_dir = self.sessions_base / f"CLIENT_{client_id}" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        lists_dir = session_dir / "packing_lists"
        lists_dir.mkdir(parents=True, exist_ok=True)

        list_file = lists_dir / f"{list_name}.json"
        list_data = {
            "list_name": list_name,
            "courier": "DHL",
            "total_orders": total_orders,
            "total_items": total_items,
            "created_at": "2025-11-20T10:00:00",
            "orders": []
        }

        with open(list_file, 'w') as f:
            json.dump(list_data, f)

        return session_dir, list_file

    def test_init(self):
        """Test tab initialization."""
        tab = AvailableSessionsTab(
            profile_manager=self.mock_profile_manager,
            session_manager=self.mock_session_manager
        )

        self.assertIsNotNone(tab.table)
        self.assertIsNotNone(tab.client_combo)
        self.assertEqual(tab.client_combo.count(), 3)  # "All Clients" + 2 clients

    def test_scan_available_sessions(self):
        """Test scanning for available sessions."""
        # Create test packing list
        self._create_test_packing_list('M', '2025-11-20_1', 'DHL_Orders')

        tab = AvailableSessionsTab(
            profile_manager=self.mock_profile_manager,
            session_manager=self.mock_session_manager
        )

        available = tab._scan_available_sessions()

        self.assertEqual(len(available), 1)
        self.assertEqual(available[0]['list_name'], 'DHL_Orders')
        self.assertEqual(available[0]['total_orders'], 10)
        self.assertEqual(available[0]['client_id'], 'M')

    def test_scan_skips_started_lists(self):
        """Test that started lists (with work directories) are not shown."""
        # Create test packing list
        session_dir, _ = self._create_test_packing_list('M', '2025-11-20_1', 'DHL_Orders')

        # Create work directory (marks as started)
        work_dir = session_dir / "packing" / "DHL_Orders"
        work_dir.mkdir(parents=True)

        tab = AvailableSessionsTab(
            profile_manager=self.mock_profile_manager,
            session_manager=self.mock_session_manager
        )

        available = tab._scan_available_sessions()

        self.assertEqual(len(available), 0)  # Should be hidden

    def test_scan_multiple_clients(self):
        """Test scanning with multiple clients."""
        # Create packing lists for different clients
        self._create_test_packing_list('M', '2025-11-20_1', 'DHL_Orders')
        self._create_test_packing_list('K', '2025-11-20_1', 'PostOne_Orders')

        tab = AvailableSessionsTab(
            profile_manager=self.mock_profile_manager,
            session_manager=self.mock_session_manager
        )

        available = tab._scan_available_sessions()

        self.assertEqual(len(available), 2)
        client_ids = {item['client_id'] for item in available}
        self.assertEqual(client_ids, {'M', 'K'})

    def test_populate_table(self):
        """Test populating table with available lists."""
        # Create test packing list
        self._create_test_packing_list('M', '2025-11-20_1', 'DHL_Orders', 15, 50)

        tab = AvailableSessionsTab(
            profile_manager=self.mock_profile_manager,
            session_manager=self.mock_session_manager
        )

        tab.refresh()

        self.assertEqual(tab.table.rowCount(), 1)
        # Check order count
        self.assertEqual(tab.table.item(0, 5).text(), '15')
        # Check item count
        self.assertEqual(tab.table.item(0, 6).text(), '50')


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
